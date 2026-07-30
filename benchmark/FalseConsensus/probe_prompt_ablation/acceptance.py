#!/usr/bin/env python3
"""Strict acceptance for the Simple@32 vs CertaIndex@32 prompt-timing ablation.

Checks:
  - 36 complete CertaIndex partial-environment directories;
  - 3,420 frozen main trajectories;
  - 3,420 existing Simple trajectories;
  - 3,420 CertaIndex@32 trajectories;
  - zero duplicate paired identities;
  - zero corrupt/request-error rows;
  - zero probe_out_tokens > 32;
  - settings exactly cap 32, interval 64, start 64, patience 3;
  - all 3,420 Simple/CertaIndex pairs replayed (per_problem.csv row count).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GOV = REPO / "benchmark/FalseConsensus/results/governor_v2"
C32 = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/certaindex32"
ANALYSIS = REPO / "benchmark/FalseConsensus/results/probe_prompt_ablation/analysis"

SLUGS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    "Qwen/Qwen3-8B": "qwen-qwen3-8b",
}
BENCHMARKS = ["math500", "amc23", "aime24"]
DEV_SEEDS = [42, 43, 44]
CONF_SEEDS = [45, 46, 47]


def envs() -> list[str]:
    out = []
    for slug in SLUGS.values():
        for ph, seeds in (("development", DEV_SEEDS), ("confirmation", CONF_SEEDS)):
            for b in BENCHMARKS:
                for s in seeds:
                    out.append(f"{ph}__{slug}__{b}__seed_{s}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path,
                    default=ANALYSIS / "acceptance.json")
    args = ap.parse_args(argv)
    errors = []
    n_envs = 0
    total_main = 0
    total_simple = 0
    total_certaindex = 0
    cap_violations = 0
    error_rows = 0
    corrupt_files = 0
    dup_ids = 0
    seen_pairs = set()
    settings_ok = True
    expected_settings = {"probe_tokens": 32, "probe_interval": 64,
                         "start_token": 64, "patience": 3}
    for env in envs():
        main_dir = GOV / env / "main" / "traj"
        simp_dir = GOV / env / "dense_simple32" / "probes"
        cidx_dir = C32 / env / "probes"
        cidx_manifest = C32 / env / "probe_manifest.json"
        if not main_dir.exists():
            continue
        n_envs += 1
        main_ids = {int(p.stem.split("_")[1]) for p in main_dir.glob("problem_*.json")}
        simp_ids = {int(p.stem.split("_")[1]) for p in simp_dir.glob("problem_*.json")} if simp_dir.exists() else set()
        cidx_ids = {int(p.stem.split("_")[1]) for p in cidx_dir.glob("problem_*.json")} if cidx_dir.exists() else set()
        total_main += len(main_ids)
        total_simple += len(simp_ids)
        total_certaindex += len(cidx_ids)
        if not cidx_manifest.exists():
            errors.append(f"{env}: missing certaindex probe_manifest.json")
        else:
            mf = json.loads(cidx_manifest.read_text(encoding="utf-8"))
            st = mf.get("probe_settings", {})
            for k, v in expected_settings.items():
                if st.get(k) != v:
                    errors.append(f"{env}: setting {k}={st.get(k)} != {v}")
                    settings_ok = False
            if st.get("probe_suffix_sha256") != "c3c5fe2d9ab1d28fd0be92c2316e90475142ef6ce8d23c1033764b2445401968":
                errors.append(f"{env}: CERTAINDEX_SUFFIX sha mismatch")
                settings_ok = False
        if cidx_ids != main_ids:
            errors.append(f"{env}: certaindex ids != main ids "
                          f"(cidx={len(cidx_ids)} main={len(main_ids)})")
        if simp_ids != main_ids:
            errors.append(f"{env}: simple ids != main ids")
        # per-probe integrity: cap + errors + duplicates + corrupt
        for p in cidx_dir.glob("problem_*.json") if cidx_dir.exists() else []:
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                corrupt_files += 1
                errors.append(f"{env}/{p.name}: corrupt json {e}")
                continue
            pid = payload.get("problem_id")
            pair = (env, pid)
            if pair in seen_pairs:
                dup_ids += 1
            seen_pairs.add(pair)
            for r in payload.get("probes", []):
                if int(r.get("probe_out_tokens", 0)) > 32:
                    cap_violations += 1
                if "error" in r:
                    error_rows += 1

    # per_problem.csv replayed pairs
    per_csv = ANALYSIS / "per_problem.csv"
    n_pairs = 0
    if per_csv.exists():
        with per_csv.open(encoding="utf-8") as f:
            n_pairs = sum(1 for _ in f) - 1

    g = {
        "certaindex_env_dirs": n_envs,
        "expected_env_dirs": 36,
        "envs_ok": n_envs == 36,
        "main_trajectories": total_main,
        "simple_trajectories": total_simple,
        "certaindex_trajectories": total_certaindex,
        "expected_per_bank": 3420,
        "main_ok": total_main == 3420,
        "simple_ok": total_simple == 3420,
        "certaindex_ok": total_certaindex == 3420,
        "duplicate_paired_identities": dup_ids,
        "duplicates_ok": dup_ids == 0,
        "corrupt_files": corrupt_files,
        "request_error_rows": error_rows,
        "errors_ok": corrupt_files == 0 and error_rows == 0,
        "cap_violations_gt_32": cap_violations,
        "caps_enforced_ok": cap_violations == 0,
        "settings_cap32_interval64_start64_patience3": settings_ok,
        "settings_ok": settings_ok and not any("setting" in e or "sha mismatch" in e for e in errors),
        "replayed_pairs": n_pairs,
        "expected_replayed_pairs": 3420,
        "pairs_replayed_ok": n_pairs == 3420,
        "errors": errors[:40],
        "n_error_entries": len(errors),
    }
    g["accept"] = all(v for k, v in g.items() if k.endswith("_ok") and k != "errors_ok") and g["errors_ok"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(g, indent=2)[:1600])
    return 0 if g["accept"] else 1


if __name__ == "__main__":
    sys.exit(main())
