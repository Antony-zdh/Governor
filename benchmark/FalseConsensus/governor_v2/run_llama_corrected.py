#!/usr/bin/env python3
"""Drive the corrected post-BOS-fix Llama-8B multi-seed scale-dev collection.

Reads the authoritative 27 Llama jobs from origin/main's
``matrix_scale_dev.jsonl`` (provided as --origin-matrix) and rewrites each
job's ``--url`` and output paths into the isolated, integration-safe
``governor_v2_scale_dev_llama_corrected`` namespace, so that NO file from the
invalid pre-BOS Llama bank is ever read or written. Dense and adaptive stages
read main/dense outputs ONLY from the corrected namespace.

Stages run in dependency order: all main_generation, then all dense_probe,
then all adaptive_probe. Each underlying collector resumes by skipping
existing per-problem files, so the driver is safely re-runnable.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CORR = REPO / "benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected"
OLD = "benchmark/FalseConsensus/results/governor_v2_scale_dev"


def rewrite_command(cmd: list[str], url: str) -> list[str]:
    out = list(cmd)
    def replace_flag(flag, value):
        if flag in out:
            out[out.index(flag) + 1] = value
    replace_flag("--url", url)
    # remap every output-ish path from scale_dev -> corrected namespace
    for flag in ("--output", "--main-run", "--dense-probe-bank"):
        if flag in out:
            i = out.index(flag)
            out[i + 1] = out[i + 1].replace(OLD,
                                            "benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origin-matrix", type=Path, required=True)
    ap.add_argument("--url", default="http://127.0.0.1:18000/v1")
    ap.add_argument("--phase", default="all", choices=["all","main","dense","adaptive"])
    ap.add_argument("--python", default="/localdata/dzhaoah/gov-venv/bin/python")
    args = ap.parse_args()

    jobs = [json.loads(l) for l in args.origin_matrix.read_text().splitlines()
            if l.strip()]
    llama = [j for j in jobs if "llama" in j["model"].lower()]
    assert len(llama) == 27, f"expected 27 llama jobs, got {len(llama)}"

    # dependency order
    order = {"main_generation": 0, "dense_probe": 1, "adaptive_probe": 2}
    stage_filter = {"main": ["main_generation"], "dense": ["dense_probe"],
                    "adaptive": ["adaptive_probe"],
                    "all": ["main_generation","dense_probe","adaptive_probe"]}[args.phase]
    llama = [j for j in llama if j["stage"] in stage_filter]
    llama.sort(key=lambda j: (order[j["stage"]], j["benchmark"], j["seed"]))

    for j in llama:
        cmd = rewrite_command(j["command"], args.url)
        # matrix command[0] is the literal "python" interpreter token; replace
        # it with the full venv python path.
        cmd[0] = args.python
        # ensure output dirs exist
        out_idx = cmd.index("--output") + 1
        Path(REPO / cmd[out_idx]).parent.mkdir(parents=True, exist_ok=True)
        print(f"\n=== {j['job_id']} ===", flush=True)
        print(" ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=str(REPO))
        if r.returncode != 0:
            print(f"[ERROR] job {j['job_id']} exited {r.returncode}", flush=True)
            sys.exit(r.returncode)
    print("\n=== phase complete:", args.phase, "===", flush=True)


if __name__ == "__main__":
    main()
