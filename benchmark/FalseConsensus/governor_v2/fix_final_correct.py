"""Recompute stored `final_correct` flags with the robust grader.

Early v2 collections graded `math_equal(final_answer, raw_target)` without
trying the stripped reference, so formatting-only differences (e.g.
`\\left( ... \\right)`) were recorded as wrong. This walks main trajectory
files, recomputes the flag via `grading.robust_answers_equal`, rewrites files
whose flag changes, and prints an audit summary. Idempotent.

Usage:
    python fix_final_correct.py <results_root> [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

from grading import robust_answers_equal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed = {}
    total = 0
    for path in sorted(args.root.glob("**/main/traj/problem_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        total += 1
        old = bool(payload.get("final_correct"))
        new = bool(robust_answers_equal(payload.get("final_answer"), payload.get("target")))
        if new != old:
            env = path.parent.parent.parent.name
            changed.setdefault(env, []).append(
                {"problem_id": payload.get("problem_id"), "old": old, "new": new}
            )
            if not args.dry_run:
                payload["final_correct"] = new
                payload.setdefault("grading_notes", []).append(
                    "final_correct recomputed by fix_final_correct.py "
                    "(robust reference forms)"
                )
                path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    summary = {
        "trajectories_scanned": total,
        "flags_changed": sum(len(v) for v in changed.values()),
        "by_environment": {k: len(v) for k, v in sorted(changed.items())},
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if changed:
        detail_path = args.root / "final_correct_fix_audit.json"
        if not args.dry_run:
            detail_path.write_text(
                json.dumps(changed, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("audit detail written to", detail_path, file=sys.stderr)


if __name__ == "__main__":
    main()
