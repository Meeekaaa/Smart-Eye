import logging
import math
import time
import uuid
from pathlib import Path

import cv2

from backend.models.passive_liveness_model import get_passive_liveness_model
from backend.repository import db
from utils import config
from utils.image_utils import save_snapshot

_log = logging.getLogger(__name__)


def _iou(a, b):
    try:
        if not a or not b:
            return 0.0
        x_a, y_a = max(a[0], b[0]), max(a[1], b[1])
        x_b, y_b = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, x_b - x_a) * max(0, y_b - y_a)
        area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        denom = float(area_a + area_b - inter)
        return inter / denom if denom > 0 else 0.0
    except Exception:
        return 0.0


def _bbox_center_x(bbox) -> float:
    return (float(bbox[0]) + float(bbox[2])) / 2.0


def _identity_key(face: dict) -> str:
    ident = face.get("identity") or face.get("_ident_info")
    if isinstance(ident, dict):
        value = ident.get("id") or ident.get("name") or ident.get("identity")
    else:
        value = ident
    text = str(value or "").strip()
    return text.lower() if text else ""


def _identity_text(face: dict) -> str | None:
    ident = face.get("identity") or face.get("_ident_info")
    if isinstance(ident, dict):
        return ident.get("name") or ident.get("id") or None
    return ident if ident else None


def _landmarks(face: dict) -> list[list[float]] | None:
    points = face.get("landmarks") or face.get("kps")
    if not points:
        return None
    result = []
    try:
        for point in points:
            if len(point) < 2:
                continue
            result.append([float(point[0]), float(point[1])])
    except Exception:
        return None
    return result if len(result) >= 3 else None


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    try:
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    except Exception:
        return default


def _estimate_yaw(face: dict) -> float | None:
    points = _landmarks(face)
    if not points:
        return None

    left_eye = points[0]
    right_eye = points[1]
    nose = points[2]
    eye_mid_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_dist = math.hypot(right_eye[0] - left_eye[0], right_eye[1] - left_eye[1])
    if len(points) >= 5:
        mouth_mid_x = (points[3][0] + points[4][0]) / 2.0
        mouth_width = abs(points[4][0] - points[3][0])
        anchor_x = (eye_mid_x * 0.65) + (mouth_mid_x * 0.35)
        scale = max(eye_dist, mouth_width, 1.0)
    else:
        anchor_x = eye_mid_x
        scale = max(eye_dist, 1.0)
    return (nose[0] - anchor_x) / scale


def _intersection_area(a, b) -> float:
    try:
        x1 = max(float(a[0]), float(b[0]))
        y1 = max(float(a[1]), float(b[1]))
        x2 = min(float(a[2]), float(b[2]))
        y2 = min(float(a[3]), float(b[3]))
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except Exception:
        return 0.0


def _box_area(box) -> float:
    try:
        return max(0.0, float(box[2]) - float(box[0])) * max(0.0, float(box[3]) - float(box[1]))
    except Exception:
        return 0.0


def _object_label(obj: dict) -> str:
    return str(
        obj.get("class_name")
        or obj.get("_class_name")
        or obj.get("label")
        or obj.get("name")
        or obj.get("class")
        or ""
    ).strip().lower()


class LivenessManager:
    """Landmark-based side-to-side liveness challenge.

    The old implementation used Haar eye detection and bbox-center movement.
    Bbox movement is easy to trigger by sliding a face/photo across the frame,
    so the default path now measures nose offset relative to eye/mouth
    landmarks. Translation does not change that ratio; an actual head rotation
    does.
    """

    def __init__(self):
        self._cameras = {}
        self._cleanup_last = 0.0
        self._refresh_settings()

    def _refresh_settings(self):
        try:
            self._mode = str(config.get("liveness_mode", "passive") or "passive").strip().lower()
        except Exception:
            self._mode = "passive"
        if self._mode not in ("passive", "active", "hybrid"):
            self._mode = "passive"
        try:
            self._challenge_secs = float(config.get("liveness_challenge_seconds", 8.0) or 8.0)
        except Exception:
            self._challenge_secs = 8.0
        try:
            self._yaw_threshold = float(config.get("liveness_yaw_threshold", 0.16) or 0.16)
        except Exception:
            self._yaw_threshold = 0.16
        try:
            self._pose_frames = max(1, int(config.get("liveness_pose_frames", 2) or 2))
        except Exception:
            self._pose_frames = 2
        try:
            self._pass_ttl = max(1.0, float(config.get("liveness_pass_ttl_sec", 30.0) or 30.0))
        except Exception:
            self._pass_ttl = 30.0
        try:
            self._failure_hold = max(0.5, float(config.get("liveness_failure_hold_sec", 2.0) or 2.0))
        except Exception:
            self._failure_hold = 2.0
        try:
            self._failure_log_cooldown = max(1.0, float(config.get("liveness_failure_log_cooldown_sec", 20.0) or 20.0))
        except Exception:
            self._failure_log_cooldown = 20.0
        try:
            self._allow_bbox_fallback = _as_bool(config.get("liveness_allow_bbox_fallback", False), False)
        except Exception:
            self._allow_bbox_fallback = False
        try:
            self._turn_frac = float(config.get("liveness_turn_fraction", 0.12) or 0.12)
        except Exception:
            self._turn_frac = 0.12
        try:
            self._passive_model_path = str(config.get("liveness_passive_model_path", "data/models/liveness.onnx") or "").strip()
        except Exception:
            self._passive_model_path = "data/models/liveness.onnx"
        try:
            self._passive_threshold = max(0.05, min(0.99, float(config.get("liveness_passive_threshold", 0.70) or 0.70)))
        except Exception:
            self._passive_threshold = 0.70
        try:
            self._passive_min_frames = max(1, int(config.get("liveness_passive_min_frames", 3) or 3))
        except Exception:
            self._passive_min_frames = 3
        try:
            self._passive_window_sec = max(0.25, float(config.get("liveness_passive_window_sec", 1.2) or 1.2))
        except Exception:
            self._passive_window_sec = 1.2
        try:
            self._passive_every_n_frames = max(1, int(config.get("liveness_passive_every_n_frames", 3) or 3))
        except Exception:
            self._passive_every_n_frames = 3
        try:
            self._pass_recheck_every_n_frames = max(1, int(config.get("liveness_pass_recheck_every_n_frames", 1) or 1))
        except Exception:
            self._pass_recheck_every_n_frames = 1
        try:
            self._pass_revoke_threshold = max(0.01, min(0.95, float(config.get("liveness_pass_revoke_threshold", 0.20) or 0.20)))
        except Exception:
            self._pass_revoke_threshold = 0.20
        try:
            self._identity_track_min_iou = max(0.05, min(0.95, float(config.get("liveness_identity_track_min_iou", 0.20) or 0.20)))
        except Exception:
            self._identity_track_min_iou = 0.20
        try:
            self._passive_temporal_fallback = _as_bool(config.get("liveness_passive_temporal_fallback", False), False)
        except Exception:
            self._passive_temporal_fallback = False
        self._screen_labels = {
            "cell phone",
            "phone",
            "smartphone",
            "mobile phone",
            "mobile",
            "tablet",
            "ipad",
            "screen",
            "monitor",
            "tv",
            "television",
            "laptop",
        }

    def _get_cam(self, camera_id):
        cam = self._cameras.get(camera_id)
        if cam is None:
            cam = {"tracks": {}}
            self._cameras[camera_id] = cam
        return cam

    def _cleanup(self):
        now = time.time()
        if now - self._cleanup_last < 10.0:
            return
        self._cleanup_last = now
        max_age = max(30.0, self._challenge_secs * 4.0, self._pass_ttl * 2.0)
        for cam in list(self._cameras.values()):
            tracks = cam.get("tracks", {})
            for tid, tr in list(tracks.items()):
                if now - tr.get("last_seen", now) > max_age:
                    tracks.pop(tid, None)

    def _match_track(self, tracks: dict, face: dict, bbox, now: float) -> str:
        ident_key = _identity_key(face)
        if ident_key:
            best_id = None
            best_score = -1.0
            for tid, tr in tracks.items():
                if tr.get("identity_key") != ident_key:
                    continue
                age = now - tr.get("last_seen", now)
                if age > max(self._pass_ttl, self._challenge_secs * 2.0):
                    continue
                score = _iou(tr.get("last_bbox"), bbox)
                if score > best_score:
                    best_id = tid
                    best_score = score
            if best_id is not None and best_score >= self._identity_track_min_iou:
                return best_id

        best_id = None
        best_iou = 0.0
        for tid, tr in tracks.items():
            score = _iou(tr.get("last_bbox"), bbox)
            if score > best_iou:
                best_iou = score
                best_id = tid
        if best_id is not None and best_iou >= 0.18:
            return best_id

        tid = str(uuid.uuid4())
        center_x = _bbox_center_x(bbox)
        tracks[tid] = {
            "started": now,
            "last_seen": now,
            "last_bbox": bbox,
            "identity_key": ident_key,
            "first_turn": None,
            "opposite_seen": False,
            "neg_count": 0,
            "pos_count": 0,
            "first_center": center_x,
            "min_center": center_x,
            "max_center": center_x,
            "passed_at": 0.0,
            "failed_at": 0.0,
            "fail_logged": False,
            "passive_started": now,
            "passive_observations": 0,
            "passive_scores": [],
        }
        return tid

    def _reset_challenge(self, tr: dict, bbox, now: float):
        center_x = _bbox_center_x(bbox)
        tr.update(
            {
                "started": now,
                "first_turn": None,
                "opposite_seen": False,
                "neg_count": 0,
                "pos_count": 0,
                "first_center": center_x,
                "min_center": center_x,
                "max_center": center_x,
                "failed_at": 0.0,
                "fail_logged": False,
                "passive_started": now,
                "passive_observations": 0,
                "passive_scores": [],
            }
        )

    def _record_failure(self, camera_id, frame, face, bbox, tr: dict, fail_type: str, yaw: float | None):
        if tr.get("fail_logged"):
            return
        now = time.time()
        try:
            last_at = float(tr.get("last_fail_log_at", 0.0) or 0.0)
        except Exception:
            last_at = 0.0
        if tr.get("last_fail_log_type") == fail_type and now - last_at < self._failure_log_cooldown:
            return
        tr["fail_logged"] = True
        tr["last_fail_log_at"] = now
        tr["last_fail_log_type"] = fail_type
        try:
            can_persist = db.can_persist_events()
        except Exception:
            can_persist = False
        if not can_persist:
            _log.warning("Skipping liveness failure log because database size limit is reached")
            return
        try:
            snap_dir = Path("data") / "snapshots"
            snap_path = save_snapshot(frame, snap_dir, prefix="liveness_fail")
        except Exception:
            snap_path = ""

        identity = _identity_text(face)
        det_payload = {
            "identity": identity or "unknown",
            "gender": face.get("gender", "unknown"),
            "bbox": bbox,
            "liveness": 0.0,
            "spoof_type": fail_type,
            "liveness_yaw": yaw,
        }
        try:
            safe_camera_id = camera_id
            if safe_camera_id is not None:
                try:
                    if not db.get_camera(safe_camera_id):
                        safe_camera_id = None
                except Exception:
                    safe_camera_id = None
            db.add_detection_log(
                camera_id=safe_camera_id,
                identity=identity,
                face_confidence=float(face.get("_confidence") or face.get("confidence") or 0.0),
                detections=det_payload,
                rules_triggered=["LivenessFailure"],
                # Liveness failures are face-verification events, not rule
                # alarms. Keep the log/snapshot without driving popup alerts.
                alarm_level=0,
                snapshot_path=snap_path,
            )
        except Exception:
            _log.exception("Failed to log liveness failure")

    def _update_bbox_fallback(self, tr: dict, bbox, now: float) -> bool:
        center_x = _bbox_center_x(bbox)
        tr["min_center"] = min(tr.get("min_center", center_x), center_x)
        tr["max_center"] = max(tr.get("max_center", center_x), center_x)
        width = max(1.0, float(bbox[2] - bbox[0]))
        threshold_px = width * float(self._turn_frac)
        if tr.get("first_turn") is None:
            if (tr.get("first_center", center_x) - tr["min_center"]) >= threshold_px:
                tr["first_turn"] = "negative"
                tr["first_turn_at"] = now
            elif (tr["max_center"] - tr.get("first_center", center_x)) >= threshold_px:
                tr["first_turn"] = "positive"
                tr["first_turn_at"] = now
        elif tr.get("first_turn") == "negative":
            tr["opposite_seen"] = (tr["max_center"] - tr.get("first_center", center_x)) >= threshold_px
        elif tr.get("first_turn") == "positive":
            tr["opposite_seen"] = (tr.get("first_center", center_x) - tr["min_center"]) >= threshold_px
        return bool(tr.get("first_turn") and tr.get("opposite_seen"))

    def _update_landmark_challenge(self, tr: dict, yaw: float, now: float) -> bool:
        threshold = float(self._yaw_threshold)
        if tr.get("first_turn") is None:
            if yaw <= -threshold:
                tr["neg_count"] = int(tr.get("neg_count", 0)) + 1
                tr["pos_count"] = 0
                if tr["neg_count"] >= self._pose_frames:
                    tr["first_turn"] = "negative"
                    tr["first_turn_at"] = now
            elif yaw >= threshold:
                tr["pos_count"] = int(tr.get("pos_count", 0)) + 1
                tr["neg_count"] = 0
                if tr["pos_count"] >= self._pose_frames:
                    tr["first_turn"] = "positive"
                    tr["first_turn_at"] = now
            elif abs(yaw) < threshold * 0.5:
                tr["neg_count"] = 0
                tr["pos_count"] = 0
        elif tr.get("first_turn") == "negative":
            if yaw >= threshold:
                tr["pos_count"] = int(tr.get("pos_count", 0)) + 1
                if tr["pos_count"] >= self._pose_frames:
                    tr["opposite_seen"] = True
            elif abs(yaw) < threshold * 0.5:
                tr["pos_count"] = 0
        elif tr.get("first_turn") == "positive":
            if yaw <= -threshold:
                tr["neg_count"] = int(tr.get("neg_count", 0)) + 1
                if tr["neg_count"] >= self._pose_frames:
                    tr["opposite_seen"] = True
            elif abs(yaw) < threshold * 0.5:
                tr["neg_count"] = 0
        return bool(tr.get("first_turn") and tr.get("opposite_seen"))

    def _passive_model_score(self, frame, bbox) -> float | None:
        model = get_passive_liveness_model(self._passive_model_path)
        if model is None:
            return None
        if not model.load():
            return None
        return model.predict(frame, bbox)

    def _objects_indicate_screen(self, bbox, objects) -> bool:
        if not objects:
            return False
        face_area = max(1.0, _box_area(bbox))
        face_cx = (float(bbox[0]) + float(bbox[2])) / 2.0
        face_cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        for obj in objects:
            label = _object_label(obj)
            if label not in self._screen_labels:
                continue
            ob = obj.get("bbox")
            if not ob:
                continue
            obj_area = _box_area(ob)
            if obj_area < face_area * 1.2:
                continue
            if not (float(ob[0]) <= face_cx <= float(ob[2]) and float(ob[1]) <= face_cy <= float(ob[3])):
                continue
            if _intersection_area(bbox, ob) / face_area >= 0.70:
                return True
        return False

    def _frame_indicates_screen(self, frame, bbox) -> bool:
        try:
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = [int(v) for v in bbox]
            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            pad_x = int(bw * 0.65)
            pad_y = int(bh * 0.85)
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(w, x2 + pad_x)
            cy2 = min(h, y2 + pad_y)
            if cx2 - cx1 < bw * 1.25 or cy2 - cy1 < bh * 1.25:
                return False

            crop = frame[cy1:cy2, cx1:cx2]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(gray, 50, 140)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, kernel, iterations=1)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return False

            face_rel = [x1 - cx1, y1 - cy1, x2 - cx1, y2 - cy1]
            face_area = max(1.0, _box_area(face_rel))
            crop_area = max(1.0, float(crop.shape[0] * crop.shape[1]))
            face_cx = (face_rel[0] + face_rel[2]) / 2.0
            face_cy = (face_rel[1] + face_rel[3]) / 2.0

            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < face_area * 1.8 or area > crop_area * 0.96:
                    continue
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.035 * peri, True)
                if len(approx) < 4 or len(approx) > 8:
                    continue
                rx, ry, rw, rh = cv2.boundingRect(approx)
                if rw <= 0 or rh <= 0:
                    continue
                aspect = rw / float(rh)
                if not (0.35 <= aspect <= 2.2):
                    continue
                rect = [rx, ry, rx + rw, ry + rh]
                if not (rect[0] <= face_cx <= rect[2] and rect[1] <= face_cy <= rect[3]):
                    continue
                if _intersection_area(face_rel, rect) / face_area >= 0.82:
                    return True
        except Exception:
            return False
        return False

    def _looks_like_presentation_attack(self, frame, bbox, objects) -> bool:
        if self._objects_indicate_screen(bbox, objects):
            return True
        return self._frame_indicates_screen(frame, bbox)

    def detect_presentation_attack(self, frame, face, objects=None) -> bool:
        bbox = face.get("bbox") if isinstance(face, dict) else None
        if not bbox:
            return False
        try:
            return self._looks_like_presentation_attack(frame, [int(v) for v in bbox], objects or [])
        except Exception:
            return False

    def _cached_pass_still_live(self, frame, bbox, frame_idx, tr: dict) -> bool:
        if self._mode not in ("passive", "hybrid") or not self._passive_model_path:
            return True
        if int(frame_idx or 0) % int(self._pass_recheck_every_n_frames or 1) != 0:
            return True
        score = self._passive_model_score(frame, bbox)
        if score is None:
            return True
        score = float(score)
        tr["last_passive_score"] = score
        tr["passive_scores"] = [(time.time(), score)]
        return score >= self._pass_revoke_threshold

    def _evaluate_passive(self, camera_id, frame, face, bbox, frame_idx, tr: dict, now: float, *, allow_active_fallback: bool):
        tr["passive_observations"] = int(tr.get("passive_observations", 0)) + 1
        tr.setdefault("passive_started", now)
        scores = list(tr.get("passive_scores") or [])

        should_score = bool(self._passive_model_path) and (
            not scores or int(frame_idx or 0) % int(self._passive_every_n_frames) == 0
        )
        if should_score:
            score = self._passive_model_score(frame, bbox)
            if score is not None:
                scores.append((now, float(score)))
                cutoff = now - max(self._passive_window_sec * 2.0, 5.0)
                scores = [(ts, val) for ts, val in scores if ts >= cutoff]
                tr["passive_scores"] = scores
                tr["last_passive_score"] = float(score)

        if scores:
            recent = [val for ts, val in scores if now - ts <= max(self._passive_window_sec * 2.0, 1.0)]
            if not recent:
                recent = [scores[-1][1]]
            avg_score = sum(recent) / max(1, len(recent))
            tr["last_passive_score"] = avg_score
            if len(recent) >= self._passive_min_frames and avg_score >= self._passive_threshold:
                tr["passed_at"] = now
                tr["failed_at"] = 0.0
                tr["fail_logged"] = False
                return 1.0, None, False, 0.0

            elapsed = now - float(tr.get("passive_started", now) or now)
            if elapsed >= self._passive_window_sec and len(recent) >= self._passive_min_frames:
                tr["failed_at"] = now
                tr["fail_type"] = "passive_spoof"
                self._record_failure(camera_id, frame, face, bbox, tr, "passive_spoof", _estimate_yaw(face))
                return 0.0, "passive_spoof", False, 0.0

            return 0.0, None, True, max(0.0, self._passive_window_sec - elapsed)

        elapsed = now - float(tr.get("passive_started", now) or now)
        has_landmarks = _landmarks(face) is not None
        if self._passive_temporal_fallback and has_landmarks:
            if elapsed >= self._passive_window_sec and int(tr.get("passive_observations", 0)) >= self._passive_min_frames:
                tr["passed_at"] = now
                tr["failed_at"] = 0.0
                tr["fail_logged"] = False
                return 1.0, None, False, 0.0
            return 0.0, None, True, max(0.0, self._passive_window_sec - elapsed)

        if allow_active_fallback:
            return None

        if elapsed < self._passive_window_sec:
            return 0.0, None, True, max(0.0, self._passive_window_sec - elapsed)

        fail_type = "liveness_model_missing" if self._passive_model_path else "passive_unavailable"
        if not has_landmarks:
            fail_type = "landmarks_missing"
        tr["failed_at"] = now
        tr["fail_type"] = fail_type
        self._record_failure(camera_id, frame, face, bbox, tr, fail_type, None)
        return 0.0, fail_type, False, 0.0

    def evaluate(self, camera_id, frame, face, frame_idx, objects=None):
        """
        Returns: (liveness_float, fail_type_or_None, pending_bool, seconds_left)
        """
        try:
            self._refresh_settings()
            self._cleanup()
            bbox = face.get("bbox")
            if not bbox:
                return 1.0, None, False, 0.0

            bbox = [int(v) for v in bbox]
            now = time.time()
            cam = self._get_cam(camera_id)
            tracks = cam["tracks"]
            tid = self._match_track(tracks, face, bbox, now)
            tr = tracks[tid]
            tr["last_seen"] = now
            tr["last_bbox"] = bbox
            ident_key = _identity_key(face)
            if ident_key:
                tr["identity_key"] = ident_key

            if tr.get("failed_at"):
                if now - tr["failed_at"] <= self._failure_hold:
                    return 0.0, tr.get("fail_type", "turn_failed"), False, 0.0
                self._reset_challenge(tr, bbox, now)

            if self._looks_like_presentation_attack(frame, bbox, objects or []):
                tr["passed_at"] = 0.0
                tr["failed_at"] = now
                tr["fail_type"] = "screen_presentation"
                self._record_failure(camera_id, frame, face, bbox, tr, "screen_presentation", _estimate_yaw(face))
                return 0.0, "screen_presentation", False, 0.0

            if tr.get("passed_at") and now - tr["passed_at"] <= self._pass_ttl:
                if self._cached_pass_still_live(frame, bbox, frame_idx, tr):
                    return 1.0, None, False, 0.0
                tr["passed_at"] = 0.0
                tr["failed_at"] = now
                tr["fail_type"] = "passive_spoof"
                self._record_failure(camera_id, frame, face, bbox, tr, "passive_spoof", _estimate_yaw(face))
                return 0.0, "passive_spoof", False, 0.0
            if tr.get("passed_at") and now - tr["passed_at"] > self._pass_ttl:
                tr["passed_at"] = 0.0
                self._reset_challenge(tr, bbox, now)

            if self._mode in ("passive", "hybrid"):
                passive_result = self._evaluate_passive(
                    camera_id,
                    frame,
                    face,
                    bbox,
                    frame_idx,
                    tr,
                    now,
                    allow_active_fallback=self._mode == "hybrid",
                )
                if passive_result is not None:
                    return passive_result

            yaw = _estimate_yaw(face)
            passed = False
            fail_type = "turn_failed"
            if yaw is None:
                fail_type = "landmarks_missing"
                if self._allow_bbox_fallback:
                    passed = self._update_bbox_fallback(tr, bbox, now)
            else:
                tr["last_yaw"] = yaw
                passed = self._update_landmark_challenge(tr, yaw, now)

            if passed:
                tr["passed_at"] = now
                tr["failed_at"] = 0.0
                tr["fail_logged"] = False
                _log.info("Liveness passed cam=%s tid=%s identity=%s", camera_id, tid, _identity_text(face))
                return 1.0, None, False, 0.0

            elapsed = now - tr.get("started", now)
            if elapsed < self._challenge_secs:
                return 0.0, None, True, max(0.0, self._challenge_secs - elapsed)

            tr["failed_at"] = now
            tr["fail_type"] = fail_type
            self._record_failure(camera_id, frame, face, bbox, tr, fail_type, yaw)
            _log.info("Liveness failed cam=%s tid=%s type=%s identity=%s", camera_id, tid, fail_type, _identity_text(face))
            return 0.0, fail_type, False, 0.0
        except Exception:
            _log.exception("LivenessManager.evaluate failed")
            return 1.0, None, False, 0.0
