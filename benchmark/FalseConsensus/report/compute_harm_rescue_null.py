#!/usr/bin/env python3
"""D1: what null does harm:rescue actually have to beat?

The paper (§4.4, abstract, conclusion) states that "pure sampling noise predicts
a ~1:1 ratio" of harm (final-correct, stop-wrong) to rescue (final-wrong,
stop-correct).  That is only true under an exchangeability assumption the data
does not satisfy: the ratio is computed among problems a rule STOPS, and most
trajectories end correct.  Under a base-rate null in which the committed answer
is statistically independent of the final answer,

    E[harm]   = N * p * (1 - q)          p = P(final correct | stopped)
    E[rescue] = N * (1 - p) * q          q = P(stop correct   | stopped)
    ratio_0   = p (1 - q) / ((1 - p) q)

which for p ~ 0.85 and q ~ 0.5 is ~5.7:1, not 1:1.

This script recomputes, for the same canonical rule per window W that
compute_harm_rescue.py uses, the full 2x2 among stopped problems, the base-rate
null ratio, and a within-environment permutation null.  It changes no committed
artifact; it writes its own cache.

Output: report/figures/gen/harm_rescue_null_cache.json
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(FC / "governor_v2"))
sys.path.insert(0, str(FC / "related_work"))

import compute_harm_rescue as CHR  # noqa: E402
import replay_rules as RR  # noqa: E402
from rule_schema import RuleSpec  # noqa: E402

CACHE = HERE / "figures" / "gen" / "harm_rescue_null_cache.json"
N_PERM = 2000
SEED = 20260807


def collect_env_cache():
    split_map = RR.load_split_map(FC / "governor_v2" / "generated" / "split_manifest.json") \
        if hasattr(RR, "load_split_map") else None
    return split_map


def replay_2x2(rule_spec, env_cache):
    """Per-environment (baseline_correct, stop_correct) outcomes among stops."""
    per_env = {}
    for (bench, budget, model, seed), items in env_cache:
        outcomes = []
        for traj, probes, corr, base_ok in items:
            v = RR.replay_one(traj, probes, rule_spec, bench, budget,
                              answer_correctness=corr,
                              baseline_answer_correctness=base_ok)
            if v["stopped"]:
                outcomes.append((bool(v["baseline_correct"]), bool(v["correct"])))
        per_env[(model, bench, seed)] = outcomes
    return per_env


def summarize(per_env, rng):
    allo = [o for v in per_env.values() for o in v]
    n = len(allo)
    harm = sum(1 for b, c in allo if b and not c)
    rescue = sum(1 for b, c in allo if not b and c)
    both_ok = sum(1 for b, c in allo if b and c)
    both_no = sum(1 for b, c in allo if not b and not c)
    p = (harm + both_ok) / n if n else 0.0          # P(final correct | stopped)
    q = (rescue + both_ok) / n if n else 0.0        # P(stop correct  | stopped)

    null = (p * (1 - q)) / ((1 - p) * q) if (1 - p) * q else None
    exp_harm = n * p * (1 - q)
    exp_rescue = n * (1 - p) * q

    # Permutation null: within each environment, shuffle the stop verdicts
    # against the final verdicts.  This destroys the pairing but preserves both
    # marginals and the environment composition.
    perm = []
    for _ in range(N_PERM):
        h = r = 0
        for outs in per_env.values():
            if not outs:
                continue
            bs = [b for b, _ in outs]
            cs = [c for _, c in outs]
            rng.shuffle(cs)
            for b, c in zip(bs, cs):
                if b and not c:
                    h += 1
                elif not b and c:
                    r += 1
        perm.append((h + 0.5) / (r + 0.5))
    perm.sort()

    obs = (harm + 0.5) / (rescue + 0.5)
    # one-sided p: fraction of permutations at least as extreme as observed
    pval = sum(1 for x in perm if x >= obs) / len(perm)

    return {
        "n_stopped": n,
        "harm": harm, "rescue": rescue,
        "both_correct": both_ok, "both_wrong": both_no,
        "p_final_correct_given_stop": p,
        "q_stop_correct_given_stop": q,
        "ratio_observed": (harm / rescue) if rescue else None,
        "ratio_observed_haldane": obs,
        "ratio_null_baserate": null,
        "expected_harm_under_null": exp_harm,
        "expected_rescue_under_null": exp_rescue,
        "excess_over_null": (obs / null) if null else None,
        "perm_null_median": perm[len(perm) // 2],
        "perm_null_p05": perm[int(0.05 * len(perm))],
        "perm_null_p95": perm[int(0.95 * len(perm))],
        "perm_p_value_one_sided": pval,
    }


def main() -> None:
    rng = random.Random(SEED)
    rules = CHR.canonical_rules()
    envs = CHR.dev_environments()
    split_map = RR.load_split_map(
        FC / "governor_v2" / "generated" / "split_manifest.json")

    env_cache = []
    for main_run, bench, budget, model, seed in envs:
        items = CHR.load_env_problems(main_run, bench, split_map, "dev")
        env_cache.append(((bench, budget, model, seed), items))
        print(f"  cached {model.split('/')[-1]:32s} {bench:8s} seed {seed}: "
              f"{len(items)} dev problems", flush=True)

    out = {}
    for w, d in rules.items():
        spec = RuleSpec.from_dict(d)
        per_env = replay_2x2(spec, env_cache)
        s = summarize(per_env, rng)
        out[str(w)] = s
        print(f"\nW={w:>2}  stops={s['n_stopped']:>4}  harm={s['harm']:>4} "
              f"rescue={s['rescue']:>3}  observed={s['ratio_observed_haldane']:>6.2f}:1  "
              f"base-rate null={s['ratio_null_baserate']:>5.2f}:1  "
              f"perm null={s['perm_null_median']:>5.2f} "
              f"[{s['perm_null_p05']:.2f},{s['perm_null_p95']:.2f}]  "
              f"excess={s['excess_over_null']:.2f}x  p={s['perm_p_value_one_sided']:.4f}",
              flush=True)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps({
        "note": "D1 base-rate and permutation nulls for harm:rescue; dev split, "
                "18 environments, canonical rule per W (see compute_harm_rescue.CANON)",
        "canonical_rule": CHR.CANON,
        "n_permutations": N_PERM,
        "seed": SEED,
        "by_window": out,
    }, indent=1))
    print(f"\nwrote {CACHE}")


if __name__ == "__main__":
    main()
