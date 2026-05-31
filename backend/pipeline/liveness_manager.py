import logging
import math
import time
import uuid
from pathlib import Path

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
            self._allow_bbox_fallback = _as_bool(config.get("liveness_allow_bbox_fallback", False), False)
        except Exception:
            self._allow_bbox_fallback = False
        try:
            self._turn_frac = float(config.get("liveness_turn_fraction", 0.12) or 0.12)
        except Exception:
            self._turn_frac = 0.12

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
            if best_id is not None:
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
            }
        )

    def _record_failure(self, camera_id, frame, face, bbox, tr: dict, fail_type: str, yaw: float | None):
        if tr.get("fail_logged"):
            return
        tr["fail_logged"] = True
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
            db.add_detection_log(
                camera_id=camera_id,
                identity=identity,
                face_confidence=float(face.get("_confidence") or face.get("confidence") or 0.0),
                detections=det_payload,
                rules_triggered=["LivenessFailure"],
                alarm_level=2,
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

    def evaluate(self, camera_id, frame, face, frame_idx):
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

            if tr.get("passed_at") and now - tr["passed_at"] <= self._pass_ttl:
                return 1.0, None, False, 0.0
            if tr.get("passed_at") and now - tr["passed_at"] > self._pass_ttl:
                tr["passed_at"] = 0.0
                self._reset_challenge(tr, bbox, now)

            if tr.get("failed_at"):
                if now - tr["failed_at"] <= self._failure_hold:
                    return 0.0, tr.get("fail_type", "turn_failed"), False, 0.0
                self._reset_challenge(tr, bbox, now)

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
