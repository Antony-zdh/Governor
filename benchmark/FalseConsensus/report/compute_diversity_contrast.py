#!/usr/bin/env python3
"""Self-consistency vs. self-consensus: does agreement mean the same thing?

Self-consistency (Wang et al., 2023) draws its guarantee from *diverse,
independently sampled* reasoning paths: a hard problem admits many routes to
one correct answer, so when independent routes agree, the agreement is
evidence. Probe-based early exit reuses the word "consensus" for something
structurally different -- repeated reads of a *single* trajectory, every probe
conditioned on the same prefix. Agreement there measures prefix stability, not
independent corroboration.

We have both objects on the same problems, so the comparison is direct:

  SELF-CONSISTENCY (k=3): the final answers of three independently sampled
      trajectories (seeds 42/43/44) for the same problem.
  SELF-CONSENSUS (W=3):   three consecutive probes inside ONE trajectory.

For each we ask the same question: given that the three agree, how often is the
agreed answer correct? If independence is what makes agreement informative,
P(correct | agree) should be much higher for self-consistency -- and the gap is
the mechanism, measured rather than argued.

To keep the comparison honest we also report self-consensus measured at the END
of the trajectory (the last three probes), which is the most favourable
position for it, alongside the first-agreement position an online rule must use.

Output: report/figures/gen/diversity_contrast.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FC = HERE.parent
GOV = FC / "governor_v2"
RES = FC / "results"
CACHE = HERE / "figures" / "gen" / "diversity_contrast.json"

sys.path.insert(0, str(GOV))
import replay_rules as RR  # noqa: E402

SEL = {"math500": 16384, "amc23": 16384, "aime24": 32768}
DEVID = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "Qwen/Qwen3-8B"}
SEEDS = (42, 43, 44)
W = 3


def agree(vals):
    """All non-empty and mutually equal under the robust grader."""
    if any(not v for v in vals):
        return False
    return all(RR.answers_equal(vals[0], v) for v in vals[1:])


def main():
    split_map = RR.load_split_map(GOV / "generated/split_manifest.json")

    # (model, benchmark, problem_id) -> {seed: {...}}
    per = defaultdict(dict)
    for main_run in RR.discover_runs(RES / "governor_v2", "development"):
        man = json.loads((main_run / "run_manifest.json").read_text())
        s = man["run_settings"]
        if s["model"] not in DEVID:
            continue
        bench = s["dataset"]
        budget = SEL[bench]
        seed = int(s.get("seed", s.get("base_seed", -1)))
        for tp in sorted((main_run / "traj").glob("problem_*.json")):
            t = json.loads(tp.read_text(encoding="utf-8"))
            pid = int(t["problem_id"])
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = [p for p in RR.load_probes(main_run, pid)
                      if int(p["token_position"]) <= budget]
            probes.sort(key=lambda z: int(z["token_position"]))
            per[(s["model"], bench, pid)][seed] = {
                "target": t["target"],
                "final": t.get("final_answer"),
                "final_ok": RR.answers_equal(t.get("final_answer"), t["target"]),
                "probes": [RR.normalize_answer(p.get("probe_answer")) for p in probes],
            }

    sc_agree = sc_correct = 0          # self-consistency, k=3 independent paths
    cons_first = cons_first_ok = 0     # self-consensus, first W agreeing probes
    cons_last = cons_last_ok = 0       # self-consensus, last W probes
    n_problems = 0
    base_ok = 0

    for key, byseed in per.items():
        if not all(sd in byseed for sd in SEEDS):
            continue
        n_problems += 1
        tgt = byseed[SEEDS[0]]["target"]
        finals = [byseed[sd]["final"] for sd in SEEDS]
        base_ok += sum(byseed[sd]["final_ok"] for sd in SEEDS) / len(SEEDS)

        # --- self-consistency: three independent trajectories --------------
        if agree(finals):
            sc_agree += 1
            sc_correct += bool(RR.answers_equal(finals[0], tgt))

        # --- self-consensus: inside each single trajectory -----------------
        for sd in SEEDS:
            pr = byseed[sd]["probes"]
            # first window of W consecutive agreeing non-empty probes
            for i in range(len(pr) - W + 1):
                win = pr[i:i + W]
                if agree(win):
                    cons_first += 1
                    cons_first_ok += bool(RR.answers_equal(win[0], tgt))
                    break
            # the last W probes -- the most favourable position for it
            if len(pr) >= W and agree(pr[-W:]):
                cons_last += 1
                cons_last_ok += bool(RR.answers_equal(pr[-1], tgt))

    res = {
        "n_problems": n_problems,
        "n_trajectories": n_problems * len(SEEDS),
        "baseline_accuracy": 100 * base_ok / n_problems if n_problems else 0.0,
        "self_consistency_k3": {
            "n_agree": sc_agree,
            "agree_rate": 100 * sc_agree / n_problems if n_problems else 0.0,
            "acc_given_agree": 100 * sc_correct / sc_agree if sc_agree else None,
        },
        "self_consensus_first_w3": {
            "n_agree": cons_first,
            "agree_rate": 100 * cons_first / (n_problems * len(SEEDS)),
            "acc_given_agree": 100 * cons_first_ok / cons_first if cons_first else None,
        },
        "self_consensus_last_w3": {
            "n_agree": cons_last,
            "agree_rate": 100 * cons_last / (n_problems * len(SEEDS)),
            "acc_given_agree": 100 * cons_last_ok / cons_last if cons_last else None,
        },
    }

    print(f"dev problems with all 3 seeds: {res['n_problems']}"
          f"  ({res['n_trajectories']} trajectories)")
    print(f"baseline accuracy: {res['baseline_accuracy']:.1f}%\n")
    for k, lab in (("self_consistency_k3",
                    "SELF-CONSISTENCY  k=3 independent trajectories agree"),
                   ("self_consensus_first_w3",
                    "SELF-CONSENSUS    first 3 consecutive probes agree"),
                   ("self_consensus_last_w3",
                    "SELF-CONSENSUS    last 3 probes agree (best case)")):
        d = res[k]
        acc = d["acc_given_agree"]
        print(f"{lab}\n    fires on {d['agree_rate']:5.1f}% of cases"
              f"   →  correct {acc:5.1f}%" if acc is not None else lab)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(res, indent=1))
    print("\nwrote", CACHE)


if __name__ == "__main__":
    main()
