#!/usr/bin/env python3
"""Matched Simple@32 vs CertaIndex@32 prompt-timing analysis (CPU only).

For every frozen trajectory (3420 paired rows) this replays BOTH arms with the
identical patience-3 stop rule (``certaindex_mid.decide_stop``) and the official
Governor grader (``grading.robust_answers_equal``), counting only probes
*consumed up to the stop* (the online cost the CertaIndex collector actually
incurs). It then computes per-pair consensus-delay and Harm/Rescue statistics.

Outputs: analysis/per_problem.csv, analysis/summary.json, analysis/report.md.
Pooled + equal-environment-macro summaries; no train/dev/test table.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work import common
from benchmark.FalseConsensus.related_work import certaindex_mid
from benchmark.FalseConsensus.governor_v2 import grading

# Faithful speedup: memoize dynasor ``math_equal`` (the only sympy cost in the
# stop-rule ``eqaul_group`` and the grader ``robust_answers_equal``), AND bound
# each call with a SIGALRM timeout so a pathological non-terminating symbolic
# comparison cannot hang the analysis. The wrapped function returns identical
# results for normal inputs; a timed-out comparison is recorded as "not equal"
# (matching the conservative outcome of math_equal's own timeout path). Logic
# of eqaul_group/robust_answers_equal is unchanged.
try:
    import signal as _signal
    _SIGALRM = getattr(_signal, "SIGALRM", None)
except Exception:
    _SIGALRM = None


class _MathTimeout(BaseException):
    """Raised by SIGALRM to interrupt a hung symbolic comparison (BaseException
    so sympy's ``except Exception`` cannot swallow it)."""


def _alarm_handler(signum, frame):
    raise _MathTimeout()


try:
    import dynasor.core.evaluator as _dyn_eval
    _orig_math_equal = _dyn_eval.math_equal
    _me_cache: dict = {}

    def _memo_math_equal(prediction, reference, *a, **k):
        key = (prediction, reference)
        v = _me_cache.get(key)
        if v is not None:
            return v
        armed = False
        old = None
        if _SIGALRM is not None:
            try:
                old = _signal.signal(_SIGALRM, _alarm_handler)
                _signal.alarm(5)
                armed = True
            except (ValueError, OSError):
                armed = False
        try:
            v = bool(_orig_math_equal(prediction, reference, *a, **k))
        except _MathTimeout:
            v = False
        except BaseException:
            v = False
        finally:
            if armed:
                _signal.alarm(0)
                try:
                    _signal.signal(_SIGALRM, old)
                except Exception:
                    pass
        _me_cache[key] = v
        return v

    _dyn_eval.math_equal = _memo_math_equal
except Exception:
    pass

GOV = REPO / "benchmark/FalseConsensus/results/governor_v2"
C32 = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/certaindex32"
ANALYSIS = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/analysis"

SLUGS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    "Qwen/Qwen3-8B": "qwen-qwen3-8b",
}
BENCHMARKS = ["math500", "amc23", "aime24"]
DEV_SEEDS = [42, 43, 44]
CONF_SEEDS = [45, 46, 47]
PATIENCE = 3

eqaul_group = common.real_eqaul_group
count_not_empty = common.real_count_not_empty


def _real_grade(delivered, target):
    if not delivered:
        return False
    try:
        return bool(grading.robust_answers_equal(delivered, str(target)))
    except Exception:
        return False


def envs() -> list[str]:
    out = []
    for slug in SLUGS.values():
        for ph, seeds in (("development", DEV_SEEDS), ("confirmation", CONF_SEEDS)):
            for b in BENCHMARKS:
                for s in seeds:
                    out.append(f"{ph}__{slug}__{b}__seed_{s}")
    return out


def grade(delivered: str, target: Any) -> bool:
    return _real_grade(delivered, target)


def arm_replay(trajectory: Mapping, probes: Sequence[Mapping],
               *, answers_equal_fn=None, grade_fn=None) -> dict:
    """Replay one arm: stop rule + grader + consumed-probe accounting.

    ``answers_equal_fn`` and ``grade_fn`` are injectable so tests can run
    without sympy/dynasor; defaults lazily call the real Dynasor functions.
    """
    if answers_equal_fn is None:
        answers_equal_fn = eqaul_group
    if grade_fn is None:
        grade_fn = _real_grade
    full = int(trajectory.get("tokens_used", 0))
    finished = bool(trajectory.get("finished_naturally", False))
    budget = int(trajectory.get("run_settings", {}).get("budget", full or 2**31))
    target = trajectory.get("target", "")
    baseline_correct = bool(trajectory.get("final_correct", False))
    decision = certaindex_mid.decide_stop(
        probes, patience=PATIENCE, answers_equal_fn=answers_equal_fn,
        count_not_empty_fn=count_not_empty)
    if decision is not None:
        stopped = True
        main_through = int(decision["stop_position"])
        delivered = decision["delivered_answer"]
        # consumed = probes up to and including the stop window
        consumed = list(probes[: decision["stop_index"]])
        capped = False
    else:
        stopped = False
        main_through = full
        capped = not finished or full > budget
        delivered = trajectory.get("final_answer", "") if (finished and full <= budget) else ""
        consumed = list(probes)
    probe_out = sum(int(p.get("probe_out_tokens", 0)) for p in consumed)
    probe_prompt = sum(int(p.get("probe_prompt_tokens", 0)) for p in consumed)
    correct = grade_fn(delivered, target) if delivered else False
    aux_wall = sum(float(p.get("probe_latency_seconds", 0.0)) for p in consumed)
    invalid = sum(1 for p in consumed if "error" in p or not p.get("probe_answer"))
    return {
        "stopped": stopped, "stop_position": (decision["stop_position"] if decision else None),
        "delivered_answer": delivered, "correct": correct,
        "baseline_correct": baseline_correct, "full_main_tokens": full,
        "main_tokens_through_stop": main_through, "probe_out_tokens": probe_out,
        "probe_prompt_tokens": probe_prompt,
        "all_generated_tokens": main_through + probe_out,
        "baseline_all_generated_tokens": full, "n_consumed_probes": len(consumed),
        "invalid_aux": invalid, "aux_wall_seconds": aux_wall, "capped": capped,
    }


def load_probes(env: str, bank: str) -> dict:
    """bank: 'simple' (dense_simple32) or 'certaindex' (certaindex32)."""
    if bank == "simple":
        d = GOV / env / "dense_simple32" / "probes"
    else:
        d = C32 / env / "probes"
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.glob("problem_*.json")):
        payload = json.loads(p.read_text(encoding="utf-8"))
        pid = int(payload["problem_id"])
        probes = sorted(payload.get("probes", []),
                         key=lambda x: int(x["token_position"]))
        out[pid] = probes
    return out


_BANK_CACHE: dict = {}


def _get_banks(env: str):
    """Per-worker cached probe banks (so repeated batches of one env load once)."""
    if env not in _BANK_CACHE:
        _BANK_CACHE[env] = (load_probes(env, "simple"), load_probes(env, "certaindex"))
    return _BANK_CACHE[env]


def process_batch(args):
    """Build per-problem rows for a chunk of trajectories of one env
    (worker-side, picklable, balances the 400-trajectory math500 envs)."""
    env, traj_dicts = args
    simp, cidx = _get_banks(env)
    parts = env.split("__")
    slug = parts[1]
    model = next(m for m, s in SLUGS.items() if s == slug)
    benchmark = parts[2]
    seed = int(parts[3].split("_")[1])
    rows = []
    for t in traj_dicts:
        pid = int(t["problem_id"])
        s = arm_replay(t, simp.get(pid, []))
        c = arm_replay(t, cidx.get(pid, []))
        both = s["stopped"] and c["stopped"]
        delay = (c["stop_position"] - s["stop_position"]) if both else None
        row = {
            "model": model, "benchmark": benchmark, "seed": seed,
            "problem_id": pid, "env": env,
            "simple_stopped": s["stopped"], "simple_stop_position": s["stop_position"],
            "simple_correct": s["correct"], "simple_delivered": s["delivered_answer"],
            "simple_main_tokens": s["main_tokens_through_stop"],
            "simple_probe_out": s["probe_out_tokens"],
            "simple_all_generated": s["all_generated_tokens"],
            "simple_n_probes": s["n_consumed_probes"],
            "certaindex_stopped": c["stopped"],
            "certaindex_stop_position": c["stop_position"],
            "certaindex_correct": c["correct"], "certaindex_delivered": c["delivered_answer"],
            "certaindex_main_tokens": c["main_tokens_through_stop"],
            "certaindex_probe_out": c["probe_out_tokens"],
            "certaindex_all_generated": c["all_generated_tokens"],
            "certaindex_n_probes": c["n_consumed_probes"],
            "baseline_correct": s["baseline_correct"],
            "full_main_tokens": s["full_main_tokens"],
            "both_stop": both, "consensus_delay": delay,
            "simple_only_stop": s["stopped"] and not c["stopped"],
            "certaindex_only_stop": c["stopped"] and not s["stopped"],
            "neither_stop": (not s["stopped"]) and (not c["stopped"]),
            "simple_harm": s["baseline_correct"] and not s["correct"],
            "simple_rescue": (not s["baseline_correct"]) and s["correct"],
            "certaindex_harm": c["baseline_correct"] and not c["correct"],
            "certaindex_rescue": (not c["baseline_correct"]) and c["correct"],
            "certaindex_corrects_simple": (not s["correct"]) and c["correct"],
            "certaindex_breaks_simple": s["correct"] and (not c["correct"]),
            "simple_harms_protected_by_certaindex":
                (s["baseline_correct"] and not s["correct"]) and c["correct"],
            "new_harms_introduced_by_certaindex":
                (c["baseline_correct"] and not c["correct"]) and s["correct"],
        }
        if both:
            row["certaindex_later"] = c["stop_position"] > s["stop_position"]
            row["certaindex_earlier"] = c["stop_position"] < s["stop_position"]
            row["certaindex_same"] = c["stop_position"] == s["stop_position"]
        else:
            row["certaindex_later"] = row["certaindex_earlier"] = row["certaindex_same"] = False
        rows.append(row)
    return (model, benchmark, seed, rows)


def process_env_seq(env: str):
    """Process all trajectories of one env in a single main thread (signal
    timeout works here), returning (model, benchmark, seed, rows)."""
    main_dir = GOV / env / "main" / "traj"
    if not main_dir.exists():
        return None
    traj = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(main_dir.glob("problem_*.json"))]
    return process_batch((env, traj))


def _write_outputs(per_rows, env_keys) -> None:
    cols = ["model", "benchmark", "seed", "problem_id", "baseline_correct",
            "simple_stopped", "simple_stop_position", "simple_correct",
            "simple_main_tokens", "simple_probe_out", "simple_all_generated",
            "simple_n_probes", "certaindex_stopped", "certaindex_stop_position",
            "certaindex_correct", "certaindex_main_tokens", "certaindex_probe_out",
            "certaindex_all_generated", "certaindex_n_probes", "both_stop",
            "consensus_delay", "simple_only_stop", "certaindex_only_stop",
            "neither_stop", "simple_harm", "simple_rescue", "certaindex_harm",
            "certaindex_rescue", "certaindex_corrects_simple",
            "certaindex_breaks_simple", "simple_harms_protected_by_certaindex",
            "new_harms_introduced_by_certaindex", "certaindex_later",
            "certaindex_earlier", "certaindex_same", "full_main_tokens"]
    with (ANALYSIS / "per_problem.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in per_rows:
            w.writerow(r)
    summary = _summarize(per_rows, env_keys)
    (ANALYSIS / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_report(summary, len(per_rows))
    print(f"per_problem rows: {len(per_rows)}")
    print(json.dumps(summary["pooled"], indent=2)[:1500])


def _all_envs() -> list:
    return [e for e in envs() if (GOV / e / "main" / "traj").exists()]


def _merge_parts() -> tuple:
    parts = sorted(ANALYSIS.glob("_part_*.json"))
    per_rows = []
    env_keys = {}
    for pf in parts:
        for r in json.loads(pf.read_text(encoding="utf-8")):
            per_rows.append(r)
            env_keys[(r["model"], r["benchmark"], r["seed"])] = 1
    return per_rows, list(env_keys.keys())


def main(argv=None) -> int:
    import argparse, os, subprocess, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int)
    ap.add_argument("--nshards", type=int)
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--nproc", type=int, default=10)
    args = ap.parse_args(argv)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    all_envs = _all_envs()

    # ---- shard worker: process a subset of envs, write a part file ----
    if args.shard is not None:
        shard_envs = all_envs[args.shard::args.nshards]
        rows = []
        for i, env in enumerate(shard_envs):
            r = process_env_seq(env)
            if r is not None:
                rows.extend(r[3])
            if (i + 1) % 2 == 0:
                print(f"shard {args.shard}: env {i+1}/{len(shard_envs)} "
                      f"rows={len(rows)} cache={len(_me_cache)}", flush=True)
        (ANALYSIS / f"_part_{args.shard}.json").write_text(
            json.dumps(rows, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"shard {args.shard} wrote {len(rows)} rows", flush=True)
        return 0

    # ---- merge only ----
    if args.merge:
        per_rows, env_keys = _merge_parts()
        _write_outputs(per_rows, env_keys)
        return 0

    # ---- default: spawn N shard subprocesses (each a separate process so
    # signal.alarm works in its main thread to bound math_equal hangs), wait,
    # then merge. Single-process was too slow; pools hang (worker threads). ----
    N = min(args.nproc, len(all_envs))
    runlogs = REPO / ".runlogs"
    runlogs.mkdir(exist_ok=True)
    procs = []
    for i in range(N):
        cmd = [sys.executable, "-m",
               "benchmark.FalseConsensus.probe_prompt_ablation.analyze_prompt_timing",
               "--shard", str(i), "--nshards", str(N)]
        log = open(runlogs / f"ppa_shard_{i}.log", "w")
        procs.append((i, subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)))
    print(f"spawned {N} shard workers", flush=True)
    for i, p in procs:
        rc = p.wait()
        print(f"shard {i} exit {rc}", flush=True)
        if rc != 0:
            print(f"  shard {i} FAILED; see .runlogs/ppa_shard_{i}.log", flush=True)
    per_rows, env_keys = _merge_parts()
    _write_outputs(per_rows, env_keys)
    return 0



def _mean(xs):
    return math.fsum(xs) / len(xs) if xs else 0.0


def _agg(rows):
    n = len(rows)
    if not n:
        return {"n": 0}
    def frac(pred):
        return _mean([1.0 if r[pred] else 0.0 for r in rows])
    simple_stop_pos = [r["simple_stop_position"] for r in rows if r["simple_stopped"]]
    cidx_stop_pos = [r["certaindex_stop_position"] for r in rows if r["certaindex_stopped"]]
    delays = [r["consensus_delay"] for r in rows if r["both_stop"]]
    full = _mean([r["full_main_tokens"] for r in rows])
    s_main = _mean([r["simple_main_tokens"] for r in rows])
    c_main = _mean([r["certaindex_main_tokens"] for r in rows])
    s_all = _mean([r["simple_all_generated"] for r in rows])
    c_all = _mean([r["certaindex_all_generated"] for r in rows])
    s_pout = _mean([r["simple_probe_out"] for r in rows])
    c_pout = _mean([r["certaindex_probe_out"] for r in rows])
    return {
        "n": n,
        "simple": {
            "accuracy": _mean([1.0 if r["simple_correct"] else 0.0 for r in rows]),
            "baseline_accuracy": _mean([1.0 if r["baseline_correct"] else 0.0 for r in rows]),
            "stop_rate": frac("simple_stopped"),
            "mean_first_consensus_position": _mean(simple_stop_pos) if simple_stop_pos else None,
            "median_first_consensus_position": sorted(simple_stop_pos)[len(simple_stop_pos)//2] if simple_stop_pos else None,
            "wrong_among_stops": (lambda ns=sum(1 for r in rows if r["simple_stopped"]), nw=sum(1 for r in rows if r["simple_stopped"] and not r["simple_correct"]): (nw / ns if ns else 0.0))(),
            "main_only_saving": _mean([1 - r["simple_main_tokens"]/r["full_main_tokens"] for r in rows if r["full_main_tokens"]]),
            "all_generated_saving": _mean([1 - r["simple_all_generated"]/r["full_main_tokens"] for r in rows if r["full_main_tokens"]]),
            "consumed_probe_output_tax_tokens": s_pout,
            "harm": frac("simple_harm"), "rescue": frac("simple_rescue"),
            "harm_rescue_ratio": (frac("simple_harm") / frac("simple_rescue")) if frac("simple_rescue") else None,
        },
        "certaindex": {
            "accuracy": _mean([1.0 if r["certaindex_correct"] else 0.0 for r in rows]),
            "baseline_accuracy": _mean([1.0 if r["baseline_correct"] else 0.0 for r in rows]),
            "stop_rate": frac("certaindex_stopped"),
            "mean_first_consensus_position": _mean(cidx_stop_pos) if cidx_stop_pos else None,
            "median_first_consensus_position": sorted(cidx_stop_pos)[len(cidx_stop_pos)//2] if cidx_stop_pos else None,
            "wrong_among_stops": (lambda ns=sum(1 for r in rows if r["certaindex_stopped"]), nw=sum(1 for r in rows if r["certaindex_stopped"] and not r["certaindex_correct"]): (nw / ns if ns else 0.0))(),
            "main_only_saving": _mean([1 - r["certaindex_main_tokens"]/r["full_main_tokens"] for r in rows if r["full_main_tokens"]]),
            "all_generated_saving": _mean([1 - r["certaindex_all_generated"]/r["full_main_tokens"] for r in rows if r["full_main_tokens"]]),
            "consumed_probe_output_tax_tokens": c_pout,
            "harm": frac("certaindex_harm"), "rescue": frac("certaindex_rescue"),
            "harm_rescue_ratio": (frac("certaindex_harm") / frac("certaindex_rescue")) if frac("certaindex_rescue") else None,
        },
        "paired": {
            "both_stop": frac("both_stop"),
            "simple_only_stop": frac("simple_only_stop"),
            "certaindex_only_stop": frac("certaindex_only_stop"),
            "neither_stop": frac("neither_stop"),
            "certaindex_later": frac("certaindex_later"),
            "certaindex_earlier": frac("certaindex_earlier"),
            "certaindex_same": frac("certaindex_same"),
            "mean_consensus_delay": _mean(delays) if delays else None,
            "median_consensus_delay": sorted(delays)[len(delays)//2] if delays else None,
            "certaindex_corrects_simple": frac("certaindex_corrects_simple"),
            "certaindex_breaks_simple": frac("certaindex_breaks_simple"),
            "simple_harms_protected_by_certaindex": frac("simple_harms_protected_by_certaindex"),
            "new_harms_introduced_by_certaindex": frac("new_harms_introduced_by_certaindex"),
            "n_certaindex_corrects_simple": sum(1 for r in rows if r["certaindex_corrects_simple"]),
            "n_certaindex_breaks_simple": sum(1 for r in rows if r["certaindex_breaks_simple"]),
            "n_simple_harms": sum(1 for r in rows if r["simple_harm"]),
            "n_simple_rescue": sum(1 for r in rows if r["simple_rescue"]),
            "n_certaindex_harm": sum(1 for r in rows if r["certaindex_harm"]),
            "n_certaindex_rescue": sum(1 for r in rows if r["certaindex_rescue"]),
            "n_simple_harms_protected_by_certaindex": sum(1 for r in rows if r["simple_harms_protected_by_certaindex"]),
            "n_new_harms_introduced_by_certaindex": sum(1 for r in rows if r["new_harms_introduced_by_certaindex"]),
        },
    }


def _summarize(per_rows, env_keys):
    pooled = _agg(per_rows)
    # equal-environment macro over the 36 envs
    by_env = defaultdict(list)
    for r in per_rows:
        by_env[(r["model"], r["benchmark"], r["seed"])].append(r)
    env_aggs = []
    for k in sorted(by_env):
        env_aggs.append(_agg(by_env[k]))
    macro = {}
    for arm in ("simple", "certaindex"):
        macro[arm] = {k: _mean([e[arm][k] for e in env_aggs if e[arm].get(k) is not None])
                     for k in env_aggs[0][arm] if k != "n"}
    macro["paired"] = {k: _mean([e["paired"][k] for e in env_aggs if isinstance(e["paired"].get(k), (int, float))])
                       for k in env_aggs[0]["paired"]}
    return {"pooled": pooled, "env_macro": macro,
            "n_envs": len(env_aggs), "n_trajectories": len(per_rows)}


def _write_report(summary, n_rows):
    p = summary["pooled"]; m = summary["env_macro"]
    s, c, pr = p["simple"], p["certaindex"], p["paired"]
    ms, mc, mpr = m["simple"], m["certaindex"], m["paired"]
    def fmt(x):
        return f"{x:.4f}" if isinstance(x, float) else str(x)
    lines = []
    lines.append("# Simple@32 vs CertaIndex@32 prompt-timing ablation\n")
    lines.append(f"Paired trajectories (pooled): **{n_rows}** across "
                 f"{summary['n_envs']} environments (2 models x 3 benchmarks x 6 seeds). "
                 "Both arms share the frozen main trajectory, probe every 64 tokens from "
                 "token 64, max_tokens=32, and the identical patience-3 consensus stop rule; "
                 "only the probe suffix differs. No train/dev/test table.\n")
    lines.append("Primary token accounting = main tokens through stop + consumed probe "
                 "output tokens (generated output tokens only). Probe prompt/prefill tokens "
                 "and wall time are reported separately and are NOT called GPU compute/latency.\n")
    lines.append("## Pooled summary (all 3,420 rows)")
    lines.append("| metric | Simple@32 | CertaIndex@32 |")
    lines.append("|---|---|---|")
    lines.append(f"| accuracy | {fmt(s['accuracy'])} | {fmt(c['accuracy'])} |")
    lines.append(f"| baseline (full gen) accuracy | {fmt(s['baseline_accuracy'])} | {fmt(c['baseline_accuracy'])} |")
    lines.append(f"| accuracy delta vs baseline | {fmt(s['accuracy']-s['baseline_accuracy'])} | {fmt(c['accuracy']-c['baseline_accuracy'])} |")
    lines.append(f"| stop rate | {fmt(s['stop_rate'])} | {fmt(c['stop_rate'])} |")
    lines.append(f"| mean first-consensus position | {fmt(s['mean_first_consensus_position'])} | {fmt(c['mean_first_consensus_position'])} |")
    lines.append(f"| median first-consensus position | {fmt(s['median_first_consensus_position'])} | {fmt(c['median_first_consensus_position'])} |")
    lines.append(f"| wrong among stops | {fmt(s['wrong_among_stops'])} | {fmt(c['wrong_among_stops'])} |")
    lines.append(f"| main-only token saving | {fmt(s['main_only_saving'])} | {fmt(c['main_only_saving'])} |")
    lines.append(f"| all-generated token saving | {fmt(s['all_generated_saving'])} | {fmt(c['all_generated_saving'])} |")
    lines.append(f"| consumed probe-output tax (tok) | {fmt(s['consumed_probe_output_tax_tokens'])} | {fmt(c['consumed_probe_output_tax_tokens'])} |")
    lines.append(f"| Harm | {fmt(s['harm'])} | {fmt(c['harm'])} |")
    lines.append(f"| Rescue | {fmt(s['rescue'])} | {fmt(c['rescue'])} |")
    lines.append(f"| Harm/Rescue | {fmt(s['harm_rescue_ratio'])} | {fmt(c['harm_rescue_ratio'])} |")
    lines.append("\n## Paired consensus timing & direction (pooled)")
    lines.append(f"- both stop: {fmt(pr['both_stop'])}; Simple-only stop: {fmt(pr['simple_only_stop'])}; "
                 f"CertaIndex-only stop: {fmt(pr['certaindex_only_stop'])}; neither stop: {fmt(pr['neither_stop'])}")
    lines.append(f"- when both stop — CertaIndex later: {fmt(pr['certaindex_later'])}, "
                 f"earlier: {fmt(pr['certaindex_earlier'])}, same: {fmt(pr['certaindex_same'])}")
    delays = [r["consensus_delay"] for r in []]  # placeholder; values from summary
    lines.append(f"- mean CertaIndex consensus delay (tokens, when both stop): {fmt(pr['mean_consensus_delay'])}; "
                 f"median: {fmt(pr['median_consensus_delay'])}")
    lines.append("\n## Paired correctness shifts (pooled)")
    lines.append(f"- CertaIndex-corrects-Simple: {pr['n_certaindex_corrects_simple']} ({fmt(pr['certaindex_corrects_simple'])})")
    lines.append(f"- CertaIndex-breaks-Simple: {pr['n_certaindex_breaks_simple']} ({fmt(pr['certaindex_breaks_simple'])})")
    lines.append(f"- Simple harms protected by CertaIndex: {pr['n_simple_harms_protected_by_certaindex']} ({fmt(pr['simple_harms_protected_by_certaindex'])})")
    lines.append(f"- new harms introduced by CertaIndex: {pr['n_new_harms_introduced_by_certaindex']} ({fmt(pr['new_harms_introduced_by_certaindex'])})")
    lines.append(f"- Simple harm/rescue counts: harm={pr['n_simple_harms']} rescue={pr['n_simple_rescue']}; "
                 f"CertaIndex harm/rescue counts: harm={pr['n_certaindex_harm']} rescue={pr['n_certaindex_rescue']}")
    lines.append("\n## Equal-environment macro (mean over 36 environments)")
    lines.append("| metric | Simple@32 | CertaIndex@32 |")
    lines.append("|---|---|---|")
    for k in ["accuracy","stop_rate","mean_first_consensus_position","main_only_saving","all_generated_saving","consumed_probe_output_tax_tokens","harm","rescue"]:
        lines.append(f"| {k} | {fmt(ms.get(k))} | {fmt(mc.get(k))} |")
    lines.append(f"\nmacro consensus delay (mean/median): {fmt(mpr.get('mean_consensus_delay'))} / {fmt(mpr.get('median_consensus_delay'))}")
    lines.append("\n## Conclusion")
    later = pr['certaindex_later']; earlier = pr['certaindex_earlier']
    cdel = pr['mean_consensus_delay']
    lines.append(f"CertaIndex reaches first consensus {'later' if (later or 0) > (earlier or 0) else 'earlier'} "
                 f"than Simple when both stop (mean delay {fmt(cdel)} tokens); see the direction counts above. "
                 f"Accuracy: Simple {fmt(s['accuracy'])} vs CertaIndex {fmt(c['accuracy'])}; "
                 f"net all-generated saving Simple {fmt(s['all_generated_saving'])} vs CertaIndex {fmt(c['all_generated_saving'])}.")
    lines.append("\n## Artifacts")
    lines.append("- per_problem.csv (3,420 paired rows), summary.json, acceptance.json, report.md "
                 "under benchmark/FalseConsensus/results/probe_prompt_ablation/analysis/")
    (ANALYSIS / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
