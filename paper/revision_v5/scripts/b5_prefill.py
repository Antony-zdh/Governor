"""B5: how large is the probe *prompt* (prefill) cost that the paper excludes?

sec:accounting charges T = s + p where p is probe *output* only. Every probe
re-reads the whole prefix, and that prefill is charged nowhere in the paper --
`avg_probe_prompt_tokens` is recorded in the sweep archive and never reported.
Quantify it, per rule family and against DEER, relative to baseline decode.
"""
import sys, gzip, json, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2"))
import compute_harm_rescue as CHR

BANK = FC / "results/governor_v2_ws_sweep"
SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}

RULES = {}
with gzip.open(BANK / "candidate_rules_v2.jsonl.gz", "rt") as f:
    for line in f:
        d = json.loads(line)
        RULES[d["rule_id"]] = d


def interval_label(rid):
    sch = RULES[rid].get("probe", {}).get("schedule", {})
    if sch.get("kind") == "event_adaptive":
        return "event"
    return str(sch["interval_tokens"])


def load(path, split, deer=False):
    per = defaultdict(list)
    with gzip.open(path, "rt") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r["split"] != split or r["budget"] != SEL[r["benchmark"]]:
                continue
            if r["model"] not in CHR.DEVID:
                continue
            if r["rule_id"].startswith("deer") != deer:
                continue
            per[r["rule_id"]].append(r)
    return per


def summarise(per):
    """macro over the 18 envs, per rule"""
    out = {}
    for rid, rs in per.items():
        out[rid] = {
            "prompt": st.fmean(r.get("avg_probe_prompt_tokens", 0.0) for r in rs),
            "base": st.fmean(r["avg_baseline_decode_tokens"] for r in rs),
            "main": st.fmean(r["avg_main_decode_tokens"] for r in rs),
            "out": st.fmean(r.get("avg_probe_decode_tokens", 0.0) for r in rs),
            "drop": st.fmean(r["accuracy_drop_pp"] for r in rs),
            "sav": st.fmean(r["saving_fraction"] for r in rs),
        }
    return out


cons = summarise(load(BANK / "dev/consensus_dev_train.jsonl.gz", "dev"))
print(f"consensus rules: {len(cons)}")

by = defaultdict(list)
for rid, v in cons.items():
    by[interval_label(rid)].append(v)

print("\n=== probe PROMPT tokens per problem (macro over 18 dev envs, "
      "median over rules) ===")
print(f"  {'schedule':<16}{'prompt tok':>12}{'x baseline decode':>20}")
for k in ["64", "128", "256", "512", "event"]:
    if k not in by:
        continue
    p = st.median(v["prompt"] for v in by[k])
    b = st.median(v["base"] for v in by[k])
    print(f"  interval {k:<7}{p:12,.0f}{p/b:19.1f}x")
allp = st.median(v["prompt"] for v in cons.values())
allb = st.median(v["base"] for v in cons.values())
print(f"  {'ALL RULES':<16}{allp:12,.0f}{100*allp/allb:18.0f}% of baseline decode")

deer = summarise(load(BANK / "deer/deer_threshold_sweep.jsonl.gz", "dev", deer=True))
print(f"\n=== DEER (trial prompts), {len(deer)} thresholds ===")
for rid in sorted(deer, key=lambda r: deer[r]["drop"]):
    v = deer[rid]
    print(f"  {rid:<28} drop {v['drop']:6.3f}pp  sav {100*v['sav']:5.2f}%  "
          f"prompt {v['prompt']:10,.0f}  = {v['prompt']/v['base']:5.2f}x baseline")

best = max((r for r in cons.items() if r[1]["drop"] <= 1.0),
           key=lambda r: r[1]["sav"])
rid, v = best
print(f"\n=== the archive's best safe rule: {rid} ===")
print(f"  drop {v['drop']:.4f}pp   reported net saving {100*v['sav']:.2f}%")
print(f"  main {v['main']:,.0f} + probe_out {v['out']:,.0f}  vs baseline {v['base']:,.0f}")
print(f"  probe PROMPT {v['prompt']:,.0f}")
print(f"  saving if prompt were charged: "
      f"{100*(v['base'] - v['main'] - v['out'] - v['prompt'])/v['base']:.2f}%")
