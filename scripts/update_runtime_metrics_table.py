from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "docs" / "final_report.md"
DEFAULT_SUMMARY = ROOT / "data" / "report_metrics" / "runtime_metrics_summary.csv"

MEASURE_ORDER = [
    "Average inference time per frame",
    "Average displayed FPS",
    "Camera startup time",
    "Alarm response delay",
    "Report export time",
]


def _placeholder() -> str:
    return '<span class="placeholder">Insert measured value.</span>'


def load_summary(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Runtime metrics summary was not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        return {
            str(row.get("runtime_measure") or "").strip(): row
            for row in csv.DictReader(fh)
            if str(row.get("runtime_measure") or "").strip()
        }


def build_runtime_table(summary: dict[str, dict[str, str]]) -> list[str]:
    rows = [
        "| Runtime Measure | Value | Notes |",
        "|---|---:|---|",
    ]
    for measure in MEASURE_ORDER:
        row = summary.get(measure, {})
        value = str(row.get("value") or "").strip() or _placeholder()
        notes = str(row.get("notes") or "").strip()
        count = str(row.get("sample_count") or "").strip()
        if count and count != "0":
            sample_text = f"{count} sample" if count == "1" else f"{count} samples"
            notes = f"{notes}; {sample_text}" if notes else sample_text
        rows.append(f"| {measure} | {value} | {notes} |")
    return rows


def update_report(report_path: Path, summary_path: Path) -> None:
    summary = load_summary(summary_path)
    lines = report_path.read_text(encoding="utf-8").splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == "| Runtime Measure | Value | Notes |":
            start = idx
            break
    if start is None:
        raise RuntimeError("Runtime metrics table header was not found in final_report.md")

    end = start + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1

    updated = lines[:start] + build_runtime_table(summary) + lines[end:]
    report_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Update docs/final_report.md from runtime metrics CSV.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="Markdown report path.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY), help="runtime_metrics_summary.csv path.")
    args = parser.parse_args()

    update_report(Path(args.report).resolve(), Path(args.summary).resolve())
    print(f"Updated runtime metrics table in {Path(args.report).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
