import time
import uuid
from pathlib import Path
import logging

import cv2

from backend.repository import db
from utils.image_utils import save_snapshot
from utils import config

_log = logging.getLogger(__name__)


def _iou(a, b):
    try:
        if not a or not b:
            return 0.0
        xA, yA = max(a[0], b[0]), max(a[1], b[1])
        xB, yB = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        areaB = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        denom = float(areaA + areaB - inter)
        return inter / denom if denom > 0 else 0.0
    except Exception:
        return 0.0


class LivenessManager:
    """Require user to turn face left then right within the challenge window.

    This is a simple heuristic using horizontal bbox center movement. It creates
    per-camera tracks and expects a left movement (center decreases) of at
    least `turn_frac` * bbox_width followed by a right movement of the same
    magnitude within `challenge_secs` seconds.
    """

    def __init__(self):
        try:
            self._challenge_secs = float(config.get("liveness_challenge_seconds", 10.0) or 10.0)
        except Exception:
            self._challenge_secs = 10.0

        try:
            self._turn_frac = float(config.get("liveness_turn_fraction", 0.12) or 0.12)
        except Exception:
            self._turn_frac = 0.12

        self._pad = float(config.get("liveness_crop_pad", 0.35) or 0.35)
        self._cameras = {}  # camera_id -> {tracks: {tid: {...}}, recent_failures: [...]}
        self._lock_cleanup_last = 0.0
        self._eye_cascade = None
        try:
            self._pose_frames = int(config.get("liveness_pose_frames", 1) or 1)
        except Exception:
            self._pose_frames = 1

        try:
            self._failure_cooldown = float(config.get("liveness_failure_cooldown", 8.0) or 8.0)
        except Exception:
            self._failure_cooldown = 8.0

    def _get_eye_cascade(self):
        if getattr(self, "_eye_cascade", None) is not None:
            return self._eye_cascade
        try:
            path = cv2.data.haarcascades + "haarcascade_eye.xml"
            clf = cv2.CascadeClassifier(path)
            if not clf.empty():
                self._eye_cascade = clf
                return self._eye_cascade
        except Exception:
            pass
        self._eye_cascade = None
        return None

    def _estimate_head_pose(self, frame, face_rect):
        """Estimate coarse head pose: 'Front', 'Turn Left', 'Turn Right', or 'Look Up'.

        Uses a simple eye-position heuristic similar to the frontend capture widget.
        """
        fx, fy, fw, fh = face_rect
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
        except Exception:
            return "Front"

        roi_h = int(fh * 0.55)
        if roi_h <= 4 or fw <= 4:
            return "Front"
        face_roi = gray[int(fy) : int(fy + roi_h), int(fx) : int(fx + fw)]
        eye_clf = self._get_eye_cascade()
        if eye_clf is None:
            return "Front"

        min_eye = max(12, int(fw * 0.12))
        eyes = eye_clf.detectMultiScale(face_roi, 1.1, 3, minSize=(min_eye, min_eye))
        if len(eyes) == 0:
            return "Look Up"

        eye_xs = [((ex + ew / 2.0) / float(fw)) for (ex, ey, ew, eh) in eyes]
        if len(eye_xs) >= 2:
            sorted_x = sorted(eye_xs)
            avg_x = sum(sorted_x) / len(sorted_x)
            spread = sorted_x[-1] - sorted_x[0]
            if spread < 0.22:
                if avg_x < 0.44:
                    return "Turn Left"
                elif avg_x > 0.56:
                    return "Turn Right"
                else:
                    return "Front"
            else:
                if 0.30 <= avg_x <= 0.70:
                    return "Front"
                elif avg_x < 0.30:
                    return "Turn Left"
                else:
                    return "Turn Right"
        else:
            ex = eye_xs[0]
            if ex < 0.40:
                return "Turn Left"
            elif ex > 0.60:
                return "Turn Right"
            else:
                return "Front"

    def _get_cam(self, camera_id):
        cam = self._cameras.get(camera_id)
        if cam is None:
            cam = {"tracks": {}, "recent_failures": []}
            self._cameras[camera_id] = cam
        return cam

    def _cleanup(self):
        # remove stale tracks every 10s
        now = time.time()
        if now - self._lock_cleanup_last < 10.0:
            return
        self._lock_cleanup_last = now
        for cam_id, cam in list(self._cameras.items()):
            for tid, tr in list(cam["tracks"].items()):
                if now - tr.get("last_seen", now) > max(30.0, self._challenge_secs * 3):
                    cam["tracks"].pop(tid, None)
            # prune recent failures older than cooldown * 3
            try:
                rfs = cam.get("recent_failures", []) or []
                cam["recent_failures"] = [r for r in rfs if now - r.get("time", 0.0) <= (self._failure_cooldown * 3.0)]
            except Exception:
                cam["recent_failures"] = []

    def evaluate(self, camera_id, frame, face, frame_idx):
        """
        Evaluate/update liveness for a single detected face on `frame`.

        Returns: (liveness_float, fail_type_or_None, pending_bool, seconds_left)
          - liveness_float: 1.0 for passed, 0.0 for not passed
          - fail_type_or_None: 'turn_failed' when the turn challenge timed out, else None
          - pending_bool: True while the turn challenge is active and not yet passed
          - seconds_left: seconds remaining in the challenge window (float)
        """
        try:
            self._cleanup()
            bbox = face.get("bbox")
            if not bbox:
                return 1.0, None, False, 0.0

            cam = self._get_cam(camera_id)
            tracks = cam["tracks"]

            # find best matching track by IoU
            best_id = None
            best_iou = 0.0
            for tid, tr in tracks.items():
                tb = tr.get("last_bbox")
                if not tb:
                    continue
                i = _iou(tb, bbox)
                if i > best_iou:
                    best_iou = i
                    best_id = tid

            now = time.time()
            # convert bbox to x,y,w,h for pose estimation
            x1, y1, x2, y2 = [int(max(0, int(v))) for v in bbox]
            fw = max(1, x2 - x1)
            fh = max(1, y2 - y1)
            fx, fy = x1, y1

            if best_id is None or best_iou < 0.12:
                tid = str(uuid.uuid4())
                tracks[tid] = {
                    "started": now,
                    "last_seen": now,
                    "last_bbox": bbox,
                    "left_moved": False,
                    "right_moved": False,
                    "left_time": None,
                    "right_time": None,
                    "left_count": 0,
                    "right_count": 0,
                    "first_center": ( (float(x1) + float(x2)) / 2.0 ),
                    "min_center": ( (float(x1) + float(x2)) / 2.0 ),
                    "max_center": ( (float(x1) + float(x2)) / 2.0 ),
                    "passed": False,
                    "spoofed": False,
                }
            else:
                tid = best_id

            tr = tracks[tid]
            tr["last_seen"] = now
            tr["last_bbox"] = bbox
            # update center extrema for fallback motion detection
            try:
                center_x = (float(x1) + float(x2)) / 2.0
                tr["min_center"] = min(tr.get("min_center", center_x), center_x)
                tr["max_center"] = max(tr.get("max_center", center_x), center_x)
            except Exception:
                pass

            # If a recent failure overlaps this bbox (same person/area), consider
            # suppressing only for newly created/unstable tracks. Allow stable
            # matched tracks to proceed (and clear the failure) so users can
            # retry immediately without being permanently blocked.
            try:
                rfs = cam.get("recent_failures", []) or []
                for rf in list(rfs):
                    if now - rf.get("time", 0.0) <= float(self._failure_cooldown):
                        if _iou(rf.get("bbox"), bbox) >= 0.35:
                            # If this evaluate matched an existing track (best_iou>=0.12)
                            # and the track isn't brand-new, don't auto-block — allow
                            # the evaluation to continue and remove the stale failure.
                            if best_id is None or (now - tr.get("started", now) < 1.5):
                                tr["spoofed"] = True
                                tr["spoof_type"] = rf.get("spoof_type", "turn_failed")
                                return 0.0, tr.get("spoof_type"), False, 0.0
                            else:
                                try:
                                    cam.setdefault("recent_failures", []).remove(rf)
                                except Exception:
                                    pass
                                break
            except Exception:
                pass

            # estimate coarse head pose from eyes
            try:
                pose = self._estimate_head_pose(frame, (fx, fy, fw, fh))
            except Exception:
                pose = "Front"

            # Debug: log pose + track summary at debug level
            try:
                tr_debug = {
                    "pose": pose,
                    "left_count": tr.get("left_count", 0),
                    "right_count": tr.get("right_count", 0),
                    "left_moved": tr.get("left_moved", False),
                    "right_moved": tr.get("right_moved", False),
                    "first_center": tr.get("first_center"),
                    "min_center": tr.get("min_center"),
                    "max_center": tr.get("max_center"),
                }
                _log.debug("Liveness evaluate cam=%s tid=%s state=%s", camera_id, tid, tr_debug)
            except Exception:
                pass

            # record left/right detections (require consecutive pose frames)
            if pose == "Turn Left" and not tr.get("left_moved", False):
                tr["left_count"] = int(tr.get("left_count", 0)) + 1
                tr["right_count"] = 0
                if tr["left_count"] >= int(self._pose_frames):
                    tr["left_moved"] = True
                    tr["left_time"] = now

            elif pose == "Turn Right" and tr.get("left_moved", False) and not tr.get("right_moved", False):
                tr["right_count"] = int(tr.get("right_count", 0)) + 1
                tr["left_count"] = 0
                if tr["right_count"] >= int(self._pose_frames):
                    left_time = tr.get("left_time") or tr.get("started")
                    if now - left_time <= float(self._challenge_secs):
                        tr["right_moved"] = True
                        tr["right_time"] = now
            else:
                # non-turn poses reset short-lived pose counters
                tr["left_count"] = 0
                tr["right_count"] = 0

            # fallback: use horizontal bbox-center motion if eye-pose isn't detected
            try:
                bw = max(1.0, float(x2 - x1))
                threshold_px = bw * float(self._turn_frac)
                prev_left = bool(tr.get("left_moved", False))
                # only set left_moved here if it was not already set before this call
                if not prev_left:
                    if (tr.get("first_center", 0.0) - tr.get("min_center", 0.0)) >= threshold_px:
                        tr["left_moved"] = True
                        tr["left_time"] = now
                        prev_left = True
                # only set right_moved if left was already set on a prior frame
                if prev_left and not tr.get("right_moved", False):
                    # require left to have been observed prior to this frame
                    if (tr.get("max_center", 0.0) - tr.get("first_center", 0.0)) >= threshold_px:
                        # ensure the right movement occurs after left_time
                        left_time = tr.get("left_time") or tr.get("started")
                        if now - left_time >= 0.01:
                            tr["right_moved"] = True
                            tr["right_time"] = now
            except Exception:
                pass

            # passed when both left then right detected
            if tr.get("left_moved") and tr.get("right_moved"):
                tr["passed"] = True
                tr["passed_at"] = now
                tr.pop("spoofed", None)
                # clear any overlapping recent failure entries so real passes are respected
                try:
                    rfs = cam.get("recent_failures", []) or []
                    cam["recent_failures"] = [r for r in rfs if _iou(r.get("bbox"), bbox) < 0.4]
                except Exception:
                    pass
                _log.info("Liveness passed cam=%s tid=%s identity=%s", camera_id, tid, (face.get("identity") or face.get("_ident_info")))
                return 1.0, None, False, 0.0

            # still within challenge window -> pending
            elapsed = now - tr.get("started", now)
            if elapsed < self._challenge_secs:
                return 0.0, None, True, max(0.0, self._challenge_secs - elapsed)

            # challenge expired without required left->right turn -> fail
            if not tr.get("spoofed"):
                tr["spoofed"] = True
                tr["spoof_type"] = "turn_failed"
                # save snapshot and write detection log as a violation
                try:
                    snap_dir = Path("data") / "snapshots"
                    snap_path = save_snapshot(frame, snap_dir, prefix="liveness_fail")
                except Exception:
                    snap_path = ""

                try:
                    det_payload = {**(face or {})}
                    det_payload["_spoof_type"] = "turn_failed"
                    det_payload["liveness"] = 0.0
                    db.add_detection_log(
                        camera_id=camera_id,
                        identity=det_payload.get("identity") or det_payload.get("_ident_info") or None,
                        face_confidence=float(det_payload.get("_confidence") or det_payload.get("confidence") or 0.0),
                        detections=det_payload,
                        rules_triggered=["LivenessFailure"],
                        alarm_level=2,
                        snapshot_path=snap_path,
                    )
                    # record recent failure so new overlapping tracks are suppressed
                    try:
                        cam.setdefault("recent_failures", []).append({"bbox": bbox, "time": now, "spoof_type": "turn_failed"})
                    except Exception:
                        pass
                    _log.info("Liveness FAILED cam=%s tid=%s identity=%s", camera_id, tid, (face.get("identity") or face.get("_ident_info")))
                except Exception:
                    _log.exception("Failed to log liveness failure")

                return 0.0, "turn_failed", False, 0.0

            return 0.0, tr.get("spoof_type"), False, 0.0

        except Exception:
            _log.exception("LivenessManager.evaluate failed")
            return 1.0, None, False, 0.0
