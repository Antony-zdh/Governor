#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

mkdir -p output/pdf

pandoc paper/FINDING_EXPERIMENT_MAP.md \
  --from=markdown+pipe_tables+raw_tex+header_attributes \
  --standalone \
  --pdf-engine=xelatex \
  --lua-filter=paper/finding_map_table_widths.lua \
  --include-in-header=paper/finding_map_preamble.tex \
  --resource-path=paper:. \
  --toc \
  --toc-depth=2 \
  --metadata=title:"Governor Finding-Experiment 支撑矩阵" \
  --metadata=subtitle:"Claim-to-Evidence Audit with Experimental Appendix" \
  --metadata=date:"2026-08-01" \
  --metadata=lang:zh-CN \
  --metadata=pagetitle:"Governor Finding-Experiment Map" \
  -V papersize=a4 \
  -V geometry:landscape \
  -V geometry:margin=12mm \
  -V fontsize=10pt \
  -V mainfont="Helvetica Neue" \
  -V CJKmainfont="Hiragino Sans GB" \
  -V monofont="Menlo" \
  -o output/pdf/Governor_Finding_Experiment_Map.pdf
