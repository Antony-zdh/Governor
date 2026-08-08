"""B1: is 0/3,520 a string-matching artifact?

replay_rules judges consensus with normalize_answer() -- whitespace-collapsed
STRING equality. So "0.5" and "\\frac{1}{2}" read as a disagreement and reset
the streak. Meanwhile compute_probe_wording_v5 judges agreement with the
robust MATH grader. If probes routinely restate the same value in different
surface forms, the sweep's consensus signal is suppressed by parsing, not by
the model, and the negative result is an artifact.

Measures, on the committed dense_simple32 dev bank:
  (a) per problem, #distinct answer strings vs #distinct math-equivalence
      classes among them;
  (b) the share of adjacent valid-probe transitions that are a STRING switch
      but MATH-equal -- these are exactly the streak resets the sweep suffers
      and a math-equality consensus would not.
"""
import sys, json, statistics as st
from collections import defaultdict
from pathlib import Path
FC = Path("/Users/antonyzhao/code/Governor/benchmark/FalseConsensus")
sys.path.insert(0, str(FC / "report")); sys.path.insert(0, str(FC / "governor_v2")); sys.path.insert(0, str(FC / "related_work"))
import compute_boundary_consensus_v5 as B
import replay_rules as RR

split_map = RR.load_split_map(FC / "governor_v2/generated/split_manifest.json")
DEVID = B.DEVID

pair_cache = {}
def meq(a, b):
    if a == b:
        return True
    k = (a, b) if a <= b else (b, a)
    v = pair_cache.get(k)
    if v is None:
        v = B._eq_hardkill(a, b)
        pair_cache[k] = v
    return v


def classes(strs):
    """Greedy math-equivalence clustering of distinct answer strings."""
    reps = []
    for s in strs:
        for r in reps:
            if meq(s, r):
                break
        else:
            reps.append(s)
    return reps


if __name__ == "__main__":
    import multiprocessing as mp; mp.set_start_method("fork", force=True)
    n_prob = 0
    prob_collapsed = 0          # problems where math classes < string classes
    str_classes, math_classes = [], []
    trans_total = trans_switch = trans_switch_matheq = 0
    examples = []

    for main_run in RR.discover_runs(FC / "results/governor_v2", "development"):
        s = json.loads((main_run / "run_manifest.json").read_text())["run_settings"]
        if s["model"] not in DEVID:
            continue
        bench = str(s["dataset"])
        for traj_path in sorted((main_run / "traj").glob("problem_*.json")):
            pid = int(json.loads(traj_path.read_text())["problem_id"])
            if split_map.get((bench, pid)) != "dev":
                continue
            probes = RR.load_probes(main_run, pid)
            if not probes:
                continue
            seq = []
            for pr in sorted(probes, key=lambda p: int(p["token_position"])):
                a = RR.normalize_answer(pr.get("probe_answer"))
                if RR.valid_answer(a, bench, "schema"):
                    seq.append(a)
            if not seq:
                continue
            n_prob += 1
            distinct = list(dict.fromkeys(seq))
            reps = classes(distinct)
            str_classes.append(len(distinct)); math_classes.append(len(reps))
            if len(reps) < len(distinct):
                prob_collapsed += 1
                if len(examples) < 12:
                    examples.append((bench, pid, distinct[:6]))
            for x, y in zip(seq, seq[1:]):
                trans_total += 1
                if x != y:
                    trans_switch += 1
                    if meq(x, y):
                        trans_switch_matheq += 1
        print(f"  {main_run.parent.name}: {n_prob} problems so far", flush=True)

    print("\n=== B1: string-equality vs math-equality consensus, dev dense_simple32 ===")
    print(f"problems: {n_prob}")
    print(f"problems where math clustering collapses >=2 answer strings: "
          f"{prob_collapsed} ({100*prob_collapsed/n_prob:.2f}%)")
    print(f"mean distinct answer STRINGS per problem: {st.fmean(str_classes):.3f}")
    print(f"mean distinct MATH classes  per problem: {st.fmean(math_classes):.3f}")
    print(f"\nadjacent valid-probe transitions: {trans_total}")
    print(f"  string switches:              {trans_switch} ({100*trans_switch/trans_total:.2f}%)")
    print(f"  of those, MATH-equal:         {trans_switch_matheq} "
          f"({100*trans_switch_matheq/max(trans_switch,1):.2f}% of switches, "
          f"{100*trans_switch_matheq/trans_total:.3f}% of transitions)")
    print("\nexamples of collapsed problems:")
    for bench, pid, d in examples:
        print(f"  {bench}/{pid}: {d}")
