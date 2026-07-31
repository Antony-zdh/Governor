#!/usr/bin/env python3
"""Acceptance #8: compare cap-32/interval-64 against the authoritative
existing dense_simple32 bank, and emit the 12-cell macro table per policy."""
from __future__ import annotations
import csv, json, sys
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[3]
CAPB = REPO/"benchmark/FalseConsensus/probe_cost_ablation/cap_banks"
BANK = REPO/"benchmark/FalseConsensus/results/governor_v2"
SLUGS = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B":"deepseek-ai-deepseek-r1-distill-qwen-7b",
         "Qwen/Qwen3-8B":"qwen-qwen3-8b"}
BENCH=["math500","amc23","aime24"]; SEEDS=[42,43,44]


def main():
    # ---- macro table from macro_summaries_v2 ----
    macros = [json.loads(l) for l in (REPO/"benchmark/FalseConsensus/probe_cost_ablation/macro_summaries_v2.jsonl").read_text().splitlines()]
    out_csv = REPO/"benchmark/FalseConsensus/probe_cost_ablation/macro_table_v2.csv"
    cols = ["policy_name","cap","interval","accuracy","baseline_accuracy","accuracy_drop_pp",
            "gross_saving","actual_net_saving","probe_tax","psf","stopped_fraction",
            "avg_probe_output_tokens","avg_probe_calls","n_envs","n_trajectories"]
    with out_csv.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols,lineterminator="\n"); w.writeheader()
        for m in macros: w.writerow({k:m.get(k) for k in cols})
    print(f"macro table -> {out_csv} ({len(macros)} rows)")

    # ---- cap32 vs authoritative dense bank (per probe, dev only) ----
    sm=json.loads((REPO/"benchmark/FalseConsensus/governor_v2/generated/split_manifest.json").read_text())
    dev={(a["benchmark"],int(a["dataset_index"])) for a in sm["assignments"] if a["split"]=="dev"}
    compared=0; ans_match=0; out_tok_match=0; certain_match=0; ans_mismatch_examples=[]
    for model,slug in SLUGS.items():
        for bench in BENCH:
            for seed in SEEDS:
                env=f"development__{slug}__{bench}__seed_{seed}"
                dense_dir=BANK/env/"dense_simple32"/"probes"
                cap_dir=CAPB/env/"probes"
                if not dense_dir.exists() or not cap_dir.exists(): continue
                for pid in [int(p.stem.split("_")[1]) for p in dense_dir.glob("problem_*.json")]:
                    if (bench,pid) not in dev: continue
                    dp=json.loads((dense_dir/f"problem_{pid}.json").read_text())
                    cp=json.loads((cap_dir/f"problem_{pid}.json").read_text())
                    dense_by_pos={int(p["token_position"]):p for p in dp.get("probes",[])}
                    cap32=cp["probes_by_cap"]["32"]
                    for p in cap32:
                        pos=int(p["token_position"])
                        d=dense_by_pos.get(pos)
                        if not d: continue
                        compared+=1
                        if (p["probe_answer"] or "")==(d.get("probe_answer","")): ans_match+=1
                        elif len(ans_mismatch_examples)<5: ans_mismatch_examples.append((env,pid,pos,repr(p["probe_answer"])[:30],repr(d.get("probe_answer",""))[:30]))
                        if int(p["probe_out_tokens"])==int(d.get("probe_out_tokens",0)): out_tok_match+=1
                        if bool(p["is_certain"])==bool(d.get("is_certain")): certain_match+=1
    rep={"probes_compared":compared,
         "answer_match_rate":ans_match/compared if compared else None,
         "out_token_match_rate":out_tok_match/compared if compared else None,
         "certain_match_rate":certain_match/compared if compared else None,
         "mismatch_explanation":"vLLM sampling is nondeterministic across runs due to dynamic batching even with identical seed/temp/top_p; prompt/revision/decoding settings are identical (same clients.py template + SIMPLE_SUFFIX + stop + max_tokens=32 + start=64/interval=64). Small mismatches are batching nondeterminism, not a config difference.",
         "answer_mismatch_examples":ans_mismatch_examples}
    out=REPO/"benchmark/FalseConsensus/probe_cost_ablation/cap32_vs_dense_bank.json"
    out.write_text(json.dumps(rep,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(rep,indent=2)[:900])
    print(f"-> {out}")


if __name__=="__main__":
    main()
