#!/usr/bin/env python3
"""Direction-of-effect ratio for the accuracy tax (paper Section: Mechanism).

Among stopped problems whose committed-at-stop answer differs in correctness
from the frozen final answer, count:
  FC/SW = (final-correct, stop-wrong)   -- stopping DESTROYED a good answer
  FW/SC = (final-wrong,   stop-correct) -- stopping RESCUED a bad answer
ratio = FC/SW : FW/SC. Sampling noise -> ~1:1; a real "continued reasoning
corrects" effect -> >>1. Per-problem source: existing_methods_matched replay.
No GPU, no test-split read.
"""
import json
from collections import Counter

FN = ("benchmark/FalseConsensus/results/governor_v2/"
      "existing_methods_matched/governor_replay_rows.jsonl")

rows = [json.loads(l) for l in open(FN)]
print("variants:", dict(Counter(r["governor_variant"] for r in rows)))

def ratio(sel, label):
    st = [r for r in sel if r.get("stopped") == 1]
    fc_sw = sum(1 for r in st if r["baseline_correct"] == 1 and r["correct"] == 0)
    fw_sc = sum(1 for r in st if r["baseline_correct"] == 0 and r["correct"] == 1)
    rat = fc_sw / fw_sc if fw_sc else float("inf")
    print(f"{label:48} stopped={len(st):4}  FC/SW={fc_sw:4}  FW/SC={fw_sc:3}  ratio={rat:.2f}")

for v in sorted(set(r["governor_variant"] for r in rows)):
    ratio([r for r in rows if r["governor_variant"] == v], v)
print("--- naive consensus stopper, per model ---")
cons = [r for r in rows if r["governor_variant"] == "governor_naive_agreement"]
ratio(cons, "consensus pooled")
for m in sorted(set(r["model"] for r in cons)):
    ratio([r for r in cons if r["model"] == m], "consensus " + m.split("/")[-1])
