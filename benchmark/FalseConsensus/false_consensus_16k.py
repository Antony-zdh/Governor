#!/usr/bin/env python3
"""Re-run the §4.1 false-consensus phenomenon at the MAIN 16K/32K budget.

Replaces the deprecated 3072-token exploratory study (analyze.py on
results/stage1_logging) with the frozen main trajectories + dense probe bank
used for the main results. Faithful to analyze.py's fact definitions
(window=5, certain_bar=3, consensus_share=0.8, min_probes=3) but grades
correctness with the project robust grader.

Facts:
  (1) cumulative-agreement accuracy (final_share==1) and window-agreement
      accuracy (last-5 window share==1).
  (2) recovery: first-probe-wrong flip rate; 3-probe consensus-different rate.
  (3) later consensus worse: accuracy binned by consensus time.
  (4) naive stop (first 3 consecutive agreeing, certain, non-empty): stop rate,
      stopped-answer accuracy vs run-to-completion accuracy, tokens saved.

Run from repo root:
  python benchmark/FalseConsensus/false_consensus_16k.py
"""
import glob, json, os, sys
from functools import lru_cache
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "governor_v2"))
from dynasor.core.evaluator import math_equal, strip_string  # noqa: E402
from grading import robust_answers_equal  # noqa: E402

WINDOW, BAR, CONS_SHARE, MIN_PROBES = 5, 3, 0.8, 3
ROOT = os.path.join(HERE, "results/governor_v2")
MODEL = "deepseek-ai-deepseek-r1-distill-qwen-7b"


@lru_cache(maxsize=None)
def _me(a, b):
    try:
        return bool(math_equal(a, b))
    except Exception:
        return False


def eq(a, b):
    """probe-vs-probe equivalence (grouping), math_equal-based like analyze.py."""
    a, b = str(a), str(b)
    if a == "" or b == "":
        return a == b
    if a == b:
        return True
    return _me(a, b) or _me(b, a)


def cum_unanimous(nonempty):
    """Fast cumulative-unanimity: all non-empty probes in one equivalence class."""
    if not nonempty:
        return False, ""
    distinct = list(dict.fromkeys(nonempty))  # exact-dedup, order-preserving
    first = distinct[0]
    for d in distinct[1:]:
        if not eq(d, first):
            return False, ""
    return True, first


def correct_of(ans, raw_target):
    if ans is None or str(ans) == "":
        return False
    try:
        return bool(robust_answers_equal(str(ans), str(raw_target)))
    except Exception:
        return False


def group(answers):
    # bucket by exact string first (cheap), then merge buckets via math_equal
    from collections import Counter
    exact = Counter(answers)
    reps, counts = [], []
    for ans, c in exact.items():
        for i, rep in enumerate(reps):
            if eq(ans, rep):
                counts[i] += c
                break
        else:
            reps.append(ans); counts.append(c)
    return counts, reps[int(np.argmax(counts))]


def window_share(answers, w=WINDOW, min_nonempty=MIN_PROBES):
    win = [a for a in answers[-w:] if a != ""]
    if len(win) < min_nonempty:
        return float("nan"), ""
    counts, dom = group(win)
    return max(counts) / len(win), dom


def load_env(seed, phase="development"):
    d = f"{ROOT}/{phase}__{MODEL}__math500__seed_{seed}"
    rows = []
    for tf in sorted(glob.glob(f"{d}/main/traj/problem_*.json")):
        t = json.load(open(tf))
        pid = t["problem_id"]
        pf = f"{d}/dense_simple32/probes/problem_{pid}.json"
        if not os.path.exists(pf):
            continue
        pb = json.load(open(pf))
        probes = sorted(pb["probes"], key=lambda p: int(p["token_position"]))
        answers = [("" if p["probe_answer"] in (None, "") else str(p["probe_answer"])) for p in probes]
        certains = [bool(p["is_certain"]) for p in probes]
        tokens = [int(p["token_position"]) for p in probes]
        if not answers:
            continue
        rows.append(dict(pid=pid, seed=seed, raw_target=t["target"],
                         final_answer=t.get("final_answer") or "",
                         final_correct=bool(t["final_correct"]),
                         tokens_used=int(t["tokens_used"]),
                         answers=answers, certains=certains, tokens=tokens))
    return rows


def analyze(rows, label):
    n = len(rows)
    # per-problem derived signals
    for r in rows:
        a = r["answers"]; rt = r["raw_target"]
        r["probe1"] = a[0]
        r["probe1_correct"] = correct_of(a[0], rt)
        # cumulative unanimity over all non-empty (fact1 only needs share==1)
        nonempty = [x for x in a if x != ""]
        uni, dom = cum_unanimous(nonempty)
        r["cum_unanimous"] = uni; r["cum_dom"] = dom
        ws, wd = window_share(a)
        r["win_share"] = ws; r["win_dom"] = wd
        r["win_dom_correct"] = correct_of(wd, rt) if wd else None
        # naive stop: first BAR consecutive non-empty, certain, mutually equal
        stop_ans, stop_tok = None, None
        for t in range(BAR - 1, len(a)):
            win = a[t - BAR + 1:t + 1]; cert = r["certains"][t - BAR + 1:t + 1]
            if all(x != "" for x in win) and all(cert) and all(eq(x, win[0]) for x in win[1:]):
                stop_ans, stop_tok = win[0], r["tokens"][t]; break
        r["stop_ans"] = stop_ans; r["stop_tok"] = stop_tok
        r["stop_correct"] = correct_of(stop_ans, rt) if stop_ans is not None else None
        # consensus time: first probe (>=MIN_PROBES) where window share >= CONS_SHARE
        ct = None
        for t in range(MIN_PROBES - 1, len(a)):
            s, _ = window_share(a[max(0, t + 1 - WINDOW):t + 1])
            if not np.isnan(s) and s >= CONS_SHARE:
                ct = r["tokens"][t]; break
        r["consensus_time"] = ct

    print(f"\n===== {label}  (n={n} problems) =====")
    overall = np.mean([r["final_correct"] for r in rows])
    print(f"overall final accuracy: {overall:.1%}")

    # FACT 1
    unan_cum = [r for r in rows if r["cum_unanimous"] and r["cum_dom"] != ""]
    unan_win = [r for r in rows if not np.isnan(r["win_share"]) and r["win_share"] >= 1.0]
    print("\n[fact1] Final agreement is reliable")
    print(f"  cumulative share=1: {len(unan_cum)} problems, "
          f"final acc {np.mean([r['final_correct'] for r in unan_cum]):.1%}")
    print(f"  window share=1 (last {WINDOW}): {len(unan_win)} problems, "
          f"window-answer acc {np.mean([bool(r['win_dom_correct']) for r in unan_win]):.1%}")

    # FACT 2
    p1_wrong = [r for r in rows if not r["probe1_correct"]]
    rec, rec_corr = [], 0
    for r in rows:
        a = r["answers"]
        for t in range(BAR - 1, len(a)):
            win = a[t - BAR + 1:t + 1]
            if all(x != "" for x in win) and all(eq(x, win[0]) for x in win[1:]):
                if not eq(win[0], r["final_answer"]):
                    rec.append(r); rec_corr += int(r["final_correct"])
                break
    print("\n[fact2] Recovery is common")
    print(f"  first probe wrong: {len(p1_wrong)} problems, "
          f"{np.mean([r['final_correct'] for r in p1_wrong]):.1%} flip to correct")
    print(f"  3-probe consensus != final answer: {len(rec)} problems, "
          f"{rec_corr/max(len(rec),1):.1%} ended correct")

    # FACT 3
    edges = [(0, 512), (512, 1024), (1024, 2048), (2048, 10**9)]
    labels = ["<512", "512-1024", "1024-2048", ">2048"]
    have = [r for r in rows if r["consensus_time"] is not None]
    print("\n[fact3] Later consensus is worse (acc by consensus time)")
    for (lo, hi), lb in zip(edges, labels):
        sub = [r for r in have if lo <= r["consensus_time"] < hi]
        acc = np.mean([r["final_correct"] for r in sub]) if sub else float("nan")
        print(f"  {lb:>10}: n={len(sub):3d}  acc={acc:.1%}" if sub else f"  {lb:>10}: n=0")

    # FACT 4
    stopped = [r for r in rows if r["stop_ans"] is not None]
    if stopped:
        sc = np.mean([r["stop_correct"] for r in stopped])
        fc = np.mean([r["final_correct"] for r in stopped])
        saved = np.mean([r["tokens_used"] - r["stop_tok"] for r in stopped])
        wrong = sum(1 for r in stopped if not r["stop_correct"])
        print("\n[fact4] The cost lands at the stop (naive 3-consecutive-certain stop)")
        print(f"  fires on {len(stopped)}/{n} problems")
        print(f"  stopped-answer acc {sc:.1%}  vs  run-to-completion acc {fc:.1%}  "
              f"=> {(fc-sc)*100:.1f}pp loss")
        print(f"  avg tokens saved on stopped: {saved:.0f};  stops on WRONG answer: {wrong}")


if __name__ == "__main__":
    # train+dev ids collected at dev seeds 42/43/44; test ids at confirmation
    # seeds 45/46/47 -> union covers all 500 MATH500 problem ids (no id overlap).
    dev = [r for s in (42, 43, 44) for r in load_env(s, "development")]
    test = [r for s in (45, 46, 47) for r in load_env(s, "confirmation")]
    full = dev + test
    ids = set(r["pid"] for r in full)
    print(f"coverage: dev-instances={len(dev)} test-instances={len(test)} "
          f"total={len(full)} distinct_problem_ids={len(ids)}")
    analyze(full, "FULL train+dev+test (all 500 MATH500 ids, DeepSeek-7B, 16K/32K, 6 seeds)")
