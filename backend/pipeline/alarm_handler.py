import json
import logging
import os
import queue
import threading
import time
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

from backend.notifications.email_notifier import send_email_alert
from backend.notifications.webhook_notifier import send_webhook
from backend.repository import db
from utils import config
from utils.image_utils import save_snapshot


def _parse_sound_action_value(action_value, default_volume: float = 0.8):
    raw = str(action_value or "").strip()
    if not raw:
        return None, max(0.0, min(float(default_volume), 1.0))
    path_part, sep, volume_part = raw.partition("|")
    volume = default_volume
    if sep:
        try:
            volume = float(volume_part)
        except (TypeError, ValueError):
            volume = default_volume
    volume = max(0.0, min(float(volume), 1.0))
    path = path_part.strip() or None
    return path, volume


class AlarmHandler:
    def __init__(self, data_dir="data"):
        self._data_dir = data_dir
        self._log = logging.getLogger(__name__)

        self._alarm = QSoundEffect()
        self._alarm.setLoopCount(-2)
        self._alarm.setVolume(0.8)
        self._alarm_playing = False
        self._alarm_level_playing = 0
        self._alarm_volume_playing = 0.8
        self._last_trigger_ts = 0.0
        self._alarm_grace_seconds = 0.35
        self._last_action_times = {}
        self._last_log_ts: dict = {}

        self._task_queue: queue.Queue = queue.Queue(maxsize=512)
        self._stop_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, name="alarm-worker", daemon=True)
        self._worker.start()

    def close(self):
        self._stop_event.set()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if getattr(self._task_queue, "unfinished_tasks", 0) <= 0:
                break
            time.sleep(0.05)
        try:
            self._task_queue.put(None, timeout=1.0)
        except Exception:
            pass
        try:
            if self._worker.is_alive():
                self._worker.join(timeout=1.5)
        except Exception:
            pass

    def _enqueue(self, task):
        if self._stop_event.is_set():
            self._log.debug("Alarm enqueue skipped: handler stopping kind=%s", (task or {}).get("kind"))
            return
        try:
            self._task_queue.put_nowait(task)
            self._log.debug("Alarm task enqueued kind=%s qsize=%s", (task or {}).get("kind"), self._task_queue.qsize())
        except queue.Full:

            try:
                self._task_queue.get_nowait()
                self._task_queue.task_done()
            except Exception:
                pass
            try:
                self._task_queue.put_nowait(task)
            except Exception:
                self._log.warning("Alarm worker queue full; dropping task kind=%s", (task or {}).get("kind"))

    def _worker_loop(self):
        while True:
            try:
                task = self._task_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if task is None:
                self._task_queue.task_done()
                break
            try:
                kind = task.get("kind")
                self._log.debug("Alarm worker running kind=%s", kind)
                if kind == "action":
                    self._execute_action(task["action"], task["state"], task.get("frame"))
                elif kind == "log":
                    self._write_detection_log(task["rule"], task["level"], task["state"], task.get("frame"))
            except Exception:
                self._log.exception("Alarm worker task failed")
            finally:
                self._task_queue.task_done()

    def handle_alarms(self, triggered_rules, escalation_levels, state, frame=None):
        now = time.time()
        selected_sound = None
        executed = []
        self._log.debug(
            "Handle alarms camera_id=%s triggered=%s escalation_keys=%s",
            state.get("camera_id"),
            len(triggered_rules or []),
            sorted((escalation_levels or {}).keys()),
        )
        for rule in triggered_rules:
            if not rule.get("enabled", 1):
                self._log.debug("Skipping disabled rule rule_id=%s", rule.get("id"))
                continue
            rule_id = rule["id"]
            rule_action = str(rule.get("action", "") or "").strip().lower()
            if rule_action == "log_only":
                self._schedule_detection_log(rule, 0, state, frame, now)
                continue
            if rule_action != "alarm":
                continue
            level = escalation_levels.get(rule_id, 0)
            if level <= 0:
                self._log.debug("Rule has no active escalation level rule_id=%s level=%s", rule_id, level)
                continue

            actions = db.get_alarm_actions(rule_id=rule_id, escalation_level=level)
            self._log.debug(
                "Rule escalation resolved rule_id=%s level=%s rule_action=%s actions=%s",
                rule_id,
                level,
                str(rule.get("action", "") or "").strip().lower(),
                [str(a.get("action_type") or "") for a in actions],
            )
            for action in actions:
                atype = str(action.get("action_type") or "").strip().lower()
                if atype == "sound":
                    try:
                        sound_level = int(action.get("escalation_level") or level or 1)
                    except Exception:
                        sound_level = int(level or 1)
                    sound_path, sound_volume = _parse_sound_action_value(action.get("action_value", ""))
                    if sound_volume > 0 and (
                        selected_sound is None or sound_level >= selected_sound["level"]
                    ):
                        selected_sound = {
                            "level": sound_level,
                            "path": sound_path,
                            "volume": sound_volume,
                        }

                cooldown = action.get("cooldown_sec", 10)
                key = (rule_id, action["id"])
                last = self._last_action_times.get(key, 0)
                if now - last < cooldown:
                    self._log.debug(
                        "Skipping action due cooldown rule_id=%s action_id=%s type=%s remaining=%.2fs",
                        rule_id,
                        action.get("id"),
                        atype,
                        max(0.0, cooldown - (now - last)),
                    )
                    continue
                action_frame = frame.copy() if frame is not None else None
                self._enqueue({"kind": "action", "action": dict(action), "state": dict(state), "frame": action_frame})
                self._last_action_times[key] = now
                executed.append(action)
                self._log.info(
                    "Escalation action scheduled rule_id=%s level=%s action_id=%s type=%s",
                    rule_id,
                    level,
                    action.get("id"),
                    atype,
                )

            self._schedule_detection_log(rule, level, state, frame, now)

        if selected_sound is not None:
            self._last_trigger_ts = now
            self._start_alarm(
                selected_sound["level"],
                volume=selected_sound["volume"],
                sound_path=selected_sound["path"],
            )
        else:
            if self._alarm_playing and (now - self._last_trigger_ts > self._alarm_grace_seconds):
                self._stop_alarm()

        return executed

    def _schedule_detection_log(self, rule, level, state, frame, now):
        rule_id = rule["id"]
        log_key = (rule_id, state.get("camera_id"), state.get("identity"))
        if now - self._last_log_ts.get(log_key, 0) < 30.0:
            self._log.debug("Skipping detection log due debounce rule_id=%s key=%s", rule_id, log_key)
            return
        self._last_log_ts[log_key] = now
        log_frame = frame.copy() if frame is not None and config.snapshot_on_alarm() else None
        self._enqueue({"kind": "log", "rule": dict(rule), "level": level, "state": dict(state), "frame": log_frame})
        self._log.info(
            "Detection log scheduled rule_id=%s level=%s identity=%s camera_id=%s",
            rule_id,
            level,
            state.get("identity"),
            state.get("camera_id"),
        )

    def _write_detection_log(self, rule, level, state, frame):
        if not db.can_persist_events():
            self._log.warning("Detection log skipped because database size limit is reached")
            return
        snapshot_path = ""
        if frame is not None:
            snapshot_path = save_snapshot(
                frame,
                Path(self._data_dir) / "snapshots",
            )
        row_id = db.add_detection_log(
            camera_id=state.get("camera_id"),
            identity=state.get("identity"),
            face_confidence=state.get("face_confidence", 0),
            detections=state.get("detections", {}),
            rules_triggered=[rule.get("name")],
            alarm_level=level,
            snapshot_path=snapshot_path,
        )
        self._log.info(
            "Detection log written id=%s rule=%s level=%s camera_id=%s identity=%s",
            row_id,
            rule.get("name"),
            level,
            state.get("camera_id"),
            state.get("identity"),
        )

    def _execute_action(self, action, state, frame):
        atype = str(action.get("action_type") or "").strip().lower()
        avalue = action.get("action_value", "")
        self._log.debug(
            "Executing action id=%s type=%s rule_state_camera=%s identity=%s",
            action.get("id"),
            atype,
            state.get("camera_id"),
            state.get("identity"),
        )
        if atype == "popup":
            # Popup visibility is driven by detection_logs.alarm_level in main window polling.
            self._log.info("Popup action acknowledged action_id=%s", action.get("id"))
            return True
        if atype == "email":
            address, _token = self._resolve_notification_target("email", avalue)
            if not address:
                self._log.warning("Email action has no target address")
                return False
            self._send_email(address, state)
            return True
        elif atype == "webhook":
            url, token = self._resolve_notification_target("webhook", avalue)
            if not url:
                self._log.warning("Webhook action has no target URL")
                return False
            self._send_webhook(url, state, auth_token=token)
            return True
        elif atype == "sound":
            # Sound playback is coordinated in handle_alarms() to pick the highest active level.
            return True
        elif atype == "log":
            # Log actions are persisted by _write_detection_log; no additional side effect needed.
            return True
        else:
            self._log.warning("Unsupported alarm action type: %s", atype)
        return False

    def _resolve_notification_target(self, ntype: str, action_value: str):
        raw = str(action_value or "").strip()
        if not raw.startswith("profile:"):
            self._log.debug("Notification target resolved direct type=%s target=%s", ntype, raw)
            return raw, None
        try:
            pid = int(raw.split(":", 1)[1])
        except Exception:
            self._log.warning("Invalid profile target format type=%s value=%s", ntype, raw)
            return "", None
        try:
            rows = db.get_notification_profiles(enabled_only=True, ntype=ntype)
            prof = next((p for p in rows if int(p.get("id") or -1) == pid), None)
            if not prof:
                self._log.warning("Notification profile not found/disabled type=%s profile_id=%s", ntype, pid)
                return "", None
            endpoint = str(prof.get("endpoint") or "").strip()
            token = str(prof.get("auth_token") or "").strip() or None
            self._log.debug(
                "Notification target resolved profile type=%s profile_id=%s endpoint_set=%s token_set=%s",
                ntype,
                pid,
                bool(endpoint),
                bool(token),
            )
            return endpoint, token
        except Exception:
            self._log.exception("Notification target resolution failed type=%s value=%s", ntype, raw)
            return "", None

    def _start_alarm(self, sound_level: int = 1, volume: float = 0.8, sound_path: str | None = None):
        level = max(1, min(int(sound_level or 1), 5))
        volume = max(0.0, min(float(volume), 1.0))
        if volume <= 0:
            self._stop_alarm()
            return
        if self._alarm_playing and self._alarm_level_playing == level and abs(self._alarm_volume_playing - volume) < 0.01:
            return
        resolved_sound_path = Path(sound_path).resolve() if sound_path else Path(f"frontend/assets/sounds/alarm_level_{level}.wav").resolve()
        if not resolved_sound_path.is_file():
            self._log.warning("Alarm sound not found: %s", resolved_sound_path)
            return
        if os.name == "nt":
            try:
                import winsound

                winsound.PlaySound(
                    str(resolved_sound_path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP,
                )
                self._alarm_playing = True
                self._alarm_level_playing = level
                self._alarm_volume_playing = volume
                self._log.info("Alarm STARTED (winsound) -> %s", resolved_sound_path)
                return
            except Exception:
                self._log.exception("winsound start failed; falling back to QSoundEffect")
        if self._alarm is None:
            return
        self._alarm.setVolume(volume)
        self._alarm.setSource(QUrl.fromLocalFile(str(resolved_sound_path)))
        self._alarm.play()
        self._alarm_playing = True
        self._alarm_level_playing = level
        self._alarm_volume_playing = volume
        self._log.info("Alarm STARTED (qt) -> %s", resolved_sound_path)

    def _stop_alarm(self):
        if not self._alarm_playing:
            return
        if os.name == "nt":
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                self._log.exception("winsound stop failed")
        if self._alarm is None:
            self._alarm_playing = False
            return
        self._alarm.stop()
        self._alarm_playing = False
        self._alarm_level_playing = 0
        self._alarm_volume_playing = 0.8
        self._log.info("Alarm STOPPED")

    def _send_email(self, address, state):
        try:
            subject = f"SmartEye Alert: {state.get('identity', 'Unknown')}"
            body = json.dumps(state.get("detections", {}), indent=2)
            ok = send_email_alert(address, subject, body)
            if ok:
                self._log.info("Email sent to %s", address)
            else:
                self._log.error("Email send returned failure for %s", address)
        except Exception:
            self._log.exception("Email send failed")

    def _send_webhook(self, url, state, auth_token=None):
        try:
            payload = {
                "identity": state.get("identity"),
                "detections": state.get("detections", {}),
                "camera_id": state.get("camera_id"),
                "timestamp": time.time(),
            }
            send_webhook(url, payload, auth_token=auth_token)
        except Exception:
            self._log.exception("Webhook send failed")


_instance = None


def get_handler(data_dir="data"):
    global _instance
    if _instance is None:
        try:
            _instance = AlarmHandler(data_dir)
        except Exception:
            logging.getLogger(__name__).exception("Failed to initialize AlarmHandler; using silent fallback")
            _instance = AlarmHandler.__new__(AlarmHandler)
            _instance._data_dir = data_dir
            _instance._log = logging.getLogger(__name__)
            _instance._alarm = None
            _instance._alarm_playing = False
            _instance._alarm_volume_playing = 0.8
            _instance._last_trigger_ts = 0.0
            _instance._alarm_grace_seconds = 2.0
            _instance._last_action_times = {}
            _instance._last_log_ts = {}
            _instance._task_queue = queue.Queue(maxsize=16)
            _instance._worker = threading.Thread(target=lambda: None, daemon=True)
            _instance._stop_event = threading.Event()
    return _instance


def stop_all_sounds():
    handler = get_handler()
    with_logging = getattr(handler, "_stop_alarm", None)
    if callable(with_logging):
        handler._stop_alarm()


def close_handler():
    global _instance
    if _instance is None:
        return
    close_fn = getattr(_instance, "close", None)
    if callable(close_fn):
        close_fn()
    _instance = None
