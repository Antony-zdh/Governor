import json, sys, os, hashlib
from pathlib import Path
from collections import defaultdict

REPO = Path("/localdata/dzhaoah/Governor")
BANK = REPO / "benchmark/FalseConsensus/results/governor_v2"
SM = json.load(open(REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"))
DEV_IDS = {}
for a in SM["assignments"]:
    if a["split"] == "dev":
        DEV_IDS.setdefault(a["benchmark"], set()).add(int(a["dataset_index"]))

MODELS = {
    "deepseek": ("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "deepseek-ai-deepseek-r1-distill-qwen-7b"),
    "qwen3": ("Qwen/Qwen3-8B", "qwen-qwen3-8b"),
}
BENCHMARKS = ["math500", "amc23", "aime24"]
SEEDS = [42, 43, 44]
INTERVALS = [64, 128, 256, 512]
CAPS = [8, 16, 32]

def load_probe_file(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None

def downsample_probes(probes, interval):
    if interval == 64:
        return probes
    selected = []
    for p in probes:
        pos = int(p["token_position"])
        if pos % interval == 0:
            selected.append(p)
    return selected

def truncate_probe_text(text, cap):
    if cap >= 32:
        return text
    return text[:cap * 4]

def main():
    results = []
    for key, (model_id, slug) in MODELS.items():
        for bench in BENCHMARKS:
            dev_set = DEV_IDS.get(bench, set())
            for seed in SEEDS:
                env = f"development__{slug}__{bench}__seed_{seed}"
                dense_dir = BANK / env / "dense_simple32" / "probes"
                if not dense_dir.exists():
                    continue
                for prob_file in sorted(dense_dir.glob("problem_*.json")):
                    pid = int(prob_file.stem.split("_")[1])
                    if pid not in dev_set:
                        continue
                    data = load_probe_file(prob_file)
                    if not data or "probes" not in data:
                        continue
                    full_probes = data["probes"]
                    for interval in INTERVALS:
                        sub = downsample_probes(full_probes, interval)
                        for cap in CAPS:
                            truncated = []
                            for p in sub:
                                tp = dict(p)
                                tp["probe_text"] = truncate_probe_text(p.get("probe_text", ""), cap)
                                truncated.append(tp)
                            results.append({
                                "model": model_id, "benchmark": bench, "seed": seed,
                                "problem_id": pid, "split": "dev",
                                "interval": interval, "cap": cap,
                                "n_probes": len(truncated),
                                "total_probe_out_tokens": sum(int(p.get("probe_out_tokens", 0)) for p in truncated),
                            })
    out_dir = REPO / "benchmark/FalseConsensus/probe_cost_ablation"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "ablation_rows.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    agg = defaultdict(lambda: {"n": 0, "probes": 0, "tokens": 0})
    for r in results:
        key = (r["model"], r["interval"], r["cap"])
        agg[key]["n"] += 1
        agg[key]["probes"] += r["n_probes"]
        agg[key]["tokens"] += r["total_probe_out_tokens"]
    with open(out_dir / "ablation_summary.json", "w") as f:
        summary = []
        for (model, interval, cap), v in sorted(agg.items()):
            summary.append({"model": model, "interval": interval, "cap": cap,
                          "n_trajectories": v["n"], "avg_probes": v["probes"]/v["n"],
                          "avg_probe_tokens": v["tokens"]/v["n"]})
        json.dump(summary, f, indent=2)
    print(f"Written {len(results)} ablation rows, {len(summary)} aggregated cells")
    print(f"Output: {out_dir / 'ablation_rows.jsonl'}")
    print(f"Summary: {out_dir / 'ablation_summary.json'}")

if __name__ == "__main__":
    main()
