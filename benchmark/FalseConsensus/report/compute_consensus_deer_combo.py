#!/usr/bin/env python3
"""Does consensus help as an ADD-ON to DEER's boundary-confidence signal?

The paper's negative result is about consensus *alone*. This script asks the
complementary question: if we pair agreement with a confidence floor, can we
stop EARLIER than DEER at equal-or-better accuracy? The hypothesis is that
before DEER commits at a very high-confidence boundary, the model has often
already emitted the same trial answer at several earlier boundaries at merely
moderate confidence -- so "last W boundary trials agree AND each exceeds a
moderate floor tau_c" might dominate a pure-threshold rule.

CRITICAL DESIGN CHOICE -- everything runs on DEER's OWN trial stream.
We do not try to align the 64/128-token consensus probe bank with DEER's
Wait-boundary trials (schedules differ; any alignment would be an artefact).
Instead, both the confidence signal and the agreement signal are read off the
same per-boundary trial sequence in the DEER confidence bank, so the combined
rule is exactly comparable to DEER and W=1 degenerates to plain DEER.

Combined rule (STOP at the first boundary i such that):
    * boundaries i-W+1 .. i all exist,
    * every one of them has a non-empty trial_answer,
    * every one of them has confidence > tau_c,
    * all W trial answers are mutually equal under the robust grader.
  -> commit trial answer at boundary i.
Token accounting is byte-identical to deer_threshold_sweep.replay_problem:
main tokens through the committed boundary's token_position (capped at the
selection budget), plus every trial's output tokens up to and including the
committed candidate_id. Non-stopping problems keep the frozen final answer and
pay every trial's output tokens.

W=1 with floor tau_c is, by construction, plain DEER at tau=tau_c; the script
asserts this against the committed deer_threshold_sweep.jsonl.gz rows and
against a locally recomputed DEER baseline (both must match).

Everything is macro-averaged over the 18 dev environments (2 dev models x 3
benchmarks x 3 seeds); never problem-micro.

PROCESS HYGIENE: this module must be the FIRST thing that touches the shared
answer evaluator in its interpreter. Running confidence replays *after*
consensus-probe replays in the same process perturbs evaluator state and
inflates DEER's drop by ~0.7pp (0.33 -> 1.06 at tau=0.995) while leaving token
counts bit-identical. Run this file directly; do not import it into an
analysis process that has already replayed probe-bank rules.

Reads only committed banks. Writes report/figures/gen/consensus_deer_combo.json.
"""
from __future__ import annotations

import gzip
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
CACHE = HERE / "figures" / "gen" / "consensus_deer_combo.json"

sys.path.insert(0, str(GOV))
sys.path.insert(0, str(FC / "related_work"))  # deer_threshold_sweep -> model_map

import replay_rules as RR  # noqa: E402
import deer_threshold_sweep as DS  # noqa: E402


# --------------------------------------------------------------------------
# Grader hardening: latex2sympy2 has a module-global `var` dict that its
# converter clobbers into a bare Symbol when it fails on certain malformed
# answers (e.g. the MATH500 answer string
# "8thgradeshouldhave10representatives"). Once clobbered, EVERY later
# latex2sympy call raises `TypeError: argument of type 'Symbol' is not
# iterable`, so `symbolic_equal` silently returns False for expressions it
# would otherwise grade correctly -- e.g. \frac{9a+11}{20} vs \frac{11+9a}{20}
# flips True -> False. Grading therefore becomes ORDER-DEPENDENT: whether a
# problem is graded correctly depends on whether some unrelated garbage answer
# was graded earlier in the same process.
#
# This script grades more answers, and in a different order, than
# deer_threshold_sweep does (it builds baselines for every problem in the main
# index, not just the dev split), so without this guard it hits the poison
# earlier and inflates DEER's drop by ~0.95pp -- exactly the ~1pp
# "fresh process" discrepancy documented in the handoff.
#
# We restore `var` to a clean dict before every grader call. That makes
# grading order-independent AND reproduces the committed bank exactly (the
# faithful deer_threshold_sweep path never trips the poison, so repaired and
# as-committed agree; verified in verify_deer_baseline()).
try:
    import latex2sympy2 as _L2S
except Exception:  # pragma: no cover - grader falls back if absent
    _L2S = None


def _repair_latex2sympy() -> None:
    if _L2S is not None and not isinstance(getattr(_L2S, "var", None), dict):
        _L2S.var = {}

BANK = RES / "related_work" / "deer_confidence_bank_cap30" / "full"
COMMITTED_DEER = RES / "governor_v2_ws_sweep" / "deer" / "deer_threshold_sweep.jsonl.gz"

# Confidence floors for the combined rule. Deliberately reaches well BELOW
# DEER's operating points (0.97/0.99/0.995) -- the whole premise is that
# agreement lets us accept a lower per-boundary floor. The DEER operating
# points themselves are included so W>1 can be read as "DEER + agreement".
TAU_C_GRID = [0.5, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97, 0.99, 0.995]
W_GRID = [1, 2, 3]

# DEER's dev-selected operating points (committed).
DEER_POINTS = {"C": 0.995, "B": 0.99, "T": 0.97}
# Reference values from the committed bank, asserted in verify_deer_baseline().
DEER_EXPECTED = {0.995: (0.333, 28.21), 0.99: (1.028, 29.56), 0.97: (2.750, 31.94)}

GATES = {
    "conservative": {"max_drop_pp": 1.0, "min_saving_pct": 10.0},
    "balanced": {"max_drop_pp": 2.0, "min_saving_pct": 20.0},
    "token_efficient": {"max_drop_pp": 3.5, "min_saving_pct": 30.0},
}


# --------------------------------------------------------------------------
# grading helpers (cached; the robust grader is the expensive part)
# --------------------------------------------------------------------------
# Two SEPARATE caches, deliberately. `robust_answers_equal` is asymmetric: it
# treats its second argument as the *reference* and retries extra un-stripped
# forms of it. Agreement checks between two model answers call the grader in
# both argument orders, so their (b, a) entries must never be visible to
# reference grading -- sharing one cache lets a reversed-order entry answer a
# later `eq(answer, target)` lookup and silently shifts accuracy (it inflated
# DEER's drop by ~0.95pp here before the split; savings were unaffected).
_EQ_CACHE: dict[tuple[str, str], bool] = {}
_AGREE_CACHE: dict[tuple[str, str], bool] = {}


def eq(left: Any, right: Any) -> bool:
    """Robust answer-vs-REFERENCE equality, memoised on the ordered pair.

    `right` is always the ground-truth target. This cache is only ever keyed by
    (model answer, target) pairs.
    """
    key = (str(left), str(right))
    hit = _EQ_CACHE.get(key)
    if hit is None:
        _repair_latex2sympy()
        hit = RR.answers_equal(left, right)
        _EQ_CACHE[key] = hit
    return hit


def answers_agree(left: str, right: str) -> bool:
    """Mutual agreement between two *model* answers (neither is a reference).

    Symmetrised (match in either argument order counts as agreement) because
    neither side is ground truth. Uses its own cache, keyed order-insensitively.
    """
    if left == right:
        return True
    key = (left, right) if left <= right else (right, left)
    hit = _AGREE_CACHE.get(key)
    if hit is None:
        _repair_latex2sympy()
        first = RR.answers_equal(left, right)
        _repair_latex2sympy()
        hit = first or RR.answers_equal(right, left)
        _AGREE_CACHE[key] = hit
    return hit


# deer_threshold_sweep.replay_problem grades through DS.eq, which we also use
# in verify_deer_baseline(); wrap it with the same guard so the DEER leg is
# order-independent too.
_DS_EQ_RAW = DS.eq


def _ds_eq_guarded(answer: Any, target: Any) -> bool:
    _repair_latex2sympy()
    return _DS_EQ_RAW(answer, target)


DS.eq = _ds_eq_guarded


# --------------------------------------------------------------------------
# the combined stop rule
# --------------------------------------------------------------------------
def combined_decision(
    trials: Sequence[Mapping[str, Any]],
    *,
    window: int,
    tau_c: float,
    max_attempts: int = 30,
) -> dict[str, Any] | None:
    """First boundary where the last `window` trials agree and all clear tau_c.

    Mirrors DS.direct_submit_decision's guards exactly (candidate_id cap,
    non-empty answer, strict `>` on the confidence comparison) so that
    window == 1 is bit-identical to plain DEER at tau = tau_c.
    """
    # `run` holds the consecutive tail of boundaries that are non-empty AND
    # above the floor; any boundary failing either resets it (a below-floor or
    # empty boundary breaks the chain -- the conservative reading).
    run: list[dict[str, Any]] = []
    for row in trials:
        candidate_id = int(row.get("candidate_id", -1))
        if candidate_id > max_attempts:
            break
        answer = str(row.get("trial_answer", "")).strip()
        confidence = float(row.get("confidence", 0.0))
        if not answer or not confidence > tau_c:
            run = []
            continue
        run.append({"candidate_id": candidate_id, "answer": answer,
                    "confidence": confidence,
                    "token_position": int(row.get("token_position", 0))})
        if len(run) > window:
            run.pop(0)
        if len(run) < window:
            continue
        head = run[0]["answer"]
        if all(answers_agree(head, r["answer"]) for r in run[1:]):
            last = run[-1]
            return {"candidate_id": last["candidate_id"],
                    "token_position": last["token_position"],
                    "confidence": last["confidence"],
                    "trial_answer": last["answer"],
                    "window_start_candidate_id": run[0]["candidate_id"]}
    return None


def replay_problem(record, main, baseline, *, window, tau_c, budget):
    """Token accounting identical to DS.replay_problem; only the decision differs."""
    trials = list(record.get("trials", []))
    baseline_correct = baseline["baseline_correct"]
    baseline_tokens = baseline["baseline_tokens"]
    baseline_complete = baseline["baseline_complete"]

    decision = combined_decision(trials, window=window, tau_c=tau_c)
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
            "stopped": False,
            "capped": not baseline_complete,
        }
    committed_id = int(decision["candidate_id"])
    stop = min(int(decision["token_position"]), budget)
    correct = eq(decision["trial_answer"], main["target"])
    charged = [t for t in trials if int(t.get("candidate_id", 0)) <= committed_id]
    return {
        "correct": correct,
        "baseline_correct": baseline_correct,
        "main_decode_tokens": stop,
        "probe_decode_tokens": sum(int(t.get("trial_out_tokens", 0)) for t in charged),
        "probe_prompt_tokens": sum(int(t.get("trial_prompt_tokens", 0)) for t in charged),
        "total_decode_tokens": stop + sum(int(t.get("trial_out_tokens", 0)) for t in charged),
        "baseline_decode_tokens": baseline_tokens,
        "stopped": True,
        "capped": not baseline_complete,
    }


# --------------------------------------------------------------------------
# environment loading (mirrors deer_threshold_sweep.main / compute_harm_rescue)
# --------------------------------------------------------------------------
def load_dev_environments():
    """[(env_name, model, benchmark, seed, budget, records, main_index,
        baseline_index, dev_pids)] for the 18 dev environments."""
    protocol = json.loads((GOV / "protocol_v2.json").read_text(encoding="utf-8"))
    budgets = DS.selection_budgets(protocol)
    split_map = RR.load_split_map(GOV / "generated/split_manifest.json")
    if not BANK.exists():
        raise SystemExit(f"DEER dev confidence bank not found: {BANK}")

    envs = []
    for env_dir in sorted(BANK.iterdir()):
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
                "baseline_correct": (eq(m["final_answer"], m["target"])
                                     if complete and m["final_answer"] is not None
                                     else False),
                "baseline_tokens": min(m["tokens_used"], budget)}
        dev_pids = sorted(pid for pid in records
                          if split_map.get((benchmark, pid)) == "dev")
        if not dev_pids:
            continue
        envs.append({"name": env_dir.name, "model": DS.MODEL_ID[model_key],
                     "benchmark": benchmark, "seed": seed, "budget": budget,
                     "records": records, "main_index": main_index,
                     "baseline_index": baseline_index, "pids": dev_pids})
    return envs


def macro(envs, replay):
    """Macro-average per-environment drop/saving/stop-rate + pooled harm/rescue."""
    per_env, harm, rescue, n_stop, n_tot = [], 0, 0, 0, 0
    for env in envs:
        vals = [replay(env, pid) for pid in env["pids"]]
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
            "env": env["name"],
            "drop_pp": 100 * (st.fmean(v["baseline_correct"] for v in vals)
                              - st.fmean(v["correct"] for v in vals)),
            "saving_pct": ((bl - tot) / bl * 100.0) if bl else 0.0,
            "stop_rate": st.fmean(v["stopped"] for v in vals),
            "accuracy": st.fmean(v["correct"] for v in vals),
            "baseline_accuracy": st.fmean(v["baseline_correct"] for v in vals)})
    return {
        "drop_pp": st.fmean(e["drop_pp"] for e in per_env),
        "saving_pct": st.fmean(e["saving_pct"] for e in per_env),
        "stop_rate": st.fmean(e["stop_rate"] for e in per_env),
        "accuracy": st.fmean(e["accuracy"] for e in per_env),
        "baseline_accuracy": st.fmean(e["baseline_accuracy"] for e in per_env),
        "harm": harm, "rescue": rescue,
        "ratio": (harm / rescue) if rescue else None,
        "n_stopped": n_stop, "n_problems": n_tot, "n_env": len(per_env),
        "per_env": per_env,
    }


# --------------------------------------------------------------------------
# STEP 0 -- baseline reproduction check
# --------------------------------------------------------------------------
def committed_deer_macro():
    out = defaultdict(list)
    with gzip.open(COMMITTED_DEER, "rt") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["phase"] == "development" and r["split"] == "dev":
                out[float(r["threshold"])].append(r)
    return {thr: {"drop_pp": st.fmean(x["accuracy_drop_pp"] for x in rs),
                  "saving_pct": 100 * st.fmean(x["saving_fraction"] for x in rs),
                  "stop_rate": st.fmean(x["stop_rate"] for x in rs),
                  "n_env": len(rs)}
            for thr, rs in out.items()}


def verify_deer_baseline(envs):
    """Recompute DEER locally and assert it matches the committed bank."""
    committed = committed_deer_macro()
    local, checks = {}, []
    for thr in sorted(set(TAU_C_GRID) | set(DEER_POINTS.values())):
        m = macro(envs, lambda env, pid, thr=thr: DS.replay_problem(
            env["records"][pid], env["main_index"][pid],
            env["baseline_index"][pid], thr, env["budget"]))
        m.pop("per_env")
        local[thr] = m
        c = committed.get(thr)
        if c is None:
            continue
        ok = (abs(m["drop_pp"] - c["drop_pp"]) < 1e-6
              and abs(m["saving_pct"] - c["saving_pct"]) < 1e-6
              and abs(m["stop_rate"] - c["stop_rate"]) < 1e-9)
        checks.append({"threshold": thr, "matches_committed": ok,
                       "local": {k: m[k] for k in ("drop_pp", "saving_pct", "stop_rate")},
                       "committed": c})
        print(f"  DEER tau={thr:<8g} local drop={m['drop_pp']:7.3f}pp "
              f"saving={m['saving_pct']:6.2f}%  committed drop={c['drop_pp']:7.3f}pp "
              f"saving={c['saving_pct']:6.2f}%  {'OK' if ok else 'MISMATCH'}")
    bad = [c for c in checks if not c["matches_committed"]]
    if bad:
        raise SystemExit(f"DEER baseline does NOT reproduce committed bank: {bad}")
    for thr, (drop, sav) in DEER_EXPECTED.items():
        m = local[thr]
        assert abs(m["drop_pp"] - drop) < 0.005 and abs(m["saving_pct"] - sav) < 0.02, \
            f"tau={thr} expected {drop}/{sav}, got {m['drop_pp']}/{m['saving_pct']}"
    print(f"  DEER baseline reproduces the committed bank exactly "
          f"({len(checks)} thresholds checked).")
    return local, checks


# --------------------------------------------------------------------------
# STEP 1 -- descriptive statistics over the dev boundary trials
# --------------------------------------------------------------------------
THRESH_REPORT = [0.8, 0.9, 0.92, 0.95, 0.97, 0.99, 0.995, 0.999]


def _frac_table(confidences):
    if not confidences:
        return {"n": 0}
    s = sorted(confidences)
    return {
        "n": len(s),
        "mean": st.fmean(s),
        "median": st.median(s),
        "p10": s[int(0.10 * (len(s) - 1))],
        "p25": s[int(0.25 * (len(s) - 1))],
        "p75": s[int(0.75 * (len(s) - 1))],
        **{f"frac_gt_{t:g}": sum(1 for c in s if c > t) / len(s)
           for t in THRESH_REPORT},
    }


def descriptive_stats(envs):
    """(a) all trials, (b) pre-DEER-commit trials, (c) correct vs wrong trial
    answers, (d) W=3-agreeing boundaries split by correctness of the agreed
    answer. All pooled over the dev split of the 18 environments."""
    all_conf, pre_commit, correct_conf, wrong_conf = [], [], [], []
    agree3_correct, agree3_wrong = [], []
    n_traj = n_traj_commit = 0

    for env in envs:
        for pid in env["pids"]:
            trials = [t for t in env["records"][pid].get("trials", [])
                      if int(t.get("candidate_id", -1)) <= 30]
            target = env["main_index"][pid]["target"]
            n_traj += 1
            confs = [float(t.get("confidence", 0.0)) for t in trials]
            all_conf.extend(confs)

            # (b) boundaries strictly BEFORE DEER's conservative commit
            dec = DS.direct_submit_decision(trials, threshold=0.995)
            if dec is not None:
                n_traj_commit += 1
                cid = int(dec["candidate_id"])
                pre_commit.extend(float(t.get("confidence", 0.0)) for t in trials
                                  if int(t.get("candidate_id", 0)) < cid)

            # (c) correctness of each individual trial answer
            for t in trials:
                ans = str(t.get("trial_answer", "")).strip()
                if not ans:
                    continue
                c = float(t.get("confidence", 0.0))
                (correct_conf if eq(ans, target) else wrong_conf).append(c)

            # (d) boundaries where the last 3 answers all agree (no floor)
            for i in range(2, len(trials)):
                win = trials[i - 2:i + 1]
                answers = [str(t.get("trial_answer", "")).strip() for t in win]
                if not all(answers):
                    continue
                if not all(answers_agree(answers[0], a) for a in answers[1:]):
                    continue
                c = float(win[-1].get("confidence", 0.0))
                (agree3_correct if eq(answers[-1], target) else agree3_wrong).append(c)

    return {
        "a_all_trials": _frac_table(all_conf),
        "b_pre_deer995_commit": _frac_table(pre_commit),
        "c_trial_answer_correct": _frac_table(correct_conf),
        "c_trial_answer_wrong": _frac_table(wrong_conf),
        "d_w3_agree_correct": _frac_table(agree3_correct),
        "d_w3_agree_wrong": _frac_table(agree3_wrong),
        "n_trajectories": n_traj,
        "n_trajectories_deer995_commits": n_traj_commit,
        "thresholds_reported": THRESH_REPORT,
    }


# --------------------------------------------------------------------------
# STEP 2/3 -- the sweep and the Pareto comparison
# --------------------------------------------------------------------------
def gates_passed(drop_pp, saving_pct):
    return [name for name, g in GATES.items()
            if drop_pp <= g["max_drop_pp"] and saving_pct >= g["min_saving_pct"]]


def dominance(point, deer):
    """Which DEER operating points does `point` Pareto-dominate?

    Dominates := drop <= DEER drop AND saving >= DEER saving (weak dominance,
    with a 1e-9 tolerance), i.e. no worse on either axis.
    """
    out = {}
    for lab, d in deer.items():
        no_worse = (point["drop_pp"] <= d["drop_pp"] + 1e-9
                    and point["saving_pct"] >= d["saving_pct"] - 1e-9)
        strictly_better = (point["drop_pp"] < d["drop_pp"] - 1e-9
                           or point["saving_pct"] > d["saving_pct"] + 1e-9)
        out[lab] = {"dominates": bool(no_worse and strictly_better),
                    "weakly_dominates": bool(no_worse),
                    "d_drop_pp": point["drop_pp"] - d["drop_pp"],
                    "d_saving_pct": point["saving_pct"] - d["saving_pct"]}
    return out


def main() -> None:
    print("Loading the 18 dev environments from the DEER confidence bank ...")
    envs = load_dev_environments()
    print(f"  {len(envs)} environments, "
          f"{sum(len(e['pids']) for e in envs)} dev problems")
    if len(envs) != 18:
        raise SystemExit(f"expected 18 dev environments, got {len(envs)}")

    print("\nSTEP 0 -- verifying the DEER baseline against the committed bank")
    deer_local, deer_checks = verify_deer_baseline(envs)

    print("\nSTEP 1 -- descriptive statistics over dev boundary trials")
    stats = descriptive_stats(envs)
    for key in ("a_all_trials", "b_pre_deer995_commit", "c_trial_answer_correct",
                "c_trial_answer_wrong", "d_w3_agree_correct", "d_w3_agree_wrong"):
        s = stats[key]
        print(f"  {key:<26} n={s['n']:>6} mean={s.get('mean', 0):.4f} "
              f"median={s.get('median', 0):.4f} "
              f">0.9={s.get('frac_gt_0.9', 0):.3f} >0.95={s.get('frac_gt_0.95', 0):.3f} "
              f">0.99={s.get('frac_gt_0.99', 0):.3f} >0.995={s.get('frac_gt_0.995', 0):.3f}")

    print("\nSTEP 2 -- combined-rule sweep (W x tau_c)")
    deer_ref = {lab: {k: deer_local[thr][k] for k in
                      ("drop_pp", "saving_pct", "stop_rate", "harm", "rescue",
                       "ratio", "n_stopped")}
                for lab, thr in DEER_POINTS.items()}
    for lab in deer_ref:
        deer_ref[lab]["threshold"] = DEER_POINTS[lab]

    combo = []
    for w in W_GRID:
        for tau in TAU_C_GRID:
            m = macro(envs, lambda env, pid, w=w, tau=tau: replay_problem(
                env["records"][pid], env["main_index"][pid],
                env["baseline_index"][pid],
                window=w, tau_c=tau, budget=env["budget"]))
            per_env = m.pop("per_env")
            row = {"W": w, "tau_c": tau, **m,
                   "gates_passed": gates_passed(m["drop_pp"], m["saving_pct"]),
                   "dominance_vs_deer": dominance(m, deer_ref),
                   "per_env": per_env}
            # W=1 must be identical to plain DEER at tau=tau_c.
            if w == 1:
                d = deer_local[tau]
                row["equals_plain_deer"] = (
                    abs(m["drop_pp"] - d["drop_pp"]) < 1e-9
                    and abs(m["saving_pct"] - d["saving_pct"]) < 1e-9
                    and m["harm"] == d["harm"] and m["rescue"] == d["rescue"])
                if not row["equals_plain_deer"]:
                    raise SystemExit(
                        f"W=1 tau={tau} does not reduce to plain DEER: "
                        f"{m['drop_pp']}/{m['saving_pct']} vs "
                        f"{d['drop_pp']}/{d['saving_pct']}")
            combo.append(row)
            ratio_txt = "inf" if not m["ratio"] else f"{m['ratio']:.2f}"
            print(f"  W={w} tau_c={tau:<7g} drop={m['drop_pp']:7.3f}pp "
                  f"saving={m['saving_pct']:6.2f}% stop={m['stop_rate']:.3f} "
                  f"harm={m['harm']:>4} rescue={m['rescue']:>3} "
                  f"ratio={ratio_txt:>6} "
                  f"gates={row['gates_passed']}", flush=True)

    print("\nSTEP 3 -- Pareto dominance vs DEER's operating points")
    dominators = defaultdict(list)
    for row in combo:
        if row["W"] == 1:
            continue  # W=1 IS DEER; not an add-on
        for lab, d in row["dominance_vs_deer"].items():
            if d["dominates"]:
                dominators[lab].append((row["W"], row["tau_c"],
                                        row["drop_pp"], row["saving_pct"]))
    for lab, thr in DEER_POINTS.items():
        d = deer_ref[lab]
        hits = dominators.get(lab, [])
        print(f"  DEER {lab} (tau={thr}): drop={d['drop_pp']:.2f}pp "
              f"saving={d['saving_pct']:.2f}%  -> "
              f"{len(hits)} dominating combined point(s)"
              + ("" if not hits else ": " + ", ".join(
                  f"W={w},tau_c={t:g} ({dr:.2f}pp/{sv:.2f}%)"
                  for w, t, dr, sv in hits)))

    payload = {
        "meta": {
            "split": "dev", "n_env": len(envs),
            "n_dev_problems": sum(len(e["pids"]) for e in envs),
            "bank": str(BANK.relative_to(FC)),
            "stream": "DEER boundary trials (no consensus-probe alignment)",
            "token_view": "all_generated_tokens (main through stop + trial output)",
            "aggregation": "macro over 18 dev environments",
            "gates": GATES,
            "W_grid": W_GRID, "tau_c_grid": TAU_C_GRID,
        },
        "deer_baseline_verification": deer_checks,
        "deer_local": {f"{k:g}": v for k, v in deer_local.items()},
        "deer_operating_points": deer_ref,
        "step1_descriptive": stats,
        "step2_combo": combo,
        "step3_dominators": {k: v for k, v in dominators.items()},
    }
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(payload, indent=1))
    print("\nwrote", CACHE)


if __name__ == "__main__":
    main()
