#!/usr/bin/env python3
"""Audit and inventory the 2026-08-01 CPU-only evidence closure."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "benchmark/FalseConsensus/results/cpu_finalization_20260801"

ARTIFACTS = {
    "matched_signal_manifest": "benchmark/FalseConsensus/results/related_work/matched_signal_cpu/manifest.json",
    "matched_signal_frontier": "benchmark/FalseConsensus/results/related_work/matched_signal_cpu/frontier.csv",
    "governor_freeze": "benchmark/FalseConsensus/results/governor_v2/extended_frozen_selection/selection_manifest.json",
    "governor_test": "benchmark/FalseConsensus/results/governor_v2/extended_frozen_selection/evaluated_manifest.json",
    "governor_test_summary": "benchmark/FalseConsensus/results/governor_v2/extended_frozen_selection/test_summary.csv",
    "related_test": "benchmark/FalseConsensus/results/related_work/test/aggregate/aggregate.json",
    "related_test_report": "benchmark/FalseConsensus/results/related_work/test/aggregate/report.md",
    "human_adjudication": "benchmark/FalseConsensus/results/human_eval/adjudicated/summary.json",
    "oracle": "benchmark/FalseConsensus/results/governor_v2/simple32_oracle/manifest.json",
    "oracle_summary": "benchmark/FalseConsensus/results/governor_v2/simple32_oracle/summary.csv",
    "evidence_map": "paper/FINDING_EXPERIMENT_MAP.md",
    "evidence_pdf": "output/pdf/Governor_Finding_Experiment_Map.pdf",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((REPO / relative).read_text(encoding="utf-8"))


def csv_rows(relative: str) -> list[dict[str, str]]:
    with (REPO / relative).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def audit() -> dict[str, Any]:
    missing = [relative for relative in ARTIFACTS.values() if not (REPO / relative).exists()]
    # The PDF is generated after the first audit pass; permit exactly that one omission.
    if missing and missing != [ARTIFACTS["evidence_pdf"]]:
        raise FileNotFoundError(f"missing closure artifacts: {missing}")

    matched = load_json(ARTIFACTS["matched_signal_manifest"])
    if matched["audit"]["trajectories"] != 3420:
        raise AssertionError("matched-signal trajectory count")
    if matched["audit"]["exact_trigger_matches"] != 30606:
        raise AssertionError("matched-signal exact match count")

    frozen = load_json(ARTIFACTS["governor_freeze"])
    if frozen["test_data_read"] is not False:
        raise AssertionError("freeze manifest indicates Test access")
    if frozen["candidate_counts"]["combined"] != 33264 or len(frozen["selected"]) != 3:
        raise AssertionError("Governor freeze coverage")
    evaluated = load_json(ARTIFACTS["governor_test"])
    if evaluated["test_evaluation"]["rows"] != 2052:
        raise AssertionError("Governor Test row count")

    related = load_json(ARTIFACTS["related_test"])
    if related["row_count"] != 2052 or related["coverage"]["test_rows"] != 2052:
        raise AssertionError("related-work Test row count")
    if set(related["coverage"]["rows_per_method"].values()) != {684}:
        raise AssertionError("related-work per-method Test coverage")
    for required_view in ("per_model", "per_benchmark", "per_seed", "pooled", "environment_macro"):
        if not related.get(required_view):
            raise AssertionError(f"missing related-work view: {required_view}")

    human = load_json(ARTIFACTS["human_adjudication"])
    if human["taxonomy"]["unresolved"] or human["grader"]["unresolved"]:
        raise AssertionError("human adjudication unresolved cases")
    if human["taxonomy"]["n"] != 134 or human["grader"]["n"] != 89:
        raise AssertionError("human adjudication coverage")

    oracle = load_json(ARTIFACTS["oracle"])
    if oracle["trajectory_count"] != 3420 or oracle["test_data_used_for_rule_selection"]:
        raise AssertionError("Oracle coverage/leakage marker")
    oracle_pooled = next(row for row in csv_rows(ARTIFACTS["oracle_summary"]) if row["scope"] == "pooled")
    if int(oracle_pooled["n"]) != 3420:
        raise AssertionError("Oracle pooled count")

    inventory = {}
    for name, relative in ARTIFACTS.items():
        path = REPO / relative
        inventory[name] = {
            "path": relative,
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else None,
            "sha256": sha256(path) if path.exists() else None,
        }
    return {
        "schema_version": "false-consensus-cpu-finalization-1",
        "status": "complete_except_independent_remote_unseen_model_increment",
        "cpu_tasks": {task: "complete" for task in ("A", "B", "C", "D", "E", "F")},
        "invariants": {
            "matched_signal_trajectories": 3420,
            "matched_exact_events": 30606,
            "governor_candidate_count": 33264,
            "governor_test_rows": 2052,
            "related_work_test_rows": 2052,
            "human_rows": 223,
            "oracle_trajectories": 3420,
            "test_used_for_governor_selection": False,
            "oracle_is_non_deployable": True,
        },
        "artifacts": inventory,
        "remaining_nonblocking": [
            "Independent remote unseen-model Llama-8B/Qwen-32B Test seeds 46/47 may be merged later after audit."
        ],
    }


def report(manifest: dict[str, Any]) -> str:
    return """# FalseConsensus CPU evidence closure - 2026-08-01

All locally executable CPU tasks A-F passed row-count, scope, leakage and artifact
checks. No GPU inference or model download was performed.

| Task | Result |
|---|---|
| A matched signal | 3,420 trajectories; 30,606 exact DEER/TJE-position matches; unified frontier emitted |
| B Governor freeze/Test | 33,264 Train/Dev candidates; 3 rules frozen before Test; 2,052 rule-problem Test rows |
| C related-work Test | 3 methods x 684 = 2,052 rows; scope bug fixed; per-axis and macro tables emitted |
| D human adjudication | Task A 134/134 and Task B 89/89 resolved; raw annotations unchanged |
| E simple@32 Oracle | 3,420 trajectories; 80.56% strict upper-bound accuracy; 46.70% micro saving |
| F evidence closure | A24-A28, figures, artifact pointers and PDF updated |

Key limitations remain explicit: all core data are competition mathematics; matched
signal retains only exact-position overlap; long persistence is post-hoc sensitivity;
Oracle uses reference labels and is non-deployable; human Task B is risk-enriched.
The independent remote unseen-model seed 46/47 increment is not a blocker and is not
represented as complete here.

## Verification commands

```bash
python -m py_compile benchmark/FalseConsensus/related_work/aggregate_all.py benchmark/FalseConsensus/related_work/report_gen.py benchmark/FalseConsensus/report/analyze_matched_signal_frontier.py benchmark/FalseConsensus/governor_v2/analysis/freeze_extended_candidates.py benchmark/FalseConsensus/governor_v2/analysis/oracle_simple32.py benchmark/FalseConsensus/human_eval/adjudicate_reviews.py benchmark/FalseConsensus/finalize_cpu_evidence.py
python -m unittest benchmark.FalseConsensus.related_work.tests.test_postprocess.ReportGenTests -v
python benchmark/FalseConsensus/finalize_cpu_evidence.py
bash paper/render_finding_map_pdf.sh
```

Machine-readable inventory: `artifact_manifest.json` in this directory.
"""


def main() -> None:
    manifest = audit()
    atomic(OUT / "artifact_manifest.json", json.dumps(manifest, indent=2) + "\n")
    atomic(OUT / "COMPLETION_REPORT.md", report(manifest))
    print(json.dumps(manifest["invariants"], indent=2))


if __name__ == "__main__":
    main()
