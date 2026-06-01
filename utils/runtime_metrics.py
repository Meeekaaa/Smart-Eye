from __future__ import annotations

import csv
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[1]
_OUT_DIR = _ROOT / "data" / "report_metrics"
_EVENTS_CSV = _OUT_DIR / "runtime_metrics_events.csv"
_SUMMARY_CSV = _OUT_DIR / "runtime_metrics_summary.csv"
_SUMMARY_TXT = _OUT_DIR / "runtime_metrics_summary.txt"

_EVENT_FIELDS = [
    "timestamp",
    "metric_key",
    "runtime_measure",
    "value",
    "unit",
    "notes",
    "context_json",
]
_SUMMARY_FIELDS = [
    "runtime_measure",
    "value",
    "notes",
    "sample_count",
    "minimum",
    "maximum",
    "latest",
    "unit",
]

_METADATA = {
    "average_inference_time_per_frame": {
        "runtime_measure": "Average inference time per frame",
        "unit": "ms",
        "notes": "measured inside local application",
    },
    "average_displayed_fps": {
        "runtime_measure": "Average displayed FPS",
        "unit": "FPS",
        "notes": "dashboard or playback test",
    },
    "camera_startup_time": {
        "runtime_measure": "Camera startup time",
        "unit": "ms",
        "notes": "time to begin live monitoring",
    },
    "alarm_response_delay": {
        "runtime_measure": "Alarm response delay",
        "unit": "ms",
        "notes": "time from rule trigger to visible alert",
    },
    "report_export_time": {
        "runtime_measure": "Report export time",
        "unit": "ms",
        "notes": "analytics report generation test",
    },
}


@dataclass
class _MetricStats:
    runtime_measure: str
    unit: str
    notes: str
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    latest: float | None = None

    def add(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.latest = value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    @property
    def average(self) -> float:
        return self.total / self.count if self.count else 0.0


_lock = threading.RLock()
_stats: dict[str, _MetricStats] = {}
_stats_loaded = False
_last_record_ts: dict[str, float] = {}
_enabled_cache: tuple[float, bool] = (0.0, True)


def _truthy(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _is_enabled() -> bool:
    global _enabled_cache
    now = time.monotonic()
    cached_at, cached_value = _enabled_cache
    if now - cached_at < 5.0:
        return cached_value

    env_value = os.environ.get("SMART_EYE_RUNTIME_METRICS")
    if env_value is not None:
        enabled = _truthy(env_value, True)
        _enabled_cache = (now, enabled)
        return enabled

    try:
        from backend.repository import db

        enabled = bool(db.get_bool("runtime_metrics_enabled", True))
    except Exception:
        enabled = True
    _enabled_cache = (now, enabled)
    return enabled


def _format_value(value: float, unit: str) -> str:
    if unit == "FPS":
        return f"{value:.1f} FPS"
    if unit == "ms":
        if value >= 1000.0:
            return f"{value / 1000.0:.2f} s"
        return f"{value:.1f} ms"
    return f"{value:.2f} {unit}".strip()


def _append_event(metric_key: str, value: float, unit: str, notes: str, context: dict[str, Any] | None) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    needs_header = not _EVENTS_CSV.exists() or _EVENTS_CSV.stat().st_size == 0
    with _EVENTS_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_EVENT_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "metric_key": metric_key,
                "runtime_measure": _stats[metric_key].runtime_measure,
                "value": f"{value:.6f}",
                "unit": unit,
                "notes": notes,
                "context_json": json.dumps(context or {}, sort_keys=True),
            }
        )


def _stats_for(metric_key: str, *, unit: str | None = None, notes: str | None = None) -> _MetricStats:
    meta = _METADATA.get(metric_key, {})
    return _stats.setdefault(
        metric_key,
        _MetricStats(
            runtime_measure=str(meta.get("runtime_measure") or metric_key),
            unit=unit or str(meta.get("unit") or ""),
            notes=notes or str(meta.get("notes") or ""),
        ),
    )


def _load_existing_events_locked() -> None:
    global _stats_loaded
    if _stats_loaded:
        return
    _stats_loaded = True
    if not _EVENTS_CSV.exists():
        return
    try:
        with _EVENTS_CSV.open("r", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                metric_key = str(row.get("metric_key") or "").strip()
                if not metric_key:
                    continue
                try:
                    value = float(row.get("value") or 0.0)
                except (TypeError, ValueError):
                    continue
                stat = _stats_for(
                    metric_key,
                    unit=str(row.get("unit") or "") or None,
                    notes=str(row.get("notes") or "") or None,
                )
                stat.add(value)
    except Exception:
        return


def _write_summary() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for metric_key in _METADATA:
        stat = _stats.get(metric_key)
        meta = _METADATA[metric_key]
        if stat and stat.count:
            rows.append(
                {
                    "runtime_measure": stat.runtime_measure,
                    "value": _format_value(stat.average, stat.unit),
                    "notes": stat.notes,
                    "sample_count": str(stat.count),
                    "minimum": _format_value(stat.minimum or 0.0, stat.unit),
                    "maximum": _format_value(stat.maximum or 0.0, stat.unit),
                    "latest": _format_value(stat.latest or 0.0, stat.unit),
                    "unit": stat.unit,
                }
            )
        else:
            rows.append(
                {
                    "runtime_measure": meta["runtime_measure"],
                    "value": "",
                    "notes": meta["notes"],
                    "sample_count": "0",
                    "minimum": "",
                    "maximum": "",
                    "latest": "",
                    "unit": meta["unit"],
                }
            )

    with _SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    width = max(len(row["runtime_measure"]) for row in rows)
    lines = ["Runtime Metrics Summary", "=" * 23, ""]
    for row in rows:
        value = row["value"] or "not measured"
        count = row["sample_count"]
        sample_text = f"{count} sample" if count == "1" else f"{count} samples"
        lines.append(f"{row['runtime_measure']:<{width}}  {value}  ({sample_text})  {row['notes']}")
    _SUMMARY_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def record_runtime_metric(
    metric_key: str,
    value: float,
    *,
    unit: str | None = None,
    notes: str | None = None,
    context: dict[str, Any] | None = None,
    min_interval_sec: float = 0.0,
) -> None:
    """Record a report-facing runtime metric as CSV events plus a summary file."""
    if not _is_enabled():
        return
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return
    if numeric_value < 0:
        return

    now = time.monotonic()
    with _lock:
        _load_existing_events_locked()
        if min_interval_sec > 0:
            previous = _last_record_ts.get(metric_key, 0.0)
            if now - previous < min_interval_sec:
                return
            _last_record_ts[metric_key] = now

        meta = _METADATA.get(metric_key, {})
        metric_unit = unit or str(meta.get("unit") or "")
        metric_notes = notes or str(meta.get("notes") or "")
        stat = _stats_for(metric_key, unit=metric_unit, notes=metric_notes)
        if unit:
            stat.unit = unit
        if notes:
            stat.notes = notes
        stat.add(numeric_value)
        _append_event(metric_key, numeric_value, stat.unit, stat.notes, context)
        _write_summary()


def rebuild_runtime_metric_summaries() -> None:
    """Rebuild summary CSV/TXT from the append-only runtime metric event CSV."""
    global _stats_loaded
    with _lock:
        _stats.clear()
        _stats_loaded = False
        _load_existing_events_locked()
        _write_summary()


def summary_paths() -> dict[str, Path]:
    return {
        "events_csv": _EVENTS_CSV,
        "summary_csv": _SUMMARY_CSV,
        "summary_txt": _SUMMARY_TXT,
    }
