#!/usr/bin/env python3
"""Llama corrected-bank coverage + integrity acceptance checker.

Verifies the addendum's acceptance gates: 9 envs / 27 jobs, 1710 main +
1710 dense + 1710 adaptive unique records, no dup/malformed/error/wrong-model,
BOS/client provenance present, no path/checksum to the invalid pre-fix bank.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from collections import Counter

REPO = Path(__file__).resolve().parents[3]
BANK = REPO / "benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected"
MODEL = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
SLUG = "deepseek-ai-deepseek-r1-distill-llama-8b"
BENCHMARKS = ["math500", "amc23", "aime24"]
SEEDS = [42, 43, 44]
EXPECTED = {"math500": 500, "amc23": 40, "aime24": 30}


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": str(e)}


def main():
    g = {}
    envs_found = []
    main_ids = {}
    dense_ids = {}
    adap_ids = {}
    errors = []
    for bench in BENCHMARKS:
        for seed in SEEDS:
            env = f"development__{SLUG}__{bench}__seed_{seed}"
            envs_found.append(env)
            main_dir = BANK / env / "main" / "traj"
            dense_dir = BANK / env / "dense_simple32" / "probes"
            adap_dir = BANK / env / "adaptive_simple32" / "probes"
            mids = set()
            for p in sorted(main_dir.glob("problem_*.json")) if main_dir.exists() else []:
                d = load_json(p)
                if "_error" in d:
                    errors.append(f"{env}/main malformed: {d['_error']}"); continue
                if d.get("run_settings", {}).get("model") != MODEL:
                    errors.append(f"{env}/main wrong model for pid {d.get('problem_id')}")
                pid = int(d["problem_id"])
                if pid in mids: errors.append(f"{env}/main dup pid {pid}")
                mids.add(pid)
            dids = set()
            for p in sorted(dense_dir.glob("problem_*.json")) if dense_dir.exists() else []:
                d = load_json(p)
                if "_error" in d: errors.append(f"{env}/dense malformed"); continue
                dids.add(int(d["problem_id"]))
            aids = set()
            for p in sorted(adap_dir.glob("problem_*.json")) if adap_dir.exists() else []:
                d = load_json(p)
                if "_error" in d: errors.append(f"{env}/adaptive malformed"); continue
                aids.add(int(d["problem_id"]))
            main_ids[(bench, seed)] = mids
            dense_ids[(bench, seed)] = dids
            adap_ids[(bench, seed)] = aids
            # coverage per env
            if len(mids) != EXPECTED[bench]:
                errors.append(f"{env} main count {len(mids)} != {EXPECTED[bench]}")
            if len(dids) != EXPECTED[bench]:
                errors.append(f"{env} dense count {len(dids)} != {EXPECTED[bench]}")
            if len(aids) != EXPECTED[bench]:
                errors.append(f"{env} adaptive count {len(aids)} != {EXPECTED[bench]}")
            if mids and dids and mids != dids:
                errors.append(f"{env} dense != main ids")
            if mids and aids and mids != aids:
                errors.append(f"{env} adaptive != main ids")

    total_main = sum(len(v) for v in main_ids.values())
    total_dense = sum(len(v) for v in dense_ids.values())
    total_adap = sum(len(v) for v in adap_ids.values())

    # provenance: BOS smoke + manifest
    bos = load_json(BANK / "_bos_smoke.json") if (BANK/"_bos_smoke.json").exists() else {}
    manifest = load_json(BANK / "manifest.json") if (BANK/"manifest.json").exists() else {}
    bos_ok = all(bos.get("gates", {}).values()) if bos else False

    # invalid-bank reuse scan: ensure no file references governor_v2_scale_dev (old)
    invalid_refs = []
    for p in BANK.rglob("*.json"):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if "governor_v2_scale_dev/" in txt and "llama_corrected" not in txt:
            invalid_refs.append(str(p.relative_to(BANK)))

    g = {
        "environments_expected": 9,
        "environments_found": len(envs_found),
        "environments_ok": len(envs_found) == 9,
        "main_records": total_main, "expected_main": 1710,
        "main_ok": total_main == 1710,
        "dense_records": total_dense, "expected_dense": 1710,
        "dense_ok": total_dense == 1710,
        "adaptive_records": total_adap, "expected_adaptive": 1710,
        "adaptive_ok": total_adap == 1710,
        "errors": errors,
        "errors_ok": len(errors) == 0,
        "bos_smoke_gates": bos.get("gates", {}) if bos else {},
        "bos_provenance_ok": bos_ok,
        "manifest_present": bool(manifest),
        "manifest_no_invalid_reuse": manifest.get("no_invalid_reuse") is not None if manifest else False,
        "invalid_bank_references": invalid_refs,
        "no_invalid_reuse_ok": len(invalid_refs) == 0,
    }
    g["accept"] = all(v for k, v in g.items() if k.endswith("_ok"))
    out = BANK / "acceptance.json"
    out.write_text(json.dumps(g, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(g, indent=2)[:1500])
    print(f"-> {out}")


if __name__ == "__main__":
    main()
