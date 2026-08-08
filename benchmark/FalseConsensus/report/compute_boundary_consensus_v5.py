#!/usr/bin/env python3
"""G2: replay the preregistered consensus family at DEER's own boundary positions.

The paper (§5.7) contrasts a consensus family (reads a probe answer on a fixed
64-token grid) against DEER (reads confidence in a freshly generated trial
answer at a reasoning boundary). Three factors differ at once, so the contrast
is not a one-factor ablation. This script holds *when* fixed to DEER's own
reading positions -- the probe stream is the ``boundary_simple32`` bank, sampled
at the exact token positions DEER generated trials -- and replays the
preregistered ``consensus_fixed`` rule family with ``probes_are_scheduled=True``
so the window/evidence logic runs over DEER's boundary schedule instead of the
64-token grid. Everything else (gates, token accounting, grader, macro over 18
dev environments) is the main-sweep machinery unchanged.

If consensus still clears no gate, the timing confound is eliminated by
measurement. If it clears one, that is outcome (b) and is reported as found,
not tuned away.

Outputs (results/boundary_consensus_v5/):
  replay_rows.jsonl.gz   per (rule, env) dev macro metrics
  summary.json           gate clearance, frontier, harm:rescue by W
  report.md
"""
from __future__ import annotations

import gzip
import json
import statistics as st
import sys
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
OUT = RES / "boundary_consensus_v5"
BANK = RES / "governor_v2_ws_sweep"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(GOV))
sys.path.insert(0, str(FC / "related_work"))
import latex2sympy2  # noqa: E402
import replay_rules as RR  # noqa: E402
import compute_harm_rescue as CHR  # noqa: E402
from rule_schema import RuleSpec  # noqa: E402

WS = [1, 3, 5, 8, 12, 16, 24, 30]
SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
GATES = [
    {"name": "conservative", "drop_pp": 1.0, "saving": 0.10, "psf": 0.8},
    {"name": "balanced", "drop_pp": 2.0, "saving": 0.20, "psf": 0.8},
    {"name": "token_efficient", "drop_pp": 3.5, "saving": 0.30, "psf": 0.7},
]

# Boundary probe bank lives next to dense_simple32 in each env directory.
BOUNDARY = "boundary_simple32"

# process-local cache, filled by the pool initializer
_ENV_CACHE: list = []
_RULE_INDEX: dict = {}

# For the 659-restricted committed frontier (F2): dense_simple32 probes on the
# SAME 659 problems the boundary stream covers (those DEER recorded trials for),
# so the fixed-grid frontier is comparable like-for-like. Built once in main
# (with the hard-kill grader, because a few dense_simple32 probe answers are
# pathological sympy cases) and fork-inherited by the replay pool.
_DENSE659_CACHE: list = []
_RULES659: dict = {}

# Hard-kill grader (same approach as compute_probe_wording_v5.eq): a few probe
# answers send sympy factor/gammasimp into multi-minute loops; grade each pair
# in a worker process that is hard-killed on a 4s timeout.
from compute_probe_wording_v5 import eq as _eq_hardkill  # noqa: E402


def eq(a, b) -> bool:
    latex2sympy2.var = {}
    return RR.answers_equal(a, b)


def load_boundary_probes(env_dir: Path, pid: int):
    path = env_dir / BOUNDARY / "probes" / f"problem_{pid}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sorted(payload.get("probes", []), key=lambda p: int(p["token_position"]))


def build_env_cache():
    """List of (bench, budget, model, seed, [(traj, probes, corr, base_ok)])."""
    split_map = RR.load_split_map(
        GOV / "generated" / "split_manifest.json")
    cache = []
    for main_run in RR.discover_runs(RES / "governor_v2", "development"):
        manifest = json.loads((main_run / "run_manifest.json").read_text())
        s = manifest["run_settings"]
        if s["model"] not in DEVID:
            continue
        bench = str(s["dataset"])
        budget = SEL[bench]
        model = str(s["model"])
        seed = int(s.get("seed", s.get("base_seed", -1)))
        items = []
        for tp in sorted((main_run / "traj").glob("problem_*.json")):
            traj = json.loads(tp.read_text(encoding="utf-8"))
            pid = int(traj["problem_id"])
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = load_boundary_probes(main_run.parent, pid)
            if not probes:
                continue
            corr = {}
            for pr in probes:
                a = RR.normalize_answer(pr.get("probe_answer"))
                if a and a not in corr:
                    latex2sympy2.var = {}
                    corr[a] = RR.answers_equal(a, traj["target"])
            latex2sympy2.var = {}
            base_ok = (RR.answers_equal(traj["final_answer"], traj["target"])
                       if "final_answer" in traj
                       else bool(traj["final_correct"]))
            items.append((traj, probes, corr, base_ok))
        cache.append((bench, budget, model, seed, items))
        print(f"  cached {model.split('/')[-1]:28s} {bench:8s} seed {seed}: "
              f"{len(items)} dev problems with boundary probes", flush=True)
    return cache


def _init_worker(rules_path):
    global _ENV_CACHE, _RULE_INDEX
    _ENV_CACHE[:] = build_env_cache()
    with gzip.open(rules_path, "rt") as f:
        for line in f:
            d = json.loads(line)
            if d["metadata"]["template"] == "consensus_fixed":
                _RULE_INDEX[d["rule_id"]] = d


def replay_rule(rule_id) -> dict:
    rule_d = _RULE_INDEX[rule_id]
    rule = RuleSpec.from_dict(rule_d)
    bench_of = {}
    env_rows = []
    for bench, budget, model, seed, items in _ENV_CACHE:
        if not items:
            continue
        vals = [RR.replay_one(traj, probes, rule, bench, budget,
                             probes_are_scheduled=True,
                             answer_correctness=corr,
                             baseline_answer_correctness=base_ok)
                for traj, probes, corr, base_ok in items]
        n = len(vals)
        baseline = st.fmean(v["baseline_correct"] for v in vals)
        acc = st.fmean(v["correct"] for v in vals)
        drop = 100.0 * (baseline - acc)
        bl_tok = st.fmean(v["baseline_decode_tokens"] for v in vals)
        tot_tok = st.fmean(v["total_decode_tokens"] for v in vals)
        saving = (bl_tok - tot_tok) / bl_tok if bl_tok else 0.0
        env_rows.append({
            "rule_id": rule_id, "model": model, "benchmark": bench,
            "seed": seed, "n": n, "accuracy": acc,
            "baseline_accuracy": baseline, "accuracy_drop_pp": drop,
            "saving_fraction": saving,
            "stop_rate": st.fmean(v["stopped"] for v in vals),
            "avg_main_decode_tokens": st.fmean(v["main_decode_tokens"] for v in vals),
            "avg_probe_decode_tokens": st.fmean(v["probe_decode_tokens"] for v in vals),
            "avg_total_decode_tokens": tot_tok,
            "avg_baseline_decode_tokens": bl_tok,
        })
    # macro over environments
    macro_drop = st.fmean(r["accuracy_drop_pp"] for r in env_rows)
    macro_saving = st.fmean(r["saving_fraction"] for r in env_rows)
    macro_stop = st.fmean(r["stop_rate"] for r in env_rows)
    frac_pos = st.fmean(1.0 if r["saving_fraction"] > 0 else 0.0
                        for r in env_rows)
    return {
        "rule_id": rule_id,
        "macro_drop_pp": macro_drop,
        "macro_saving_fraction": macro_saving,
        "macro_stop_rate": macro_stop,
        "frac_envs_positive_saving": frac_pos,
        "n_envs": len(env_rows),
        "env_rows": env_rows,
    }


def replay_2x2_for_rule(rule_d):
    """Per-env (baseline_correct, stop_correct) among stops, for harm:rescue."""
    rule = RuleSpec.from_dict(rule_d)
    per_env = {}
    for bench, budget, model, seed, items in _ENV_CACHE:
        outcomes = []
        for traj, probes, corr, base_ok in items:
            v = RR.replay_one(traj, probes, rule, bench, budget,
                              probes_are_scheduled=True,
                              answer_correctness=corr,
                              baseline_answer_correctness=base_ok)
            if v["stopped"]:
                outcomes.append((v["baseline_correct"], v["correct"]))
        per_env[(model, bench, seed)] = outcomes
    return per_env


def summarize_2x2(per_env):
    """Base-rate null for harm:rescue (matches compute_harm_rescue_null).

    p = P(final correct | stopped) = (harm + both_correct) / n
    q = P(stop correct   | stopped) = (rescue + both_correct) / n
    null = p (1-q) / ((1-p) q)
    """
    allo = [o for v in per_env.values() for o in v]
    n = len(allo)
    harm = sum(1 for b, c in allo if b and not c)
    rescue = sum(1 for b, c in allo if not b and c)
    both_correct = sum(1 for b, c in allo if b and c)
    obs = (harm + 0.5) / (rescue + 0.5)
    p = (harm + both_correct) / n if n else 0
    q = (rescue + both_correct) / n if n else 0
    null = (p * (1 - q)) / ((1 - p) * q) if (1 - p) * q else None
    return {"n_stopped": n, "harm": harm, "rescue": rescue,
            "both_correct": both_correct,
            "ratio_observed_haldane": obs,
            "ratio_observed": (harm / rescue) if rescue else None,
            "ratio_null_baserate": null,
            "excess_over_null": (obs / null) if null else None,
            "p_final_correct": p, "q_stop_correct": q}


def committed_fixed_grid_frontier():
    """Macro (drop, saving) per consensus_fixed rule on the committed grid."""
    axes = {}
    with gzip.open(BANK / "candidate_rules_v2.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            if d["metadata"]["template"] == "consensus_fixed":
                axes[d["rule_id"]] = d
    by_rule = defaultdict(list)
    for r in CHR._load_dev_rows():
        by_rule[r["rule_id"]].append(r)
    out = {}
    for rid, rows in by_rule.items():
        if rid not in axes:
            continue
        out[rid] = {
            "macro_drop_pp": st.fmean(r["accuracy_drop_pp"] for r in rows),
            "macro_saving_fraction": st.fmean(r["saving_fraction"] for r in rows),
            "n_envs": len(rows),
        }
    return out


def _dense659_problem_ids(env_dir: Path) -> set:
    """Problems in this env that have DEER boundary positions (the G2 set)."""
    pids = set()
    for bp in sorted((env_dir / BOUNDARY / "probes").glob("problem_*.json")):
        d = json.loads(bp.read_text(encoding="utf-8"))
        if d.get("probes"):  # non-empty -> DEER recorded trials
            pids.add(int(d["problem_id"]))
    return pids


def build_dense659_cache():
    """dense_simple32 probes (the fixed 64-token grid) restricted to the 659
    problems that have DEER boundary positions, so the committed fixed-grid
    frontier is on the SAME problem set as the boundary frontier. Uses the
    hard-kill grader (a few dense_simple32 answers are pathological sympy
    cases)."""
    split_map = RR.load_split_map(
        GOV / "generated" / "split_manifest.json")
    cache = []
    total = 0
    for main_run in RR.discover_runs(RES / "governor_v2", "development"):
        manifest = json.loads((main_run / "run_manifest.json").read_text())
        s = manifest["run_settings"]
        if s["model"] not in DEVID:
            continue
        bench = str(s["dataset"])
        budget = SEL[bench]
        model = str(s["model"])
        seed = int(s.get("seed", s.get("base_seed", -1)))
        pids = _dense659_problem_ids(main_run.parent)
        items = []
        for pid in sorted(pids):
            traj_path = main_run / "traj" / f"problem_{pid}.json"
            if not traj_path.exists():
                continue
            traj = json.loads(traj_path.read_text(encoding="utf-8"))
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = RR.load_probes(main_run, pid)  # dense_simple32 + adaptive
            if not probes:
                continue
            corr = {}
            for pr in probes:
                a = RR.normalize_answer(pr.get("probe_answer"))
                if a and a not in corr:
                    corr[a] = _eq_hardkill(a, traj["target"])
            base_ok = (_eq_hardkill(traj["final_answer"], traj["target"])
                       if "final_answer" in traj
                       else bool(traj["final_correct"]))
            items.append((traj, probes, corr, base_ok))
            total += 1
        cache.append((bench, budget, model, seed, items))
        print(f"  dense659 cached {model.split('/')[-1]:28s} {bench:8s} "
              f"seed {seed}: {len(items)} problems", flush=True)
    print(f"  dense659 total problems: {total}", flush=True)
    return cache


def _replay_dense659(rule_id) -> dict:
    """Replay one consensus_fixed rule on the 659-problem dense_simple32 stream
    using the FIXED 64-token grid schedule (NOT probes_are_scheduled -- this is
    the committed grid, restricted to the 659 problem set)."""
    rule = RuleSpec.from_dict(_RULES659[rule_id])
    env_rows = []
    for bench, budget, model, seed, items in _DENSE659_CACHE:
        if not items:
            continue
        vals = [RR.replay_one(traj, probes, rule, bench, budget,
                             probes_are_scheduled=False,
                             answer_correctness=corr,
                             baseline_answer_correctness=base_ok)
                for traj, probes, corr, base_ok in items]
        n = len(vals)
        baseline = st.fmean(v["baseline_correct"] for v in vals)
        acc = st.fmean(v["correct"] for v in vals)
        drop = 100.0 * (baseline - acc)
        bl_tok = st.fmean(v["baseline_decode_tokens"] for v in vals)
        tot_tok = st.fmean(v["total_decode_tokens"] for v in vals)
        saving = (bl_tok - tot_tok) / bl_tok if bl_tok else 0.0
        env_rows.append({
            "drop_pp": drop, "saving_fraction": saving,
            "frac_positive": 1.0 if saving > 0 else 0.0})
    return {
        "rule_id": rule_id,
        "macro_drop_pp": st.fmean(r["drop_pp"] for r in env_rows),
        "macro_saving_fraction": st.fmean(r["saving_fraction"]
                                         for r in env_rows),
        "frac_envs_positive_saving": st.fmean(r["frac_positive"]
                                              for r in env_rows),
        "n_envs": len(env_rows),
    }


def passes_gate_dense659(rec, gate):
    return (rec["macro_drop_pp"] <= gate["drop_pp"]
            and rec["macro_saving_fraction"] >= gate["saving"]
            and rec["frac_envs_positive_saving"] >= gate["psf"])


def committed_fixed_grid_frontier_659(rules_path):
    """Committed fixed-grid consensus frontier restricted to the same 659
    problems the boundary stream covers (like-for-like comparison). Built in
    main with the hard-kill grader; the replay pool fork-inherits the cache.
    Returns frontier_quantiles + gate clearance + the per-rule rows."""
    global _DENSE659_CACHE, _RULES659
    _DENSE659_CACHE[:] = build_dense659_cache()
    _RULES659.clear()
    rule_ids = []
    with gzip.open(rules_path, "rt") as f:
        for line in f:
            d = json.loads(line)
            if d["metadata"]["template"] == "consensus_fixed":
                _RULES659[d["rule_id"]] = d
                rule_ids.append(d["rule_id"])
    print(f"  dense659 replaying {len(rule_ids)} consensus_fixed rules on "
          f"659-problem subset", flush=True)
    rows = {}
    # Pool workers fork from main after _DENSE659_CACHE/_RULES659 are set, so
    # they inherit them without a per-worker rebuild.
    with Pool(processes=16) as pool:
        for i, rec in enumerate(pool.imap_unordered(
                _replay_dense659, rule_ids, chunksize=8), start=1):
            rows[rec["rule_id"]] = rec
            if i % 400 == 0 or i == len(rule_ids):
                print(f"  dense659 replayed {i}/{len(rule_ids)}", flush=True)
    pts = {rid: {"macro_drop_pp": r["macro_drop_pp"],
                 "macro_saving_fraction": r["macro_saving_fraction"]}
           for rid, r in rows.items()}
    gate_clearers = {g["name"]: sum(1 for r in rows.values()
                                    if passes_gate_dense659(r, g))
                     for g in GATES}
    return {"frontier": frontier_quantiles(pts),
            "gate_clearers": gate_clearers,
            "n_problems": sum(len(items)
                              for *_, items in _DENSE659_CACHE),
            "n_envs": sum(1 for *_, items in _DENSE659_CACHE if items)}


def frontier_quantiles(rules):
    """From {rid: {macro_drop_pp, macro_saving_fraction}}, return key numbers."""
    pts = [(r["macro_drop_pp"], r["macro_saving_fraction"])
           for r in rules.values()]
    # max saving among drop <= 1.0 pp
    safe = [s for d, s in pts if d <= 1.0]
    max_safe_under_1 = max(safe) if safe else None
    # drop at first rule reaching 10/20/30% saving (min drop among s>=threshold)
    def drop_at(thr):
        cands = [d for d, s in pts if s >= thr]
        return min(cands) if cands else None
    return {
        "max_saving_fraction_drop_le_1pp": max_safe_under_1,
        "drop_pp_at_10pct_saving": drop_at(0.10),
        "drop_pp_at_20pct_saving": drop_at(0.20),
        "drop_pp_at_30pct_saving": drop_at(0.30),
    }


def passes_gate(rec, gate):
    return (rec["macro_drop_pp"] <= gate["drop_pp"]
            and rec["macro_saving_fraction"] >= gate["saving"]
            and rec["frac_envs_positive_saving"] >= gate["psf"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rules_path = BANK / "candidate_rules_v2.jsonl.gz"
    # canonical per-W rule dicts (for harm:rescue), computed in main process
    canon = CHR.canonical_rules()
    canon_ids = {w: d["rule_id"] for w, d in canon.items()}

    rule_ids = []
    with gzip.open(rules_path, "rt") as f:
        for line in f:
            d = json.loads(line)
            if d["metadata"]["template"] == "consensus_fixed":
                rule_ids.append(d["rule_id"])
    print(f"{len(rule_ids)} consensus_fixed rules to replay over "
          f"boundary stream", flush=True)

    rows = {}
    with Pool(processes=16, initializer=_init_worker,
              initargs=(rules_path,)) as pool:
        for i, rec in enumerate(pool.imap_unordered(replay_rule, rule_ids,
                                                   chunksize=8), start=1):
            rows[rec["rule_id"]] = rec
            if i % 200 == 0 or i == len(rule_ids):
                print(f"  replayed {i}/{len(rule_ids)} rules", flush=True)

    # write per-(rule,env) rows
    # write per-(rule,env) rows -- sorted by rule_id for byte-stable output
    # (the replay pool uses imap_unordered, so insertion order is non-deterministic;
    # sorting makes re-runs reproducible).
    with gzip.open(OUT / "replay_rows.jsonl.gz", "wt") as f:
        for rid in sorted(rows):
            for er in rows[rid]["env_rows"]:
                f.write(json.dumps(er) + "\n")

    # gates
    gate_counts = {g["name"]: 0 for g in GATES}
    clearing = {g["name"]: [] for g in GATES}
    for rid, rec in rows.items():
        for g in GATES:
            if passes_gate(rec, g):
                gate_counts[g["name"]] += 1
                clearing[g["name"]].append(rid)

    # frontier
    frontier = frontier_quantiles(rows)

    # harm:rescue by W on boundary stream -- single process (8 rules, small)
    # but needs the env cache; run in a child pool of size 1 via initializer
    harm_by_w = {}
    # rebuild cache in this process for the canonical replay
    global _ENV_CACHE
    _ENV_CACHE[:] = build_env_cache()
    for w, d in canon.items():
        per_env = replay_2x2_for_rule(d)
        harm_by_w[w] = summarize_2x2(per_env)
        s = harm_by_w[w]
        print(f"  W={w:>2} stops={s['n_stopped']:>4} harm={s['harm']:>4} "
              f"rescue={s['rescue']:>3} obs={s['ratio_observed_haldane']:>6.2f}:1 "
              f"null={s['ratio_null_baserate']}", flush=True)

    committed = committed_fixed_grid_frontier()
    committed_frontier = frontier_quantiles(committed)
    # F2: committed fixed-grid frontier restricted to the SAME 659 problems the
    # boundary stream covers (DEER recorded trials for them), like-for-like.
    c659 = committed_fixed_grid_frontier_659(rules_path)
    # committed harm:rescue (from CHR cache)
    committed_harm = {}
    chr_cache = HERE / "figures" / "gen" / "harm_rescue_cache.json"
    if chr_cache.exists():
        cc = json.loads(chr_cache.read_text())
        for w, d in cc.get("consensus", {}).items():
            committed_harm[int(w)] = {
                "harm": d.get("harm"), "rescue": d.get("rescue"),
                "ratio_haldane": d.get("ratio_haldane"),
                "n_stopped": d.get("n_stopped")}

    summary = {
        "n_rules": len(rows),
        "n_boundary_problems": 659,
        "n_dev_problems_committed_sweep": 684,
        "n_problems_excluded_no_deer_trials": 25,
        "gate_clearers": gate_counts,
        "frontier_boundary": frontier,
        "frontier_committed_fixed_grid": committed_frontier,
        "frontier_committed_fixed_grid_659": c659["frontier"],
        "gate_clearers_committed_659": c659["gate_clearers"],
        "harm_rescue_by_W_boundary": harm_by_w,
        "harm_rescue_by_W_committed": committed_harm,
        "clearing_rule_ids": clearing,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n",
                                      encoding="utf-8")
    write_report(summary, rows, committed)
    print(f"wrote {OUT / 'summary.json'} and report.md")


def write_report(summary, rows, committed):
    g = summary["gate_clearers"]
    fb = summary["frontier_boundary"]
    fc = summary["frontier_committed_fixed_grid"]
    hb = summary["harm_rescue_by_W_boundary"]
    hc = summary["harm_rescue_by_W_committed"]
    lines = []
    lines.append("# G2 boundary-aligned consensus report\n")
    lines.append("## 1. Gate clearance on the boundary-aligned stream (dev, "
                 "macro over 18 envs)\n")
    lines.append("Prediction (hypothesis a): 0 rules clear any gate. "
                 "Outcome (b) -- a gate clears -- would be a major finding "
                 "and is reported as found, not tuned away.\n")
    lines.append("| gate | drop cap | saving floor | psf | rules clearing "
                 "(boundary) |")
    lines.append("|---|---:|---:|---:|---:|")
    for gate in GATES:
        lines.append(f"| {gate['name']} | {gate['drop_pp']}pp | "
                     f"{int(gate['saving']*100)}% | {gate['psf']} | "
                     f"{g[gate['name']]} |")
    any_clear = any(v > 0 for v in g.values())
    verdict_1 = ("clears a gate" if any_clear
                 else "clears NO gate (0 rules on any gate)")
    lines.append(f"\nVerdict: the boundary-aligned consensus stream "
                 f"**{verdict_1}** on dev.\n")

    lines.append("## 2. Accuracy-drop / net-saving frontier\n")
    fc659 = summary["frontier_committed_fixed_grid_659"]
    g659 = summary["gate_clearers_committed_659"]
    lines.append("The boundary stream covers **659 problems** (those DEER "
                 "recorded trials for); the committed fixed-grid sweep covers "
                 "all 684 dev problems. The 25-problem gap is design-forced: "
                 "DEER recorded 0 trials for those 25 -- no reasoning boundary "
                 "exists, so there is no position to probe. The like-for-like "
                 "comparison restricts the committed grid to the same 659 "
                 "problems; the full-684 numbers are kept labelled separately."
                 "\n")
    lines.append("**Like-for-like (same 659 problems):**\n")
    lines.append("| quantity | boundary stream (659) | committed fixed-grid "
                 "(659) |")
    lines.append("|---|---:|---:|")
    def pct(x):  # saving fraction -> percentage
        return f"{x*100:.2f}%" if x is not None else "n/a"
    def ppp(x):  # accuracy drop in percentage points
        return f"{x:.2f}pp" if x is not None else "n/a"
    lines.append(f"| max net saving among drop<=1.0pp | "
                 f"{pct(fb['max_saving_fraction_drop_le_1pp'])} | "
                 f"{pct(fc659['max_saving_fraction_drop_le_1pp'])} |")
    lines.append(f"| drop at first 10% saving | "
                 f"{ppp(fb['drop_pp_at_10pct_saving'])} | "
                 f"{ppp(fc659['drop_pp_at_10pct_saving'])} |")
    lines.append(f"| drop at first 20% saving | "
                 f"{ppp(fb['drop_pp_at_20pct_saving'])} | "
                 f"{ppp(fc659['drop_pp_at_20pct_saving'])} |")
    lines.append(f"| drop at first 30% saving | "
                 f"{ppp(fb['drop_pp_at_30pct_saving'])} | "
                 f"{ppp(fc659['drop_pp_at_30pct_saving'])} |")
    lines.append(f"\nGate clearance on the 659-restricted committed grid "
                 f"(reference, not the headline): conservative "
                 f"{g659['conservative']}, balanced {g659['balanced']}, "
                 f"token_efficient {g659['token_efficient']}.\n")
    lines.append("*Full-684 committed fixed-grid (labelled separately, NOT the "
                 "like-for-like set):*\n")
    lines.append("| quantity | committed fixed-grid (full 684) |")
    lines.append("|---|---:|")
    lines.append(f"| max net saving among drop<=1.0pp | "
                 f"{pct(fc['max_saving_fraction_drop_le_1pp'])} |")
    lines.append(f"| drop at first 10% saving | "
                 f"{ppp(fc['drop_pp_at_10pct_saving'])} |")
    lines.append(f"| drop at first 20% saving | "
                 f"{ppp(fc['drop_pp_at_20pct_saving'])} |")
    lines.append(f"| drop at first 30% saving | "
                 f"{ppp(fc['drop_pp_at_30pct_saving'])} |")

    lines.append("\n## 3. Harm:rescue by window W\n")
    lines.append("| W | stops (boundary) | harm | rescue | observed | "
                 "base-rate null | stops (committed) | harm (committed) | "
                 "rescue (committed) | committed ratio |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for w in WS:
        b = hb.get(w, {})
        c = hc.get(w, {})
        def r2(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else "—"
        lines.append(f"| {w} | {b.get('n_stopped','—')} | "
                     f"{b.get('harm','—')} | {b.get('rescue','—')} | "
                     f"{r2(b.get('ratio_observed_haldane'))} | "
                     f"{r2(b.get('ratio_null_baserate'))} | "
                     f"{c.get('n_stopped','—')} | {c.get('harm','—')} | "
                     f"{c.get('rescue','—')} | {r2(c.get('ratio_haldane'))} |")

    lines.append("\n## 4. Plain-language verdict\n")
    if not any_clear:
        lines.append("Hypothesis **(a)** is supported: the consensus family "
                     "still clears no gate on dev when read at DEER's own "
                     "boundary positions. The timing confound is eliminated "
                     "by measurement rather than by hedging -- the failure is "
                     "in *what* is read (the signal), not in *when* it is "
                     "read. §5.7's fourth qualification can be promoted to a "
                     "positive result.")
    else:
        lines.append("Hypothesis **(b)** is supported: the consensus family "
                     f"clears a gate on the boundary-aligned stream "
                     f"({sum(g.values())} rule(s) across gates). The "
                     "published result is therefore partly about probe "
                     "schedules, not only the signal. This is reported as "
                     "found; it is not tuned back toward (a).")
    lines.append("\nHarm:rescue on the boundary stream is reported alongside "
                 "the committed fixed-grid values (45.1:1 -> 2.0:1) above; "
                 "excess over the base-rate null is in summary.json.\n")
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
