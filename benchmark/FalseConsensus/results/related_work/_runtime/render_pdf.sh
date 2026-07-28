#!/usr/bin/env bash
# render_pdf.sh -- render the Chinese Markdown report to PDF.
#
# The script derives the repository root from its own location, so it works in
# both the ugcpu2 checkout and a clean local audit worktree.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
PY="${GOVERNOR_PYTHON:-python3}"
REPORT_MD="$REPO/benchmark/FalseConsensus/results/related_work/aggregate/report.md"
REPORT_HTML="$REPO/benchmark/FalseConsensus/results/related_work/aggregate/report.html"
REPORT_PDF="$REPO/benchmark/FalseConsensus/results/related_work/aggregate/report.pdf"

cd "$REPO"

if [[ ! -f "$REPORT_MD" ]]; then
    echo "FAIL: report.md not found at $REPORT_MD" >&2
    echo "Run: python -m benchmark.FalseConsensus.related_work.report_gen --aggregate .../aggregate.json --output $REPORT_MD" >&2
    exit 1
fi

# Try pandoc (best: Markdown -> PDF via LaTeX or wkhtmltopdf)
if command -v pandoc >/dev/null 2>&1; then
    echo "pandoc found; rendering PDF..."
    PANDOC_ARGS=(
        "$REPORT_MD" -o "$REPORT_PDF" --pdf-engine=xelatex
        -V geometry:landscape -V geometry:margin=10mm
        -V mainfont=Helvetica
    )
    if [[ "$(uname -s)" == "Darwin" && -f "/System/Library/Fonts/STHeiti Light.ttc" ]]; then
        PANDOC_ARGS+=(
            -V "CJKmainfont=STHeiti Light.ttc"
            -V "CJKoptions=Path=/System/Library/Fonts/"
        )
    fi
    pandoc "${PANDOC_ARGS[@]}" || \
    pandoc "$REPORT_MD" -o "$REPORT_PDF" --pdf-engine=wkhtmltopdf 2>/dev/null || \
    pandoc "$REPORT_MD" -o "$REPORT_PDF" 2>/dev/null
    if [[ -f "$REPORT_PDF" ]]; then
        echo "PDF written to $REPORT_PDF"
        exit 0
    fi
    echo "pandoc failed to produce PDF; falling back to HTML." >&2
fi

# Try weasyprint
if command -v weasyprint >/dev/null 2>&1; then
    echo "weasyprint found; rendering PDF..."
    weasyprint "$REPORT_HTML" "$REPORT_PDF" 2>/dev/null
    if [[ -f "$REPORT_PDF" ]]; then
        echo "PDF written to $REPORT_PDF"
        exit 0
    fi
fi

# Try wkhtmltopdf
if command -v wkhtmltopdf >/dev/null 2>&1; then
    echo "wkhtmltopdf found; rendering PDF..."
    wkhtmltopdf "$REPORT_HTML" "$REPORT_PDF" 2>/dev/null
    if [[ -f "$REPORT_PDF" ]]; then
        echo "PDF written to $REPORT_PDF"
        exit 0
    fi
fi

# Fallback: generate HTML from the Markdown via Python (simple converter)
echo "No PDF tool (pandoc/weasyprint/wkhtmltopdf) found." >&2
echo "Generating HTML instead..." >&2

"$PY" - "$REPORT_MD" "$REPORT_HTML" <<'PYEOF'
import sys, html
md_path, html_path = sys.argv[1], sys.argv[2]
text = open(md_path, encoding="utf-8").read()
# minimal Markdown -> HTML (tables, headings, bold, code)
import re
lines = text.split("\n")
out = ["<!DOCTYPE html><html><head><meta charset='utf-8'><style>body{font-family:serif;max-width:900px;margin:auto}table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px}</style></head><body>"]
in_table = False
for line in lines:
    if line.startswith("|"):
        cells = [html.escape(c.strip()) for c in line.split("|")[1:-1]]
        tag = "th" if line.startswith("| 模型") or line.startswith("| 方法") or line.startswith("|---") else "td"
        if "---" in line:
            continue
        if not in_table:
            out.append("<table>")
            in_table = True
        out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
    else:
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{html.escape(line.strip('#').strip())}</h{level}>")
        elif line.startswith("```"):
            pass  # skip code fences in HTML
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(line, quote=False))
            out.append(f"<p>{line}</p>")
if in_table:
    out.append("</table>")
out.append("</body></html>")
open(html_path, "w", encoding="utf-8").write("\n".join(out))
print(f"HTML written to {html_path}")
PYEOF

echo ""
echo "No PDF tool available. The HTML report is at:"
echo "  $REPORT_HTML"
echo ""
echo "To render PDF once pandoc is installed:"
echo "  pandoc $REPORT_MD -o $REPORT_PDF --pdf-engine=xelatex"
echo "  (or: pip install pandoc weasyprint && weasyprint $REPORT_HTML $REPORT_PDF)"
