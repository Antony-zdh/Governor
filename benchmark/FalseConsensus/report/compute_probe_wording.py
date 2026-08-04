#!/usr/bin/env python3
"""Probe wording versus position: is an early "answer" a reading or an artifact?

If early probe agreement reflected a settled belief, the answer a probe returns
should not depend much on how the probe is worded. We test that on the paired
re-probe bank, where every probe position was read with FOUR probe variants on
the *same frozen prefix* -- so the model's state is identical and only the
elicitation differs.

We compare the two 32-token readouts (our boxed-answer suffix `simple__32` and
the CertaIndex suffix `certaindex__32`) and ask, binned by position as a fraction
of each trajectory's own length: how often do the two wordings return the same
answer, and how often is the answer correct?

The prediction from the placeholder account is that early answers are largely
elicitation artifacts (wordings disagree) and become properties of the state only
as the trajectory finishes (wordings converge). The competing account -- that the
model holds a stable but mistaken belief early -- predicts the opposite: both
wordings should read back the *same* wrong value.

Output: report/figures/gen/probe_wording.json
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
CACHE = HERE / "figures" / "gen" / "probe_wording.json"

sys.path.insert(0, str(GOV))
import latex2sympy2  # noqa: E402
import replay_rules as RR  # noqa: E402

PAIRED = RES / "probe_paired_2x2" / "reprobe_paired.csv"
# gold answers and trajectory lengths for the same problems
MAIN = (RES / "governor_v2"
        / "development__deepseek-ai-deepseek-r1-distill-qwen-7b__math500__seed_42"
        / "main" / "traj")

VARIANT_A, VARIANT_B = "simple__32", "certaindex__32"
BINS = [(0.00, 0.05), (0.05, 0.10), (0.10, 0.15), (0.15, 0.20),
        (0.20, 0.30), (0.30, 0.40), (0.40, 0.50), (0.50, 0.60),
        (0.60, 0.70), (0.70, 0.85), (0.85, 1.01)]

# The paired re-probe bank only re-probes out to 3,072 generated tokens. A
# trajectory longer than that has no observations in the later "% of own
# length" bins at all, so including it distorts the position normalisation --
# its probes all land in the early bins by construction. We therefore keep only
# trajectories the bank actually covers end to end. Of the 400 problems with
# both a paired bank and a main trajectory this drops 159: 140 that simply run
# past the probe coverage and 19 that hit the generation budget without
# finishing. 241 problems and 2,898 comparable probe positions remain.
PROBE_COVERAGE = 3072


def eq(a, b):
    """Robust grading with the latex2sympy2 module-global reset.

    That library keeps a module-level ``var`` dict which certain malformed answer
    strings overwrite with a bare Symbol; every later call then raises inside
    ``symbolic_equal``, which silently returns False. Resetting before each call
    makes results independent of evaluation order.
    """
    latex2sympy2.var = {}
    return RR.answers_equal(a, b)


def main():
    if not PAIRED.exists():
        raise SystemExit(f"paired re-probe bank not found: {PAIRED}")

    rows = list(csv.DictReader(PAIRED.open()))
    by_pos = collections.defaultdict(dict)
    for r in rows:
        by_pos[(r["problem_id"], int(r["token_position"]))][r["variant"]] = r

    meta = {}
    for p in MAIN.glob("problem_*.json"):
        t = json.loads(p.read_text())
        meta[str(t["problem_id"])] = (t["target"], int(t["tokens_used"]))

    agree = collections.defaultdict(lambda: [0, 0])
    correct = collections.defaultdict(lambda: [0, 0])

    kept = {p for p, (_, tu) in meta.items() if 0 < tu <= PROBE_COVERAGE}
    print(f"{len(kept)}/{len(meta)} trajectories lie within the "
          f"{PROBE_COVERAGE}-token probe coverage; the rest are dropped")

    for (pid, pos), d in by_pos.items():
        if pid not in kept or VARIANT_A not in d or VARIANT_B not in d:
            continue
        target, total = meta[pid]
        frac = pos / total
        if frac > 1.01:
            continue
        b = next((i for i, (lo, hi) in enumerate(BINS) if lo <= frac < hi), None)
        if b is None:
            continue
        a_answer = d[VARIANT_A]["probe_answer"].strip()
        b_answer = d[VARIANT_B]["probe_answer"].strip()
        if not a_answer or not b_answer:
            continue      # an empty readout is not a disagreement about content
        agree[b][0] += 1
        agree[b][1] += eq(a_answer, b_answer)
        correct[b][0] += 1
        correct[b][1] += eq(a_answer, target)

    out = {"variants": [VARIANT_A, VARIANT_B], "bins": []}
    print(f"{'position':>11} {'n':>7} {'wordings agree':>16} {'probe correct':>15}")
    tot_n = tot_a = 0
    for i, (lo, hi) in enumerate(BINS):
        n, a = agree[i]
        n2, c = correct[i]
        if n < 20:
            continue
        tot_n += n
        tot_a += a
        rec = {"lo": lo, "hi": hi, "n": n,
               "agree_pct": 100 * a / n, "correct_pct": 100 * c / n2}
        out["bins"].append(rec)
        print(f"{int(lo*100):>3}-{int(hi*100):<3}%  {n:>7} "
              f"{rec['agree_pct']:>15.1f}% {rec['correct_pct']:>14.1f}%")
    out["overall_agree_pct"] = 100 * tot_a / tot_n if tot_n else None
    out["n_total"] = tot_n
    print(f"{'overall':>11} {tot_n:>7} {out['overall_agree_pct']:>15.1f}%")

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(out, indent=1))
    print("wrote", CACHE)


if __name__ == "__main__":
    main()
