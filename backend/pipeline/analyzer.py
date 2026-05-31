from backend.repository import db
from backend.models.face_model import normalize_gender
import threading
import time


_PLUGIN_CLASSES_CACHE = {
    "ts": 0.0,
    "data": None,
}
_PLUGIN_CLASSES_TTL = 2.0

_CLASS_COLOR_CACHE: dict = {"ts": 0.0, "data": {}}
_CLASS_COLOR_TTL = 5.0
_CACHE_LOCK = threading.Lock()


def _as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _face_liveness_verified(face: dict) -> bool:
    if face.get("_spoof_type") or face.get("spoof_type") or face.get("_liveness_pending"):
        return False
    return _as_float(face.get("liveness", 1.0), 1.0) >= 0.5


def _get_plugin_classes_cached(enabled_only=True):
    now = time.time()
    with _CACHE_LOCK:
        if _PLUGIN_CLASSES_CACHE["data"] is not None and (now - _PLUGIN_CLASSES_CACHE["ts"] < _PLUGIN_CLASSES_TTL):
            return _PLUGIN_CLASSES_CACHE["data"]
    try:
        data = db.get_plugin_classes(enabled_only=enabled_only)
    except Exception:
        data = []
    with _CACHE_LOCK:
        _PLUGIN_CLASSES_CACHE["ts"] = now
        _PLUGIN_CLASSES_CACHE["data"] = data
    return data


def _get_class_colors_cached() -> dict:
    now = time.time()
    with _CACHE_LOCK:
        if _CLASS_COLOR_CACHE["data"] and (now - _CLASS_COLOR_CACHE["ts"] < _CLASS_COLOR_TTL):
            return _CLASS_COLOR_CACHE["data"]
    try:
        classes = db.get_plugin_classes(enabled_only=False)
        colors = {c["class_name"]: c.get("color") or "" for c in classes}
    except Exception:
        colors = {}
    with _CACHE_LOCK:
        _CLASS_COLOR_CACHE["ts"] = now
        _CLASS_COLOR_CACHE["data"] = colors
    return colors


def invalidate_cache():
    with _CACHE_LOCK:
        _PLUGIN_CLASSES_CACHE["ts"] = 0.0
        _PLUGIN_CLASSES_CACHE["data"] = None
        _CLASS_COLOR_CACHE["ts"] = 0.0
        _CLASS_COLOR_CACHE["data"] = {}


def merge_results(detection_results, camera_id):
    state = {
        "identity": None,
        "gender": "unknown",
        "face_confidence": 0.0,
        "gender_confidence": 0.0,
        "liveness": 1.0,
        "camera_id": camera_id,
        "face_bbox": None,
        "all_faces": [],
        "object_bboxes": [],
        "detections": {},
    }
    faces = detection_results.get("faces", [])
    state["faces_full"] = faces
    state["all_faces"] = [
        {
            "bbox": f["bbox"],
            "identity": f["identity"]["name"] if f.get("identity") else None,
            "gender": normalize_gender(f.get("gender")),
            "confidence": f.get("confidence", 0.0),
            "gender_confidence": f.get("gender_confidence", 0.0),
            "liveness": f.get("liveness", 1.0),
            "track_vx": _as_float(f.get("track_vx", 0.0)),
            "track_vy": _as_float(f.get("track_vy", 0.0)),
            "_coasted": bool(f.get("_coasted", False)),
            "liveness_pending": bool(f.get("_liveness_pending", False)),
            "liveness_seconds_left": float(f.get("_liveness_seconds_left", 0.0)) if f.get("_liveness_seconds_left") is not None else 0.0,
            "spoof_type": f.get("_spoof_type") or f.get("spoof_type"),
        }
        for f in faces
    ]
    if faces:
        real_faces = [f for f in faces if not f.get("_coasted")]
        best_face = max(real_faces or faces, key=lambda f: float(f.get("confidence", 0.0) or 0.0))
        if not best_face.get("_coasted"):
            if best_face.get("identity") and _face_liveness_verified(best_face):
                state["identity"] = best_face["identity"]["name"]
                state["face_id"] = best_face["identity"]["id"]
                state["face_confidence"] = float(best_face.get("confidence", 0.0) or 0.0)
            state["liveness"] = best_face.get("liveness", 1.0)
            state["gender"] = normalize_gender(best_face.get("gender"))
            state["gender_confidence"] = float(best_face.get("gender_confidence", 0.0) or 0.0)
            state["face_bbox"] = best_face["bbox"]

    objects = detection_results.get("objects", [])
    class_detections = {}
    class_colors = _get_class_colors_cached()
    for obj in objects:
        cls = obj["class_name"]
        if not obj.get("_coasted"):
            if cls not in class_detections:
                class_detections[cls] = []
            class_detections[cls].append(obj)
        obj_entry = dict(obj)
        obj_entry["_coasted"] = bool(obj.get("_coasted", False))
        color = class_colors.get(cls, "")
        if color:
            obj_entry["bbox_color"] = color
        state["object_bboxes"].append(obj_entry)

    plugin_classes = _get_plugin_classes_cached(enabled_only=True)
    for pc in plugin_classes:
        attr = pc["class_name"]
        vtype = pc["value_type"]
        if attr in class_detections:
            if vtype == "boolean":
                state["detections"][attr] = True
            elif vtype == "count":
                state["detections"][attr] = len(class_detections[attr])
            else:
                state["detections"][attr] = True
        else:
            if vtype == "boolean":
                state["detections"][attr] = False
            elif vtype == "count":
                state["detections"][attr] = 0
            else:
                state["detections"][attr] = "unknown"

    if state["identity"]:
        state["detections"]["identity"] = state["identity"]
    else:
        state["detections"]["identity"] = "unknown"
    state["detections"]["gender"] = normalize_gender(state.get("gender"))

    state["face_time_ms"] = detection_results.get("face_time_ms", 0)
    state["object_time_ms"] = detection_results.get("object_time_ms", 0)

    return state
