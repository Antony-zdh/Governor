#!/usr/bin/env python3
"""Per-window harm:rescue counts for the mechanism figure (paper Analysis).

Among the problems a rule STOPS, compare the committed-at-stop answer with the
trajectory's own frozen final answer and count the two directions:

    harm   = (final correct, stop wrong)   -- a recovery destroyed
    rescue = (final wrong,   stop correct) -- a wrong answer luckily banked

Sampling noise predicts ~1:1; a real "continued reasoning corrects" effect
predicts >> 1. We walk the window axis with one canonical consensus rule per
W (share threshold s = 1.0, probe interval 64, no maturity floor, non-empty
validity, certainty off) so the only thing changing is the window itself, and
also report the net saving and fire count that each W buys -- the point being
that the ratio only falls where the rule has stopped firing.

DEER's three dev-selected operating points are computed the same way for
comparison.

Output: report/figures/gen/harm_rescue_cache.json  (dev split, 18 environments)
"""
from __future__ import annotations

import gzip
import json
import statistics as st
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
BANK = RES / "governor_v2_ws_sweep"
CACHE = HERE / "figures" / "gen" / "harm_rescue_cache.json"

sys.path.insert(0, str(GOV))
sys.path.insert(0, str(FC / "related_work"))
import replay_rules as RR  # noqa: E402
from rule_schema import RuleSpec  # noqa: E402

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
WS = [1, 3, 5, 8, 12, 16, 24, 30]


# The paper's Analysis section walks the window axis with ONE rule whose only
# varying axis is W. This knob setting is the one that reproduces the published
# counts exactly: 668 dev stops at 45.1:1 for W=1, and 121 stops at 2.0:1 for
# W=30 (verified 2026-08-03 against the committed dev bank).
CANON = {"template": "consensus_fixed", "s": 1.0, "interval": 128,
         "maturity": 512, "validity": "schema", "certainty": False}


def canonical_rules():
    """One rule per W; every other axis held at CANON."""
    out = {}
    with gzip.open(BANK / "candidate_rules_v2.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            ax = d["metadata"]["axis_values"]
            if (d["metadata"]["template"] == CANON["template"]
                    and ax["evidence.dominant_share_threshold"] == CANON["s"]
                    and ax.get("probe.schedule.interval_tokens") == CANON["interval"]
                    and ax.get("maturity.minimum_tokens") == CANON["maturity"]
                    and ax.get("validity.mode") == CANON["validity"]
                    and ax.get("certainty.enabled") is CANON["certainty"]):
                out[int(ax["evidence.window_probes"])] = d
    missing = [w for w in WS if w not in out]
    if missing:
        raise SystemExit(f"canonical rule missing for W={missing}")
    return {w: out[w] for w in WS}


def best_rule_per_window():
    """Secondary view: the safest rule available at each W (min macro dev drop
    over the 440 rules sharing that W). Reported alongside the canonical curve
    so the figure can show that the ratio's fall is not an artifact of the
    particular knob setting."""
    axes_ = {}
    with gzip.open(BANK / "candidate_rules_v2.jsonl.gz", "rt") as f:
        for line in f:
            d = json.loads(line)
            axes_[d["rule_id"]] = d

    drops = defaultdict(list)
    for r in _load_dev_rows():
        drops[r["rule_id"]].append(r["accuracy_drop_pp"])
    macro = {k: st.fmean(v) for k, v in drops.items()}

    best = {}
    for rid, d in axes_.items():
        w = int(d["metadata"]["axis_values"]["evidence.window_probes"])
        if rid not in macro:
            continue
        if w not in best or macro[rid] < macro[best[w]["rule_id"]]:
            best[w] = d
    missing = [w for w in WS if w not in best]
    if missing:
        raise SystemExit(f"no rule found for W={missing}")
    for w in WS:
        ax = best[w]["metadata"]["axis_values"]
        print(f"  W={w:>2} best rule: s={ax['evidence.dominant_share_threshold']} "
              f"interval={ax.get('probe.schedule.interval_tokens', 'event')} "
              f"maturity={ax.get('maturity.minimum_tokens')} "
              f"validity={ax.get('validity.mode')} "
              f"certainty={ax.get('certainty.enabled')} "
              f"({best[w]['metadata']['template']})  dev drop="
              f"{macro[best[w]['rule_id']]:.2f}pp")
    return {w: best[w] for w in WS}


def _load_dev_rows():
    with gzip.open(BANK / "dev/consensus_dev_train.jsonl.gz", "rt") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["split"] == "dev" and r["model"] in DEVID:
                yield r


def dev_environments():
    """(main_run dir, benchmark, budget) for each development environment."""
    envs = []
    for main_run in RR.discover_runs(RES / "governor_v2", "development"):
        manifest = json.loads((main_run / "run_manifest.json").read_text())
        s = manifest["run_settings"]
        if s["model"] not in DEVID:
            continue
        envs.append((main_run, s["dataset"], SEL[s["dataset"]], s["model"],
                     int(s.get("seed", s.get("base_seed", -1)))))
    return envs


def load_env_problems(main_run, bench, split_map, split="dev"):
    """Grade each problem's probe answers ONCE; all windows then replay off it.

    The robust grader is the expensive part (sympy), and the correctness of a
    probe answer does not depend on W -- so hoisting it out of the window loop
    is what makes this tractable.
    """
    items = []
    for tp in sorted((main_run / "traj").glob("problem_*.json")):
        traj = json.loads(tp.read_text(encoding="utf-8"))
        pid = int(traj["problem_id"])
        if split_map.get((bench, pid)) != split:
            continue
        probes = RR.load_probes(main_run, pid)
        corr = {}
        for pr in probes:
            a = RR.normalize_answer(pr.get("probe_answer"))
            if a and a not in corr:
                corr[a] = RR.answers_equal(a, traj["target"])
        base_ok = (RR.answers_equal(traj["final_answer"], traj["target"])
                   if "final_answer" in traj else bool(traj["final_correct"]))
        items.append((traj, probes, corr, base_ok))
    return items


def replay_window(rule_spec, env_cache):
    """Per-environment aggregates + pooled harm/rescue counts for one rule."""
    harm = rescue = n_stop = n_tot = 0
    per_env = []
    for (bench, budget, model, seed), items in env_cache:
        vals = [RR.replay_one(traj, probes, rule_spec, bench, budget,
                              answer_correctness=corr,
                              baseline_answer_correctness=base_ok)
                for traj, probes, corr, base_ok in items]
        if not vals:
            continue
        n_tot += len(vals)
        for v in vals:
            if not v["stopped"]:
                continue
            n_stop += 1
            if v["baseline_correct"] and not v["correct"]:
                harm += 1
            elif not v["baseline_correct"] and v["correct"]:
                rescue += 1
        bl = st.fmean(v["baseline_decode_tokens"] for v in vals)
        tot = st.fmean(v["total_decode_tokens"] for v in vals)
        per_env.append({
            "model": model, "benchmark": bench, "seed": seed,
            "drop_pp": 100 * (st.fmean(v["baseline_correct"] for v in vals)
                              - st.fmean(v["correct"] for v in vals)),
            "saving": ((bl - tot) / bl * 100.0) if bl else 0.0,
            "stop_rate": st.fmean(v["stopped"] for v in vals),
        })
    return {
        "harm": harm, "rescue": rescue, "n_stopped": n_stop, "n_problems": n_tot,
        "ratio": (harm / rescue) if rescue else None,
        "ratio_haldane": (harm + 0.5) / (rescue + 0.5),
        "drop_pp": st.fmean(e["drop_pp"] for e in per_env),
        "saving": st.fmean(e["saving"] for e in per_env),
        "stop_rate": st.fmean(e["stop_rate"] for e in per_env),
        "n_env": len(per_env),
        "per_env": per_env,
    }


def deer_points():
    """harm/rescue for DEER's three dev-selected thresholds.

    Mirrors deer_threshold_sweep.main() exactly (same bank scope, same baseline
    construction, same split grouping) so the drop/saving reproduce the committed
    deer_threshold_sweep.jsonl.gz rows; we only additionally tally the two
    directions of changed correctness.
    """
    import deer_threshold_sweep as DS  # noqa: E402

    sel = {"C": 0.995, "B": 0.99, "T": 0.97}
    protocol = json.loads((GOV / "protocol_v2.json").read_text())
    budgets = DS.selection_budgets(protocol)
    split_map = RR.load_split_map(GOV / "generated/split_manifest.json")
    scope_dir = RES / "related_work/deer_confidence_bank_cap30" / "full"
    if not scope_dir.exists():
        print("! DEER dev confidence bank not found at", scope_dir, file=sys.stderr)
        return {}

    acc = {lab: {"harm": 0, "rescue": 0, "n_stopped": 0, "env": []} for lab in sel}
    n_env = 0
    for env_dir in sorted(scope_dir.iterdir()):
        if not env_dir.is_dir():
            continue
        model_key, benchmark, seed_tag = env_dir.name.split("__")
        seed = int(seed_tag.replace("seed_", ""))
        budget = budgets[benchmark]
        main_run = (RES / "governor_v2"
                    / f"development__{DS.SLUG[model_key]}__{benchmark}__seed_{seed}"
                    / "main")
        if not main_run.exists():
            raise FileNotFoundError(f"missing main run: {main_run}")
        main_index = DS.load_main_index(main_run)
        records = {int(r["problem_id"]): r for r in DS.iter_bank(env_dir)}
        baseline_index = {}
        for pid, m in main_index.items():
            complete = m["finished_naturally"] and m["tokens_used"] <= budget
            baseline_index[pid] = {
                "baseline_complete": complete,
                "baseline_correct": (DS.eq(m["final_answer"], m["target"])
                                     if complete and m["final_answer"] is not None
                                     else False),
                "baseline_tokens": min(m["tokens_used"], budget)}
        pids = [pid for pid in records if split_map.get((benchmark, pid)) == "dev"]
        if not pids:
            continue
        n_env += 1
        for lab, thr in sel.items():
            vals = [DS.replay_problem(records[pid], main_index[pid],
                                      baseline_index[pid], thr, budget)
                    for pid in pids]
            for v in vals:
                if not v["stopped"]:
                    continue
                acc[lab]["n_stopped"] += 1
                if v["baseline_correct"] and not v["correct"]:
                    acc[lab]["harm"] += 1
                elif not v["baseline_correct"] and v["correct"]:
                    acc[lab]["rescue"] += 1
            bl = st.fmean(v["baseline_decode_tokens"] for v in vals)
            tot = st.fmean(v["total_decode_tokens"] for v in vals)
            acc[lab]["env"].append({
                "drop_pp": 100 * (st.fmean(v["baseline_correct"] for v in vals)
                                  - st.fmean(v["correct"] for v in vals)),
                "saving": ((bl - tot) / bl * 100.0) if bl else 0.0})

    out = {}
    for lab, a in acc.items():
        if not a["env"]:
            continue
        out[lab] = {"threshold": sel[lab], "harm": a["harm"], "rescue": a["rescue"],
                    "n_stopped": a["n_stopped"],
                    "ratio": (a["harm"] / a["rescue"]) if a["rescue"] else None,
                    "ratio_haldane": (a["harm"] + 0.5) / (a["rescue"] + 0.5),
                    "drop_pp": st.fmean(e["drop_pp"] for e in a["env"]),
                    "saving": st.fmean(e["saving"] for e in a["env"]),
                    "n_env": len(a["env"])}
    print(f"  DEER computed over {n_env} dev environments")
    return out


def main():
    split_map = RR.load_split_map(GOV / "generated/split_manifest.json")
    envs = dev_environments()
    print(f"{len(envs)} development environments")
    rules = canonical_rules()
    print("  (secondary view: best rule per W)")
    best = best_rule_per_window()
    res = {"consensus": {}, "deer": {}, "meta": {
        "split": "dev", "n_env": len(envs),
        "rule_choice": "canonical: " + json.dumps(CANON)}}

    env_cache = []
    for main_run, bench, budget, model, seed in envs:
        items = load_env_problems(main_run, bench, split_map)
        env_cache.append(((bench, budget, model, seed), items))
        print(f"  graded {bench:<8} {model.split('/')[-1]:<28} seed {seed}: "
              f"{len(items)} dev problems", flush=True)

    for w in WS:
        spec = RuleSpec.from_dict(rules[w])
        r = replay_window(spec, env_cache)
        r["rule_id"] = rules[w]["rule_id"]
        res["consensus"][str(w)] = r
        print(f"  W={w:>2}  harm={r['harm']:>4} rescue={r['rescue']:>3} "
              f"ratio={r['ratio']}  stopped={r['n_stopped']:>4}  "
              f"drop={r['drop_pp']:.2f}pp  saving={r['saving']:.1f}%")
    res["consensus_best"] = {}
    for w in WS:
        rb = replay_window(RuleSpec.from_dict(best[w]), env_cache)
        rb["rule_id"] = best[w]["rule_id"]
        rb["axis_values"] = best[w]["metadata"]["axis_values"]
        res["consensus_best"][str(w)] = rb
        print(f"  [best] W={w:>2}  ratio={rb['ratio']}  stopped={rb['n_stopped']:>4} "
              f"drop={rb['drop_pp']:.2f}pp saving={rb['saving']:.1f}%", flush=True)

    # NB: the DEER leg MUST run in a fresh interpreter. Running it after the
    # consensus replays in the same process perturbs the shared evaluator state
    # and inflates DEER's drop by ~0.7 pp (0.33 -> 1.06 at tau=0.995). Verified
    # 2026-08-03: in a clean process it reproduces the committed
    # deer_threshold_sweep.jsonl.gz rows exactly.
    try:
        res["deer"] = json.loads(subprocess.run(
            [sys.executable, "-c",
             "import sys,json; sys.path.insert(0, %r); "
             "import compute_harm_rescue as C; print(json.dumps(C.deer_points()))"
             % str(HERE)],
            capture_output=True, text=True, check=True,
        ).stdout.strip().splitlines()[-1])
        for lab, d in res["deer"].items():
            print(f"  DEER {lab} tau={d['threshold']}  harm={d['harm']} "
                  f"rescue={d['rescue']} ratio={d['ratio']}  "
                  f"drop={d['drop_pp']:.2f}pp saving={d['saving']:.1f}%")
    except Exception as exc:  # noqa: BLE001
        print("! DEER leg skipped:", exc, file=sys.stderr)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(res, indent=1))
    print("wrote", CACHE)


if __name__ == "__main__":
    main()
