#!/usr/bin/env python3
"""DISJUNCTIVE two-threshold DEER+consensus rule (can only ever stop EARLIER).

The earlier CONJUNCTIVE experiment (`compute_consensus_deer_combo.py`) asked
whether "confidence > tau_c AND last-W trials agree" can beat plain DEER. It
cannot, essentially by construction: adding a conjunct can only DELAY a stop, so
the rule trades saving away for accuracy and never Pareto-dominates.

This script asks the mirror-image question with two thresholds:

    STOP at the first boundary i where EITHER
      (A) confidence_i > tau_hi                                [plain DEER branch]
      (B) confidence_i > tau_lo AND the last W trial answers
          (i-W+1 .. i) are all non-empty and mutually equal     [consensus branch]
    with tau_lo < tau_hi.  Commit the trial answer at boundary i.

Because branch (A) alone IS DEER at tau_hi, the disjunction is guaranteed to
stop no later than DEER-at-tau_hi. Net saving can therefore only go UP. The
entire question is accuracy: are the extra, earlier stops contributed by branch
(B) good, bad, or neutral?

Sanity checks asserted in code (they validate the implementation):
  * tau_lo == tau_hi  -> exactly plain DEER at that tau.
  * W == 1            -> branch (B) degenerates to "conf > tau_lo", so the rule
                         is exactly plain DEER at tau_lo.
  * saving(tau_hi, tau_lo, W) >= saving(plain DEER at tau_hi) for every point.

Token accounting, environment loading, macro-averaging and the latex2sympy2
grader repair are all reused verbatim from compute_consensus_deer_combo (which
reproduces the committed DEER bank exactly). We re-verify that reproduction at
the start of the run and abort if it fails.

Everything is macro-averaged over the 18 dev environments; never problem-micro.

PROCESS HYGIENE: run this file directly. It must be the first thing in its
interpreter to touch the shared answer evaluator (see the note in
compute_consensus_deer_combo).

Reads only committed banks.
Writes report/figures/gen/consensus_deer_disjunctive.json.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
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

CACHE = HERE / "figures" / "gen" / "consensus_deer_disjunctive.json"

# ---- the grid -------------------------------------------------------------
TAU_HI_GRID = [0.995, 0.99, 0.97]            # DEER's dev-selected C / B / T
TAU_LO_GRID = [0.5, 0.7, 0.8, 0.9, 0.92, 0.95]
W_GRID = [2, 3]
# DEER threshold curve, for the exchange-rate comparison. The requested grid was
# coarse; a sparse curve makes linear interpolation OVERSTATE DEER's cost in the
# convex 30-56%-saving region, which would flatter the disjunctive rule. We
# therefore sample DEER densely across the whole range plus a fine mesh in the
# gate-relevant tail near 1.0. Every "beats DEER's own curve" claim is made
# against this dense curve, never against the coarse one.
DEER_CURVE = sorted(set(
    [round(0.30 + 0.02 * i, 4) for i in range(0, 35)]          # 0.30 .. 0.98
    + [0.96, 0.965, 0.97, 0.9725, 0.975, 0.9775, 0.98, 0.9825, 0.985,
       0.98625, 0.9875, 0.98875, 0.99, 0.99125, 0.9925, 0.99375, 0.995,
       0.99625, 0.9975, 0.99875, 0.999, 0.9995, 0.9999, 0.99999, 0.999999]))

# STEP 6: a finer sweep in the gate-relevant corner. The coarse tau_lo grid above
# is far below any threshold that could plausibly be safe; the interesting
# region is tau_lo in [0.93, 0.995] with tau_hi pushed up towards 1.0 (where
# branch A almost never fires alone and branch B does the work).
FINE_TAU_HI = [0.9999, 0.999, 0.9975, 0.995, 0.9925, 0.99, 0.985, 0.98, 0.97]
FINE_TAU_LO = [0.93, 0.95, 0.96, 0.97, 0.98, 0.985, 0.99, 0.995]
FINE_W = [2, 3, 4, 5]


# --------------------------------------------------------------------------
# the disjunctive stop rule
# --------------------------------------------------------------------------
def disjunctive_decision(
    trials: Sequence[Mapping[str, Any]],
    *,
    tau_hi: float,
    tau_lo: float,
    window: int,
    max_attempts: int = 30,
) -> dict[str, Any] | None:
    """First boundary satisfying branch (A) or branch (B); records which fired.

    Guards mirror DS.direct_submit_decision exactly (candidate_id cap, non-empty
    trial answer, strict `>` comparisons) so the degenerate cases reduce to plain
    DEER bit-identically.

    Branch (B)'s window is the last `window` boundaries *in trial order*
    (consecutive candidate rows). It requires all of them non-empty and mutually
    equal, and the CURRENT boundary above tau_lo. Earlier boundaries in the
    window are not required to clear tau_lo -- the confidence condition is on the
    boundary at which we actually commit. (A stricter "all clear tau_lo" variant
    is also computed, as `variant_all_lo`, to show the choice is not load-bearing.)
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
        if confidence > tau_hi:
            hit = "A"
        elif confidence > tau_lo and window <= len(hist):
            win = hist[-window:]
            answers = [r["answer"] for r in win]
            if all(answers) and all(answers_agree(answers[0], a) for a in answers[1:]):
                hit = "B"
        if hit is not None:
            return {"candidate_id": candidate_id,
                    "token_position": hist[-1]["token_position"],
                    "confidence": confidence,
                    "trial_answer": answer,
                    "branch": hit}
    return None


def disjunctive_decision_all_lo(
    trials: Sequence[Mapping[str, Any]],
    *,
    tau_hi: float,
    tau_lo: float,
    window: int,
    max_attempts: int = 30,
) -> dict[str, Any] | None:
    """Variant: branch (B) additionally requires EVERY boundary in the window
    to clear tau_lo (not just the committing one)."""
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
        if confidence > tau_hi:
            hit = "A"
        elif confidence > tau_lo and window <= len(hist):
            win = hist[-window:]
            answers = [r["answer"] for r in win]
            if (all(answers) and all(r["confidence"] > tau_lo for r in win)
                    and all(answers_agree(answers[0], a) for a in answers[1:])):
                hit = "B"
        if hit is not None:
            return {"candidate_id": candidate_id,
                    "token_position": hist[-1]["token_position"],
                    "confidence": confidence,
                    "trial_answer": answer,
                    "branch": hit}
    return None


def replay_problem(record, main, baseline, *, tau_hi, tau_lo, window, budget,
                   decide=disjunctive_decision):
    """Token accounting identical to DS.replay_problem; only the decision differs."""
    trials = list(record.get("trials", []))
    baseline_correct = baseline["baseline_correct"]
    baseline_tokens = baseline["baseline_tokens"]
    baseline_complete = baseline["baseline_complete"]

    decision = decide(trials, tau_hi=tau_hi, tau_lo=tau_lo, window=window)
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
            "stopped": False, "branch": None, "capped": not baseline_complete,
        }
    committed_id = int(decision["candidate_id"])
    stop = min(int(decision["token_position"]), budget)
    correct = eq(decision["trial_answer"], main["target"])
    charged = [t for t in trials if int(t.get("candidate_id", 0)) <= committed_id]
    # Does the trajectory's OWN final answer agree with what we committed?
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
        "stopped": True, "branch": decision["branch"],
        "agrees_with_final": agrees_with_final,
        "committed_candidate_id": committed_id,
        "capped": not baseline_complete,
    }


# --------------------------------------------------------------------------
# branch bookkeeping: macro() only reports pooled harm/rescue, so we walk the
# environments a second time to attribute stops to branches.
# --------------------------------------------------------------------------
def branch_breakdown(envs, *, tau_hi, tau_lo, window, decide=disjunctive_decision):
    """Pooled-over-dev counts, split by which branch fired.

    Also compares against DEER-at-tau_hi on the SAME problems so we can say what
    the B-stops replaced (an A-stop that would have come later, or no stop at
    all).
    """
    out = {
        "A": {"n": 0, "correct": 0, "wrong": 0, "harm": 0, "rescue": 0},
        "B": {"n": 0, "correct": 0, "wrong": 0, "harm": 0, "rescue": 0,
              "agrees_with_final": 0, "disagrees_with_final": 0,
              "final_unavailable": 0,
              "replaced_deer_stop": 0, "replaced_no_deer_stop": 0,
              "deer_would_be_correct": 0, "deer_would_be_wrong": 0,
              "tokens_saved_vs_deer": 0, "n_tokens_cmp": 0},
        "none": {"n": 0},
    }
    for env in envs:
        for pid in env["pids"]:
            rec = env["records"][pid]
            main = env["main_index"][pid]
            v = replay_problem(rec, main, env["baseline_index"][pid],
                               tau_hi=tau_hi, tau_lo=tau_lo, window=window,
                               budget=env["budget"], decide=decide)
            if not v["stopped"]:
                out["none"]["n"] += 1
                continue
            br = v["branch"]
            d = out[br]
            d["n"] += 1
            d["correct" if v["correct"] else "wrong"] += 1
            if v["baseline_correct"] and not v["correct"]:
                d["harm"] += 1
            elif not v["baseline_correct"] and v["correct"]:
                d["rescue"] += 1
            if br != "B":
                continue
            af = v["agrees_with_final"]
            if af is None:
                d["final_unavailable"] += 1
            elif af:
                d["agrees_with_final"] += 1
            else:
                d["disagrees_with_final"] += 1
            # what plain DEER at tau_hi would have done on this problem
            dv = DS.replay_problem(rec, main, env["baseline_index"][pid],
                                   tau_hi, env["budget"])
            if dv["stopped"]:
                d["replaced_deer_stop"] += 1
                d["deer_would_be_correct" if dv["correct"]
                  else "deer_would_be_wrong"] += 1
            else:
                d["replaced_no_deer_stop"] += 1
            d["tokens_saved_vs_deer"] += (dv["total_decode_tokens"]
                                          - v["total_decode_tokens"])
            d["n_tokens_cmp"] += 1
    return out


# --------------------------------------------------------------------------
def deer_macro(envs, thr):
    m = macro(envs, lambda env, pid: DS.replay_problem(
        env["records"][pid], env["main_index"][pid],
        env["baseline_index"][pid], thr, env["budget"]))
    m.pop("per_env")
    return m


def interp_deer_cost(curve, target_saving):
    """Linear interpolation along DEER's own threshold curve: what drop does DEER
    pay to reach `target_saving`? curve = sorted list of (saving, drop, tau)."""
    pts = sorted(curve)
    if target_saving <= pts[0][0]:
        return pts[0][1], pts[0][2], "extrapolated_low"
    if target_saving >= pts[-1][0]:
        return pts[-1][1], pts[-1][2], "extrapolated_high"
    for (s0, d0, t0), (s1, d1, t1) in zip(pts, pts[1:]):
        if s0 <= target_saving <= s1:
            if s1 == s0:
                return d0, t0, "exact"
            f = (target_saving - s0) / (s1 - s0)
            return d0 + f * (d1 - d0), (t0, t1), "interpolated"
    return pts[-1][1], pts[-1][2], "fallback"


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
    deer = {}
    checks = []
    for thr in sorted(set(TAU_HI_GRID) | set(TAU_LO_GRID) | set(DEER_CURVE)):
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

    # ---- STEP 1: degenerate sanity checks ----------------------------------
    print("\nSTEP 1 -- degenerate sanity checks")
    sanity = []

    def _cmp(label, m, d):
        ok = (abs(m["drop_pp"] - d["drop_pp"]) < 1e-9
              and abs(m["saving_pct"] - d["saving_pct"]) < 1e-9
              and m["harm"] == d["harm"] and m["rescue"] == d["rescue"]
              and m["n_stopped"] == d["n_stopped"])
        sanity.append({"check": label, "passed": bool(ok),
                       "rule": {k: m[k] for k in ("drop_pp", "saving_pct", "n_stopped")},
                       "deer": {k: d[k] for k in ("drop_pp", "saving_pct", "n_stopped")}})
        print(f"  {label:<44} {'PASS' if ok else 'FAIL'}  "
              f"{m['drop_pp']:.4f}pp/{m['saving_pct']:.3f}% vs "
              f"{d['drop_pp']:.4f}pp/{d['saving_pct']:.3f}%")
        if not ok:
            raise SystemExit(f"ABORT: sanity check failed: {label}")

    for thr in TAU_HI_GRID:
        for w in W_GRID:
            m = macro(envs, lambda env, pid, thr=thr, w=w: replay_problem(
                env["records"][pid], env["main_index"][pid], env["baseline_index"][pid],
                tau_hi=thr, tau_lo=thr, window=w, budget=env["budget"]))
            m.pop("per_env")
            _cmp(f"tau_lo==tau_hi={thr:g}, W={w} == DEER({thr:g})", m, deer[thr])
    for thr_hi in TAU_HI_GRID:
        for thr_lo in [t for t in TAU_LO_GRID if t < thr_hi][:2]:
            m = macro(envs, lambda env, pid, a=thr_hi, b=thr_lo: replay_problem(
                env["records"][pid], env["main_index"][pid], env["baseline_index"][pid],
                tau_hi=a, tau_lo=b, window=1, budget=env["budget"]))
            m.pop("per_env")
            _cmp(f"W=1, tau_hi={thr_hi:g}, tau_lo={thr_lo:g} == DEER({thr_lo:g})",
                 m, deer[thr_lo])

    # ---- STEP 2: the sweep -------------------------------------------------
    print("\nSTEP 2 -- disjunctive sweep (tau_hi x tau_lo x W)")
    print(f"  {'tau_hi':>7} {'tau_lo':>7} {'W':>2} | {'drop':>7} {'saving':>7} "
          f"{'stop':>6} | {'d_drop':>7} {'d_sav':>7} | {'B':>4} {'B_ok':>5} "
          f"{'B_bad':>5} | {'harm':>4} {'resc':>4} gates")
    rows = []
    for tau_hi in TAU_HI_GRID:
        d = deer[tau_hi]
        for tau_lo in TAU_LO_GRID:
            if tau_lo >= tau_hi:
                continue
            for w in W_GRID:
                m = macro(envs, lambda env, pid, a=tau_hi, b=tau_lo, w=w: replay_problem(
                    env["records"][pid], env["main_index"][pid],
                    env["baseline_index"][pid], tau_hi=a, tau_lo=b, window=w,
                    budget=env["budget"]))
                per_env = m.pop("per_env")
                bb = branch_breakdown(envs, tau_hi=tau_hi, tau_lo=tau_lo, window=w)
                d_drop = m["drop_pp"] - d["drop_pp"]
                d_sav = m["saving_pct"] - d["saving_pct"]
                # HARD sanity: the disjunction can only stop earlier.
                if d_sav < -1e-9:
                    raise SystemExit(
                        f"ABORT: saving regressed vs DEER({tau_hi}): "
                        f"tau_lo={tau_lo} W={w} d_saving={d_sav}")
                pareto = (d_drop <= 1e-9 and d_sav > 1e-9)
                rows.append({
                    "tau_hi": tau_hi, "tau_lo": tau_lo, "W": w, **m,
                    "deer_ref": {k: d[k] for k in ("drop_pp", "saving_pct", "stop_rate",
                                                   "harm", "rescue", "n_stopped")},
                    "d_drop_pp": d_drop, "d_saving_pct": d_sav,
                    "pareto_dominates_deer_same_tau_hi": bool(pareto),
                    "exchange_rate_pp_drop_per_pp_saving":
                        (d_drop / d_sav) if d_sav > 1e-9 else None,
                    "branches": bb,
                    "gates_passed": CB.gates_passed(m["drop_pp"], m["saving_pct"]),
                    "per_env": per_env,
                })
                B = bb["B"]
                print(f"  {tau_hi:>7g} {tau_lo:>7g} {w:>2} | {m['drop_pp']:7.3f} "
                      f"{m['saving_pct']:7.3f} {m['stop_rate']:6.3f} | "
                      f"{d_drop:+7.3f} {d_sav:+7.3f} | {B['n']:>4} {B['correct']:>5} "
                      f"{B['wrong']:>5} | {m['harm']:>4} {m['rescue']:>4} "
                      f"{','.join(m and CB.gates_passed(m['drop_pp'], m['saving_pct']) or []) or '-'}",
                      flush=True)

    # ---- STEP 3: exchange-rate comparison against DEER's own curve ----------
    print("\nSTEP 3 -- would simply lowering tau_hi have bought that saving cheaper?")
    curve = sorted((deer[t]["saving_pct"], deer[t]["drop_pp"], t) for t in DEER_CURVE)
    for r in rows:
        base = deer[r["tau_hi"]]
        cost, tau_equiv, how = interp_deer_cost(curve, r["saving_pct"])
        r["deer_curve_equivalent"] = {
            "target_saving_pct": r["saving_pct"],
            "deer_drop_pp_at_same_saving": cost,
            "deer_tau_equivalent": tau_equiv,
            "interpolation": how,
            "disjunctive_drop_pp": r["drop_pp"],
            "disjunctive_minus_deer_curve_pp": r["drop_pp"] - cost,
            "beats_deer_curve": bool(r["drop_pp"] < cost - 1e-9),
        }
    for r in rows:
        e = r["deer_curve_equivalent"]
        print(f"  tau_hi={r['tau_hi']:g} tau_lo={r['tau_lo']:g} W={r['W']}: "
              f"saving {r['saving_pct']:6.2f}% at drop {r['drop_pp']:6.3f}pp; "
              f"DEER alone reaches that saving at drop {e['deer_drop_pp_at_same_saving']:6.3f}pp "
              f"(delta {e['disjunctive_minus_deer_curve_pp']:+6.3f}pp) -> "
              f"{'BEATS' if e['beats_deer_curve'] else 'loses to'} DEER curve")

    # ---- STEP 4: the strict-window variant (robustness) --------------------
    print("\nSTEP 4 -- variant where every boundary in the window must clear tau_lo")
    variant = []
    for tau_hi in TAU_HI_GRID:
        d = deer[tau_hi]
        for tau_lo in TAU_LO_GRID:
            if tau_lo >= tau_hi:
                continue
            for w in W_GRID:
                m = macro(envs, lambda env, pid, a=tau_hi, b=tau_lo, w=w: replay_problem(
                    env["records"][pid], env["main_index"][pid],
                    env["baseline_index"][pid], tau_hi=a, tau_lo=b, window=w,
                    budget=env["budget"], decide=disjunctive_decision_all_lo))
                m.pop("per_env")
                if m["saving_pct"] - d["saving_pct"] < -1e-9:
                    raise SystemExit("ABORT: variant saving regressed vs DEER")
                variant.append({"tau_hi": tau_hi, "tau_lo": tau_lo, "W": w, **m,
                                "d_drop_pp": m["drop_pp"] - d["drop_pp"],
                                "d_saving_pct": m["saving_pct"] - d["saving_pct"]})
                print(f"  {tau_hi:>7g} {tau_lo:>7g} W={w} | drop {m['drop_pp']:7.3f} "
                      f"saving {m['saving_pct']:7.3f} | d {m['drop_pp']-d['drop_pp']:+7.3f}pp "
                      f"{m['saving_pct']-d['saving_pct']:+7.3f}%", flush=True)

    # ---- STEP 5: verdict ---------------------------------------------------
    print("\nSTEP 5 -- Pareto verdict")
    winners = [r for r in rows if r["pareto_dominates_deer_same_tau_hi"]]
    print(f"  {len(winners)} / {len(rows)} points Pareto-dominate plain DEER at "
          f"the same tau_hi (saving strictly up, drop no worse).")
    for r in winners:
        print(f"    tau_hi={r['tau_hi']:g} tau_lo={r['tau_lo']:g} W={r['W']}: "
              f"{r['d_drop_pp']:+.3f}pp / {r['d_saving_pct']:+.3f}%")
    beats_curve = [r for r in rows if r["deer_curve_equivalent"]["beats_deer_curve"]]
    print(f"  {len(beats_curve)} / {len(rows)} points beat DEER's OWN threshold "
          f"curve at equal saving.")
    for r in beats_curve:
        e = r["deer_curve_equivalent"]
        print(f"    tau_hi={r['tau_hi']:g} tau_lo={r['tau_lo']:g} W={r['W']}: "
              f"{r['drop_pp']:.3f}pp vs DEER {e['deer_drop_pp_at_same_saving']:.3f}pp "
              f"at {r['saving_pct']:.2f}% saving")

    # ---- STEP 6: fine sweep in the gate-relevant corner --------------------
    print("\nSTEP 6 -- fine sweep in the gate-relevant corner "
          "(tau_hi near 1.0, tau_lo in [0.93,0.995])")
    fine = []
    for tau_hi in FINE_TAU_HI:
        for tau_lo in FINE_TAU_LO:
            if tau_lo >= tau_hi:
                continue
            for w in FINE_W:
                m = macro(envs, lambda env, pid, a=tau_hi, b=tau_lo, w=w: replay_problem(
                    env["records"][pid], env["main_index"][pid],
                    env["baseline_index"][pid], tau_hi=a, tau_lo=b, window=w,
                    budget=env["budget"]))
                m.pop("per_env")
                bb = branch_breakdown(envs, tau_hi=tau_hi, tau_lo=tau_lo, window=w)
                fine.append({"tau_hi": tau_hi, "tau_lo": tau_lo, "W": w, **m,
                             "branches": bb,
                             "gates_passed": CB.gates_passed(m["drop_pp"], m["saving_pct"])})
                print(f"  hi={tau_hi:<8g} lo={tau_lo:<6g} W={w} drop={m['drop_pp']:7.3f} "
                      f"sav={m['saving_pct']:6.2f} B={bb['B']['n']} Bok={bb['B']['correct']} "
                      f"Bbad={bb['B']['wrong']} gates={fine[-1]['gates_passed'] or '-'}",
                      flush=True)

    # ---- STEP 7: the decisive comparison -----------------------------------
    # For each disjunctive point, is there ANY DEER threshold that weakly
    # dominates it (saving >= and drop <=)? If not, the point is a genuine
    # extension of the achievable frontier, not something DEER could have
    # reached by turning its own dial.
    print("\nSTEP 7 -- is each point dominated by SOME DEER threshold?")
    deer_pts = sorted((deer[t]["saving_pct"], deer[t]["drop_pp"], t) for t in DEER_CURVE)
    all_points = rows + fine
    for r in all_points:
        dominators = [t for (s, dr, t) in deer_pts
                      if s >= r["saving_pct"] - 1e-9 and dr <= r["drop_pp"] + 1e-9]
        r["dominated_by_deer_thresholds"] = dominators
        r["extends_deer_frontier"] = not dominators
    extenders = [r for r in all_points if r["extends_deer_frontier"]]
    print(f"  {len(extenders)} / {len(all_points)} disjunctive points are NOT "
          f"dominated by any DEER threshold on the dense curve.")

    # best achievable saving under each gate's drop cap, DEER vs disjunctive
    frontier_cmp = {}
    for name, g in GATES.items():
        cap = g["max_drop_pp"]
        best_deer = max(((deer[t]["saving_pct"], t) for t in DEER_CURVE
                         if deer[t]["drop_pp"] <= cap), default=(None, None))
        cand = [r for r in all_points if r["drop_pp"] <= cap]
        best_dis = max(cand, key=lambda r: r["saving_pct"]) if cand else None
        frontier_cmp[name] = {
            "max_drop_pp": cap, "min_saving_pct": g["min_saving_pct"],
            "deer_best_saving_pct": best_deer[0], "deer_best_tau": best_deer[1],
            "deer_best_drop_pp": (deer[best_deer[1]]["drop_pp"]
                                  if best_deer[1] is not None else None),
            "disjunctive_best": (None if best_dis is None else
                                 {k: best_dis[k] for k in
                                  ("tau_hi", "tau_lo", "W", "drop_pp", "saving_pct")}),
            "delta_saving_pp": (None if (best_dis is None or best_deer[0] is None)
                                else best_dis["saving_pct"] - best_deer[0]),
        }
        f = frontier_cmp[name]
        print(f"  {name:<16} drop<={cap}pp: DEER best {f['deer_best_saving_pct']:.2f}% "
              f"(tau={f['deer_best_tau']}, drop {f['deer_best_drop_pp']:.3f}pp)"
              + ("" if best_dis is None else
                 f"  |  disjunctive best {best_dis['saving_pct']:.2f}% "
                 f"(hi={best_dis['tau_hi']}, lo={best_dis['tau_lo']}, W={best_dis['W']}, "
                 f"drop {best_dis['drop_pp']:.3f}pp)  DELTA {f['delta_saving_pp']:+.2f}pp"))

    payload = {
        "meta": {
            "split": "dev", "n_env": len(envs), "n_dev_problems": n_dev,
            "rule": "stop at first boundary with conf>tau_hi OR (conf>tau_lo AND "
                    "last W trial answers all non-empty and mutually equal)",
            "bank": str(CB.BANK.relative_to(CB.FC)),
            "token_view": "all_generated_tokens (main through stop + trial output)",
            "aggregation": "macro over 18 dev environments",
            "gates": GATES,
            "tau_hi_grid": TAU_HI_GRID, "tau_lo_grid": TAU_LO_GRID,
            "W_grid": W_GRID, "deer_curve_grid": DEER_CURVE,
            "fine_tau_hi": FINE_TAU_HI, "fine_tau_lo": FINE_TAU_LO,
            "fine_W": FINE_W,
        },
        "deer_baseline_verification": checks,
        "deer_curve": {f"{t:g}": {k: deer[t][k] for k in
                                  ("drop_pp", "saving_pct", "stop_rate", "harm",
                                   "rescue", "ratio", "n_stopped")}
                       for t in DEER_CURVE},
        "sanity_checks": sanity,
        "sweep": rows,
        "sweep_fine": fine,
        "variant_all_lo": variant,
        "frontier_comparison_by_gate": frontier_cmp,
        "verdict": {
            "n_points_extending_deer_frontier": len(extenders),
            "n_points_total": len(all_points),
            "frontier_extenders": [{k: r[k] for k in
                                    ("tau_hi", "tau_lo", "W", "drop_pp",
                                     "saving_pct", "gates_passed")}
                                   for r in extenders],
            "n_pareto_dominating_same_tau_hi": len(winners),
            "pareto_winners": [{k: r[k] for k in
                                ("tau_hi", "tau_lo", "W", "drop_pp", "saving_pct",
                                 "d_drop_pp", "d_saving_pct")} for r in winners],
            "n_beating_deer_threshold_curve": len(beats_curve),
            "curve_beaters": [{k: r[k] for k in
                               ("tau_hi", "tau_lo", "W", "drop_pp", "saving_pct")}
                              | {"deer_drop_at_same_saving":
                                 r["deer_curve_equivalent"]["deer_drop_pp_at_same_saving"]}
                              for r in beats_curve],
        },
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, indent=1))
    print("\nwrote", CACHE)


if __name__ == "__main__":
    main()
