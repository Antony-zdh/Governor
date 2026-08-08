"""B6: re-verify the paper's most counterintuitive committed numbers.

CLAUDE.md flags 478 / 0 dev / 444 test / 364 overlap / 0 joint as a factual trap
that was once written wrong. It is exactly what a reviewer who clones the
release would recompute. Rebuild all five from the committed archives with
independently written aggregation.
"""
import sys, gzip, json, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_harm_rescue as CHR

import compute_boundary_consensus_v5 as B
SELB = B.SEL
BANK = FC / "results/governor_v2_ws_sweep"
GATE = ("conservative", 1.0, 0.10, 0.80)


def load(path, split, models=None):
    per = defaultdict(list)
    with gzip.open(path, "rt") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["split"] != split:
                continue
            if r["budget"] != SELB[r["benchmark"]]:
                continue
            if models is not None and r["model"] not in models:
                continue
            if models is None and r["model"] not in CHR.DEVID:
                continue
            per[r["rule_id"]].append(r)
    return per


def macro(per):
    out = {}
    for rid, rs in per.items():
        out[rid] = (st.fmean(x["accuracy_drop_pp"] for x in rs),
                    st.fmean(x["saving_fraction"] for x in rs),
                    st.fmean(1.0 if x["saving_fraction"] > 0 else 0.0 for x in rs),
                    len(rs))
    return out


def clears(m):
    _, d, s, p = GATE
    return {rid for rid, (dd, ss, pp, _) in m.items()
            if dd <= d and ss >= s and pp >= p and not rid.startswith("deer")}


train = macro(load(BANK / "dev/consensus_dev_train.jsonl.gz", "train"))
dev = macro(load(BANK / "dev/consensus_dev_train.jsonl.gz", "dev"))
test = macro(load(BANK / "test/consensus_test.jsonl.gz", "test"))
print(f"rules scored: train {len(train)}  dev {len(dev)}  test {len(test)}")
print(f"envs per rule: train {set(v[3] for v in train.values())}  "
      f"dev {set(v[3] for v in dev.values())}  test {set(v[3] for v in test.values())}")

T, D, S = clears(train), clears(dev), clears(test)
print(f"\nconservative-gate clearers (consensus only)")
print(f"  train in-sample winners : {len(T)}      (paper: 478)")
print(f"  dev                     : {len(D)}        (paper: 0)")
print(f"  test overall            : {len(S)}      (paper: 444)")
print(f"  train winners also on test: {len(T & S)}  (paper: 364)")
print(f"  dev AND test jointly    : {len(D & S)}        (paper: 0)")
print(f"  train winners on dev    : {len(T & D)}        (paper: 0)")

md = [dev[r][0] for r in T if r in dev]
print(f"\n  478 train winners, dev macro drop: median {st.median(md):.4f}pp "
      f"(paper: 4.50)")
print(f"  all rules median drop: train "
      f"{st.median(v[0] for v in train.values()):.3f} / dev "
      f"{st.median(v[0] for v in dev.values()):.3f} / test "
      f"{st.median(v[0] for v in test.values()):.3f} pp")

# held-out models
hm = defaultdict(list)
with gzip.open(BANK / "heldout_test/consensus_heldout_32b_llama_3seed.jsonl.gz", "rt") as f:
    for line in f:
        r = json.loads(line)
        hm[r["model"]].append(r)
print(f"\nheld-out models present: " +
      ", ".join(f"{k.split('/')[-1]} ({len(v)} rows)" for k, v in hm.items()))
