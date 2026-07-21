"""Convertit docs/RAPPORT_SAMCAM.md en PDF via markdown -> HTML -> Chrome headless."""
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).parent.parent.parent
MD_PATH = ROOT / "docs" / "RAPPORT_SAMCAM.md"
# Doit être dans docs/ (pas docs/images/) : les chemins d'image du markdown
# sont relatifs à docs/ (ex: "images/diagramme_x.png") — un HTML ailleurs
# casserait tous les <img>.
HTML_PATH = ROOT / "docs" / "_rapport_tmp.html"
PDF_PATH = ROOT / "docs" / "RAPPORT_SAMCAM.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page { size: A4; margin: 20mm 18mm; }
body {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.5;
  color: #1a1a1a;
  max-width: 100%;
}
h1 { font-size: 20pt; border-bottom: 3px solid #01696F; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 15pt; color: #01696F; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-top: 28px; page-break-after: avoid; }
h3 { font-size: 12.5pt; color: #01696F; margin-top: 20px; page-break-after: avoid; }
h4 { font-size: 11pt; margin-top: 14px; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 16px 0; font-size: 9pt; }
th, td { border: 1px solid #ccc; padding: 4px 7px; text-align: left; vertical-align: top; }
th { background: #f0f4f4; font-weight: 600; }
tr:nth-child(even) { background: #fafafa; }
code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 9pt; font-family: "SF Mono", Menlo, monospace; }
pre { background: #1e1e1e; color: #e8e8e8; padding: 10px 12px; border-radius: 6px; overflow-x: auto; font-size: 8.3pt; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { border-left: 4px solid #01696F; margin: 12px 0; padding: 2px 14px; color: #444; background: #f7f9f9; }
img { max-width: 100%; }
hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
a { color: #01696F; }
ul, ol { margin: 6px 0; padding-left: 22px; }
li { margin: 2px 0; }
.cover {
  text-align: center;
  page-break-after: always;
  padding-top: 30%;
}
.cover h1 { border: none; font-size: 26pt; }
"""


def main():
    md_text = MD_PATH.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    full_html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Rapport SAMCAM</title>
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""
    HTML_PATH.write_text(full_html, encoding="utf-8")
    print(f"HTML écrit : {HTML_PATH} ({len(full_html)} octets)")

    cmd = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={PDF_PATH}",
        "--print-to-pdf-no-header",
        "--no-pdf-header-footer",
        f"file://{HTML_PATH}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        sys.exit(1)
    print(f"PDF généré : {PDF_PATH}")


if __name__ == "__main__":
    main()
