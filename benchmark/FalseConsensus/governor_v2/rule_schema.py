#!/usr/bin/env python3
"""Uniform, model-agnostic schema for Governor v2 stopping rules.

The schema separates seven optimizable rule dimensions from environment
dimensions such as model, benchmark, seed, and problem difficulty.  Every rule
uses the same nested representation, including inactive dimensions, so rule
search, reporting, and ablation can share one format.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


RULE_DIMENSIONS: Tuple[str, ...] = (
    "probe",
    "validity",
    "maturity",
    "evidence",
    "persistence",
    "certainty",
    "history",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class ProbeSchedule:
    kind: str = "fixed"
    start_token: int = 128
    interval_tokens: int = 128
    phases: Tuple[Tuple[int, int], ...] = ()
    agreement_trigger_count: Optional[int] = None
    agreement_interval_tokens: Optional[int] = None

    def validate(self) -> None:
        _require(
            self.kind in {"fixed", "phased", "agreement_adaptive"},
            f"unsupported probe schedule kind: {self.kind}",
        )
        _require(self.start_token > 0, "probe start_token must be positive")
        _require(
            self.interval_tokens > 0,
            "probe interval_tokens must be positive",
        )
        previous_until = 0
        for until_token, interval in self.phases:
            _require(
                until_token > previous_until,
                "probe phase boundaries must be strictly increasing",
            )
            _require(interval > 0, "probe phase intervals must be positive")
            previous_until = until_token
        if self.kind == "agreement_adaptive":
            _require(
                self.agreement_trigger_count is not None
                and self.agreement_trigger_count >= 2,
                "agreement_adaptive requires agreement_trigger_count >= 2",
            )
            _require(
                self.agreement_interval_tokens is not None
                and self.agreement_interval_tokens > 0,
                "agreement_adaptive requires a positive agreement interval",
            )


@dataclass(frozen=True)
class ProbeSpec:
    style: str = "simple"
    output_cap: int = 32
    schedule: ProbeSchedule = field(default_factory=ProbeSchedule)

    def validate(self) -> None:
        _require(self.style == "simple", "Governor v2 currently freezes simple")
        _require(self.output_cap > 0, "probe output_cap must be positive")
        self.schedule.validate()


@dataclass(frozen=True)
class ValiditySpec:
    mode: str = "schema"

    def validate(self) -> None:
        _require(
            self.mode in {"nonempty", "schema"},
            f"unsupported validity mode: {self.mode}",
        )


@dataclass(frozen=True)
class MaturitySpec:
    kind: str = "none"
    minimum_tokens: int = 0
    minimum_budget_fraction: float = 0.0
    online_instability_floor_tokens: int = 0

    def validate(self) -> None:
        _require(
            self.kind
            in {"none", "fixed_tokens", "budget_fraction", "online_instability"},
            f"unsupported maturity kind: {self.kind}",
        )
        _require(self.minimum_tokens >= 0, "minimum_tokens cannot be negative")
        _require(
            0.0 <= self.minimum_budget_fraction <= 1.0,
            "minimum_budget_fraction must lie in [0, 1]",
        )
        _require(
            self.online_instability_floor_tokens >= 0,
            "online instability floor cannot be negative",
        )


@dataclass(frozen=True)
class EvidenceSpec:
    family: str = "latest"
    window_probes: int = 1
    minimum_valid_probes: int = 1
    dominant_share_threshold: float = 1.0
    entropy_threshold: Optional[float] = None
    entropy_scope: str = "window"

    def validate(self) -> None:
        _require(
            self.family in {"latest", "window_share", "entropy"},
            f"unsupported evidence family: {self.family}",
        )
        _require(self.window_probes >= 1, "window_probes must be >= 1")
        _require(
            1 <= self.minimum_valid_probes <= self.window_probes,
            "minimum_valid_probes must lie in [1, window_probes]",
        )
        _require(
            0.0 < self.dominant_share_threshold <= 1.0,
            "dominant_share_threshold must lie in (0, 1]",
        )
        _require(
            self.entropy_scope in {"window", "history"},
            "entropy_scope must be window or history",
        )
        if self.family == "latest":
            _require(
                self.window_probes == 1 and self.minimum_valid_probes == 1,
                "latest evidence must use a one-probe window",
            )
        if self.family == "entropy":
            _require(
                self.entropy_threshold is not None
                and 0.0 <= self.entropy_threshold <= 1.0,
                "entropy evidence requires a threshold in [0, 1]",
            )


@dataclass(frozen=True)
class PersistenceSpec:
    minimum_consistent_accepts: int = 1
    minimum_consensus_span_tokens: int = 0

    def validate(self) -> None:
        _require(
            self.minimum_consistent_accepts >= 1,
            "minimum_consistent_accepts must be >= 1",
        )
        _require(
            self.minimum_consensus_span_tokens >= 0,
            "minimum_consensus_span_tokens cannot be negative",
        )


@dataclass(frozen=True)
class CertaintySpec:
    enabled: bool = False
    minimum_certain_fraction: float = 0.0

    def validate(self) -> None:
        _require(
            0.0 <= self.minimum_certain_fraction <= 1.0,
            "minimum_certain_fraction must lie in [0, 1]",
        )
        if self.enabled:
            _require(
                self.minimum_certain_fraction > 0.0,
                "enabled certainty requires a positive fraction",
            )


@dataclass(frozen=True)
class HistoryWindowSpec:
    kind: str = "tokens"
    size: int = 2048

    def validate(self) -> None:
        _require(
            self.kind in {"tokens", "probes"},
            "history switch window kind must be tokens or probes",
        )
        _require(self.size >= 1, "history switch window size must be positive")


@dataclass(frozen=True)
class HistorySpec:
    maximum_switches: Optional[int] = None
    switch_window: HistoryWindowSpec = field(
        default_factory=HistoryWindowSpec
    )
    minimum_stable_span_tokens: int = 0

    def validate(self) -> None:
        _require(
            self.maximum_switches is None or self.maximum_switches >= 0,
            "maximum_switches cannot be negative",
        )
        self.switch_window.validate()
        _require(
            self.minimum_stable_span_tokens >= 0,
            "minimum_stable_span_tokens cannot be negative",
        )


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    probe: ProbeSpec = field(default_factory=ProbeSpec)
    validity: ValiditySpec = field(default_factory=ValiditySpec)
    maturity: MaturitySpec = field(default_factory=MaturitySpec)
    evidence: EvidenceSpec = field(default_factory=EvidenceSpec)
    persistence: PersistenceSpec = field(default_factory=PersistenceSpec)
    certainty: CertaintySpec = field(default_factory=CertaintySpec)
    history: HistorySpec = field(default_factory=HistorySpec)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _require(bool(self.rule_id), "rule_id cannot be empty")
        self.probe.validate()
        self.validity.validate()
        self.maturity.validate()
        self.evidence.validate()
        self.persistence.validate()
        self.certainty.validate()
        self.history.validate()

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["probe"]["schedule"]["phases"] = [
            list(phase) for phase in self.probe.schedule.phases
        ]
        result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuleSpec":
        data = copy.deepcopy(dict(payload))
        probe_data = data.get("probe", {})
        schedule_data = probe_data.get("schedule", {})
        phases = tuple(
            (int(until), int(interval))
            for until, interval in schedule_data.get("phases", [])
        )
        schedule = ProbeSchedule(
            kind=str(schedule_data.get("kind", "fixed")),
            start_token=int(schedule_data.get("start_token", 128)),
            interval_tokens=int(schedule_data.get("interval_tokens", 128)),
            phases=phases,
            agreement_trigger_count=schedule_data.get(
                "agreement_trigger_count"
            ),
            agreement_interval_tokens=schedule_data.get(
                "agreement_interval_tokens"
            ),
        )
        rule = cls(
            rule_id=str(data.get("rule_id", "")),
            probe=ProbeSpec(
                style=str(probe_data.get("style", "simple")),
                output_cap=int(probe_data.get("output_cap", 32)),
                schedule=schedule,
            ),
            validity=ValiditySpec(**data.get("validity", {})),
            maturity=MaturitySpec(**data.get("maturity", {})),
            evidence=EvidenceSpec(**data.get("evidence", {})),
            persistence=PersistenceSpec(**data.get("persistence", {})),
            certainty=CertaintySpec(**data.get("certainty", {})),
            history=HistorySpec(
                maximum_switches=data.get("history", {}).get(
                    "maximum_switches"
                ),
                switch_window=HistoryWindowSpec(
                    **data.get("history", {}).get("switch_window", {})
                ),
                minimum_stable_span_tokens=int(
                    data.get("history", {}).get(
                        "minimum_stable_span_tokens", 0
                    )
                ),
            ),
            metadata=data.get("metadata", {}),
        )
        rule.validate()
        return rule


def set_path(payload: Dict[str, Any], dotted_path: str, value: Any) -> None:
    parts = dotted_path.split(".")
    _require(parts[0] in RULE_DIMENSIONS, f"not a rule dimension: {parts[0]}")
    cursor: Dict[str, Any] = payload
    for part in parts[:-1]:
        child = cursor.setdefault(part, {})
        _require(isinstance(child, dict), f"path is not an object: {dotted_path}")
        cursor = child
    cursor[parts[-1]] = copy.deepcopy(value)


def stable_rule_id(template_name: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{template_name}__{digest}"


def expand_template(template: Mapping[str, Any]) -> List[RuleSpec]:
    name = str(template["name"])
    base = copy.deepcopy(dict(template["base"]))
    axes = dict(template.get("axes", {}))
    paths = sorted(axes)
    values: Iterable[Tuple[Any, ...]]
    if paths:
        values = itertools.product(*(axes[path] for path in paths))
    else:
        values = [()]
    rules = []
    for combination in values:
        payload = copy.deepcopy(base)
        for path, value in zip(paths, combination):
            set_path(payload, path, value)
        payload["rule_id"] = stable_rule_id(name, payload)
        metadata = dict(payload.get("metadata", {}))
        metadata.update(
            {
                "template": name,
                "axis_values": {
                    path: value for path, value in zip(paths, combination)
                },
            }
        )
        payload["metadata"] = metadata
        rules.append(RuleSpec.from_dict(payload))
    return rules


def expand_search_space(search: Mapping[str, Any]) -> List[RuleSpec]:
    rules = []
    seen = set()
    for template in search.get("templates", []):
        for rule in expand_template(template):
            _require(rule.rule_id not in seen, f"duplicate rule_id: {rule.rule_id}")
            seen.add(rule.rule_id)
            rules.append(rule)
    return rules


def replace_dimension(
    rule: RuleSpec,
    dimension: str,
    replacement: Mapping[str, Any],
    *,
    rule_id: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> RuleSpec:
    _require(dimension in RULE_DIMENSIONS, f"unknown dimension: {dimension}")
    payload = rule.to_dict()
    payload[dimension] = copy.deepcopy(dict(replacement))
    payload["rule_id"] = rule_id
    merged_metadata = dict(payload.get("metadata", {}))
    merged_metadata.update(metadata or {})
    payload["metadata"] = merged_metadata
    return RuleSpec.from_dict(payload)


def one_at_a_time_ablations(
    rule: RuleSpec,
    references: Mapping[str, Mapping[str, Any]],
) -> List[RuleSpec]:
    variants = [rule]
    for dimension in RULE_DIMENSIONS:
        if dimension not in references:
            continue
        variants.append(
            replace_dimension(
                rule,
                dimension,
                references[dimension],
                rule_id=f"{rule.rule_id}__reference_{dimension}",
                metadata={
                    "ablation_kind": "one_at_a_time",
                    "ablation_parent": rule.rule_id,
                    "ablated_dimensions": [dimension],
                    "ablation_semantics": (
                        "replace selected dimension with the declared "
                        "reference; probe/evidence remain operational"
                    ),
                },
            )
        )
    return variants


def factorial_ablations(
    rule: RuleSpec,
    references: Mapping[str, Mapping[str, Any]],
    dimensions: Sequence[str],
) -> List[RuleSpec]:
    dimensions = tuple(dimensions)
    for dimension in dimensions:
        _require(dimension in references, f"missing reference for {dimension}")
    variants = []
    for enabled_bits in itertools.product((False, True), repeat=len(dimensions)):
        payload = rule.to_dict()
        state = {}
        for dimension, enabled in zip(dimensions, enabled_bits):
            state[dimension] = bool(enabled)
            if not enabled:
                payload[dimension] = copy.deepcopy(dict(references[dimension]))
        suffix = "_".join(
            f"{dimension}{int(state[dimension])}" for dimension in dimensions
        )
        payload["rule_id"] = f"{rule.rule_id}__factorial__{suffix}"
        metadata = dict(payload.get("metadata", {}))
        metadata.update(
            {
                "ablation_kind": "factorial",
                "ablation_parent": rule.rule_id,
                "component_state": state,
            }
        )
        payload["metadata"] = metadata
        variants.append(RuleSpec.from_dict(payload))
    return variants
