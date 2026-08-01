#!/usr/bin/env python3
"""v2 unified gate + selection over consensus and DEER metric rows.

Both consensus (replay_rules sweep) and DEER (deer_threshold_sweep) emit
per-environment rows with the same schema. This module aggregates each rule to
macro-mean-over-environments metrics and applies the v2 gates:

    eligible iff  total_accuracy_drop_pp   <= total_accuracy_drop_pp_max
             AND  total_saving_fraction    >= minimum_total_saving_fraction
             AND  positive_saving_fraction >= psf_floor

where every "total" is a macro-mean over the split's model x benchmark x seed
environments (protocol mandates macro, never problem-micro). Gates are evaluated
on the dev split (held-in selection target); train is reported alongside.

Outputs a JSON summary: per rule the dev/train totals, per gate the eligible
count and best point, split by method (consensus vs deer), and the dev Pareto
frontier over (total_drop minimize, total_saving maximize).
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent


def load_rows(paths: Sequence[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def aggregate(rows: Iterable[Mapping[str, Any]], split: str) -> dict[str, dict[str, Any]]:
    """rule_id -> macro-mean totals over the split's environments."""
    by_rule: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row["split"]) != split:
            continue
        by_rule[str(row["rule_id"])].append(row)
    out: dict[str, dict[str, Any]] = {}
    for rule_id, envs in by_rule.items():
        drops = [float(r["accuracy_drop_pp"]) for r in envs]
        savings = [float(r["saving_fraction"]) for r in envs]
        out[rule_id] = {
            "n_env": len(envs),
            "total_accuracy_drop_pp": statistics.fmean(drops),
            "total_saving_fraction": statistics.fmean(savings),
            "positive_saving_fraction": sum(s > 0 for s in savings) / len(savings),
            "method": str(envs[0].get("method", "consensus")),
        }
    return out


def pareto(points: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Non-dominated over (drop minimize, saving maximize)."""
    ordered = sorted(
        points,
        key=lambda p: (float(p["total_accuracy_drop_pp"]), -float(p["total_saving_fraction"])),
    )
    frontier: list[dict[str, Any]] = []
    best_saving = float("-inf")
    for p in ordered:
        s = float(p["total_saving_fraction"])
        if s > best_saving:
            frontier.append(dict(p))
            best_saving = s
    return frontier


def eligible(agg: Mapping[str, Any], gate: Mapping[str, Any]) -> bool:
    return (
        agg["total_accuracy_drop_pp"] <= float(gate["total_accuracy_drop_pp_max"])
        and agg["total_saving_fraction"] >= float(gate["minimum_total_saving_fraction"])
        and agg["positive_saving_fraction"]
        >= float(gate["minimum_fraction_environments_with_positive_saving"])
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocol", type=Path, default=HERE / "protocol_v2.json")
    ap.add_argument("--consensus", type=Path, nargs="+", required=True)
    ap.add_argument("--deer", type=Path, nargs="*", default=[])
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    gates = protocol["selection"]["operating_points"]

    consensus_rows = load_rows(args.consensus)
    deer_rows = load_rows(args.deer) if args.deer else []
    all_rows = consensus_rows + deer_rows

    dev = aggregate(all_rows, "dev")
    train = aggregate(all_rows, "train")

    # attach ids and merge train view
    records = []
    for rule_id, a in dev.items():
        rec = {"rule_id": rule_id, **a}
        t = train.get(rule_id)
        if t:
            rec["train_total_accuracy_drop_pp"] = t["total_accuracy_drop_pp"]
            rec["train_total_saving_fraction"] = t["total_saving_fraction"]
        records.append(rec)

    def split_method(recs, method_pred):
        return [r for r in recs if method_pred(r["method"])]

    is_deer = lambda m: m == "deer_direct_submit"
    is_consensus = lambda m: not is_deer(m)

    summary: dict[str, Any] = {
        "protocol_version": protocol["protocol_version"],
        "n_rules_dev": len(records),
        "n_consensus": len(split_method(records, is_consensus)),
        "n_deer": len(split_method(records, is_deer)),
        "gates": {},
        "pareto_dev": {},
    }

    for gate in gates:
        name = gate["name"]
        gate_out: dict[str, Any] = {"gate": dict(gate)}
        for label, pred in (("consensus", is_consensus), ("deer", is_deer)):
            elig = [r for r in split_method(records, pred) if eligible(r, gate)]
            elig.sort(key=lambda r: (-r["total_saving_fraction"], r["total_accuracy_drop_pp"]))
            gate_out[label] = {
                "eligible_count": len(elig),
                "best": elig[0] if elig else None,
            }
        summary["gates"][name] = gate_out

    for label, pred in (("consensus", is_consensus), ("deer", is_deer)):
        fr = pareto(split_method(records, pred))
        summary["pareto_dev"][label] = [
            {
                "rule_id": p["rule_id"],
                "total_accuracy_drop_pp": round(p["total_accuracy_drop_pp"], 3),
                "total_saving_fraction": round(p["total_saving_fraction"], 4),
                "positive_saving_fraction": round(p["positive_saving_fraction"], 3),
            }
            for p in fr
        ]

    args.output.write_text(json.dumps(summary, indent=1), encoding="utf-8")

    # console digest
    print(f"rules: consensus={summary['n_consensus']} deer={summary['n_deer']}")
    for name, g in summary["gates"].items():
        c = g["consensus"]["eligible_count"]
        d = g["deer"]["eligible_count"]
        print(f"[{name}] consensus_pass={c}  deer_pass={d}")
        cb, db = g["consensus"]["best"], g["deer"]["best"]
        if cb:
            print(f"    consensus best: drop={cb['total_accuracy_drop_pp']:.2f}pp "
                  f"save={cb['total_saving_fraction']*100:.1f}% psf={cb['positive_saving_fraction']:.2f} {cb['rule_id'][:40]}")
        if db:
            print(f"    deer best:      drop={db['total_accuracy_drop_pp']:.2f}pp "
                  f"save={db['total_saving_fraction']*100:.1f}% psf={db['positive_saving_fraction']:.2f} {db['rule_id']}")


if __name__ == "__main__":
    main()
