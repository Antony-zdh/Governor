#!/usr/bin/env python3
"""k-TIER disjunctive DEER+consensus rule (generalises the 2-branch disjunction).

Prior experiments in this series:
  * compute_consensus_deer_combo.py       -- CONJUNCTIVE (conf>tau AND last-W
    agree). Negative: adding a conjunct can only DELAY a stop, so 0/20 points
    Pareto-dominate DEER.
  * compute_consensus_deer_disjunctive.py -- DISJUNCTIVE 2-branch
    (conf>tau_hi OR (conf>tau_lo AND last-W agree)). Qualified positive: still
    0/36 Pareto-dominate at equal tau_hi, but it EXTENDS the achievable frontier
    (balanced gate: identical 1.944pp drop, +3.79pp saving vs the best DEER
    threshold). The optimal tau_lo landed HIGH (0.93-0.99).

This script generalises to k tiers, each with its own confidence floor and its
own required run length, monotone in both:

    STOP at the first boundary i where ANY tier fires:
      tier 1: conf_i > tau_1                                       (run len 1)
      tier 2: last 2 trial answers agree AND both  exceed tau_2    (run len 2)
      tier 3: last 3 trial answers agree AND all 3 exceed tau_3    (run len 3)
      ...
    with tau_1 > tau_2 > tau_3 > ...

Rationale: the more corroboration a candidate answer has, the less confidence
any single reading needs to carry.

Tier semantics chosen to match the PREVIOUS experiment's `variant_all_lo`
convention -- EVERY boundary in the run must clear that tier's floor, not just
the committing one. This is what makes "all j exceed tau_j" literal and makes
tier 1 (run length 1) exactly plain DEER at tau_1. The looser variant
(only the committing boundary must clear the floor) is also computed as
`variant_last_only` so the choice is shown not to be load-bearing.

Sanity checks asserted in code:
  * k=1 (tiers = [(1, tau)]) == plain DEER at tau, bit-identical.
  * all tau equal          == plain DEER at that tau (lower tiers are then
    strictly redundant: any run of j boundaries above tau contains a single
    boundary above tau, which tier 1 already fires on, no later).
  * k=2 with (tau_1, tau_2, W=2) reproduces the previous disjunctive
    experiment's `variant_all_lo` numbers at the same (tau_hi, tau_lo, W).
  * Net saving is monotone non-decreasing in the number of tiers (adding a tier
    can only add stop opportunities); any violation is a bug.

Token accounting, environment loading, macro-averaging and the latex2sympy2
grader repair are reused verbatim from compute_consensus_deer_combo (which
reproduces the committed DEER bank exactly). That reproduction is re-verified
at the start of the run; the script aborts if it fails.

Everything is macro-averaged over the 18 dev environments; never problem-micro.

PROCESS HYGIENE: run this file directly. It must be the first thing in its
interpreter to touch the shared answer evaluator.

Reads only committed banks.
Writes report/figures/gen/consensus_deer_tiered.json.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Reuse the validated machinery. NOTE: importing this module also installs the
# latex2sympy2 grader repair and the DS.eq guard, and sets up sys.path.
import compute_consensus_deer_combo as CB  # noqa: E402

RR = CB.RR
DS = CB.DS
eq = CB.eq
answers_agree = CB.answers_agree
macro = CB.macro
GATES = CB.GATES

CACHE = HERE / "figures" / "gen" / "consensus_deer_tiered.json"

# --------------------------------------------------------------------------
# GRIDS
# --------------------------------------------------------------------------
# Prior finding: useful floors sit at 0.93-0.995, and reaching below ~0.9 enters
# the placeholder/guess regime (median boundary confidence is 0.0; only 17.6% of
# pre-commit boundaries exceed 0.9). We therefore space the tiers TIGHTLY near
# the top and do not go below 0.90.
TAU1_GRID = [0.9999, 0.999, 0.9975, 0.995, 0.9925]
TAU2_GRID = [0.995, 0.99, 0.98, 0.97, 0.95, 0.93]
TAU3_GRID = [0.99, 0.98, 0.97, 0.95, 0.93]
TAU4_GRID = [0.97, 0.95, 0.93, 0.90]
# NOTE on fairness of the k comparison: tau2 reaches down to 0.93 so that k=2
# is given the same floor range as the deeper tiers. Without this, "k=3 beats
# k=2" could be an artefact of k=2 simply not being allowed to use the low
# floors that k=3's third tier can.

# Dense DEER threshold curve for the exchange-rate comparison. A sparse curve
# would make linear interpolation OVERSTATE DEER's cost in the convex region and
# flatter the tiered rule; every "beats DEER" claim is made against this curve.
DEER_CURVE = sorted(set(
    [round(0.30 + 0.02 * i, 4) for i in range(0, 35)]          # 0.30 .. 0.98
    + [0.96, 0.965, 0.97, 0.9725, 0.975, 0.9775, 0.98, 0.9825, 0.985,
       0.98625, 0.9875, 0.98875, 0.99, 0.99125, 0.9925, 0.99375, 0.995,
       0.99625, 0.9975, 0.99875, 0.999, 0.9995, 0.9999, 0.99999, 0.999999]))

# The previous experiment's headline 2-tier results, for the k=2 vs k=3/4
# comparison (from figures/gen/consensus_deer_disjunctive.json).
PREV_DISJUNCTIVE_JSON = HERE / "figures" / "gen" / "consensus_deer_disjunctive.json"


# --------------------------------------------------------------------------
# the k-tier stop rule
# --------------------------------------------------------------------------
def tiered_decision(
    trials: Sequence[Mapping[str, Any]],
    *,
    tiers: Sequence[tuple[int, float]],
    max_attempts: int = 30,
    last_only: bool = False,
) -> dict[str, Any] | None:
    """First boundary where ANY tier fires. Records which tier fired.

    `tiers` is a sequence of (run_length, threshold) pairs, conventionally
    sorted by increasing run_length with strictly decreasing threshold. Tier j
    fires at boundary i when the last `run_length` boundaries (in trial order,
    consecutive candidate rows) are all non-empty, mutually equal under the
    robust grader, and all exceed `threshold` (or, with last_only=True, only
    boundary i must exceed it).

    Guards mirror DS.direct_submit_decision exactly (candidate_id cap, non-empty
    trial answer at the committing boundary, strict `>` comparisons) so a single
    tier of run length 1 is bit-identical to plain DEER at its threshold.

    Tiers are evaluated in list order at each boundary; the first one that fires
    is reported. Because all tiers are checked at every boundary, the rule stops
    at the EARLIEST boundary any tier fires on, regardless of tier order.
    """
    hist: list[dict[str, Any]] = []
    for row in trials:
        candidate_id = int(row.get("candidate_id", -1))
        if candidate_id > max_attempts:
            break
        answer = str(row.get("trial_answer", "")).strip()
        confidence = float(row.get("confidence", 0.0))
        hist.append({"candidate_id": candidate_id, "answer": answer,
                     "confidence": confidence,
                     "token_position": int(row.get("token_position", 0))})
        if not answer:
            continue
        hit = None
        for tier_idx, (run_len, tau) in enumerate(tiers):
            if confidence <= tau:
                continue                       # committing boundary must clear
            if run_len <= 1:
                hit = tier_idx
                break
            if len(hist) < run_len:
                continue
            win = hist[-run_len:]
            answers = [r["answer"] for r in win]
            if not all(answers):
                continue
            if not last_only and not all(r["confidence"] > tau for r in win):
                continue
            if all(answers_agree(answers[0], a) for a in answers[1:]):
                hit = tier_idx
                break
        if hit is not None:
            return {"candidate_id": candidate_id,
                    "token_position": hist[-1]["token_position"],
                    "confidence": confidence,
                    "trial_answer": answer,
                    "tier": hit}
    return None


def replay_problem(record, main, baseline, *, tiers, budget, last_only=False):
    """Token accounting identical to DS.replay_problem; only the decision differs."""
    trials = list(record.get("trials", []))
    baseline_correct = baseline["baseline_correct"]
    baseline_tokens = baseline["baseline_tokens"]
    baseline_complete = baseline["baseline_complete"]

    decision = tiered_decision(trials, tiers=tiers, last_only=last_only)
    if decision is None:
        probe_decode = sum(int(t.get("trial_out_tokens", 0)) for t in trials)
        return {
            "correct": baseline_correct,
            "baseline_correct": baseline_correct,
            "main_decode_tokens": baseline_tokens,
            "probe_decode_tokens": probe_decode,
            "probe_prompt_tokens": sum(int(t.get("trial_prompt_tokens", 0)) for t in trials),
            "total_decode_tokens": baseline_tokens + probe_decode,
            "baseline_decode_tokens": baseline_tokens,
            "stopped": False, "tier": None, "capped": not baseline_complete,
        }
    committed_id = int(decision["candidate_id"])
    stop = min(int(decision["token_position"]), budget)
    correct = eq(decision["trial_answer"], main["target"])
    charged = [t for t in trials if int(t.get("candidate_id", 0)) <= committed_id]
    final_answer = main.get("final_answer")
    if final_answer is None or not str(final_answer).strip():
        agrees_with_final = None
    else:
        agrees_with_final = answers_agree(decision["trial_answer"],
                                          str(final_answer).strip())
    return {
        "correct": correct,
        "baseline_correct": baseline_correct,
        "main_decode_tokens": stop,
        "probe_decode_tokens": sum(int(t.get("trial_out_tokens", 0)) for t in charged),
        "probe_prompt_tokens": sum(int(t.get("trial_prompt_tokens", 0)) for t in charged),
        "total_decode_tokens": stop + sum(int(t.get("trial_out_tokens", 0)) for t in charged),
        "baseline_decode_tokens": baseline_tokens,
        "stopped": True, "tier": decision["tier"],
        "agrees_with_final": agrees_with_final,
        "committed_candidate_id": committed_id,
        "capped": not baseline_complete,
    }


def tier_breakdown(envs, *, tiers, last_only=False):
    """Pooled-over-dev counts split by which tier fired.

    Per tier: n stops, correct/wrong, harm (baseline right -> stop wrong) and
    rescue (baseline wrong -> stop right). Also, for tiers >= 2, how the stop
    compares with plain DEER at tau_1 on the same problem.
    """
    k = len(tiers)
    out = {str(i): {"run_length": tiers[i][0], "tau": tiers[i][1],
                    "n": 0, "correct": 0, "wrong": 0, "harm": 0, "rescue": 0,
                    "agrees_with_final": 0, "disagrees_with_final": 0,
                    "final_unavailable": 0,
                    "replaced_deer_stop": 0, "replaced_no_deer_stop": 0,
                    "deer_would_be_correct": 0, "deer_would_be_wrong": 0}
           for i in range(k)}
    out["none"] = {"n": 0}
    tau1 = tiers[0][1]
    for env in envs:
        for pid in env["pids"]:
            rec = env["records"][pid]
            main = env["main_index"][pid]
            v = replay_problem(rec, main, env["baseline_index"][pid],
                               tiers=tiers, budget=env["budget"],
                               last_only=last_only)
            if not v["stopped"]:
                out["none"]["n"] += 1
                continue
            d = out[str(v["tier"])]
            d["n"] += 1
            d["correct" if v["correct"] else "wrong"] += 1
            if v["baseline_correct"] and not v["correct"]:
                d["harm"] += 1
            elif not v["baseline_correct"] and v["correct"]:
                d["rescue"] += 1
            af = v["agrees_with_final"]
            if af is None:
                d["final_unavailable"] += 1
            elif af:
                d["agrees_with_final"] += 1
            else:
                d["disagrees_with_final"] += 1
            if v["tier"] == 0:
                continue
            dv = DS.replay_problem(rec, main, env["baseline_index"][pid],
                                   tau1, env["budget"])
            if dv["stopped"]:
                d["replaced_deer_stop"] += 1
                d["deer_would_be_correct" if dv["correct"]
                  else "deer_would_be_wrong"] += 1
            else:
                d["replaced_no_deer_stop"] += 1
    return out


# --------------------------------------------------------------------------
def deer_macro(envs, thr):
    m = macro(envs, lambda env, pid: DS.replay_problem(
        env["records"][pid], env["main_index"][pid],
        env["baseline_index"][pid], thr, env["budget"]))
    m.pop("per_env")
    return m


def tiered_macro(envs, tiers, *, last_only=False, keep_per_env=False):
    m = macro(envs, lambda env, pid: replay_problem(
        env["records"][pid], env["main_index"][pid], env["baseline_index"][pid],
        tiers=tiers, budget=env["budget"], last_only=last_only))
    if not keep_per_env:
        m.pop("per_env")
    return m


def main() -> None:
    print("Loading the 18 dev environments from the DEER confidence bank ...")
    envs = CB.load_dev_environments()
    n_dev = sum(len(e["pids"]) for e in envs)
    print(f"  {len(envs)} environments, {n_dev} dev problems")
    if len(envs) != 18:
        raise SystemExit(f"expected 18 dev environments, got {len(envs)}")

    # ---- STEP 0: reproduce the committed DEER bank --------------------------
    print("\nSTEP 0 -- verifying DEER reproduces the committed bank")
    committed = CB.committed_deer_macro()
    all_taus = sorted(set(TAU1_GRID) | set(TAU2_GRID) | set(TAU3_GRID)
                      | set(TAU4_GRID) | set(DEER_CURVE))
    deer = {}
    checks = []
    for thr in all_taus:
        m = deer_macro(envs, thr)
        deer[thr] = m
        c = committed.get(thr)
        if c is None:
            continue
        ok = (abs(m["drop_pp"] - c["drop_pp"]) < 1e-6
              and abs(m["saving_pct"] - c["saving_pct"]) < 1e-6
              and abs(m["stop_rate"] - c["stop_rate"]) < 1e-9)
        checks.append({"threshold": thr, "matches_committed": ok,
                       "local": {k: m[k] for k in ("drop_pp", "saving_pct", "stop_rate")},
                       "committed": c})
        print(f"  DEER tau={thr:<8g} local {m['drop_pp']:7.3f}pp / {m['saving_pct']:6.2f}%"
              f"   committed {c['drop_pp']:7.3f}pp / {c['saving_pct']:6.2f}%"
              f"   {'OK' if ok else 'MISMATCH'}")
    bad = [c for c in checks if not c["matches_committed"]]
    if bad:
        raise SystemExit(f"ABORT: DEER does not reproduce the committed bank: {bad}")
    for thr, (dr, sv) in CB.DEER_EXPECTED.items():
        m = deer[thr]
        if not (abs(m["drop_pp"] - dr) < 0.005 and abs(m["saving_pct"] - sv) < 0.02):
            raise SystemExit(f"ABORT: tau={thr} expected {dr}pp/{sv}%, "
                             f"got {m['drop_pp']}/{m['saving_pct']}")
    print(f"  reproduces exactly ({len(checks)} thresholds checked); "
          f"handoff reference values confirmed.")

    # ---- STEP 1: sanity checks ---------------------------------------------
    print("\nSTEP 1 -- sanity checks")
    sanity = []

    def _cmp(label, m, d):
        ok = (abs(m["drop_pp"] - d["drop_pp"]) < 1e-9
              and abs(m["saving_pct"] - d["saving_pct"]) < 1e-9
              and m["harm"] == d["harm"] and m["rescue"] == d["rescue"]
              and m["n_stopped"] == d["n_stopped"])
        sanity.append({"check": label, "passed": bool(ok),
                       "rule": {k: m[k] for k in ("drop_pp", "saving_pct", "n_stopped")},
                       "reference": {k: d[k] for k in ("drop_pp", "saving_pct", "n_stopped")}})
        print(f"  {label:<56} {'PASS' if ok else 'FAIL'}  "
              f"{m['drop_pp']:.4f}pp/{m['saving_pct']:.3f}% vs "
              f"{d['drop_pp']:.4f}pp/{d['saving_pct']:.3f}%")
        if not ok:
            raise SystemExit(f"ABORT: sanity check failed: {label}")

    # (a) k=1 == plain DEER
    for thr in TAU1_GRID + [0.99, 0.97]:
        _cmp(f"k=1 tiers=[(1,{thr:g})] == DEER({thr:g})",
             tiered_macro(envs, [(1, thr)]), deer[thr])

    # (b) all tau equal == plain DEER at that tau (any k)
    for thr in [0.995, 0.99, 0.97]:
        for k in (2, 3, 4):
            tiers = [(j + 1, thr) for j in range(k)]
            _cmp(f"k={k} all tau={thr:g} == DEER({thr:g})",
                 tiered_macro(envs, tiers), deer[thr])

    # (c) k=2 reproduces the previous disjunctive experiment (variant_all_lo)
    prev_all_lo = {}
    prev_json = None
    if PREV_DISJUNCTIVE_JSON.exists():
        prev_json = json.loads(PREV_DISJUNCTIVE_JSON.read_text())
        for r in prev_json.get("variant_all_lo", []):
            prev_all_lo[(r["tau_hi"], r["tau_lo"], r["W"])] = r
    n_prev_checked = 0
    for (hi, lo, w), r in sorted(prev_all_lo.items()):
        if w != 2:
            continue
        m = tiered_macro(envs, [(1, hi), (2, lo)])
        ok = (abs(m["drop_pp"] - r["drop_pp"]) < 1e-9
              and abs(m["saving_pct"] - r["saving_pct"]) < 1e-9)
        sanity.append({"check": f"k=2 ({hi:g},{lo:g}) == prev disjunctive variant_all_lo",
                       "passed": bool(ok),
                       "rule": {"drop_pp": m["drop_pp"], "saving_pct": m["saving_pct"]},
                       "reference": {"drop_pp": r["drop_pp"], "saving_pct": r["saving_pct"]}})
        n_prev_checked += 1
        if not ok:
            raise SystemExit(
                f"ABORT: k=2 ({hi},{lo},W=2) does not reproduce the previous "
                f"disjunctive variant_all_lo: {m['drop_pp']}/{m['saving_pct']} "
                f"vs {r['drop_pp']}/{r['saving_pct']}")
    print(f"  k=2 reproduces previous disjunctive variant_all_lo on "
          f"{n_prev_checked}/{n_prev_checked} shared (tau_hi,tau_lo,W=2) points  PASS")

    # ---- STEP 2: the sweep --------------------------------------------------
    # Every configuration is a strictly decreasing tuple of thresholds. Tier j
    # has run length j.
    def enumerate_configs(k):
        grids = [TAU1_GRID, TAU2_GRID, TAU3_GRID, TAU4_GRID][:k]
        for combo in itertools.product(*grids):
            if all(a > b for a, b in zip(combo, combo[1:])):
                yield tuple((j + 1, t) for j, t in enumerate(combo))

    configs = {k: list(enumerate_configs(k)) for k in (2, 3, 4)}
    print(f"\nSTEP 2 -- tiered sweep: "
          + ", ".join(f"k={k}: {len(v)} configs" for k, v in configs.items())
          + f"  (total {sum(len(v) for v in configs.values())})")

    # IMPORTANT: run the full grid under BOTH tier semantics.
    #   strict    -- every boundary in the run must clear tau_j (this is the
    #                previous experiment's `variant_all_lo`)
    #   last_only -- only the committing boundary must clear tau_j (this is the
    #                previous experiment's DEFAULT, and what its headline table
    #                reported)
    # Comparing k=2 here against the previous headline requires matched
    # semantics, so both are swept and reported side by side.
    SEMANTICS = ("strict", "last_only")
    rows_by_sem: dict[str, list[dict]] = {s: [] for s in SEMANTICS}
    results: dict[tuple[str, tuple], dict] = {}
    for sem in SEMANTICS:
        lo = (sem == "last_only")
        print(f"\n  ===== semantics = {sem} =====")
        for k in (2, 3, 4):
            print(f"\n  --- k={k} ---")
            print(f"  {'taus':<34} | {'drop':>7} {'saving':>7} {'stop':>6} | "
                  f"{'d_drop':>7} {'d_sav':>7} | {'harm':>4} {'resc':>4} "
                  f"{'ratio':>6} | gates")
            for tiers in configs[k]:
                m = tiered_macro(envs, tiers, last_only=lo)
                tau1 = tiers[0][1]
                d = deer[tau1]
                d_drop = m["drop_pp"] - d["drop_pp"]
                d_sav = m["saving_pct"] - d["saving_pct"]
                if d_sav < -1e-9:
                    raise SystemExit(
                        f"ABORT: saving regressed vs DEER({tau1}) for tiers={tiers} "
                        f"({sem}): d_saving={d_sav}")
                row = {
                    "semantics": sem, "k": k, "tiers": [list(t) for t in tiers],
                    "taus": [t[1] for t in tiers], **m,
                    "deer_ref": {k2: d[k2] for k2 in ("drop_pp", "saving_pct",
                                                      "stop_rate", "harm", "rescue",
                                                      "n_stopped")},
                    "d_drop_pp": d_drop, "d_saving_pct": d_sav,
                    "pareto_dominates_deer_same_tau1":
                        bool(d_drop <= 1e-9 and d_sav > 1e-9),
                    "gates_passed": CB.gates_passed(m["drop_pp"], m["saving_pct"]),
                }
                rows_by_sem[sem].append(row)
                results[(sem, tuple(t[1] for t in tiers))] = row
                ratio = "inf" if not m["ratio"] else f"{m['ratio']:.2f}"
                print(f"  {str([f'{t[1]:g}' for t in tiers]):<34} | {m['drop_pp']:7.3f} "
                      f"{m['saving_pct']:7.3f} {m['stop_rate']:6.3f} | {d_drop:+7.3f} "
                      f"{d_sav:+7.3f} | {m['harm']:>4} {m['rescue']:>4} {ratio:>6} | "
                      f"{','.join(row['gates_passed']) or '-'}", flush=True)
    rows = rows_by_sem["strict"] + rows_by_sem["last_only"]

    # ---- STEP 3: monotonicity in k -----------------------------------------
    # Truncating a config to its first j tiers can only remove stop
    # opportunities, so saving must be non-decreasing as tiers are added, and
    # every prefix of a config must appear in `results` (it does, because the
    # grids are nested by construction: a valid k=4 tuple's k=3 and k=2 prefixes
    # are valid too iff their taus lie in the earlier grids -- we recompute any
    # prefix that is missing rather than assume).
    print("\nSTEP 3 -- monotonicity: saving must be non-decreasing in k")
    mono = []
    prefix_cache: dict[tuple, dict] = {}

    def get_prefix(sem, taus):
        key = (sem, tuple(taus))
        if key in results:
            return results[key]
        if key in prefix_cache:
            return prefix_cache[key]
        tiers = tuple((j + 1, t) for j, t in enumerate(taus))
        m = tiered_macro(envs, tiers, last_only=(sem == "last_only"))
        prefix_cache[key] = m
        return m

    n_mono_checks = 0
    for row in rows:
        sem, taus = row["semantics"], row["taus"]
        chain = []
        for j in range(1, len(taus) + 1):
            chain.append(deer[taus[0]] if j == 1 else get_prefix(sem, taus[:j]))
        for a, b in zip(chain, chain[1:]):
            n_mono_checks += 1
            if b["saving_pct"] < a["saving_pct"] - 1e-9:
                raise SystemExit(
                    f"ABORT: saving regressed when adding a tier ({sem}) for {taus}: "
                    f"{a['saving_pct']} -> {b['saving_pct']}")
        mono.append({"semantics": sem, "taus": taus,
                     "saving_chain": [c["saving_pct"] for c in chain],
                     "drop_chain": [c["drop_pp"] for c in chain]})
    print(f"  {n_mono_checks} prefix comparisons across both semantics, "
          f"0 violations  PASS")

    # ---- STEP 4: per-tier breakdown for the gate-relevant configs ----------
    # Expensive (replays DEER per stopped problem), so restricted to configs
    # under the loosest drop cap.
    print("\nSTEP 4 -- per-tier breakdown (configs with drop <= 3.5pp)")
    n_bd = 0
    for row in rows:
        if row["drop_pp"] > GATES["token_efficient"]["max_drop_pp"]:
            continue
        row["tier_breakdown"] = tier_breakdown(
            envs, tiers=[tuple(t) for t in row["tiers"]],
            last_only=(row["semantics"] == "last_only"))
        n_bd += 1
    print(f"  computed for {n_bd} configs")

    # ---- STEP 5: decisive comparison 1 -- Pareto vs DEER at same tau_1 ------
    print("\nSTEP 5 -- Q1: does any config Pareto-dominate plain DEER at the same tau_1?")
    winners = [r for r in rows if r["pareto_dominates_deer_same_tau1"]]
    print(f"  {len(winners)} / {len(rows)} configs Pareto-dominate DEER at their own "
          f"tau_1 (saving strictly up, drop no worse).")
    for sem in SEMANTICS:
        w = [r for r in winners if r["semantics"] == sem]
        print(f"  [{sem}] {len(w)} / {len(rows_by_sem[sem])}")
        for r in sorted(w, key=lambda r: -r["d_saving_pct"])[:12]:
            print(f"    k={r['k']} taus={[f'{t:g}' for t in r['taus']]}: "
                  f"{r['d_drop_pp']:+.3f}pp / {r['d_saving_pct']:+.3f}% "
                  f"(abs {r['drop_pp']:.3f}pp / {r['saving_pct']:.2f}%)")

    # ---- STEP 6: decisive comparison 2 -- gate frontier vs dense DEER -------
    print("\nSTEP 6 -- Q2: best saving under each gate's drop cap")
    # The previous experiment's headline used its DEFAULT decision rule, which
    # is our `last_only` semantics. Take its best-under-cap over its full
    # coarse+fine sweep so the comparison is like-for-like.
    # Two flavours of the previous best, because that experiment's "2-branch"
    # family also allowed a SKIPPED run length (W in {2,3,4,5}) on the second
    # branch, whereas our tier j is pinned to run length j:
    #   prev_best      -- its full family (any W), the headline table
    #   prev_best_w2   -- its W=2 subset, which is literally our k=2
    prev_best, prev_best_w2 = {}, {}
    if prev_json is not None:
        prev_pts = prev_json.get("sweep", []) + prev_json.get("sweep_fine", [])
        for name, g in GATES.items():
            cand = [p for p in prev_pts if p["drop_pp"] <= g["max_drop_pp"]]
            prev_best[name] = (max(cand, key=lambda p: p["saving_pct"])
                               if cand else None)
            cand2 = [p for p in cand if p["W"] == 2]
            prev_best_w2[name] = (max(cand2, key=lambda p: p["saving_pct"])
                                  if cand2 else None)

    def _pt(v):
        if v is None:
            return None
        return {"semantics": v["semantics"], "k": v["k"], "taus": v["taus"],
                "drop_pp": v["drop_pp"], "saving_pct": v["saving_pct"],
                "stop_rate": v["stop_rate"], "harm": v["harm"],
                "rescue": v["rescue"], "ratio": v["ratio"],
                "gates_passed": v["gates_passed"]}

    frontier = {}
    for name, g in GATES.items():
        cap = g["max_drop_pp"]
        best_deer = max(((deer[t]["saving_pct"], t) for t in DEER_CURVE
                         if deer[t]["drop_pp"] <= cap), default=(None, None))
        by_sem_k = {}
        for sem in SEMANTICS:
            for k in (2, 3, 4):
                cand = [r for r in rows_by_sem[sem]
                        if r["k"] == k and r["drop_pp"] <= cap]
                by_sem_k[(sem, k)] = (max(cand, key=lambda r: r["saving_pct"])
                                      if cand else None)
        cand_all = [r for r in rows if r["drop_pp"] <= cap]
        best_any = max(cand_all, key=lambda r: r["saving_pct"]) if cand_all else None
        pb = prev_best.get(name)
        pb2 = prev_best_w2.get(name)

        def _prev(p, note):
            return (None if p is None else
                    {"tau_hi": p["tau_hi"], "tau_lo": p["tau_lo"], "W": p["W"],
                     "drop_pp": p["drop_pp"], "saving_pct": p["saving_pct"],
                     "note": note})

        frontier[name] = {
            "max_drop_pp": cap, "min_saving_pct": g["min_saving_pct"],
            "deer_best_saving_pct": best_deer[0], "deer_best_tau": best_deer[1],
            "deer_best_drop_pp": (deer[best_deer[1]]["drop_pp"]
                                  if best_deer[1] is not None else None),
            "best_by_semantics_and_k": {
                f"{sem}_k{k}": _pt(v) for (sem, k), v in by_sem_k.items()},
            "best_any": _pt(best_any),
            "prev_experiment_best_2branch_anyW": _prev(
                pb, "previous script's full 2-branch family (W in 2..5) under its "
                    "DEFAULT rule == our last_only semantics; its headline table"),
            "prev_experiment_best_2branch_W2": _prev(
                pb2, "previous script's W=2 subset -- literally our k=2 under "
                     "last_only semantics"),
            "delta_vs_deer_pp": (None if (best_any is None or best_deer[0] is None)
                                 else best_any["saving_pct"] - best_deer[0]),
            "delta_vs_prev_2branch_anyW_pp": (
                None if (best_any is None or pb is None)
                else best_any["saving_pct"] - pb["saving_pct"]),
            "delta_vs_prev_2branch_W2_pp": (
                None if (best_any is None or pb2 is None)
                else best_any["saving_pct"] - pb2["saving_pct"]),
        }
        f = frontier[name]
        print(f"\n  {name} (drop <= {cap}pp):")
        print(f"    DEER dense curve      : {f['deer_best_saving_pct']:.2f}% "
              f"@ {f['deer_best_drop_pp']:.3f}pp (tau={f['deer_best_tau']})")
        if pb is not None:
            print(f"    prev 2-branch any W   : {pb['saving_pct']:.2f}% "
                  f"@ {pb['drop_pp']:.3f}pp (hi={pb['tau_hi']:g}, lo={pb['tau_lo']:g}, "
                  f"W={pb['W']})")
        if pb2 is not None:
            print(f"    prev 2-branch W=2     : {pb2['saving_pct']:.2f}% "
                  f"@ {pb2['drop_pp']:.3f}pp (hi={pb2['tau_hi']:g}, "
                  f"lo={pb2['tau_lo']:g})")
        for sem in SEMANTICS:
            for k in (2, 3, 4):
                v = by_sem_k[(sem, k)]
                lab = f"{sem} k={k}"
                if v is None:
                    print(f"    {lab:<22}: none under cap")
                else:
                    print(f"    {lab:<22}: {v['saving_pct']:.2f}% @ {v['drop_pp']:.3f}pp "
                          f"taus={[f'{t:g}' for t in v['taus']]}")
        if best_any is not None and best_deer[0] is not None:
            print(f"    -> best any vs DEER: {f['delta_vs_deer_pp']:+.2f}pp saving"
                  + ("" if pb is None else
                     f"; vs prev 2-branch anyW: "
                     f"{f['delta_vs_prev_2branch_anyW_pp']:+.2f}pp")
                  + ("" if pb2 is None else
                     f"; vs prev 2-branch W=2: "
                     f"{f['delta_vs_prev_2branch_W2_pp']:+.2f}pp"))

    # ---- STEP 7: is each config dominated by SOME DEER threshold? ----------
    print("\nSTEP 7 -- frontier extension: configs not weakly dominated by any DEER tau")
    deer_pts = sorted((deer[t]["saving_pct"], deer[t]["drop_pp"], t) for t in DEER_CURVE)
    for r in rows:
        dominators = [t for (s, dr, t) in deer_pts
                      if s >= r["saving_pct"] - 1e-9 and dr <= r["drop_pp"] + 1e-9]
        r["dominated_by_deer_thresholds"] = dominators
        r["extends_deer_frontier"] = not dominators
    extenders = [r for r in rows if r["extends_deer_frontier"]]
    print(f"  {len(extenders)} / {len(rows)} configs are NOT dominated by any DEER "
          f"threshold on the dense {len(DEER_CURVE)}-point curve.")
    for sem in SEMANTICS:
        for k in (2, 3, 4):
            n = sum(1 for r in extenders if r["k"] == k and r["semantics"] == sem)
            tot = sum(1 for r in rows if r["k"] == k and r["semantics"] == sem)
            print(f"    {sem} k={k}: {n}/{tot}")

    # ---- STEP 8: Q3 -- does k=3/4 beat k=2? --------------------------------
    print("\nSTEP 8 -- Q3: does k=3 or k=4 beat k=2?")
    print("  (a) best-under-cap by k, within each semantics")
    k_cmp = {}
    for name in GATES:
        f = frontier[name]
        b = f["best_by_semantics_and_k"]
        k_cmp[name] = {}
        for sem in SEMANTICS:
            g2, g3, g4 = (b[f"{sem}_k2"], b[f"{sem}_k3"], b[f"{sem}_k4"])
            s2 = g2["saving_pct"] if g2 else None
            s3 = g3["saving_pct"] if g3 else None
            s4 = g4["saving_pct"] if g4 else None
            k_cmp[name][sem] = {
                "k2_saving_pct": s2, "k3_saving_pct": s3, "k4_saving_pct": s4,
                "k3_minus_k2": (None if None in (s2, s3) else s3 - s2),
                "k4_minus_k2": (None if None in (s2, s4) else s4 - s2),
                "k4_minus_k3": (None if None in (s3, s4) else s4 - s3),
            }

            def _fmt(v):
                return "n/a" if v is None else f"{v:+.2f}pp"

            c = k_cmp[name][sem]
            print(f"    {name:<16} {sem:<10} k2={'n/a' if s2 is None else f'{s2:.2f}%':>8}  "
                  f"k3-k2 {_fmt(c['k3_minus_k2']):>8}  "
                  f"k4-k2 {_fmt(c['k4_minus_k2']):>8}  "
                  f"k4-k3 {_fmt(c['k4_minus_k3']):>8}")

    # (b) PAIRED comparison: for every k=3 (k=4) config, what did the extra tier
    # buy over its own truncated prefix? This removes the max-over-grid
    # selection effect present in (a).
    import statistics as _st
    paired = []
    for r in rows:
        if r["k"] < 3:
            continue
        sem = r["semantics"]
        pref = get_prefix(sem, r["taus"][:-1])
        paired.append({"semantics": sem, "k": r["k"], "taus": r["taus"],
                       "prev_drop_pp": pref["drop_pp"],
                       "prev_saving_pct": pref["saving_pct"],
                       "drop_pp": r["drop_pp"], "saving_pct": r["saving_pct"],
                       "d_drop_pp": r["drop_pp"] - pref["drop_pp"],
                       "d_saving_pct": r["saving_pct"] - pref["saving_pct"]})
    print("\n  (b) paired: adding the k-th tier to its own (k-1)-tier prefix")
    for sem in SEMANTICS:
        for k in (3, 4):
            grp = [p for p in paired if p["semantics"] == sem and p["k"] == k]
            if not grp:
                continue
            gains = sorted(p["d_saving_pct"] for p in grp)
            drops = sorted(p["d_drop_pp"] for p in grp)
            nz = [p for p in grp if p["d_saving_pct"] > 1e-9]
            free = [p for p in nz if p["d_drop_pp"] <= 1e-9]
            print(f"    {sem:<10} k={k-1}->{k} ({len(grp)} pairs): "
                  f"saving median {_st.median(gains):+.3f}pp mean {_st.fmean(gains):+.3f}pp "
                  f"max {gains[-1]:+.3f}pp | drop median {_st.median(drops):+.3f}pp | "
                  f"{len(nz)} change anything, {len(free)} of those at no extra drop")

    # (c) the honest question: does the best k>=3 config beat the best k=2
    # config on the FULL achievable frontier (not just at three drop caps)?
    print("\n  (c) frontier envelope: at each k=2 point's drop, is there a k>=3 "
          "config with strictly more saving at no more drop?")
    envelope = {}
    for sem in SEMANTICS:
        k2 = [r for r in rows_by_sem[sem] if r["k"] == 2]
        khi = [r for r in rows_by_sem[sem] if r["k"] >= 3]
        beaten = 0
        details = []
        for r in k2:
            better = [q for q in khi
                      if q["drop_pp"] <= r["drop_pp"] + 1e-9
                      and q["saving_pct"] > r["saving_pct"] + 1e-9]
            if better:
                beaten += 1
                best = max(better, key=lambda q: q["saving_pct"])
                details.append({"k2_taus": r["taus"], "k2_drop_pp": r["drop_pp"],
                                "k2_saving_pct": r["saving_pct"],
                                "best_k": best["k"], "best_taus": best["taus"],
                                "best_drop_pp": best["drop_pp"],
                                "best_saving_pct": best["saving_pct"],
                                "d_saving_pct": best["saving_pct"] - r["saving_pct"]})
        # and the reverse: k=2 points not dominated by any k>=3 config
        envelope[sem] = {"n_k2": len(k2), "n_k2_beaten_by_k_ge_3": beaten,
                         "details": details}
        gains = [d["d_saving_pct"] for d in details]
        print(f"    {sem:<10}: {beaten}/{len(k2)} k=2 points are strictly improved "
              f"by some k>=3 config"
              + (f"; median gain {_st.median(gains):+.3f}pp, max {max(gains):+.3f}pp"
                 if gains else ""))

    # ---- STEP 9: per-tier detail for the headline configs ------------------
    print("\nSTEP 9 -- per-tier stop counts for the per-gate winners")
    headline = []
    seen = set()
    for name in GATES:
        f = frontier[name]
        cands = [f["best_any"]] + [f["best_by_semantics_and_k"][f"{s}_k{k}"]
                                   for s in SEMANTICS for k in (2, 3, 4)]
        for c in cands:
            if c is None:
                continue
            key = (c["semantics"], tuple(c["taus"]))
            if key in seen:
                continue
            seen.add(key)
            row = results.get((c["semantics"], tuple(c["taus"])))
            if row is None or "tier_breakdown" not in row:
                continue
            headline.append({"gate_context": name, **_pt(row),
                             "tier_breakdown": row["tier_breakdown"]})
    for h in headline:
        bd = h["tier_breakdown"]
        parts = []
        for i in range(h["k"]):
            d = bd[str(i)]
            parts.append(f"T{i+1}(run{d['run_length']},tau{d['tau']:g}): "
                         f"n={d['n']} ok={d['correct']} bad={d['wrong']} "
                         f"harm={d['harm']} resc={d['rescue']}")
        ratio_txt = "inf" if not h["ratio"] else f"{h['ratio']:.2f}"
        print(f"  [{h['semantics']}] k={h['k']} taus={[f'{t:g}' for t in h['taus']]} "
              f"{h['drop_pp']:.3f}pp/{h['saving_pct']:.2f}%  "
              f"pooled harm:rescue {ratio_txt}:1")
        for p in parts:
            print(f"      {p}")

    # ---- STEP 10: pooled marginal stop quality by tier depth ---------------
    # The mechanism question: as we go deeper (longer run, lower floor), does
    # the marginal stop get better or worse? Pooled over every config with a
    # breakdown, per tier INDEX. Also split by the tier's own floor, so the
    # depth effect can be separated from the "deeper tiers have lower floors by
    # construction" confound.
    print("\nSTEP 10 -- pooled marginal stop quality by tier depth")
    from collections import defaultdict as _dd
    by_depth = _dd(lambda: {"n_configs": 0, "n": 0, "correct": 0, "wrong": 0,
                            "harm": 0, "rescue": 0})
    by_depth_tau = _dd(lambda: {"n_configs": 0, "n": 0, "correct": 0, "wrong": 0,
                                "harm": 0, "rescue": 0})
    for r in rows:
        bd = r.get("tier_breakdown")
        if not bd:
            continue
        for i in range(r["k"]):
            t = bd[str(i)]
            for tgt in (by_depth[i + 1], by_depth_tau[(i + 1, t["tau"])]):
                tgt["n_configs"] += 1
                tgt["n"] += t["n"]
                tgt["correct"] += t["correct"]
                tgt["wrong"] += t["wrong"]
                tgt["harm"] += t["harm"]
                tgt["rescue"] += t["rescue"]

    def _finish(d):
        d["accuracy"] = d["correct"] / d["n"] if d["n"] else None
        d["harm_rescue"] = d["harm"] / d["rescue"] if d["rescue"] else None
        return d

    depth_stats = {str(k): _finish(dict(v)) for k, v in sorted(by_depth.items())}
    print(f"  {'tier':>5} {'cfgs':>5} {'stops':>7} {'ok':>7} {'bad':>6} "
          f"{'acc':>7} {'harm':>6} {'resc':>5} {'h:r':>7}")
    for k, v in depth_stats.items():
        hr = "inf" if v["harm_rescue"] is None else f"{v['harm_rescue']:.2f}"
        print(f"  {k:>5} {v['n_configs']:>5} {v['n']:>7} {v['correct']:>7} "
              f"{v['wrong']:>6} {v['accuracy']:>7.3f} {v['harm']:>6} "
              f"{v['rescue']:>5} {hr:>7}")

    depth_tau_stats = {f"tier{d}_tau{t:g}": _finish(dict(v))
                       for (d, t), v in sorted(by_depth_tau.items())}
    print("\n  same, split by the tier's own floor (separates depth from floor):")
    print(f"  {'tier':>5} {'tau':>8} {'stops':>7} {'acc':>7} {'h:r':>7}")
    for key, v in depth_tau_stats.items():
        if v["n"] < 200:
            continue
        d, t = key.replace("tier", "").split("_tau")
        hr = "inf" if v["harm_rescue"] is None else f"{v['harm_rescue']:.2f}"
        print(f"  {d:>5} {t:>8} {v['n']:>7} {v['accuracy']:>7.3f} {hr:>7}")

    payload = {
        "meta": {
            "split": "dev", "n_env": len(envs), "n_dev_problems": n_dev,
            "rule": "stop at the first boundary where ANY tier j fires: the last "
                    "run_length_j trial answers are all non-empty, mutually equal, "
                    "and all exceed tau_j (tier 1 has run length 1 == plain DEER)",
            "tier_semantics": {
                "strict": "every boundary in the run must clear tau_j (== the "
                          "previous disjunctive script's `variant_all_lo`)",
                "last_only": "only the committing boundary must clear tau_j (== the "
                             "previous disjunctive script's DEFAULT rule, which its "
                             "headline table reported)",
                "note": "the full grid is swept under BOTH; every k=2 vs k>=3 and "
                        "vs-previous-experiment comparison uses matched semantics",
            },
            "semantics_swept": list(SEMANTICS),
            "bank": str(CB.BANK.relative_to(CB.FC)),
            "token_view": "all_generated_tokens (main through stop + trial output)",
            "aggregation": "macro over 18 dev environments",
            "gates": GATES,
            "tau1_grid": TAU1_GRID, "tau2_grid": TAU2_GRID,
            "tau3_grid": TAU3_GRID, "tau4_grid": TAU4_GRID,
            "n_configs_by_k": {str(k): len(v) for k, v in configs.items()},
            "deer_curve_grid": DEER_CURVE,
            "caveat": "dev-only, in-sample selection over a large search space; "
                      "exploratory. A single frozen operating point would have to be "
                      "confirmed on the test split before any claim.",
        },
        "deer_baseline_verification": checks,
        "deer_curve": {f"{t:g}": {k: deer[t][k] for k in
                                  ("drop_pp", "saving_pct", "stop_rate", "harm",
                                   "rescue", "ratio", "n_stopped")}
                       for t in DEER_CURVE},
        "sanity_checks": sanity,
        "sweep": rows,
        "monotonicity": {"n_prefix_comparisons": n_mono_checks, "violations": 0,
                         "chains": mono},
        "frontier_comparison_by_gate": frontier,
        "k_comparison_by_gate": k_cmp,
        "paired_added_tier": paired,
        "k2_envelope_vs_higher_k": envelope,
        "headline_configs_with_tier_breakdown": headline,
        "marginal_stop_quality_by_tier_depth": depth_stats,
        "marginal_stop_quality_by_tier_depth_and_tau": depth_tau_stats,
        "verdict": {
            "n_configs": len(rows),
            "n_configs_by_semantics": {s: len(v) for s, v in rows_by_sem.items()},
            "n_pareto_dominating_same_tau1": len(winners),
            "pareto_winners": [{k2: r[k2] for k2 in
                                ("semantics", "k", "taus", "drop_pp", "saving_pct",
                                 "d_drop_pp", "d_saving_pct")} for r in winners],
            "n_extending_deer_frontier": len(extenders),
            "extenders_by_semantics_and_k": {
                f"{s}_k{k}": sum(1 for r in extenders
                                 if r["k"] == k and r["semantics"] == s)
                for s in SEMANTICS for k in (2, 3, 4)},
        },
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, indent=1))
    print("\nwrote", CACHE)


if __name__ == "__main__":
    main()
