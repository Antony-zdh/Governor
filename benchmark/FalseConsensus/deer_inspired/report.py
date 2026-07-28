"""Render the aggregate Markdown report to PDF and perform basic QA."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise SystemExit("pandoc is required to render report.pdf")
    engines = [engine for engine in ("xelatex", "lualatex") if shutil.which(engine)]
    if not engines:
        raise SystemExit("xelatex or lualatex is required for Chinese PDF output")
    args.pdf.parent.mkdir(parents=True, exist_ok=True)
    command = [
        pandoc,
        str(args.markdown),
        "-o",
        str(args.pdf),
        f"--pdf-engine={engines[0]}",
        "-V",
        "geometry:margin=2.2cm",
        "-V",
        "CJKmainfont=Noto Sans CJK SC",
    ]
    subprocess.run(command, check=True)
    if not args.pdf.exists() or args.pdf.stat().st_size < 1024:
        raise SystemExit("rendered PDF is missing or implausibly small")
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", str(args.pdf), "-"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
        if len(result.stdout.strip()) < 200:
            raise SystemExit("PDF text extraction QA failed")
    print(f"rendered {args.pdf} ({args.pdf.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
