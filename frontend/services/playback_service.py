from __future__ import annotations

import contextlib
import logging
import os
from datetime import datetime
from typing import Callable

import sqlite3

from backend.repository import db


logger = logging.getLogger(__name__)

CLIP_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".wmv")
SNAPSHOT_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def parse_clip_filename_parts(name: str) -> tuple[int | None, int | None, str]:
    if name.startswith("clip_cam") and "_" in name:
        try:
            rest = name.replace("clip_cam", "", 1)
            cam_part, ts_part = rest.split("_", 1)
            return int(cam_part), int(ts_part.split(".", 1)[0]), "live"
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            return None, None, "live"
    if name.startswith("clip_"):
        try:
            return None, int(name.replace("clip_", "", 1).split(".", 1)[0]), "playback"
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            return None, None, "playback"
    return None, None, "playback"


def snapshot_epoch(value, path: str) -> int:
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value or "").strip()
    if text:
        with contextlib.suppress(TypeError, ValueError):
            return int(float(text))

        normalized = text.replace("Z", "+00:00")
        candidates = [normalized]
        if " " in normalized and "T" not in normalized:
            candidates.append(normalized.replace(" ", "T", 1))
        for candidate in candidates:
            with contextlib.suppress(ValueError):
                return int(datetime.fromisoformat(candidate).timestamp())

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
            with contextlib.suppress(ValueError):
                return int(datetime.strptime(text, fmt).timestamp())

    with contextlib.suppress(RuntimeError, AttributeError, TypeError, ValueError, OSError):
        return int(os.path.getmtime(path) or 0)
    return 0


class PlaybackService:
    def index_saved_clips(
        self,
        *,
        cancel_requested: Callable[[], bool] | None = None,
        per_folder_limit: int = 1000,
    ) -> int:
        cancel_requested = cancel_requested or (lambda: False)
        try:
            existing_raw = set(db.get_clip_paths(limit=1000) or [])
            existing = {os.path.normcase(os.path.abspath(p)) for p in existing_raw if p}
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.warning("Failed to read existing clips index", exc_info=True)
            existing = set()

        indexed = 0
        for folder in ("data/clips_live", "data/clips"):
            if cancel_requested() or not os.path.isdir(folder):
                continue
            try:
                names = sorted(
                    os.listdir(folder),
                    key=lambda n, f=folder: os.path.getmtime(os.path.join(f, n)),
                    reverse=True,
                )[: max(1, int(per_folder_limit or 1000))]
            except OSError:
                names = []
            for name in names:
                if cancel_requested():
                    break
                if not name.lower().endswith(CLIP_EXTENSIONS):
                    continue
                path = os.path.join(folder, name)
                norm_path = os.path.normcase(os.path.abspath(path))
                if norm_path in existing:
                    continue
                cam_id, ts, source = parse_clip_filename_parts(name)
                if ts is None:
                    with contextlib.suppress(RuntimeError, AttributeError, TypeError, ValueError, OSError):
                        ts = int(os.path.getmtime(path))
                try:
                    db.add_clip(path, source, cam_id, ts, None, [], [])
                    existing.add(norm_path)
                    indexed += 1
                except (sqlite3.Error, OSError, TypeError, ValueError):
                    logger.warning("Failed to index clip path=%s", path, exc_info=True)
        return indexed

    def list_clips(self, filters: dict, *, limit: int, offset: int = 0) -> list[dict]:
        return db.get_clips(
            camera_id=filters.get("camera_id"),
            ts_from=filters.get("ts_from"),
            ts_to=filters.get("ts_to"),
            face_label=filters.get("face_label"),
            object_type=filters.get("object_type"),
            rule_triggered=filters.get("rule_triggered"),
            limit=limit,
            offset=offset,
        )

    def delete_clip(self, path: str) -> None:
        if path and os.path.exists(path):
            os.remove(path)
        db.delete_clip(path)

    def list_snapshots(self, *, include_db: bool, limit: int) -> list[tuple[str, int, str, str]]:
        rows: dict[str, tuple[str, int, str, str]] = {}
        if include_db:
            try:
                for row in db.get_snapshot_logs(limit=max(10, int(limit))):
                    path = str(row.get("snapshot_path") or "").strip()
                    if path and os.path.exists(path):
                        key = os.path.normcase(os.path.abspath(path))
                        camera_name = str(row.get("camera_name") or f"Camera {row.get('camera_id') or '-'}")
                        rules_raw = row.get("rules_triggered")
                        rule_text = rules_raw if isinstance(rules_raw, str) and rules_raw.strip() else "No rule context"
                        rows[key] = (path, snapshot_epoch(row.get("timestamp"), path), camera_name, rule_text)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                logger.warning("Failed to load snapshot records", exc_info=True)

        if os.path.isdir("data/snapshots"):
            try:
                for name in os.listdir("data/snapshots"):
                    path = os.path.join("data/snapshots", name)
                    if os.path.isfile(path) and name.lower().endswith(SNAPSHOT_EXTENSIONS):
                        key = os.path.normcase(os.path.abspath(path))
                        rows.setdefault(
                            key,
                            (path, int(os.path.getmtime(path) or 0), "Snapshot", "No rule context"),
                        )
            except OSError:
                logger.debug("Failed filesystem snapshot listing", exc_info=True)

        ordered = sorted(rows.values(), key=lambda row: row[1], reverse=True)
        return ordered[: max(10, int(limit))]

    def delete_snapshot(self, path: str) -> tuple[bool, int]:
        deleted = False
        if path and os.path.exists(path):
            os.remove(path)
            deleted = True
        cleared = db.clear_snapshot_path(path)
        return deleted, cleared
