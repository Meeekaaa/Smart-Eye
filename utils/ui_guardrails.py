from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HOTSPOTS = (
    FRONTEND / "dialogs.py",
    FRONTEND / "pages" / "models" / "_page.py",
    FRONTEND / "pages" / "playback" / "_page.py",
    FRONTEND / "pages" / "analytics" / "_page.py",
    FRONTEND / "pages" / "logs" / "_page.py",
    FRONTEND / "pages" / "rules_manager" / "_page.py",
    FRONTEND / "pages" / "notifications_manager" / "_forms.py",
    FRONTEND / "pages" / "face_manager" / "_page.py",
    FRONTEND / "pages" / "camera_manager" / "_cards.py",
    FRONTEND / "pages" / "camera_manager" / "_detail_panel.py",
    FRONTEND / "widgets" / "sidebar.py",
    FRONTEND / "widgets" / "face_capture_widget.py",
    FRONTEND / "widgets" / "auth_login_card.py",
    FRONTEND / "widgets" / "auth_reset_card.py",
    FRONTEND / "widgets" / "stat_card_widget.py",
    FRONTEND / "widgets" / "performance_widget.py",
    FRONTEND / "widgets" / "chart_widget.py",
    FRONTEND / "widgets" / "heatmap_widget.py",
    FRONTEND / "widgets" / "multi_feed_widget.py",
    FRONTEND / "widgets" / "toast.py",
    FRONTEND / "widgets" / "auth_overlay.py",
    FRONTEND / "widgets" / "video_widget.py",
    FRONTEND / "widgets" / "base" / "roster_card_base.py",
    FRONTEND / "widgets" / "alert_popup.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_inline_styles_in_hotspots() -> list[tuple[Path, int, str]]:
    pat = re.compile(r"setStyleSheet\(\s*f[\"']")
    hits: list[tuple[Path, int, str]] = []
    for path in HOTSPOTS:
        text = _read(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if pat.search(line):
                hits.append((path, idx, line.strip()))
    return hits


def find_dialogs_without_popup_theme() -> list[Path]:
    offenders: list[Path] = []
    for path in FRONTEND.rglob("*.py"):
        if path.name == "dialogs.py":
            continue
        text = _read(path)
        if "QDialog(" in text and "apply_popup_theme(" not in text:
            offenders.append(path)
    return offenders


def find_input_underlines() -> list[str]:
    path = FRONTEND / "styles" / "_input_styles.py"
    text = _read(path)
    return [line.strip() for line in text.splitlines() if "border-bottom" in line]


def main() -> int:
    inline_hotspot = find_inline_styles_in_hotspots()
    missing_theme = find_dialogs_without_popup_theme()
    input_underlines = find_input_underlines()

    print("Frontend guardrails report")
    print(f"- Hotspot inline setStyleSheet(f...): {len(inline_hotspot)}")
    print(f"- Dialogs missing apply_popup_theme: {len(missing_theme)}")
    print(f"- _input_styles border-bottom rules: {len(input_underlines)}")

    if missing_theme:
        print("\nDialogs missing popup theme:")
        for path in missing_theme[:20]:
            print(f"  - {path.relative_to(ROOT)}")

    if input_underlines:
        print("\nForbidden input underlines:")
        for line in input_underlines[:20]:
            print(f"  - {line}")

    if inline_hotspot:
        print("\nHotspot inline style samples:")
        for path, line_no, snippet in inline_hotspot[:20]:
            print(f"  - {path.relative_to(ROOT)}:{line_no}: {snippet}")

    if missing_theme or input_underlines:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
