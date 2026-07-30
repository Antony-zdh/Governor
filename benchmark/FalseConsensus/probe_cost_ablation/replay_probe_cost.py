#!/usr/bin/env python3
"""Probe-cost v2 replay + cost accounting + aggregation.

Replays the three frozen Governor v1 policies (naive_agreement, conservative,
balanced_task_aware_secondary) over REAL cap-specific probe banks at four
intervals, using the repository's authoritative rule interpreter
(``evaluate_existing_methods.decide_stop`` / ``_valid``) and grader
(``replay_rules.answers_equal``). No simplified substitute.

Per (trajectory x cap x interval x policy) it records:
  - stop position / stopped / delivered answer / correct / baseline_correct
  - consumed_main_tokens, probe_calls_used, probe_output_tokens_used,
    probe_prompt_tokens_used
  - gross_tokens_used = consumed_main_tokens
  - actual_total_tokens_used = consumed_main + probe_output_tokens
  - ideal_zero_probe_tax_tokens_used = consumed_main (probe output tax zeroed)
  - gross_saving, actual_net_saving, ideal_zero_probe_tax_saving, probe_tax,
    positive_net_saving (PSF per-row flag)

Aggregates first by environment = model x benchmark x seed, then macro-averages
environments. Bootstrap CIs reuse ``related_work.metrics.paired_hierarchical_ci``
where the existing implementation provides one; PSF/zero-tax CIs use the same
paired hierarchical resampler.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.governor_v2 import evaluate_existing_methods as eem  # noqa: E402
from benchmark.FalseConsensus.governor_v2 import replay_rules  # noqa: E402
from benchmark.FalseConsensus.related_work import metrics  # noqa: E402


MODELS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    "Qwen/Qwen3-8B": "qwen-qwen3-8b",
}
BENCHMARKS = ["math500", "amc23", "aime24"]
SEEDS = [42, 43, 44]
INTERVALS = [64, 128, 256, 512]
CAPS = [8, 16, 32]
START_TOKEN = 64
POLICIES = [
    eem.METHOD_NAIVE,
    eem.METHOD_CONSERVATIVE,
    eem.METHOD_BALANCED,
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--bank-root", type=Path,
                   default=REPO / "benchmark/FalseConsensus/results/governor_v2")
    p.add_argument("--cap-root", type=Path,
                   default=HERE / "cap_banks")
    p.add_argument("--splits", type=Path,
                   default=REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json")
    p.add_argument("--v1-protocol", type=Path,
                   default=REPO / "benchmark/FalseConsensus/final_eval/protocol.json")
    p.add_argument("--output", type=Path, default=HERE)
    p.add_argument("--bootstrap-samples", type=int, default=metrics.BOOTSTRAP_SAMPLES)
    p.add_argument("--bootstrap-seed", type=int, default=metrics.BOOTSTRAP_SEED)
    return p.parse_args()


def load_dev_assignments(splits: Path) -> dict:
    """Return {(benchmark, dataset_index): assignment} for dev split."""
    sm = json.loads(splits.read_text(encoding="utf-8"))
    out = {}
    for a in sm["assignments"]:
        if a.get("split") == "dev":
            out[(a["benchmark"], int(a["dataset_index"]))] = a
    return out


def downsample(probes: Sequence[Mapping[str, Any]], interval: int,
               start: int = START_TOKEN) -> list[dict]:
    """Strict position downsampling: keep probes at start, start+interval, ..."""
    return [
        dict(p) for p in sorted(probes, key=lambda x: int(x["token_position"]))
        if (int(p["token_position"]) - start) % interval == 0
        and int(p["token_position"]) >= start
    ]


def cost_row(trajectory: Mapping[str, Any], probes: Sequence[Mapping[str, Any]],
             *, method: str, config: Mapping[str, Any], cap: int, interval: int,
             split: str) -> dict[str, Any]:
    """One replay row with full cost accounting. Mirrors eem.replay_one then
    adds gross/net/zero-tax/PSF fields per probe-cost-v2 protocol."""
    run = trajectory["run_settings"]
    benchmark = str(run["dataset"])
    full_tokens = int(trajectory["tokens_used"])
    budget = int(run.get("budget", full_tokens))
    stop_index = eem.decide_stop(probes, config, trajectory, benchmark)
    stopped = stop_index is not None
    consumed = list(probes if stop_index is None else probes[: stop_index + 1])
    if stopped:
        stop_probe = consumed[-1]
        main_tokens = int(stop_probe["token_position"])
        delivered = replay_rules.normalize_answer(stop_probe.get("probe_answer", ""))
        capped = False
        stop_position = main_tokens
    else:
        main_tokens = full_tokens
        finished = bool(trajectory.get("finished_naturally", False))
        capped = not finished or full_tokens > budget
        stop_position = None
        delivered = (
            replay_rules.normalize_answer(trajectory.get("final_answer", ""))
            if not capped else ""
        )
    correct = bool(delivered and replay_rules.answers_equal(
        delivered, str(trajectory.get("target", ""))))
    baseline_correct = bool(trajectory.get("final_correct", False))
    probe_out = sum(int(p.get("probe_out_tokens", 0)) for p in consumed)
    probe_prompt = sum(int(p.get("probe_prompt_tokens", 0)) for p in consumed)
    gross = main_tokens
    actual = main_tokens + probe_out
    ideal = main_tokens  # zero probe-output tax counterfactual
    denom = full_tokens
    gross_saving = (denom - gross) / denom if denom else 0.0
    actual_net_saving = (denom - actual) / denom if denom else 0.0
    ideal_zero_tax = (denom - ideal) / denom if denom else 0.0
    probe_tax = gross_saving - actual_net_saving
    return {
        "model": run["model"],
        "benchmark": benchmark,
        "seed": int(run["base_seed"]),
        "problem_id": int(trajectory["problem_id"]),
        "split": split,
        "interval": interval,
        "cap": cap,
        "policy_name": method,
        "rule_variant": config.get("variant", method),
        "validity_mode": config.get("validity_mode", "schema"),
        "patience": int(config["patience"]),
        "floor_kind": config.get("floor_kind"),
        "full_main_tokens": full_tokens,
        "consumed_main_tokens": main_tokens,
        "stop_position": stop_position,
        "stopped": stopped,
        "capped": capped,
        "delivered_answer": delivered,
        "correct": correct,
        "baseline_correct": baseline_correct,
        "probe_calls_used": len(consumed),
        "probe_output_tokens_used": probe_out,
        "probe_prompt_tokens_used": probe_prompt,
        "gross_tokens_used": gross,
        "actual_total_tokens_used": actual,
        "ideal_zero_probe_tax_tokens_used": ideal,
        "gross_saving": gross_saving,
        "actual_net_saving": actual_net_saving,
        "ideal_zero_probe_tax_saving": ideal_zero_tax,
        "probe_tax": probe_tax,
        "positive_net_saving": (denom - actual) > 0,
        # sensitivity view: include probe prefill
        "sensitivity_total_tokens_with_prefill": actual + probe_prompt,
    }


# ---------------- aggregation ----------------

def _mean(xs: Sequence[float]) -> float:
    return math.fsum(xs) / len(xs) if xs else 0.0


def aggregate_env(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"n": 0}
    acc = _mean([float(r["correct"]) for r in rows])
    base_acc = _mean([float(r["baseline_correct"]) for r in rows])
    full = _mean([float(r["full_main_tokens"]) for r in rows])
    gross = _mean([float(r["gross_tokens_used"]) for r in rows])
    actual = _mean([float(r["actual_total_tokens_used"]) for r in rows])
    pout = _mean([float(r["probe_output_tokens_used"]) for r in rows])
    pprompt = _mean([float(r["probe_prompt_tokens_used"]) for r in rows])
    calls = _mean([float(r["probe_calls_used"]) for r in rows])
    gross_saving = _mean([float(r["gross_saving"]) for r in rows])
    net_saving = _mean([float(r["actual_net_saving"]) for r in rows])
    zero_tax = _mean([float(r["ideal_zero_probe_tax_saving"]) for r in rows])
    probe_tax = _mean([float(r["probe_tax"]) for r in rows])
    psf = _mean([1.0 if r["positive_net_saving"] else 0.0 for r in rows])
    stopped = _mean([1.0 if r["stopped"] else 0.0 for r in rows])
    # valid-stop fraction: stopped AND delivered nonempty AND valid answer
    valid_stop = _mean([1.0 if (r["stopped"] and r["delivered_answer"]) else 0.0
                        for r in rows])
    sorted_pout = sorted(float(r["probe_output_tokens_used"]) for r in rows)
    sorted_calls = sorted(float(r["probe_calls_used"]) for r in rows)
    return {
        "n": n,
        "accuracy": acc,
        "baseline_accuracy": base_acc,
        "accuracy_drop_pp": 100.0 * (base_acc - acc),
        "avg_full_main_tokens": full,
        "avg_gross_tokens": gross,
        "avg_actual_total_tokens": actual,
        "avg_probe_output_tokens": pout,
        "avg_probe_prompt_tokens": pprompt,
        "avg_probe_calls": calls,
        "gross_saving": gross_saving,
        "actual_net_saving": net_saving,
        "ideal_zero_probe_tax_saving": zero_tax,
        "probe_tax": probe_tax,
        "psf": psf,
        "stopped_fraction": stopped,
        "valid_stop_fraction": valid_stop,
        "median_probe_output_tokens": sorted_pout[n // 2] if n else 0.0,
        "median_probe_calls": sorted_calls[n // 2] if n else 0.0,
    }


def macro_env(env_summaries: list[dict]) -> dict:
    """Macro-average across environments (equal weight per env)."""
    if not env_summaries:
        return {"n_envs": 0}
    keys = ["accuracy", "baseline_accuracy", "accuracy_drop_pp",
            "avg_full_main_tokens", "avg_gross_tokens", "avg_actual_total_tokens",
            "avg_probe_output_tokens", "avg_probe_prompt_tokens",
            "avg_probe_calls", "gross_saving", "actual_net_saving",
            "ideal_zero_probe_tax_saving", "probe_tax", "psf",
            "stopped_fraction", "valid_stop_fraction"]
    out = {"n_envs": len(env_summaries),
           "n_trajectories": sum(e.get("n", 0) for e in env_summaries)}
    for k in keys:
        out[k] = _mean([float(e[k]) for e in env_summaries if k in e])
    return out


def bootstrap_ci(rows: list[dict], n_samples: int, seed: int) -> dict:
    """Paired hierarchical bootstrap over seeds+problems for net saving,
    accuracy drop, and PSF. Reuses metrics' resampling shape."""
    import random
    rng = random.Random(seed)
    by_seed = defaultdict(list)
    for r in rows:
        by_seed[r["seed"]].append(r)
    seeds = sorted(by_seed)
    if len(seeds) < 2:
        return {"note": "too few seeds for bootstrap", "n_seeds": len(seeds)}
    base_full = _mean([float(r["full_main_tokens"]) for r in rows])
    stats = {"actual_net_saving": [], "gross_saving": [],
             "probe_tax": [], "psf": [], "accuracy_drop_pp": []}
    for _ in range(n_samples):
        sampled = []
        for _ in range(len(seeds)):
            s = seeds[rng.randrange(len(seeds))]
            pool = by_seed[s]
            for _ in range(len(pool)):
                sampled.append(pool[rng.randrange(len(pool))])
        full = _mean([float(r["full_main_tokens"]) for r in sampled])
        gross = _mean([float(r["gross_tokens_used"]) for r in sampled])
        actual = _mean([float(r["actual_total_tokens_used"]) for r in sampled])
        stats["actual_net_saving"].append((full - actual) / full if full else 0.0)
        stats["gross_saving"].append((full - gross) / full if full else 0.0)
        stats["probe_tax"].append(
            ((full - gross) - (full - actual)) / full if full else 0.0)
        stats["psf"].append(_mean(
            [1.0 if r["positive_net_saving"] else 0.0 for r in sampled]))
        acc = _mean([float(r["correct"]) for r in sampled])
        bacc = _mean([float(r["baseline_correct"]) for r in sampled])
        stats["accuracy_drop_pp"].append(100.0 * (bacc - acc))
    out = {}
    for k, vs in stats.items():
        vs.sort()
        lo = vs[int(0.025 * (len(vs) - 1))]
        hi = vs[int(0.975 * (len(vs) - 1))]
        out[k] = {"mean": _mean(vs), "ci_lo": lo, "ci_hi": hi}
    return out


def main() -> None:
    args = parse_args()
    dev = load_dev_assignments(args.splits)
    protocol = json.loads(args.v1_protocol.read_text(encoding="utf-8"))
    rows: list[dict] = []
    coverage: dict[tuple, int] = defaultdict(int)
    for model, slug in MODELS.items():
        for bench in BENCHMARKS:
            configs = eem._configs(protocol, bench)
            for seed in SEEDS:
                env = f"development__{slug}__{bench}__seed_{seed}"
                main_dir = args.bank_root / env / "main"
                cap_dir = args.cap_root / env
                if not main_dir.exists():
                    print(f"[skip] no main bank: {main_dir}", flush=True)
                    continue
                if not cap_dir.exists():
                    print(f"[skip] no cap bank: {cap_dir}", flush=True)
                    continue
                for traj_path in sorted((main_dir / "traj").glob("problem_*.json")):
                    pid = int(traj_path.stem.split("_")[1])
                    if (bench, pid) not in dev:
                        continue
                    trajectory = json.loads(traj_path.read_text(encoding="utf-8"))
                    cap_path = cap_dir / "probes" / f"problem_{pid}.json"
                    if not cap_path.exists():
                        print(f"[miss] cap file {cap_path}", flush=True)
                        continue
                    cap_payload = json.loads(cap_path.read_text(encoding="utf-8"))
                    by_cap = cap_payload["probes_by_cap"]
                    for cap in CAPS:
                        probes64 = list(by_cap[str(cap)])
                        if not probes64:
                            continue
                        for interval in INTERVALS:
                            sub = downsample(probes64, interval)
                            for method, config in configs:
                                row = cost_row(trajectory, sub, method=method,
                                               config=config, cap=cap,
                                               interval=interval, split="dev")
                                rows.append(row)
                                coverage[(model, bench, seed)] += 1
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    import os
    def wjsonl(name, data):
        tmp = out / (name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, out / name)
    wjsonl("ablation_rows_v2.jsonl", rows)

    # environment-level summaries
    env_summaries = []
    env_index = {}
    for (model, bench, seed), _ in sorted(coverage.items()):
        env_rows = [r for r in rows if r["model"] == model
                    and r["benchmark"] == bench and r["seed"] == seed]
        for policy in POLICIES:
            for cap in CAPS:
                for interval in INTERVALS:
                    cell = [r for r in env_rows if r["policy_name"] == policy
                            and r["cap"] == cap and r["interval"] == interval]
                    s = aggregate_env(cell)
                    s.update({"model": model, "benchmark": bench, "seed": seed,
                              "policy_name": policy, "cap": cap, "interval": interval})
                    env_summaries.append(s)
    wjsonl("env_summaries_v2.jsonl", env_summaries)

    # macro over environments
    macro_rows = []
    for policy in POLICIES:
        for cap in CAPS:
            for interval in INTERVALS:
                cells = [s for s in env_summaries if s["policy_name"] == policy
                         and s["cap"] == cap and s["interval"] == interval]
                m = macro_env(cells)
                m.update({"policy_name": policy, "cap": cap, "interval": interval})
                macro_rows.append(m)
    wjsonl("macro_summaries_v2.jsonl", macro_rows)

    # bootstrap CIs per (policy, cap, interval) on the pooled dev rows
    ci_rows = []
    for policy in POLICIES:
        for cap in CAPS:
            for interval in INTERVALS:
                cell_rows = [r for r in rows if r["policy_name"] == policy
                             and r["cap"] == cap and r["interval"] == interval]
                ci = bootstrap_ci(cell_rows, args.bootstrap_samples,
                                  args.bootstrap_seed)
                ci_rows.append({"policy_name": policy, "cap": cap,
                                "interval": interval, "ci": ci})
    wjsonl("bootstrap_ci_v2.jsonl", ci_rows)

    print(f"rows={len(rows)} env_cells={len(env_summaries)} macro_cells={len(macro_rows)}",
          flush=True)


if __name__ == "__main__":
    main()
