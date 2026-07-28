"""Replay/evaluation runner for the related-work baselines.

Turns collected probe/trigger/trial files into per-problem replay records
(with robust grading) and environment-level aggregate metrics + paired
hierarchical bootstrap CIs against the frozen full-generation baseline.

Heavy grading deps (sympy / latex2sympy2-backed ``dynasor.core.evaluator``,
``governor_v2.grading``) are imported lazily inside :func:`_real_fns`, so the
module imports cleanly without them; only the live replay subcommand needs
them.

    python -m benchmark.FalseConsensus.related_work.replay \
        --method certaindex_mid --main-run <ENV>/main \
        --collected <ENV>/certaindex_mid_frozen \
        --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json \
        --output <ENV>/certaindex_mid_frozen_replay
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from . import common, certaindex_mid, deer, metrics, tje

METHODS = {
    "certaindex_mid": certaindex_mid,
    "tje": tje,
    "deer": deer,
}


def _real_fns() -> tuple:
    """Lazy real equivalence functions (needs sympy/latex2sympy2)."""
    eqaul_group = common.real_eqaul_group
    count_not_empty = common.real_count_not_empty
    answers_equal_target = common.real_answers_equal
    return eqaul_group, count_not_empty, answers_equal_target


_COLLECTED_SUBDIR = {
    certaindex_mid.METHOD: "probes",
    tje.METHOD: "triggers",
    deer.METHOD: "trials",
}


def _load_collected(method_mod, collected: Path, problem_id: int) -> dict:
    """Load the per-problem collected record for the method."""
    sub = _COLLECTED_SUBDIR[method_mod.METHOD]
    path = collected / sub / f"problem_{problem_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing collected record: {path}")
    payload = common.load_json(path)
    if payload.get("method") != method_mod.METHOD or int(payload.get("problem_id", -1)) != problem_id:
        raise ValueError(f"identity mismatch in collected record: {path}")
    return payload


def _build_records(method_mod: Any, collected: dict) -> tuple:
    """Return (sequence_records, readout) for the method from a collected file."""
    if method_mod is certaindex_mid:
        return collected.get("probes", []), None
    if method_mod is tje:
        return collected.get("triggers", []), collected.get("readout")
    if method_mod is deer:
        return collected.get("trials", []), collected.get("readout")
    raise ValueError(method_mod)


def replay_environment(
    method_mod: Any,
    main_run: Path,
    collected_root: Path,
    split_map: Mapping[tuple, str],
    *,
    threshold_label: Optional[str] = None,
    threshold: Optional[float] = None,
) -> List[dict]:
    """Replay every frozen trajectory in an environment and return per-problem records."""
    eqaul_group, count_not_empty, answers_equal_target = _real_fns()
    manifest = common.load_main_manifest(main_run)
    dataset = manifest["run_settings"]["dataset"]
    records: List[dict] = []
    for tp in common.trajectory_paths(main_run):
        traj = common.load_trajectory(tp)
        problem_id = int(traj["problem_id"])
        collected_payload = _load_collected(method_mod, collected_root, problem_id)
        seq, readout = _build_records(method_mod, collected_payload)
        split = split_map.get((dataset, problem_id))
        kw: dict = {"answers_equal_target_fn": answers_equal_target, "split": split}
        if method_mod is certaindex_mid:
            kw["answers_equal_fn"] = eqaul_group
            kw["count_not_empty_fn"] = count_not_empty
        if method_mod is tje and threshold_label is not None:
            kw["threshold_label"] = threshold_label
        if method_mod is tje:
            kw["include_think_close"] = bool(collected_payload.get("include_think_close", True))
        if method_mod is deer and threshold is not None:
            kw["threshold"] = threshold
        if method_mod is certaindex_mid:
            rec = method_mod.replay(traj, seq, **kw)
        else:
            rec = method_mod.replay(traj, seq, readout=readout, **kw)
        records.append(rec)
    return records


def _baseline_rows(main_run: Path) -> List[dict]:
    """Full-generation baseline rows (the frozen main trajectory itself)."""
    manifest = common.load_main_manifest(main_run)
    rs = manifest["run_settings"]
    dataset = rs["dataset"]
    rows: List[dict] = []
    for tp in common.trajectory_paths(main_run):
        traj = common.load_trajectory(tp)
        pid = int(traj["problem_id"])
        rows.append({
            "method": "full_generation",
            "model": rs["model"], "dataset": dataset, "base_seed": rs["base_seed"],
            "problem_id": pid, "split": None,
            "correct": int(bool(traj.get("final_correct", False))),
            "baseline_correct": int(bool(traj.get("final_correct", False))),
            "all_generated_tokens": int(traj.get("tokens_used", 0)),
            "baseline_all_generated_tokens": int(traj.get("tokens_used", 0)),
            "delivered_answer": traj.get("final_answer", ""),
        })
    return rows


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay + evaluate a related-work baseline")
    p.add_argument("--method", required=True, choices=sorted(METHODS))
    p.add_argument("--main-run", type=Path, required=True)
    p.add_argument("--collected", type=Path, required=True)
    p.add_argument("--split-manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--threshold-label", default=None)
    p.add_argument("--threshold", type=float, default=None)
    p.add_argument("--bootstrap-samples", type=int, default=metrics.BOOTSTRAP_SAMPLES)
    p.add_argument("--bootstrap-seed", type=int, default=metrics.BOOTSTRAP_SEED)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    method_mod = METHODS[args.method]
    split_map = common.load_split_map(args.split_manifest)
    replay_records = replay_environment(
        method_mod, args.main_run, args.collected, split_map,
        threshold_label=args.threshold_label, threshold=args.threshold,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    # per-problem replay rows (JSONL, atomic)
    rows = [metrics.per_problem_metric(r) for r in replay_records]
    common.atomic_write_text(
        args.output / "replay_rows.jsonl",
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
    )
    # attach split to baseline rows too
    manifest = common.load_main_manifest(args.main_run)
    dataset = manifest["run_settings"]["dataset"]
    baseline = _baseline_rows(args.main_run)
    for r in baseline:
        r["split"] = split_map.get((dataset, r["problem_id"]))
    # aggregate
    summary = metrics.aggregate(rows)
    summary["method"] = method_mod.METHOD
    summary["model"] = manifest["run_settings"]["model"]
    summary["dataset"] = dataset
    summary["base_seed"] = manifest["run_settings"]["base_seed"]
    # paired hierarchical bootstrap vs full generation
    ci = metrics.paired_hierarchical_ci(rows, baseline,
                                        n_samples=args.bootstrap_samples,
                                        seed=args.bootstrap_seed)
    summary["ci"] = ci
    common.atomic_write_json(args.output / "summary.json", summary)
    common.atomic_write_json(args.output / "replay_manifest.json", {
        "schema_version": "related-work-replay-1",
        "method": method_mod.METHOD,
        "main_run": str(args.main_run),
        "collected": str(args.collected),
        "split_manifest": str(args.split_manifest),
        "protocol_version": manifest["run_settings"].get("protocol_version"),
        "n": len(rows),
        "bootstrap_samples": args.bootstrap_samples,
        "bootstrap_seed": args.bootstrap_seed,
        "test_read": False,
        "main_generation_changed": False,
    })
    print(json.dumps({k: summary[k] for k in ("method", "model", "dataset", "base_seed",
                                              "n", "accuracy", "stop_rate",
                                              "all_generated_token_saving_fraction")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
