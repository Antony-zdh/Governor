"""A4b: does the 0/3,520 negative result survive excluding budget-hitters?

Budget-hitting trajectories are scored baseline_correct=False and
baseline_tokens=budget, so any stop on them is free saving with no accuracy
cost. They are 8.22% of dev problems (macro) but carry 19.52% of baseline
tokens. Recompute the committed fixed-grid consensus frontier over the
non-capped subset only, via the same fresh-replay path already validated to
reproduce the committed archive to 16 digits."""
import sys, json
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_boundary_consensus_v5 as B


def noncap_pids(env_dir):
    """Problems in the committed dense_simple32 bank whose frozen trajectory
    finished naturally within the selection budget."""
    man = json.loads((env_dir / "main" / "run_manifest.json").read_text())
    budget = B.SEL[str(man["run_settings"]["dataset"])]
    keep = set()
    for p in (env_dir / "dense_simple32" / "probes").glob("problem_*.json"):
        pid = int(json.loads(p.read_text())["problem_id"])
        t = json.loads((env_dir / "main" / "traj" / f"problem_{pid}.json").read_text())
        if t["finished_naturally"] and int(t["tokens_used"]) <= budget:
            keep.add(pid)
    return keep


if __name__ == "__main__":
    import multiprocessing as mp; mp.set_start_method("fork", force=True)
    rules = str(B.BANK / "candidate_rules_v2.jsonl.gz")
    B._dense659_problem_ids = noncap_pids
    out = B.committed_fixed_grid_frontier_659(rules)
    print("\n=== fresh replay, NON-CAPPED problems only ===")
    print(" problems:", out.get("n_problems"), " envs:", out.get("n_envs"))
    print(" gates:", out["gate_clearers"])
    print(" frontier:", json.dumps(out["frontier"], indent=1))
