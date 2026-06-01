import os
import threading
import json

import cv2
import numpy as np

from backend.repository import db


class HeatmapGenerator:
    def __init__(self, width=640, height=480):
        self._width = width
        self._height = height
        self._accumulator = np.zeros((height, width), dtype=np.float32)
        self._count = 0

    def add_detection(self, bbox, frame_w, frame_h):
        x1, y1, x2, y2 = bbox
        sx1 = int(x1 / frame_w * self._width)
        sy1 = int(y1 / frame_h * self._height)
        sx2 = int(x2 / frame_w * self._width)
        sy2 = int(y2 / frame_h * self._height)
        sx1 = max(0, min(sx1, self._width - 1))
        sy1 = max(0, min(sy1, self._height - 1))
        sx2 = max(0, min(sx2, self._width))
        sy2 = max(0, min(sy2, self._height))
        self._accumulator[sy1:sy2, sx1:sx2] += 1
        self._count += 1

    def generate(self, background=None, alpha=0.6):
        if self._count == 0:
            if background is not None:
                return background.copy()
            return np.zeros((self._height, self._width, 3), dtype=np.uint8)
        normalized = self._accumulator / self._accumulator.max()
        heatmap = (normalized * 255).astype(np.uint8)
        colored = cv2.applyColorMap(heatmap, cv2.COLORMAP_JET)
        if background is not None:
            bg = cv2.resize(background, (self._width, self._height))
            result = cv2.addWeighted(bg, 1 - alpha, colored, alpha, 0)
        else:
            result = colored
        return result

    def has_data(self):
        return self._count > 0

    def save(self, filepath, background=None):
        img = self.generate(background)
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        cv2.imwrite(filepath, img)
        return filepath

    def reset(self):
        self._accumulator[:] = 0
        self._count = 0


_generators = {}
_generators_lock = threading.Lock()


def get_generator(camera_id, width=640, height=480):
    with _generators_lock:
        if camera_id not in _generators:
            _generators[camera_id] = HeatmapGenerator(width, height)
        return _generators[camera_id]


def _iter_bboxes(payload):
    data = payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return

    object_bboxes = data.get("object_bboxes") or []
    if isinstance(object_bboxes, list):
        for item in object_bboxes:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                yield bbox

    faces = data.get("all_faces") or []
    if isinstance(faces, list):
        for face in faces:
            if not isinstance(face, dict):
                continue
            bbox = face.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                yield bbox

    heatmap_boxes = data.get("heatmap_boxes") or []
    if isinstance(heatmap_boxes, list):
        for bbox in heatmap_boxes:
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                yield bbox


def generate_heatmap_from_db(
    camera_id,
    date_from=None,
    date_to=None,
    width=640,
    height=480,
    max_rows=12000,
    rule_name=None,
    min_alarm_level=None,
    gender=None,
):
    if camera_id is None:
        return None
    gen = HeatmapGenerator(width=width, height=height)
    conn = db.get_conn()
    q = (
        "SELECT detections FROM detection_logs WHERE camera_id=? "
        "AND LOWER(COALESCE(rules_triggered, '')) NOT LIKE '%livenessfailure%' "
        "AND LOWER(COALESCE(snapshot_path, '')) NOT LIKE '%liveness_fail%'"
    )
    params = [camera_id]
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if rule_name:
        q += (
            " AND (EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(rules_triggered) THEN rules_triggered ELSE '[]' END) WHERE value=?) "
            "OR rules_triggered=?)"
        )
        params.extend([str(rule_name), str(rule_name)])
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    if gender:
        q += " AND gender_norm=?"
        params.append(str(gender).strip().lower())
    q += " ORDER BY timestamp DESC LIMIT ?"
    params.append(max_rows)

    for row in conn.execute(q, params).fetchall():
        payload = row[0]
        frame_w = width
        frame_h = height
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = {}
            if isinstance(parsed, dict):
                frame_w = int(parsed.get("frame_w") or width)
                frame_h = int(parsed.get("frame_h") or height)
        for bbox in _iter_bboxes(payload):
            try:
                gen.add_detection(bbox, frame_w, frame_h)
            except Exception:
                continue

    if not gen.has_data():
        return None
    return gen.generate()
