#!/usr/bin/env python3
"""Build the v2 unified-consensus protocol and candidate rule set.

Design (per CORE_PAPER_FLOW.md + user redesign 2026-08-01):
  * The consensus signal collapses to TWO hyperparameters:
        window_size  W = evidence.window_probes
        share_thr    s = evidence.dominant_share_threshold
    expressed with the ``window_share`` evidence family (W=1 == latest,
    s=1.0 == "last W probes all agree"). The entropy family and the standalone
    persistence dimension are removed (subsumed by (W, s)); history is dropped.
  * Two rule families remain, differing only in probe schedule:
        consensus_fixed     -- fixed-interval probing
        consensus_adaptive  -- event-triggered probing (kept as the
                               "sophisticated" comparator)
  * Operational axes kept: probe interval (fixed only), validity, maturity
    (unified to min_tokens), certainty.
  * New gates: cut TOTAL (macro-mean) accuracy drop, then TOTAL (macro-mean)
    net token saving, then positive-saving fraction.

Grids (user-approved 2026-08-01):
    interval  {64,128,256,512}          (fixed family)
    maturity  min_tokens {0,512,1024,2048,4096}
    W         {1,3,5,8,12,16,24,30}
    s         {0.6,0.8,1.0}
    certainty {False,True}
    validity  {nonempty,schema}

Writes protocol_v2.json and generated/candidate_rules_v2.jsonl.
Leaves the frozen protocol.json untouched.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

try:
    from .rule_schema import expand_search_space
except ImportError:
    from rule_schema import expand_search_space  # type: ignore

HERE = Path(__file__).resolve().parent

INTERVALS = [64, 128, 256, 512]
MATURITY = [0, 512, 1024, 2048, 4096]
WINDOWS = [1, 3, 5, 8, 12, 16, 24, 30]
SHARES = [0.6, 0.8, 1.0]

# Event-trigger probe schedules carried over verbatim from the original
# adaptive_event_probe family (the "sophisticated" comparator).
EVENT_SCHEDULES = None  # filled from protocol.json


def _base(schedule: dict) -> dict:
    return {
        "probe": {"style": "simple", "output_cap": 32, "schedule": schedule},
        "validity": {"mode": "schema"},
        "maturity": {
            "kind": "fixed_tokens",
            "minimum_tokens": 0,
            "minimum_budget_fraction": 0.0,
            "online_instability_floor_tokens": 0,
        },
        "evidence": {
            "family": "window_share",
            "window_probes": 5,
            "minimum_valid_probes": 1,
            "dominant_share_threshold": 1.0,
            "entropy_threshold": None,
            "entropy_scope": "window",
        },
        "persistence": {
            "minimum_consistent_accepts": 1,
            "minimum_consensus_span_tokens": 0,
        },
        "certainty": {"enabled": False, "minimum_certain_fraction": 1.0},
        "history": {
            "maximum_switches": None,
            "switch_window": {"kind": "tokens", "size": 2048},
            "minimum_stable_span_tokens": 0,
        },
    }


CONSENSUS_AXES = {
    "validity.mode": ["nonempty", "schema"],
    "maturity.minimum_tokens": MATURITY,
    "evidence.window_probes": WINDOWS,
    "evidence.dominant_share_threshold": SHARES,
    "certainty.enabled": [False, True],
}


def build_protocol() -> dict:
    protocol = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    p = copy.deepcopy(protocol)
    p["protocol_version"] = protocol["protocol_version"] + "+unified-ws-v2"
    p["status"] = (
        "v2 revision: unified (window_size, share_threshold) consensus signal; "
        "fixed + adaptive probe families; total-drop/total-saving/psf gates; "
        "DEER swept jointly (trial-answer-submit)"
    )

    # Pull the event schedules from the original adaptive template.
    event_scheds = []
    for t in protocol["rule_search"]["templates"]:
        if t["name"] == "adaptive_event_probe":
            event_scheds = t["axes"]["probe.schedule"]
    if not event_scheds:
        raise RuntimeError("could not find event schedules in protocol.json")

    fixed_schedule = {
        "kind": "fixed",
        "start_token": 128,
        "interval_tokens": 128,
        "phases": [],
        "agreement_trigger_count": None,
        "agreement_interval_tokens": None,
    }

    fixed_tmpl = {
        "name": "consensus_fixed",
        "base": _base(fixed_schedule),
        "axes": {
            "probe.schedule.interval_tokens": INTERVALS,
            **CONSENSUS_AXES,
        },
    }
    adaptive_tmpl = {
        "name": "consensus_adaptive",
        "base": _base(copy.deepcopy(event_scheds[0])),
        "axes": {
            "probe.schedule": event_scheds,
            **CONSENSUS_AXES,
        },
    }

    p["rule_search"]["templates"] = [fixed_tmpl, adaptive_tmpl]
    p["rule_search"]["uniform_dimensions"] = protocol["rule_search"][
        "uniform_dimensions"
    ]

    # New gates.
    p["selection"]["operating_points"] = [
        {
            "name": "conservative",
            "total_accuracy_drop_pp_max": 1.0,
            "minimum_total_saving_fraction": 0.10,
            "minimum_fraction_environments_with_positive_saving": 0.8,
        },
        {
            "name": "balanced",
            "total_accuracy_drop_pp_max": 2.0,
            "minimum_total_saving_fraction": 0.20,
            "minimum_fraction_environments_with_positive_saving": 0.8,
        },
        {
            "name": "token_efficient",
            "total_accuracy_drop_pp_max": 3.5,
            "minimum_total_saving_fraction": 0.30,
            "minimum_fraction_environments_with_positive_saving": 0.7,
        },
    ]
    p["selection"]["gate_semantics"] = (
        "v2: eligible iff total_accuracy_drop_pp (macro-mean over dev "
        "environments) <= total_accuracy_drop_pp_max AND total_saving_fraction "
        "(macro-mean net) >= minimum_total_saving_fraction AND "
        "positive_saving_fraction >= floor; ranked by total_saving_fraction desc"
    )
    p["selection"]["ranking_metric"] = "macro-mean net total-token saving"
    p["selection"]["pareto_objectives"] = {
        "maximize": "macro-mean net total-token saving",
        "minimize": ["macro-mean accuracy drop"],
        "equivalent_metric_tie_breaker": "lower complexity, then lexical rule_id",
    }
    return p


def main() -> None:
    p = build_protocol()
    out = HERE / "protocol_v2.json"
    out.write_text(json.dumps(p, indent=1), encoding="utf-8")

    rules = expand_search_space(p["rule_search"])
    # Drop redundant W=1 rules with s != 1.0 (a one-probe window has share 1.0
    # by construction, so those s-values produce behaviourally identical rules).
    kept = [
        r
        for r in rules
        if not (
            r.evidence.window_probes == 1
            and r.evidence.dominant_share_threshold != 1.0
        )
    ]
    rules_out = HERE / "generated/candidate_rules_v2.jsonl"
    with rules_out.open("w", encoding="utf-8") as fh:
        for r in kept:
            fh.write(json.dumps(r.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")

    by_fam: dict[str, int] = {}
    for r in kept:
        fam = r.metadata.get("template", "?")
        by_fam[fam] = by_fam.get(fam, 0) + 1
    print(json.dumps({"protocol": str(out)}))
    print(f"raw expanded = {len(rules)}, kept after W=1 dedup = {len(kept)}")
    for fam, n in sorted(by_fam.items()):
        print(f"  {fam}: {n}")
    print(f"wrote {rules_out}")


if __name__ == "__main__":
    main()
