#!/usr/bin/env python3
"""Threshold sweep of trial-answer-submit DEER on the frozen confidence bank.

DEER's only hyperparameter is the confidence threshold. For each threshold we
replay the *direct-submit* variant (the stronger, non-faithful one): walk the
per-boundary trials in order and commit the first valid trial answer whose
confidence strictly exceeds the threshold; otherwise keep the frozen full
answer. Token accounting matches the consensus sweep's fair
(all-generated-token) view: main tokens through the stop plus every trial's
output tokens generated up to and including the committed boundary.

Emits per-environment metric rows in the *same schema* as
``replay_rules.sweep_rows`` (rule_id = ``deer_thr_<tau>``) so DEER and consensus
rules are scored and gated by one selector.

Scope map: bank ``full`` (seeds 42-44) -> development main runs / train+dev
splits; bank ``test`` (seeds 45-47) -> confirmation main runs / test split.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any, Mapping

from replay_rules import answers_equal, load_split_map, summarize
from model_map import MODELS


def direct_submit_decision(trials, *, threshold, max_attempts=30):
    """First valid direct-submit trial strictly above ``threshold``.

    Inlined from related_work/deer_confidence_bank.py to avoid its torch-bearing
    import chain.
    """
    for row in trials:
        candidate_id = int(row.get("candidate_id", -1))
        if candidate_id > max_attempts:
            break
        answer = str(row.get("trial_answer", "")).strip()
        if answer and float(row.get("confidence", 0.0)) > threshold:
            return {
                "candidate_id": candidate_id,
                "token_position": int(row.get("token_position", 0)),
                "confidence": float(row["confidence"]),
                "trial_answer": answer,
            }
    return None

HERE = Path(__file__).resolve().parent

# Confidence threshold grid (DEER's sole hyperparameter). Dense near 1.0 where
# the avg-prob confidences concentrate.
THRESHOLDS = [
    0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99, 0.995,
    0.999, 0.9995, 0.9999, 0.99999, 0.999999,
]

MODEL_ID = {key: str(info["model_id"]) for key, info in MODELS.items()}
SLUG = {key: str(info["slug"]) for key, info in MODELS.items()}


def selection_budgets(protocol: Mapping[str, Any]) -> dict[str, int]:
    return {
        b["name"]: int(b["selection_budget"])
        for b in protocol["environments"]["benchmarks"]
        if b.get("enabled", True)
    }


def load_main_index(main_run: Path) -> dict[int, dict[str, Any]]:
    index: dict[int, dict[str, Any]] = {}
    for path in sorted((main_run / "traj").glob("problem_*.json")):
        t = json.loads(path.read_text(encoding="utf-8"))
        index[int(t["problem_id"])] = {
            "target": t["target"],
            "final_answer": t.get("final_answer"),
            "tokens_used": int(t["tokens_used"]),
            "finished_naturally": bool(t["finished_naturally"]),
        }
    return index


def iter_bank(env_dir: Path):
    with gzip.open(env_dir / "trials.jsonl.gz", "rt") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


_EQ_CACHE: dict[tuple[str, str], bool] = {}


def eq(answer: Any, target: Any) -> bool:
    key = (str(answer), str(target))
    hit = _EQ_CACHE.get(key)
    if hit is None:
        hit = answers_equal(answer, target)
        _EQ_CACHE[key] = hit
    return hit


def replay_problem(
    record: Mapping[str, Any],
    main: Mapping[str, Any],
    baseline: Mapping[str, Any],
    threshold: float,
    budget: int,
) -> dict[str, Any]:
    trials = list(record.get("trials", []))
    baseline_correct = baseline["baseline_correct"]
    baseline_tokens = baseline["baseline_tokens"]
    baseline_complete = baseline["baseline_complete"]

    decision = direct_submit_decision(trials, threshold=threshold)
    if decision is None:
        # never commits: keep frozen answer, but pay every trial probe.
        probe_decode = sum(int(t.get("trial_out_tokens", 0)) for t in trials)
        return {
            "correct": baseline_correct,
            "baseline_correct": baseline_correct,
            "main_decode_tokens": baseline_tokens,
            "probe_decode_tokens": probe_decode,
            "probe_prompt_tokens": sum(int(t.get("trial_prompt_tokens", 0)) for t in trials),
            "total_decode_tokens": baseline_tokens + probe_decode,
            "baseline_decode_tokens": baseline_tokens,
            "stopped": False,
            "capped": not baseline_complete,
        }
    committed_id = int(decision["candidate_id"])
    stop = min(int(decision["token_position"]), budget)
    correct = eq(decision["trial_answer"], main["target"])
    charged = [t for t in trials if int(t.get("candidate_id", 0)) <= committed_id]
    probe_decode = sum(int(t.get("trial_out_tokens", 0)) for t in charged)
    probe_prompt = sum(int(t.get("trial_prompt_tokens", 0)) for t in charged)
    return {
        "correct": correct,
        "baseline_correct": baseline_correct,
        "main_decode_tokens": stop,
        "probe_decode_tokens": probe_decode,
        "probe_prompt_tokens": probe_prompt,
        "total_decode_tokens": stop + probe_decode,
        "baseline_decode_tokens": baseline_tokens,
        "stopped": True,
        "capped": not baseline_complete,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, default=HERE / "protocol_v2.json")
    ap.add_argument(
        "--bank",
        type=Path,
        default=HERE.parent / "results/related_work/deer_confidence_bank_cap30",
    )
    ap.add_argument(
        "--main-root", type=Path, default=HERE.parent / "results/governor_v2"
    )
    ap.add_argument(
        "--split-manifest",
        type=Path,
        default=HERE / "generated/split_manifest.json",
    )
    ap.add_argument("--scopes", nargs="+", default=["full", "test"])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    budgets = selection_budgets(protocol)
    split_map = load_split_map(args.split_manifest)

    rows_out: list[dict[str, Any]] = []
    for scope in args.scopes:
        scope_dir = args.bank / scope
        phase = "development" if scope == "full" else "confirmation"
        main_prefix = "development" if scope == "full" else "confirmation"
        for env_dir in sorted(scope_dir.iterdir()):
            if not env_dir.is_dir():
                continue
            model_key, benchmark, seed_tag = env_dir.name.split("__")
            seed = int(seed_tag.replace("seed_", ""))
            budget = budgets[benchmark]
            main_run = (
                args.main_root
                / f"{main_prefix}__{SLUG[model_key]}__{benchmark}__seed_{seed}"
                / "main"
            )
            if not main_run.exists():
                raise FileNotFoundError(f"missing main run: {main_run}")
            main_index = load_main_index(main_run)
            records = {int(r["problem_id"]): r for r in iter_bank(env_dir)}

            # precompute per-problem baseline once (not per threshold)
            baseline_index: dict[int, dict[str, Any]] = {}
            for pid, m in main_index.items():
                complete = m["finished_naturally"] and m["tokens_used"] <= budget
                baseline_index[pid] = {
                    "baseline_complete": complete,
                    "baseline_correct": (
                        eq(m["final_answer"], m["target"])
                        if complete and m["final_answer"] is not None
                        else False
                    ),
                    "baseline_tokens": min(m["tokens_used"], budget),
                }

            # group problems by split
            by_split: dict[str, list[int]] = {}
            for pid in records:
                split = split_map.get((benchmark, pid))
                if split is None:
                    raise ValueError(f"unassigned split: {benchmark}/{pid}")
                by_split.setdefault(split, []).append(pid)

            for threshold in THRESHOLDS:
                for split, pids in sorted(by_split.items()):
                    values = [
                        replay_problem(
                            records[pid], main_index[pid], baseline_index[pid],
                            threshold, budget
                        )
                        for pid in pids
                    ]
                    rows_out.append(
                        {
                            "rule_id": f"deer_thr_{threshold:g}",
                            "method": "deer_direct_submit",
                            "phase": phase,
                            "split": split,
                            "model": MODEL_ID[model_key],
                            "model_role": "development",
                            "benchmark": benchmark,
                            "seed": seed,
                            "budget": budget,
                            "threshold": threshold,
                            **summarize(values),
                        }
                    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        for row in rows_out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows_out), "thresholds": len(THRESHOLDS)}))


if __name__ == "__main__":
    main()
