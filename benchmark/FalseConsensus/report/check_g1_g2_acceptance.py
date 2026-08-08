#!/usr/bin/env python3
"""Acceptance checks for the G1/G2 probe banks (GOAL §4 integrity).

Verifies:
  G1 dense_certaindex32: 18 dirs, dev counts, token_position lists exactly
    equal to the paired dense_simple32, zero probe_out>32 / errors / dup
    (problem_id, token_position), manifest settings, and that no frozen
    dense_simple32 bank changed.
  G2 boundary_simple32: 18 dirs, manifest probe_style/probe_schedule,
    boundary positions within trajectory length, zero probe_out>32 / errors.

Exit 0 iff all pass; prints a per-check report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
RES = FC / "results"
GOV = FC / "governor_v2"
EXPECT = {"math500": 100, "amc23": 8, "aime24": 6}


def load_probes(bank_dir: Path, pid: int):
    path = bank_dir / "probes" / f"problem_{pid}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check_g1():
    fails = []
    envs = sorted((RES / "governor_v2").glob("development__*/dense_certaindex32"))
    if len(envs) != 18:
        fails.append(f"expected 18 dense_certaindex32 dirs, found {len(envs)}")
    total_probes = 0
    for env in envs:
        name = env.parent.name
        bench = next(b for b in EXPECT if b in name)
        manifest = json.loads((env / "probe_manifest.json").read_text())
        s = manifest["probe_settings"]
        if s["probe_style"] != "certaindex":
            fails.append(f"{name}: probe_style != certaindex")
        if s["probe_tokens"] != 32 or s["dense_interval"] != 64 \
                or s["start_token"] != 64:
            fails.append(f"{name}: manifest settings wrong")
        simple_dir = env.parent / "dense_simple32"
        n = 0
        for pf in sorted((env / "probes").glob("problem_*.json")):
            d = json.loads(pf.read_text())
            pid = d["problem_id"]
            n += 1
            pos_c = [p["token_position"] for p in d["probes"]]
            if len(pos_c) != len(set(pos_c)):
                fails.append(f"{name}/p{pid}: duplicate token_position")
            for p in d["probes"]:
                total_probes += 1
                if p.get("probe_out_tokens", 0) > 32:
                    fails.append(f"{name}/p{pid}: probe_out>32")
                if p.get("error") or p.get("request_error"):
                    fails.append(f"{name}/p{pid}: request error row")
            sp = load_probes(simple_dir, pid)
            if sp is not None:
                pos_s = [p["token_position"] for p in sp["probes"]]
                if pos_c != pos_s:
                    fails.append(f"{name}/p{pid}: position list != dense_simple32")
        if n < EXPECT[bench]:
            fails.append(f"{name}: {n} problems < {EXPECT[bench]}")
    print(f"[G1] {len(envs)} dirs, {total_probes} probes total")
    return fails


def check_g2():
    fails = []
    envs = sorted((RES / "governor_v2").glob("development__*/boundary_simple32"))
    if len(envs) != 18:
        fails.append(f"expected 18 boundary_simple32 dirs, found {len(envs)}")
    total_probes = 0
    for env in envs:
        name = env.parent.name
        manifest = json.loads((env / "probe_manifest.json").read_text())
        s = manifest["probe_settings"]
        if s["probe_style"] != "simple":
            fails.append(f"{name}: probe_style != simple")
        if s.get("probe_schedule") != "deer_boundary":
            fails.append(f"{name}: probe_schedule != deer_boundary")
        for pf in sorted((env / "probes").glob("problem_*.json")):
            d = json.loads(pf.read_text())
            pid = d["problem_id"]
            n_tok = d.get("main_token_count_reencoded", 0)
            for p in d["probes"]:
                total_probes += 1
                if p.get("probe_out_tokens", 0) > 32:
                    fails.append(f"{name}/p{pid}: probe_out>32")
                if p.get("error") or p.get("request_error"):
                    fails.append(f"{name}/p{pid}: request error row")
                if int(p["token_position"]) > n_tok:
                    fails.append(f"{name}/p{pid}: boundary pos > trajectory len")
    print(f"[G2] {len(envs)} dirs, {total_probes} probes total")
    return fails


def main():
    all_fails = []
    print("== G1 ==")
    all_fails += check_g1()
    print("== G2 ==")
    all_fails += check_g2()
    # frozen data integrity: no dense_simple32 modified
    import subprocess
    diff = subprocess.run(
        ["git", "status", "--porcelain",
         str(RES / "governor_v2")],
        cwd=HERE.parents[2], capture_output=True, text=True)
    mod = [l for l in diff.stdout.splitlines()
           if "dense_simple32" in l and l.startswith("  M"[:0] or " M") or
           ("dense_simple32" in l and l.strip().startswith("M"))]
    if mod:
        all_fails.append(f"frozen dense_simple32 modified: {mod}")
    else:
        print("[frozen] no dense_simple32 modified (clean)")
    if all_fails:
        print(f"\nFAIL ({len(all_fails)} issues):")
        for f in all_fails[:20]:
            print("  -", f)
        sys.exit(1)
    print("\nALL ACCEPTANCE CHECKS PASS")


if __name__ == "__main__":
    main()
