"""Preflight: validate the frozen main-run bank before any GPU work.

Runs the read-only identity / coverage / test-leakage validation (goal §5, §11)
against the committed development bank and exits non-zero on any violation.
CPU-only; no deps beyond the standard library.

    python -m benchmark.FalseConsensus.related_work.preflight \
        --results-root benchmark/FalseConsensus/results \
        --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import common


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate the frozen Governor v2 development bank")
    p.add_argument("--results-root", type=Path,
                   default=Path("benchmark/FalseConsensus/results"))
    p.add_argument("--split-manifest", type=Path,
                   default=Path("benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"))
    p.add_argument("--no-strict-hashes", action="store_true",
                   help="skip source_sha256 comparison (use only when the bank was re-materialized)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = common.validate_frozen_bank(
            args.results_root, args.split_manifest, strict_hashes=not args.no_strict_hashes
        )
    except ValueError as error:
        print(f"preflight FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    print("preflight OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
