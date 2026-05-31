import contextlib
import logging
import os
import time
from typing import Any

import cv2
import numpy as np

from backend.repository import db
from utils.embedding_utils import cosine_similarity


def capture_unknown_faces(thread: Any, frame, result):
    log = logging.getLogger(__name__)
    now = time.time()
    last = getattr(thread, "_last_inbox_save_ts", 0.0)
    if last and now - last < 10.0:
        return

    faces_full = result.get("faces_full") or []
    all_faces = result.get("all_faces") or []
    faces = result.get("faces") or []

    def is_unknown(face):
        ident = face.get("identity")
        if not ident:
            return True
        if isinstance(ident, dict):
            return not ident.get("id")
        name = str(ident)
        lname = name.lower()
        return (not name) or ("unknown" in lname) or (lname == "face")

    known_count = 0
    with contextlib.suppress(Exception):
        known_count = len(db.get_faces())

    if known_count == 0:
        unknown_faces = faces_full or all_faces or faces
    else:
        unknown_faces = (
            [f for f in faces_full if is_unknown(f)] or [f for f in all_faces if is_unknown(f)] or [f for f in faces if is_unknown(f)]
        )

    def usable(face):
        if face.get("_coasted"):
            return False
        bbox = face.get("bbox")
        if not bbox or len(bbox) != 4:
            return False
        x1, y1, x2, y2 = [int(v) for v in bbox]
        return x2 > x1 and y2 > y1

    unknown_faces = [f for f in unknown_faces if usable(f)]

    log.warning(
        "Inbox debug camera=%s faces_full=%s all_faces=%s faces=%s unknown=%s",
        thread._camera_id,
        len(faces_full),
        len(all_faces),
        len(faces),
        len(unknown_faces),
    )
    if not unknown_faces:
        return

    inbox_rows = []
    with contextlib.suppress(Exception):
        inbox_rows = db.get_face_inbox()

    existing_embs = []
    for r in inbox_rows:
        emb = r.get("embedding")
        if emb:
            with contextlib.suppress(Exception):
                existing_embs.append(np.frombuffer(emb, dtype=np.float32))
    with contextlib.suppress(Exception):
        known_rows = db.get_faces()
        for r in known_rows:
            emb = r.get("embedding")
            if emb:
                existing_embs.append(np.frombuffer(emb, dtype=np.float32))
    recent = getattr(thread, "_recent_inbox_embs", [])
    recent = [(ts, e) for ts, e in recent if now - ts <= 60.0]
    thread._recent_inbox_embs = recent
    existing_embs.extend([e for _, e in recent])

    saved = 0
    skipped = 0
    SIM_THRESHOLD = 0.92

    for face in unknown_faces:
        emb = face.get("embedding")
        if emb is None:
            with contextlib.suppress(Exception):
                from backend.models import model_loader

                fm = model_loader.get_face_model()
                if fm is not None and fm.is_loaded:
                    bbox = face.get("bbox")
                    if bbox:
                        x1, y1, x2, y2 = [int(v) for v in bbox]
                        x1 = max(0, min(x1, frame.shape[1] - 1))
                        x2 = max(0, min(x2, frame.shape[1] - 1))
                        y1 = max(0, min(y1, frame.shape[0] - 1))
                        y2 = max(0, min(y2, frame.shape[0] - 1))
                        if x2 > x1 and y2 > y1:
                            crop = frame[y1:y2, x1:x2]
                            emb = fm.get_embedding(crop)
                            face["embedding"] = emb
                            if not face.get("embedding_model"):
                                face["embedding_model"] = fm.model_name

        if emb is None:
            skipped += 1
            continue

        try:
            np_emb = np.array(emb, dtype=np.float32) if not isinstance(emb, np.ndarray) else emb.astype(np.float32)
        except Exception:
            skipped += 1
            continue

        duplicate = False
        for e in existing_embs:
            if e is None or e.size == 0:
                continue
            with contextlib.suppress(Exception):
                if cosine_similarity(np_emb, e) >= SIM_THRESHOLD:
                    duplicate = True
                    break
        if duplicate:
            skipped += 1
            continue

        bbox = face.get("bbox")
        if not bbox:
            skipped += 1
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(x1, frame.shape[1] - 1))
        x2 = max(0, min(x2, frame.shape[1] - 1))
        y1 = max(0, min(y1, frame.shape[0] - 1))
        y2 = max(0, min(y2, frame.shape[0] - 1))
        if x2 <= x1 or y2 <= y1:
            skipped += 1
            continue
        crop = frame[y1:y2, x1:x2]

        os.makedirs("data/face_inbox", exist_ok=True)
        fname = f"data/face_inbox/face_{int(time.time() * 1000)}_{thread._camera_id}.jpg"
        with contextlib.suppress(Exception):
            cv2.imwrite(fname, crop)

        db.add_face_inbox("Unlabeled", thread._camera_id, np_emb, fname, face.get("embedding_model") or "")
        existing_embs.append(np_emb)
        thread._recent_inbox_embs.append((time.time(), np_emb))
        saved += 1

    if saved:
        thread._last_inbox_save_ts = time.time()

    log.warning("Inbox summary camera=%s unknown=%s saved=%s skipped=%s", thread._camera_id, len(unknown_faces), saved, skipped)
