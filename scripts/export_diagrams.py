"""Export Mermaid diagrams from methodology_for_presentation.md to standalone PNG/HTML files.

Usage:
    python scripts/export_diagrams.py                              # HTML + auto-open
    python scripts/export_diagrams.py --png                        # PNG via Playwright
    python scripts/export_diagrams.py --png --no-open              # PNG only, no browser open
    python scripts/export_diagrams.py --out-dir docs/diagrams      # Custom output dir
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

MERMAID_HTML_TMPL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ margin: 0; padding: 40px; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; background: transparent;
         font-family: sans-serif; box-sizing: border-box; }}
  .mermaid {{ max-width: none; width: max-content; }}
  .mermaid svg {{ background: transparent !important; }}
  svg {{ background: transparent !important; }}
</style>
</head>
<body>
<div class="mermaid">
{code}
</div>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
mermaid.initialize({{
  startOnLoad: true,
  theme: "base",
  themeVariables: {{
    background: "transparent",
    primaryBackground: "transparent",
    lineColor: "#1f4e79",
    primaryTextColor: "#1f4e79",
    primaryColor: "#e8f0fe",
    secondaryColor: "#f0f4f8",
    tertiaryColor: "#fafbfc",
    mainBkg: "#e8f0fe",
    nodeBorder: "#1f4e79",
    clusterBkg: "#f4f7fb",
    clusterBorder: "#3b82f6",
    edgeLabelBackground: "#ffffffcc",
    nodeTextColor: "#111827",
    titleColor: "#1f4e79",
    actorBkg: "#e8f0fe",
    actorBorder: "#1f4e79",
    actorTextColor: "#111827",
    signalColor: "#1f4e79",
    signalTextColor: "#111827",
    labelBoxBkgColor: "#e8f0fe",
    labelBoxBorderColor: "#1f4e79",
    labelTextColor: "#111827",
    loopTextColor: "#111827",
    activationBorderColor: "#1f4e79",
    activationBkgColor: "#e8f0fe",
    sequenceNumberColor: "#111827",
  }},
  flowchart: {{ useMaxWidth: false, htmlLabels: true }},
  sequence: {{ useMaxWidth: false }},
}});
</script>
</body>
</html>"""

INDEX_HTML_TMPL = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Smart Eye — All Diagrams</title>
<style>
  body {{ font-family: sans-serif; margin: 2em; background: transparent; }}
  h2 {{ border-bottom: 2px solid #1f4e79; padding-bottom: 0.3em; margin-top: 2em; }}
  .diagram-box {{ border: 1px solid #d0d0d0; border-radius: 8px;
                  padding: 1.5em; margin: 1em 0 2em; }}
  .mermaid {{ max-width: none; }}
  .mermaid svg {{ background: transparent !important; }}
  svg {{ background: transparent !important; }}
</style>
</head>
<body>
<h1>Smart Eye — All Diagrams</h1>
{body}
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
mermaid.initialize({{
  startOnLoad: true,
  theme: "base",
  themeVariables: {{
    background: "transparent",
    primaryBackground: "transparent",
    lineColor: "#1f4e79",
    primaryTextColor: "#1f4e79",
    primaryColor: "#e8f0fe",
    secondaryColor: "#f0f4f8",
    tertiaryColor: "#fafbfc",
    mainBkg: "#e8f0fe",
    nodeBorder: "#1f4e79",
    clusterBkg: "#f4f7fb",
    clusterBorder: "#3b82f6",
    edgeLabelBackground: "#ffffffcc",
    nodeTextColor: "#111827",
    titleColor: "#1f4e79",
    actorBkg: "#e8f0fe",
    actorBorder: "#1f4e79",
    actorTextColor: "#111827",
    signalColor: "#1f4e79",
    signalTextColor: "#111827",
    labelBoxBkgColor: "#e8f0fe",
    labelBoxBorderColor: "#1f4e79",
    labelTextColor: "#111827",
    loopTextColor: "#111827",
    activationBorderColor: "#1f4e79",
    activationBkgColor: "#e8f0fe",
    sequenceNumberColor: "#111827",
  }},
  flowchart: {{ useMaxWidth: false, htmlLabels: true }},
  sequence: {{ useMaxWidth: false }},
}});
</script>
</body>
</html>"""


def extract_mermaid_blocks(md_text: str) -> list[dict]:
    blocks = []
    lines = md_text.splitlines()
    i = 0
    current_section = "Overview"

    while i < len(lines):
        line = lines[i]

        h2_match = re.match(r"^##\s+(.+)", line)
        if h2_match:
            current_section = h2_match.group(1).strip()

        h3_match = re.match(r"^###\s+(.+)", line)
        if h3_match:
            current_section = h3_match.group(1).strip()

        if line.strip() == "```mermaid":
            start = i + 1
            code_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != "```":
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines)

            title = _infer_title(lines, start - 2, current_section)
            slug = _to_slug(title)

            blocks.append({
                "title": title,
                "slug": slug,
                "code": code,
                "section": current_section,
            })
        i += 1

    return blocks


def _infer_title(lines_before: list[str], start_idx: int, section: str) -> str:
    for offset in range(start_idx, max(start_idx - 5, -1), -1):
        line = lines_before[offset].strip() if offset < len(lines_before) else ""
        line = re.sub(r"^#{1,4}\s*", "", line)
        if line and not line.startswith("```"):
            return line
    return section


def _to_slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug[:48]


def generate_html_files(blocks: list[dict], out_dir: Path) -> list[Path]:
    console_enc = sys.stdout.encoding or "utf-8"

    def safe(text: str) -> str:
        return text.encode(console_enc, errors="replace").decode(console_enc, errors="replace")

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for block in blocks:
        html = MERMAID_HTML_TMPL.format(title=block["title"], code=block["code"])
        path = out_dir / f"{block['slug']}.html"
        path.write_text(html, encoding="utf-8")
        paths.append(path)
        print(safe(f"  + {path.name}"))

    return paths


def generate_index_html(blocks: list[dict], out_dir: Path) -> Path:
    parts = []
    for block in blocks:
        parts.append(f'<h2>{block["title"]}</h2>')
        parts.append('<div class="diagram-box">')
        parts.append('<div class="mermaid">')
        parts.append(block["code"])
        parts.append("</div></div>")

    html = INDEX_HTML_TMPL.format(body="\n".join(parts))
    path = out_dir / "all_diagrams.html"
    path.write_text(html, encoding="utf-8")
    return path


def export_png(blocks: list[dict], html_dir: Path, png_dir: Path) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ~ playwright not installed. Install: pip install playwright", file=sys.stderr)
        return 0

    console_enc = sys.stdout.encoding or "utf-8"

    def safe(text: str) -> str:
        return text.encode(console_enc, errors="replace").decode(console_enc, errors="replace")

    png_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 3840, "height": 2160}, device_scale_factor=2)

        for block in blocks:
            html_path = html_dir / f"{block['slug']}.html"
            png_path = png_dir / f"{block['slug']}.png"
            page = context.new_page()
            page.goto(html_path.as_uri(), wait_until="networkidle", timeout=30000)

            try:
                page.wait_for_function(
                    "() => document.querySelector('.mermaid svg') !== null",
                    timeout=20000,
                )
            except Exception:
                print(safe(f"  ~ Mermaid render timeout for {block['slug']}"), file=sys.stderr)
                page.close()
                continue

            page.evaluate("""() => {
                const s = document.createElement('style');
                s.textContent = 'svg { background: transparent !important; }';
                document.head.appendChild(s);
                const svg = document.querySelector('svg');
                if (svg) {
                    const w = svg.getAttribute('width');
                    if (w && parseFloat(w) > 0 && parseFloat(w) < 800) {
                        svg.style.width = '2000px';
                        svg.style.height = 'auto';
                    }
                }
            }""")

            mermaid_div = page.locator(".mermaid")
            box = mermaid_div.bounding_box()
            if box and box["width"] > 0 and box["height"] > 0:
                clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]}
                page.screenshot(clip=clip, omit_background=True, path=str(png_path))
                print(safe(f"  + {png_path.name}  ({box['width']:.0f} x {box['height']:.0f})"))
                count += 1
            else:
                print(safe(f"  ~ Empty bounding box for {block['slug']}"), file=sys.stderr)

            page.close()

        browser.close()

    return count


def open_files(paths: list[Path]) -> None:
    import subprocess
    import webbrowser

    for path in paths:
        uri = path.resolve().as_uri()
        try:
            webbrowser.open(uri)
        except Exception:
            try:
                subprocess.Popen(["start", uri], shell=True)
            except Exception:
                pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Mermaid diagrams to PNG/HTML")
    p.add_argument("--md", default=str(PROJECT / "docs" / "methodology_for_presentation.md"),
                   help="Input markdown file path")
    p.add_argument("--out-dir", default=str(PROJECT / "docs" / "diagrams"),
                   help="Output directory for HTML/PNG files")
    p.add_argument("--png", action="store_true", help="Export PNG via Playwright")
    p.add_argument("--no-open", action="store_true", help="Skip opening HTML files in browser")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    md_path = Path(args.md).resolve()
    if not md_path.exists():
        print(f"File not found: {md_path}", file=sys.stderr)
        return 1

    md_text = md_path.read_text(encoding="utf-8")
    blocks = extract_mermaid_blocks(md_text)

    if not blocks:
        print("No Mermaid diagrams found.", file=sys.stderr)
        return 1

    console_enc = sys.stdout.encoding or "utf-8"

    def safe(text: str) -> str:
        return text.encode(console_enc, errors="replace").decode(console_enc, errors="replace")

    print(f"\nFound {len(blocks)} diagrams in {md_path.name}:\n")
    for b in blocks:
        print(f"  {safe(b['slug']):45s}  ({safe(b['section'])})")

    out_dir = Path(args.out_dir).resolve()
    html_dir = out_dir / "html"
    png_dir = out_dir / "png"

    def safep(text: str) -> str:
        return text.encode(console_enc, errors="replace").decode(console_enc, errors="replace")

    print(safep(f"\nGenerating HTML files -> {html_dir}"))
    html_paths = generate_html_files(blocks, html_dir)

    index_path = generate_index_html(blocks, out_dir)
    print(safep("  + all_diagrams.html (combined)"))

    if args.png:
        print(safep(f"\nExporting PNG -> {png_dir}"))
        n = export_png(blocks, html_dir, png_dir)
        print(safep(f"\nExported {n}/{len(blocks)} PNG files"))

    if not args.no_open:
        print(safep("\nOpening in browser..."))
        open_files([index_path])

    print(safep(f"\nDone. All files in: {out_dir}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
