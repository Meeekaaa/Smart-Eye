from __future__ import annotations

import contextlib
import csv
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

from backend.repository import db


@dataclass(frozen=True)
class LogQueryResult:
    rows: list[dict]
    total: int
    page: int
    limit: int

    @property
    def has_next(self) -> bool:
        return self.page * self.limit < self.total

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.limit - 1) // self.limit)


class LogService:
    TYPE_LABELS: ClassVar[dict[str, str]] = {
        "all": "All types",
        "face": "Faces",
        "object": "Objects",
        "violation": "Violations",
    }

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
        return self.query_logs(
            camera_id=camera_id,
            date_from=date_from,
            date_to=date_to,
            log_type=log_type,
            search=search,
            limit=limit,
            page=page,
        ).rows

    def query_logs(
        self,
        *,
        camera_id=None,
        date_from: str | None = None,
        date_to: str | None = None,
        log_type: str = "All types",
        search: str = "",
        rule_name: str | None = None,
        alarm_level=None,
        reviewed=None,
        limit: int = 500,
        page: int = 1,
    ) -> LogQueryResult:
        normalized_type = str(log_type or "All types").strip().lower()
        normalized_type = {
            "all types": "all",
            "faces": "face",
            "objects": "object",
            "violations": "violation",
        }.get(normalized_type, normalized_type)
        if normalized_type == "all":
            normalized_type = None
        safe_limit = max(int(limit), 1)
        safe_page = max(int(page), 1)
        offset = (safe_page - 1) * safe_limit
        common = {
            "camera_id": camera_id,
            "date_from": date_from,
            "date_to": date_to,
            "search": search.strip() if search.strip() else None,
            "rule_name": rule_name or None,
            "alarm_level": alarm_level,
            "reviewed": reviewed,
            "log_type": normalized_type,
        }
        total = int(db.count_detection_logs(**common) or 0)
        rows = db.get_detection_logs(
            **common,
            limit=safe_limit,
            offset=offset,
        )
        return LogQueryResult(rows=rows, total=total, page=safe_page, limit=safe_limit)

    def export_logs_csv(self, filepath: str, **query_kwargs) -> int:
        normalized_type = str(query_kwargs.pop("log_type", None) or "All types").strip().lower()
        normalized_type = {
            "all types": None,
            "all": None,
            "faces": "face",
            "objects": "object",
            "violations": "violation",
        }.get(normalized_type, normalized_type)
        common = {
            "camera_id": query_kwargs.get("camera_id"),
            "date_from": query_kwargs.get("date_from"),
            "date_to": query_kwargs.get("date_to"),
            "search": str(query_kwargs.get("search") or "").strip() or None,
            "rule_name": query_kwargs.get("rule_name") or None,
            "alarm_level": query_kwargs.get("alarm_level"),
            "reviewed": query_kwargs.get("reviewed"),
            "log_type": normalized_type,
        }
        fieldnames = [
            "id",
            "timestamp",
            "camera_name",
            "identity",
            "gender",
            "alarm_level",
            "reviewed",
            "rules_triggered",
            "snapshot_path",
            "detections",
        ]
        exported = 0
        offset = 0
        batch_size = 1000
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            while True:
                rows = db.get_detection_logs(**common, limit=batch_size, offset=offset)
                if not rows:
                    break
                for row in rows:
                    detections = self.parse_detections(row)
                    writer.writerow(
                        {
                            "id": row.get("id"),
                            "timestamp": row.get("timestamp"),
                            "camera_name": row.get("camera_name") or row.get("camera_id"),
                            "identity": row.get("identity") or "",
                            "gender": row.get("gender_norm") or detections.get("gender") or "unknown",
                            "alarm_level": row.get("alarm_level") or 0,
                            "reviewed": 1 if int(row.get("reviewed") or 0) else 0,
                            "rules_triggered": row.get("rules_triggered") or "",
                            "snapshot_path": row.get("snapshot_path") or "",
                            "detections": json.dumps(detections, default=str),
                        }
                    )
                    exported += 1
                if len(rows) < batch_size:
                    break
                offset += batch_size
        return exported

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

    def delete_logs(self, log_ids: list[int], *, delete_evidence: bool = False) -> dict:
        ids = [int(log_id) for log_id in log_ids if log_id is not None]
        evidence_paths = db.get_detection_snapshot_paths(log_ids=ids) if delete_evidence else []
        deleted = int(db.delete_detection_logs(ids) or 0)
        evidence_deleted = self._delete_paths(evidence_paths) if delete_evidence else 0
        return {"logs": deleted, "evidence": evidence_deleted}

    def mark_reviewed(self, log_ids: list[int], reviewed: bool = True) -> int:
        return int(db.mark_detection_logs_reviewed(log_ids, 1 if reviewed else 0) or 0)

    def cleanup_older_than_days(self, days: int, *, delete_evidence: bool = False) -> dict:
        cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")
        evidence_paths = db.get_detection_snapshot_paths(cutoff_date=cutoff) if delete_evidence else []
        deleted = int(db.cleanup_old_logs(cutoff) or 0)
        evidence_deleted = self._delete_paths(evidence_paths) if delete_evidence else 0
        return {"logs": deleted, "evidence": evidence_deleted}

    @staticmethod
    def _delete_paths(paths: list[str]) -> int:
        deleted = 0
        seen: set[str] = set()
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            with contextlib.suppress(OSError):
                if os.path.isfile(path):
                    os.remove(path)
                    deleted += 1
        return deleted
