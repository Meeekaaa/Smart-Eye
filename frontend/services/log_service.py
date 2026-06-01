from __future__ import annotations

import contextlib
import json
from datetime import datetime, timedelta

from backend.repository import db


class LogService:
    def get_logs(
        self,
        *,
        camera_id=None,
        date_from: str | None = None,
        date_to: str | None = None,
        log_type: str = "All types",
        search: str = "",
        limit: int = 500,
        page: int = 1,
    ) -> list[dict]:
        normalized_type = str(log_type or "All types").strip().lower()
        safe_limit = max(int(limit), 1)
        safe_page = max(int(page), 1)
        if normalized_type in {"face", "object"}:
            return self._get_type_filtered_page(
                camera_id=camera_id,
                date_from=date_from,
                date_to=date_to,
                log_type=normalized_type,
                search=search,
                limit=safe_limit,
                page=safe_page,
            )
        rows = db.get_detection_logs(
            camera_id=camera_id,
            date_from=date_from,
            date_to=date_to,
            identity=search.strip() if search.strip() else None,
            alarm_level=1 if normalized_type == "violation" else None,
            limit=safe_limit,
            offset=(safe_page - 1) * safe_limit,
        )
        if normalized_type in {"all types", "violation"}:
            return rows
        return [row for row in rows if self.matches_type(row, normalized_type)]

    def _get_type_filtered_page(
        self,
        *,
        camera_id=None,
        date_from: str | None,
        date_to: str | None,
        log_type: str,
        search: str,
        limit: int,
        page: int,
    ) -> list[dict]:
        target_start = (page - 1) * limit
        target_count = page * limit
        batch_size = max(limit, 250)
        matches: list[dict] = []
        offset = 0
        while len(matches) < target_count:
            rows = db.get_detection_logs(
                camera_id=camera_id,
                date_from=date_from,
                date_to=date_to,
                identity=search.strip() if search.strip() else None,
                limit=batch_size,
                offset=offset,
            )
            if not rows:
                break
            matches.extend(row for row in rows if self.matches_type(row, log_type))
            if len(rows) < batch_size:
                break
            offset += batch_size
        return matches[target_start:target_start + limit]

    @staticmethod
    def parse_detections(row: dict) -> dict:
        detections = row.get("detections", {})
        if isinstance(detections, dict):
            return detections
        if isinstance(detections, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                parsed = json.loads(detections or "{}")
                return parsed if isinstance(parsed, dict) else {}
        return {}

    def matches_type(self, row: dict, log_type: str) -> bool:
        detections = self.parse_detections(row)
        if log_type == "face":
            identity = str(row.get("identity") or detections.get("identity") or "").strip().lower()
            return bool(identity and identity != "-") or bool(detections.get("all_faces"))
        if log_type == "object":
            if detections.get("object_bboxes") or detections.get("objects"):
                return True
            ignored = {"identity", "gender", "age_group", "all_faces", "frame_w", "frame_h", "camera_name"}
            return any(key not in ignored for key in detections)
        return True

    def delete_logs(self, log_ids: list[int]) -> None:
        for log_id in log_ids:
            db.delete_detection_log(int(log_id))

    def cleanup_older_than_days(self, days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat()
        return int(db.cleanup_old_logs(cutoff) or 0)
