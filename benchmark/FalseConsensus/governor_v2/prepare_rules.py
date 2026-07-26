#!/usr/bin/env python3
"""Expand Governor v2 rule templates and selected-rule ablations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable, List

try:
    from .rule_schema import (
        RuleSpec,
        expand_search_space,
        factorial_ablations,
        one_at_a_time_ablations,
    )
except ImportError:
    from rule_schema import (  # type: ignore
        RuleSpec,
        expand_search_space,
        factorial_ablations,
        one_at_a_time_ablations,
    )


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    expand = subparsers.add_parser("expand")
    expand.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    expand.add_argument(
        "--output",
        type=Path,
        default=HERE / "generated/candidate_rules.jsonl",
    )
    ablate = subparsers.add_parser("ablate")
    ablate.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    ablate.add_argument(
        "--selected",
        type=Path,
        required=True,
        help="JSON/JSONL selected RuleSpec objects",
    )
    ablate.add_argument(
        "--output",
        type=Path,
        default=HERE / "generated/selected_rule_ablations.jsonl",
    )
    return parser.parse_args()


def write_jsonl(path: Path, rules: Iterable[RuleSpec]) -> int:
    rules = list(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for rule in rules:
            handle.write(
                json.dumps(rule.to_dict(), sort_keys=True, ensure_ascii=False)
                + "\n"
            )
    return len(rules)


def read_rules(path: Path) -> List[RuleSpec]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix == ".json":
        payload = json.loads(text)
        if isinstance(payload, dict):
            payload = payload.get("rules", [payload])
        return [RuleSpec.from_dict(item) for item in payload]
    return [
        RuleSpec.from_dict(json.loads(line))
        for line in text.splitlines()
        if line.strip()
    ]


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if args.command == "expand":
        rules = expand_search_space(protocol["rule_search"])
        count = write_jsonl(args.output, rules)
        print(json.dumps({"candidate_rules": count, "output": str(args.output)}))
        return
    selected = read_rules(args.selected)
    references = protocol["ablation"]["reference_dimensions"]
    factorial_dimensions = protocol["ablation"]["factorial_dimensions"]
    output = []
    seen = set()
    for rule in selected:
        variants = one_at_a_time_ablations(rule, references)
        if protocol["ablation"].get("full_factorial", True):
            variants.extend(
                factorial_ablations(
                    rule, references, factorial_dimensions
                )
            )
        for variant in variants:
            if variant.rule_id in seen:
                continue
            seen.add(variant.rule_id)
            output.append(variant)
    count = write_jsonl(args.output, output)
    print(
        json.dumps(
            {
                "selected_rules": len(selected),
                "ablation_rules": count,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
