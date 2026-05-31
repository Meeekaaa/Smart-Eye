from __future__ import annotations

import datetime
import json
import logging
import contextlib
import os
import random

from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

from backend.pipeline.rule_engine import evaluate_rules
from backend.repository import db
from frontend.services.debug_service import DebugService
from frontend.styles._colors import _ACCENT_HI_BG_03, _SUCCESS, _TEXT_PRI
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_3,
    RADIUS_MD,
    SIZE_BTN_W_100,
    SIZE_BTN_W_160,
    SIZE_BTN_W_70,
    SIZE_FIELD_W_LG,
    SIZE_LABEL_W_XL,
    SIZE_ROW_54,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_XL,
    SPACE_XXXS,
)

from ._constants import (
    _ACCENT,
    _BORDER_DIM,
    _FIELD_H,
    _PRIMARY_BTN,
    _TEXT_MUTED,
    _TEXT_SEC,
    _combo_ss,
    _make_sdiv,
)

logger = logging.getLogger(__name__)

_UNITS = ["KB", "MB", "GB"]
_UNIT_BYTES = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
_DUMMY_FRAME_W = 1280
_DUMMY_FRAME_H = 720
_DUMMY_IDENTITIES = [
    ("Alice Chen", "female"),
    ("Bob Martinez", "male"),
    ("Carol King", "female"),
    ("David Lee", "male"),
    ("Ethan Park", "male"),
    ("Mia Rivera", "female"),
]
_DUMMY_OBJECT_LABELS = [
    "person",
    "person",
    "person",
    "helmet",
    "vest",
    "NO-Hardhat",
    "NO-Safety Vest",
    "forklift",
    "car",
    "phone",
    "bag",
]


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def _rand_bbox(frame_w: int = _DUMMY_FRAME_W, frame_h: int = _DUMMY_FRAME_H, min_frac: float = 0.08, max_frac: float = 0.25):
    bw = random.randint(int(frame_w * min_frac), int(frame_w * max_frac))
    bh = random.randint(int(frame_h * min_frac), int(frame_h * max_frac))
    x1 = random.randint(0, max(1, frame_w - bw - 1))
    y1 = random.randint(0, max(1, frame_h - bh - 1))
    return [x1, y1, x1 + bw, y1 + bh]


def _build_dummy_detection_payload(camera_name: str, identity: str | None, gender: str):
    objects = []
    person_count = 0
    hardhat_violation = False
    vest_violation = False
    obj_total = random.randint(2, 6)
    for _ in range(obj_total):
        label = random.choice(_DUMMY_OBJECT_LABELS)
        if label == "person":
            person_count += 1
        if label == "NO-Hardhat":
            hardhat_violation = True
        if label == "NO-Safety Vest":
            vest_violation = True
        objects.append(
            {
                "label": label,
                "conf": round(random.uniform(0.55, 0.98), 3),
                "bbox": _rand_bbox(),
            }
        )

    if person_count == 0:
        person_count = 1
        objects.append(
            {
                "label": "person",
                "conf": round(random.uniform(0.65, 0.99), 3),
                "bbox": _rand_bbox(),
            }
        )

    face_bbox = _rand_bbox(min_frac=0.10, max_frac=0.18)
    face_conf = round(random.uniform(0.50, 0.99), 3)
    identity_text = identity or "Unknown"

    payload = {
        "identity": identity_text,
        "gender": gender,
        "age_group": random.choice(["young_adult", "adult", "senior"]),
        "camera_name": camera_name,
        "person_count": person_count,
        "object_count": len(objects),
        "ppe_violation": bool(hardhat_violation or vest_violation),
        "NO-Hardhat": hardhat_violation,
        "NO-Safety Vest": vest_violation,
        "person": person_count > 0,
        "objects": objects,
        "object_bboxes": [{"class": o["label"], "conf": o["conf"], "bbox": o["bbox"]} for o in objects],
        "all_faces": [
            {
                "bbox": face_bbox,
                "conf": face_conf,
                "identity": identity_text,
                "gender": gender,
            }
        ],
        "heatmap_boxes": [o["bbox"] for o in objects] + [face_bbox],
        "frame_w": _DUMMY_FRAME_W,
        "frame_h": _DUMMY_FRAME_H,
    }
    return payload, face_conf


def _alarm_level_from_rules(rule_names: list[str]) -> int:
    if not rule_names:
        return 0
    lower = [str(name or "").lower() for name in rule_names]
    has_hardhat = any("hardhat violation" in name for name in lower)
    has_vest = any("vest violation" in name for name in lower)
    if has_hardhat and has_vest:
        return 3
    if has_hardhat or has_vest:
        return 2
    if any("crowd threshold exceeded" in name for name in lower):
        return 2
    return 1


def _evaluate_rules_for_payload(camera_id: int, payload: dict) -> tuple[list[str], int]:
    state = {
        "camera_id": camera_id,
        "detections": {
            "identity": payload.get("identity"),
            "gender": payload.get("gender"),
            "person_count": payload.get("person_count", 0),
            "ppe_violation": payload.get("ppe_violation", False),
            "NO-Hardhat": payload.get("NO-Hardhat", False),
            "NO-Safety Vest": payload.get("NO-Safety Vest", False),
        },
        "object_bboxes": payload.get("object_bboxes") or [],
    }
    try:
        triggered = evaluate_rules(state, camera_id=camera_id) or []
    except Exception:
        triggered = []
    names = [str(r.get("name")) for r in triggered if isinstance(r, dict) and r.get("name")]
    return names, _alarm_level_from_rules(names)


def _build_detection_log_row(ts: datetime.datetime, camera_id: int, camera_name: str) -> dict:
    if random.random() < 0.22:
        identity = None
        gender = "unknown"
    else:
        identity, gender = random.choice(_DUMMY_IDENTITIES)
    payload, face_confidence = _build_dummy_detection_payload(camera_name, identity, gender)
    rules_triggered, alarm_level = _evaluate_rules_for_payload(camera_id, payload)
    return {
        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "camera_id": camera_id,
        "identity": identity or "Unknown",
        "face_confidence": face_confidence,
        "detections": payload,
        "rules_triggered": rules_triggered,
        "alarm_level": alarm_level,
        "snapshot_path": f"data/snapshots/debug_cam{camera_id}_{random.randint(100_000, 999_999)}.jpg",
    }


class _FloodWorker(QThread):
    progress = Signal(int)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(self, db_path: str, target_bytes: int, cam_rows: list[dict], debug_service: DebugService, parent=None) -> None:
        super().__init__(parent)
        self._db_path = db_path
        self._target = target_bytes
        self._cam_rows = cam_rows
        self._debug_service = debug_service
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            now = datetime.datetime.now()
            cameras = self._debug_service.prepare_seed_support(
                camera_count=2,
                camera_rows=self._cam_rows,
                face_count=len(_DUMMY_IDENTITIES),
            )

            def _det():
                off = random.randint(0, 90 * 86400)
                ts = now - datetime.timedelta(seconds=off)
                cam = random.choice(cameras)
                camera_id = int(cam.get("id", 0) or 0)
                camera_name = str(cam.get("name") or f"Camera {camera_id}")
                return _build_detection_log_row(ts, camera_id, camera_name)

            start = os.path.getsize(self._db_path)
            needed = max(0, self._target - start)
            total = 0
            BATCH = 500

            while not self._cancelled:
                total += db.seed_detection_logs([_det() for _ in range(BATCH)], ignore_size_limit=True)

                current = os.path.getsize(self._db_path)
                gained = current - start
                pct = int(min(99, gained * 100 / needed)) if needed > 0 else 99
                self.progress.emit(pct)

                if current >= self._target:
                    break
                if total >= 20_000_000:
                    break

            self.finished.emit(total, os.path.getsize(self._db_path))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            self.error.emit(str(exc))


class _SeedWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, count: int, debug_service: DebugService, parent=None) -> None:
        super().__init__(parent)
        self._count = count
        self._debug_service = debug_service

    def run(self) -> None:
        try:
            cam_rows = self._debug_service.prepare_seed_support(camera_count=3, face_count=len(_DUMMY_IDENTITIES))
            now = datetime.datetime.now()

            BATCH = 1000
            rows = []
            for i in range(self._count):
                off = random.randint(0, 90 * 86400)
                ts = now - datetime.timedelta(seconds=off)
                cam = random.choice(cam_rows)
                camera_id = int(cam.get("id", 0) or 0)
                camera_name = str(cam.get("name") or f"Camera {camera_id}")
                rows.append(_build_detection_log_row(ts, camera_id, camera_name))
                if len(rows) >= BATCH:
                    db.seed_detection_logs(rows, ignore_size_limit=True)
                    rows.clear()
                    pct = int(min(99, (i + 1) * 100 / max(self._count, 1)))
                    self.progress.emit(pct, f"Inserted {i + 1:,} / {self._count:,} records")

            if rows:
                db.seed_detection_logs(rows, ignore_size_limit=True)

            self.finished.emit(
                True,
                f"Inserted {self._count:,} detection log records across {max(1, len(cam_rows))} dummy cameras.",
            )
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            self.finished.emit(False, str(exc))


class DebugTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._flood_worker: _FloodWorker | None = None
        self._seed_worker: _SeedWorker | None = None
        self._debug_service = DebugService()
        self._cb_twitch = None
        self._cb_http_live = None
        self._cb_ffmpeg_first = None
        self._cb_win_trace = None
        self._cb_dummy_analytics = None
        self._build_ui()

    def load(self) -> None:
        try:
            t = db.get_setting("twitch_enabled", False)
            if self._cb_twitch:
                self._cb_twitch.setChecked(t in (True, 1, "1", "true", "True"))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        try:
            h = db.get_setting("http_stream_as_live", False)
            if self._cb_http_live:
                self._cb_http_live.setChecked(h in (True, 1, "1", "true", "True"))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        try:
            wt = db.get_setting("debug_window_trace", False)
            if self._cb_win_trace:
                self._cb_win_trace.setChecked(wt in (True, 1, "1", "true", "True"))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        try:
            demo_analytics = db.get_setting("debug_dummy_analytics_enabled", False)
            if self._cb_dummy_analytics:
                self._cb_dummy_analytics.setChecked(demo_analytics in (True, 1, "1", "true", "True"))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        try:
            cb = db.get_setting("capture_backends", None)
            ff_first = False
            if isinstance(cb, str):
                try:
                    cb = json.loads(cb)
                except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                    cb = None
            if isinstance(cb, (list, tuple)) and len(cb) > 0 and cb[0] == "CAP_FFMPEG":
                ff_first = True
            if self._cb_ffmpeg_first:
                self._cb_ffmpeg_first.setChecked(ff_first)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        with contextlib.suppress(Exception):
            db.get_setting("inbox_capture_enabled", False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, SPACE_XL)
        bl.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        bl.addWidget(_make_sdiv("Debug Toggles"))
        bl.addWidget(self._build_toggle_card())

        bl.addWidget(_make_sdiv("Test Data"))
        bl.addWidget(self._build_seed_card())
        bl.addStretch()
        bl.addWidget(self._make_action_bar())

    def _build_toggle_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(0, 0, 0, SPACE_MD)
        vl.setSpacing(0)

        row = QFrame()
        row.setMinimumHeight(SIZE_ROW_54)
        row.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame QLineEdit, QFrame QComboBox, QFrame QSpinBox, QFrame QTextEdit, QFrame QLabel, QFrame QPushButton, QFrame QCheckBox {{ background: transparent; border: none; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        hl = QHBoxLayout(row)
        hl.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        hl.setSpacing(SPACE_MD)

        lbl = QLabel("Enable Twitch capture")
        lbl.setFixedWidth(SIZE_LABEL_W_XL)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};")
        hl.addWidget(lbl)

        cb = QCheckBox("Resolve twitch.tv URLs via streamlink")
        cb.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
        current = db.get_setting("twitch_enabled", False)
        cb.setChecked(current in (True, 1, "1", "true", "True"))

        def _on_toggle(state: int) -> None:
            db.set_setting("twitch_enabled", "1" if state == Qt.CheckState.Checked else "0")

        cb.stateChanged.connect(_on_toggle)
        self._cb_twitch = cb
        hl.addWidget(cb, stretch=1)

        hl.addStretch()
        vl.addWidget(row)

        row2 = QFrame()
        row2.setMinimumHeight(SIZE_ROW_54)
        row2.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame QLineEdit, QFrame QComboBox, QFrame QSpinBox, QFrame QTextEdit, QFrame QLabel, QFrame QPushButton, QFrame QCheckBox {{ background: transparent; border: none; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        h2 = QHBoxLayout(row2)
        h2.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        h2.setSpacing(SPACE_MD)

        lbl2 = QLabel("Treat HTTP streams as live")
        lbl2.setFixedWidth(SIZE_LABEL_W_XL)
        lbl2.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl2.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};")
        h2.addWidget(lbl2)

        cb2 = QCheckBox("Use live FPS/reconnect for http/https")
        cb2.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
        current_http = db.get_setting("http_stream_as_live", False)
        cb2.setChecked(current_http in (True, 1, "1", "true", "True"))

        def _on_toggle_http(state: int) -> None:
            db.set_setting("http_stream_as_live", "1" if state == Qt.CheckState.Checked else "0")

        cb2.stateChanged.connect(_on_toggle_http)
        self._cb_http_live = cb2
        h2.addWidget(cb2, stretch=1)
        h2.addStretch()
        vl.addWidget(row2)

        row3 = QFrame()
        row3.setMinimumHeight(SIZE_ROW_54)
        row3.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame QLineEdit, QFrame QComboBox, QFrame QSpinBox, QFrame QTextEdit, QFrame QLabel, QFrame QPushButton, QFrame QCheckBox {{ background: transparent; border: none; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        h3 = QHBoxLayout(row3)
        h3.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        h3.setSpacing(SPACE_MD)

        lbl3 = QLabel("Prefer FFmpeg backend")
        lbl3.setFixedWidth(SIZE_LABEL_W_XL)
        lbl3.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl3.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};")
        h3.addWidget(lbl3)

        cb3 = QCheckBox("Try CAP_FFMPEG before device backends")
        cb3.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
        current_backends = db.get_setting("capture_backends", None)
        _is_ff_first = False
        try:
            if isinstance(current_backends, str):
                current_backends = json.loads(current_backends)
            if isinstance(current_backends, (list, tuple)):
                _is_ff_first = len(current_backends) > 0 and current_backends[0] == "CAP_FFMPEG"
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            _is_ff_first = False
        cb3.setChecked(_is_ff_first)

        def _on_toggle_ff(state: int) -> None:
            if state == Qt.CheckState.Checked:
                db.set_setting("capture_backends", json.dumps(["CAP_FFMPEG", "CAP_ANY", "CAP_MSMF", "CAP_DSHOW"]))
            else:
                db.set_setting("capture_backends", "")

        cb3.stateChanged.connect(_on_toggle_ff)
        self._cb_ffmpeg_first = cb3
        h3.addWidget(cb3, stretch=1)
        h3.addStretch()
        vl.addWidget(row3)

        row4 = QFrame()
        row4.setMinimumHeight(SIZE_ROW_54)
        row4.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame QLineEdit, QFrame QComboBox, QFrame QSpinBox, QFrame QTextEdit, QFrame QLabel, QFrame QPushButton, QFrame QCheckBox {{ background: transparent; border: none; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        h4 = QHBoxLayout(row4)
        h4.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        h4.setSpacing(SPACE_MD)

        lbl4 = QLabel("Window trace logging")
        lbl4.setFixedWidth(SIZE_LABEL_W_XL)
        lbl4.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl4.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};")
        h4.addWidget(lbl4)

        cb4 = QCheckBox("Log every top-level QWidget/QDialog show event")
        cb4.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
        current_wt = db.get_setting("debug_window_trace", False)
        cb4.setChecked(current_wt in (True, 1, "1", "true", "True"))

        def _on_toggle_wt(state: int) -> None:
            db.set_setting("debug_window_trace", "1" if state == Qt.CheckState.Checked else "0")

        cb4.stateChanged.connect(_on_toggle_wt)
        self._cb_win_trace = cb4
        h4.addWidget(cb4, stretch=1)
        h4.addStretch()
        vl.addWidget(row4)

        row5 = QFrame()
        row5.setMinimumHeight(SIZE_ROW_54)
        row5.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame QLineEdit, QFrame QComboBox, QFrame QSpinBox, QFrame QTextEdit, QFrame QLabel, QFrame QPushButton, QFrame QCheckBox {{ background: transparent; border: none; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        h5 = QHBoxLayout(row5)
        h5.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        h5.setSpacing(SPACE_MD)

        lbl5 = QLabel("Use dummy analytics data")
        lbl5.setFixedWidth(SIZE_LABEL_W_XL)
        lbl5.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl5.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};")
        h5.addWidget(lbl5)

        cb5 = QCheckBox("Render Analytics and PDF reports with synthetic data")
        cb5.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
        current_demo = db.get_setting("debug_dummy_analytics_enabled", False)
        cb5.setChecked(current_demo in (True, 1, "1", "true", "True"))

        def _on_toggle_demo(state: int) -> None:
            db.set_setting("debug_dummy_analytics_enabled", "1" if state == Qt.CheckState.Checked else "0")

        cb5.stateChanged.connect(_on_toggle_demo)
        self._cb_dummy_analytics = cb5
        h5.addWidget(cb5, stretch=1)
        h5.addStretch()
        vl.addWidget(row5)
        return card

    def _make_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_MD)
        row.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{_SUCCESS};font-weight:{FONT_WEIGHT_BOLD};font-size:{FONT_SIZE_LABEL}px;")
        self._status_lbl.setContentsMargins(0, 0, 0, 0)
        self._status_lbl.setVisible(False)
        row.addWidget(self._status_lbl)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_PRIMARY_BTN)
        save_btn.setFixedWidth(SIZE_BTN_W_100)
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return bar

    def _save(self) -> None:
        try:
            db.set_setting("twitch_enabled", "1" if self._cb_twitch and self._cb_twitch.isChecked() else "0")
            db.set_setting("http_stream_as_live", "1" if self._cb_http_live and self._cb_http_live.isChecked() else "0")
            db.set_setting("debug_window_trace", "1" if self._cb_win_trace and self._cb_win_trace.isChecked() else "0")
            db.set_setting(
                "debug_dummy_analytics_enabled",
                "1" if self._cb_dummy_analytics and self._cb_dummy_analytics.isChecked() else "0",
            )
            if self._cb_ffmpeg_first and self._cb_ffmpeg_first.isChecked():
                db.set_setting("capture_backends", json.dumps(["CAP_FFMPEG", "CAP_ANY", "CAP_MSMF", "CAP_DSHOW"]))
            else:
                db.set_setting("capture_backends", "")
            if db.get_bool("ui_show_save_popups", False):
                QMessageBox.information(self, "Saved", "Debug settings saved.")
            else:
                self._flash_status("Saved")
                logger.info("Debug settings saved.")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", f"Failed to save debug settings: {exc}")

    def _flash_status(self, text: str) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setVisible(True)
        eff = QGraphicsOpacityEffect(self._status_lbl)
        self._status_lbl.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self._status_lbl)
        anim.setDuration(1000)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(
            lambda: (
                self._status_lbl.setText(""),
                self._status_lbl.setGraphicsEffect(None),
                self._status_lbl.setVisible(False),
            )
        )
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _build_seed_card(self) -> QWidget:
        _row_ss = (
            f"QFrame {{ background: transparent; border: none;"
            f"  border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}"
            f"QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}"
        )
        _mode_btn_ss = (
            f"QPushButton {{"
            f"  background: transparent;"
            f"  border: {SPACE_XXXS}px solid {_BORDER_DIM};"
            f"  border-radius: {RADIUS_MD}px;"
            f"  padding: 0 {SPACE_MD}px;"
            f"  color: {_TEXT_SEC};"
            f"  font-size: {FONT_SIZE_LABEL}px;"
            f"  font-weight: {FONT_WEIGHT_SEMIBOLD};"
            f"}}"
            f"QPushButton:hover {{"
            f"  border-color: {_ACCENT};"
            f"  color: {_TEXT_PRI};"
            f"}}"
        )

        card = QWidget()
        card.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        def _switch_mode(mode: str) -> None:
            is_rec = mode == "records"
            self._seed_row_records.setVisible(is_rec)
            self._seed_row_size.setVisible(not is_rec)

        self._seed_row_records = QFrame()
        self._seed_row_records.setMinimumHeight(SIZE_ROW_54)
        self._seed_row_records.setStyleSheet(_row_ss)
        rhl = QHBoxLayout(self._seed_row_records)
        rhl.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        rhl.setSpacing(SPACE_MD)

        rlbl = QLabel("Records to insert")
        rlbl.setFixedWidth(SIZE_BTN_W_160)
        rlbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        rlbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; background: transparent; border: none;"
        )
        rhl.addWidget(rlbl)

        self._seed_count = QSpinBox()
        self._seed_count.setRange(10, 500_000)
        self._seed_count.setValue(5_000)
        self._seed_count.setSingleStep(1_000)
        self._seed_count.setFixedHeight(_FIELD_H)
        self._seed_count.setToolTip("Number of dummy rows to insert.")
        rhl.addWidget(self._seed_count, stretch=1)

        self._seed_type_rec = QComboBox()
        self._seed_type_rec.setStyleSheet(_combo_ss())
        self._seed_type_rec.addItems(["Detection Logs"])
        self._seed_type_rec.setCurrentText("Detection Logs")
        self._seed_type_rec.setFixedHeight(_FIELD_H)
        self._seed_type_rec.setFixedWidth(SIZE_FIELD_W_LG)
        rhl.addWidget(self._seed_type_rec)

        mode_btn_to_size = QPushButton("Size Mode")
        mode_btn_to_size.setStyleSheet(_mode_btn_ss)
        mode_btn_to_size.setFixedHeight(_FIELD_H)
        mode_btn_to_size.setToolTip("Switch to size-based flood mode")
        mode_btn_to_size.clicked.connect(lambda: _switch_mode("size"))
        rhl.addWidget(mode_btn_to_size)

        gen_btn = QPushButton("Generate")
        gen_btn.setStyleSheet(_PRIMARY_BTN)
        gen_btn.setFixedHeight(_FIELD_H)
        gen_btn.setFixedWidth(SIZE_BTN_W_100)
        gen_btn.clicked.connect(self._seed_records)
        rhl.addWidget(gen_btn)

        vl.addWidget(self._seed_row_records)
        self._seed_row_records.setVisible(True)

        self._seed_row_size = QFrame()
        self._seed_row_size.setMinimumHeight(SIZE_ROW_54)
        self._seed_row_size.setStyleSheet(_row_ss)
        shl = QHBoxLayout(self._seed_row_size)
        shl.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        shl.setSpacing(SPACE_MD)

        slbl = QLabel("Fill database to")
        slbl.setFixedWidth(SIZE_BTN_W_160)
        slbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        slbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; background: transparent; border: none;"
        )
        shl.addWidget(slbl)

        self._seed_size_val = QDoubleSpinBox()
        self._seed_size_val.setRange(0.1, 9_999)
        self._seed_size_val.setValue(50)
        self._seed_size_val.setDecimals(1)
        self._seed_size_val.setFixedHeight(_FIELD_H)
        self._seed_size_val.setToolTip("Target database size for the flood operation.")
        shl.addWidget(self._seed_size_val, stretch=1)

        self._seed_size_unit = QComboBox()
        self._seed_size_unit.setStyleSheet(_combo_ss())
        self._seed_size_unit.addItems(["KB", "MB", "GB"])
        self._seed_size_unit.setCurrentText("MB")
        self._seed_size_unit.setFixedHeight(_FIELD_H)
        self._seed_size_unit.setFixedWidth(SIZE_BTN_W_70)
        shl.addWidget(self._seed_size_unit)

        self._seed_type_size = QComboBox()
        self._seed_type_size.setStyleSheet(_combo_ss())
        self._seed_type_size.addItems(["Detection Logs"])
        self._seed_type_size.setCurrentText("Detection Logs")
        self._seed_type_size.setFixedHeight(_FIELD_H)
        self._seed_type_size.setFixedWidth(SIZE_FIELD_W_LG)
        shl.addWidget(self._seed_type_size)

        mode_btn_to_rec = QPushButton("Count Mode")
        mode_btn_to_rec.setStyleSheet(_mode_btn_ss)
        mode_btn_to_rec.setFixedHeight(_FIELD_H)
        mode_btn_to_rec.setToolTip("Switch to record-count mode")
        mode_btn_to_rec.clicked.connect(lambda: _switch_mode("records"))
        shl.addWidget(mode_btn_to_rec)

        self._seed_flood_btn = QPushButton("Flood")
        self._seed_flood_btn.setStyleSheet(_PRIMARY_BTN)
        self._seed_flood_btn.setFixedHeight(_FIELD_H)
        self._seed_flood_btn.setFixedWidth(SIZE_BTN_W_100)
        self._seed_flood_btn.clicked.connect(self._seed_size)
        shl.addWidget(self._seed_flood_btn)

        vl.addWidget(self._seed_row_size)
        self._seed_row_size.setVisible(False)

        self._seed_progress = QProgressBar()
        self._seed_progress.setRange(0, 100)
        self._seed_progress.setValue(0)
        self._seed_progress.setFixedHeight(SPACE_6)
        self._seed_progress.setTextVisible(False)
        self._seed_progress.setStyleSheet(
            f"QProgressBar {{ background: {_BORDER_DIM}; border: none; border-radius: {RADIUS_3}px; }}"
            f"QProgressBar::chunk {{ background: {_ACCENT}; border-radius: {RADIUS_3}px; }}"
        )
        self._seed_progress.setVisible(False)
        vl.addWidget(self._seed_progress)

        self._seed_status = QLabel(
            "Creates new dummy cameras and populates the database with synthetic detection events "
            "including real faces (single debug PNG), notification profiles, gender, objects, real rule-engine hits, and heatmap boxes. Existing data is preserved."
        )
        self._seed_status.setWordWrap(True)
        self._seed_status.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; background: transparent;"
            f" padding: {SPACE_6}px {SPACE_20}px {SPACE_MD}px {SPACE_20}px;"
        )
        vl.addWidget(self._seed_status)

        return card

    def _seed_records(self) -> None:
        count = self._seed_count.value()

        if self._seed_worker and self._seed_worker.isRunning():
            return

        self._seed_progress.setValue(0)
        self._seed_progress.setVisible(True)
        self._seed_status.setText(f"Generating {count:,} records...")
        self._seed_count.setEnabled(False)
        self._seed_type_rec.setEnabled(False)

        self._seed_worker = _SeedWorker(count, self._debug_service, self)

        def _on_progress(pct: int, msg: str) -> None:
            self._seed_progress.setValue(pct)
            self._seed_status.setText(msg)

        def _on_done(ok: bool, msg: str) -> None:
            self._seed_worker = None
            self._seed_progress.setVisible(False)
            self._seed_count.setEnabled(True)
            self._seed_type_rec.setEnabled(True)
            if ok:
                self._seed_status.setText(msg)
            else:
                logger.exception("seed_records error")
                QMessageBox.warning(self, "Error", msg)
                self._seed_status.setText("Seed failed. See logs for details.")

        self._seed_worker.progress.connect(_on_progress)
        self._seed_worker.finished.connect(_on_done)
        self._seed_worker.finished.connect(self._seed_worker.deleteLater)
        self._seed_worker.start()

    def _seed_size(self) -> None:

        if self._flood_worker and self._flood_worker.isRunning():
            self._flood_worker.cancel()
            self._seed_flood_btn.setText("Flood")
            return

        target = int(self._seed_size_val.value() * _UNIT_BYTES[self._seed_size_unit.currentText()])
        db_path = db.get_db_path()
        current = os.path.getsize(db_path) if os.path.isfile(db_path) else 0

        if current >= target:
            QMessageBox.information(
                self,
                "Nothing to do",
                f"Database is already {_fmt_bytes(current)},\nat or above the target {_fmt_bytes(target)}.",
            )
            return

        try:
            cam_rows = self._debug_service.prepare_seed_support(camera_count=3, face_count=len(_DUMMY_IDENTITIES))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return

        self._seed_progress.setValue(0)
        self._seed_progress.setVisible(True)
        self._seed_status.setText(f"Flooding to {_fmt_bytes(target)}\u2026  (currently {_fmt_bytes(current)})")
        self._seed_flood_btn.setText("Cancel")

        self._flood_worker = _FloodWorker(db_path, target, cam_rows, self._debug_service, self)
        self._flood_worker.progress.connect(self._seed_progress.setValue)
        self._flood_worker.error.connect(self._on_flood_error)
        self._flood_worker.finished.connect(self._on_flood_done)
        self._flood_worker.start()

    def _on_flood_error(self, msg: str) -> None:
        logger.error("Flood worker error: %s", msg)
        self._seed_progress.setVisible(False)
        self._seed_flood_btn.setText("Flood")
        QMessageBox.warning(self, "Flood Error", msg)

    def _on_flood_done(self, rows: int, final_bytes: int) -> None:
        self._seed_progress.setValue(100)
        self._seed_flood_btn.setText("Flood")
        self._seed_status.setText(f"Done — inserted ~{rows:,} rows, DB is now {_fmt_bytes(final_bytes)}")

