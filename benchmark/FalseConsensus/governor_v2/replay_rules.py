#!/usr/bin/env python3
"""Leakage-safe offline replay, selection, and confirmation for Governor v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))

from benchmark.FalseConsensus.governor_v2.rule_schema import (  # noqa: E402
    RULE_DIMENSIONS,
    RuleSpec,
    factorial_ablations,
    one_at_a_time_ablations,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    os.replace(temporary, path)
    return count


def load_split_map(path: Path) -> dict[tuple[str, int], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["assignments"] if isinstance(payload, dict) else payload
    return {
        (str(row["benchmark"]), int(row["dataset_index"])): str(row["split"])
        for row in rows
    }


def protocol_benchmark(protocol: Mapping[str, Any], name: str) -> dict[str, Any]:
    for benchmark in protocol["environments"]["benchmarks"]:
        if benchmark["name"] == name:
            return dict(benchmark)
    raise KeyError(f"benchmark not in protocol: {name}")


def normalize_answer(value: Any) -> str:
    text = str(value or "").strip()
    return " ".join(text.split())


def valid_answer(answer: str, benchmark: str, mode: str) -> bool:
    answer = normalize_answer(answer)
    if not answer:
        return False
    if mode == "nonempty":
        return True
    if benchmark == "math500":
        return not (len(answer) == 1 and answer.upper() in {"A", "B", "C", "D"})
    return any(character.isdigit() for character in answer)


def answers_equal(left: Any, right: Any) -> bool:
    """Use the project evaluator when installed, with a numeric-safe fallback."""
    try:
        from dynasor.core.evaluator import math_equal

        return bool(math_equal(left, right))
    except ModuleNotFoundError:
        left_text = normalize_answer(left).replace(",", "")
        right_text = normalize_answer(right).replace(",", "")
        if left_text == right_text:
            return True
        try:
            return math.isclose(
                float(left_text), float(right_text), rel_tol=1e-9, abs_tol=1e-9
            )
        except ValueError:
            return False


def scheduled_probes(
    probes: Sequence[Mapping[str, Any]], rule: RuleSpec, budget: int
) -> list[dict[str, Any]]:
    schedule = rule.probe.schedule
    available = [
        dict(probe)
        for probe in probes
        if schedule.start_token <= int(probe["token_position"]) <= budget
    ]
    selected: list[dict[str, Any]] = []
    agreement_streak = 0
    previous = None
    for probe in sorted(available, key=lambda item: int(item["token_position"])):
        position = int(probe["token_position"])
        interval = schedule.interval_tokens
        if schedule.kind == "phased":
            for until, phase_interval in schedule.phases:
                if position <= until:
                    interval = phase_interval
                    break
        elif (
            schedule.kind == "agreement_adaptive"
            and agreement_streak >= int(schedule.agreement_trigger_count or 0)
        ):
            interval = int(schedule.agreement_interval_tokens or interval)
        if (position - schedule.start_token) % interval:
            continue
        selected.append(probe)
        answer = normalize_answer(probe.get("probe_answer"))
        if answer and answer == previous:
            agreement_streak += 1
        else:
            agreement_streak = 1 if answer else 0
        previous = answer or None
    return selected


def window_switches(
    history: Sequence[tuple[int, str]], *, kind: str, size: int
) -> int:
    if not history:
        return 0
    if kind == "tokens":
        cutoff = history[-1][0] - size
        values = [item for item in history if item[0] >= cutoff]
    else:
        values = list(history[-size:])
    return sum(
        left[1] != right[1] for left, right in zip(values, values[1:])
    )


def evidence_candidate(
    history: Sequence[dict[str, Any]], rule: RuleSpec, benchmark: str
) -> tuple[str | None, list[dict[str, Any]]]:
    spec = rule.evidence
    window = list(history[-spec.window_probes :])
    valid = [
        probe
        for probe in window
        if valid_answer(
            str(probe.get("probe_answer", "")),
            benchmark,
            rule.validity.mode,
        )
    ]
    if len(valid) < spec.minimum_valid_probes:
        return None, valid
    if spec.family == "latest":
        return normalize_answer(valid[-1]["probe_answer"]), valid
    scope = valid
    if spec.family == "entropy" and spec.entropy_scope == "history":
        scope = [
            probe
            for probe in history
            if valid_answer(
                str(probe.get("probe_answer", "")),
                benchmark,
                rule.validity.mode,
            )
        ]
    counts = Counter(normalize_answer(probe["probe_answer"]) for probe in scope)
    candidate, count = counts.most_common(1)[0]
    if spec.family == "window_share":
        if count / len(scope) < spec.dominant_share_threshold:
            return None, scope
    else:
        probabilities = [value / len(scope) for value in counts.values()]
        entropy = -sum(p * math.log(p) for p in probabilities)
        normalized = entropy / math.log(len(counts)) if len(counts) > 1 else 0.0
        if normalized > float(spec.entropy_threshold):
            return None, scope
    return candidate, scope


def stop_decision(
    probes: Sequence[Mapping[str, Any]],
    rule: RuleSpec,
    benchmark: str,
    budget: int,
    *,
    probes_are_scheduled: bool = False,
) -> tuple[int | None, str | None, int, int]:
    history: list[dict[str, Any]] = []
    valid_history: list[tuple[int, str]] = []
    accepted: list[tuple[int, str]] = []
    probe_decode = 0
    probe_prompt = 0
    stream = list(probes) if probes_are_scheduled else scheduled_probes(
        probes, rule, budget
    )
    for raw in stream:
        probe = dict(raw)
        position = int(probe["token_position"])
        probe_decode += int(probe.get("probe_out_tokens", 0))
        probe_prompt += int(probe.get("probe_prompt_tokens", 0))
        history.append(probe)
        raw_answer = normalize_answer(probe.get("probe_answer"))
        if valid_answer(raw_answer, benchmark, rule.validity.mode):
            valid_history.append((position, raw_answer))
        maturity = rule.maturity
        if maturity.kind == "fixed_tokens" and position < maturity.minimum_tokens:
            continue
        if (
            maturity.kind == "budget_fraction"
            and position < budget * maturity.minimum_budget_fraction
        ):
            continue
        if maturity.kind == "online_instability":
            if position < maturity.online_instability_floor_tokens:
                continue
            if len(valid_history) > 1 and valid_history[-1][1] != valid_history[-2][1]:
                continue
        candidate, supporting = evidence_candidate(history, rule, benchmark)
        if candidate is None:
            continue
        if rule.certainty.enabled:
            matching = [
                probe
                for probe in supporting
                if normalize_answer(probe.get("probe_answer")) == candidate
            ]
            certain = sum(bool(probe.get("is_certain")) for probe in matching)
            if not matching or certain / len(matching) < rule.certainty.minimum_certain_fraction:
                continue
        accepted.append((position, candidate))
        streak = 1
        for earlier in reversed(accepted[:-1]):
            if earlier[1] != candidate:
                break
            streak += 1
        streak_start = accepted[-streak][0]
        if streak < rule.persistence.minimum_consistent_accepts:
            continue
        if position - streak_start < rule.persistence.minimum_consensus_span_tokens:
            continue
        history_spec = rule.history
        if history_spec.maximum_switches is not None:
            if window_switches(
                valid_history,
                kind=history_spec.switch_window.kind,
                size=history_spec.switch_window.size,
            ) > history_spec.maximum_switches:
                continue
        if history_spec.minimum_stable_span_tokens:
            last_switch = valid_history[0][0] if valid_history else position
            for left, right in zip(valid_history, valid_history[1:]):
                if left[1] != right[1]:
                    last_switch = right[0]
            if position - last_switch < history_spec.minimum_stable_span_tokens:
                continue
        return position, candidate, probe_decode, probe_prompt
    return None, None, probe_decode, probe_prompt


def replay_one(
    trajectory: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
    rule: RuleSpec,
    benchmark: str,
    budget: int,
    *,
    probes_are_scheduled: bool = False,
    answer_correctness: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    token_count = int(trajectory["tokens_used"])
    stop, answer, probe_decode, probe_prompt = stop_decision(
        probes,
        rule,
        benchmark,
        budget,
        probes_are_scheduled=probes_are_scheduled,
    )
    baseline_complete = bool(trajectory["finished_naturally"]) and token_count <= budget
    baseline_correct = bool(trajectory["final_correct"]) if baseline_complete else False
    baseline_tokens = min(token_count, budget)
    if stop is None:
        correct = baseline_correct
        main_tokens = baseline_tokens
    else:
        normalized = normalize_answer(answer)
        if answer_correctness is not None and normalized in answer_correctness:
            correct = bool(answer_correctness[normalized])
        else:
            correct = answers_equal(answer, trajectory["target"])
        main_tokens = stop
    total_tokens = main_tokens + probe_decode
    return {
        "correct": correct,
        "baseline_correct": baseline_correct,
        "main_decode_tokens": main_tokens,
        "probe_decode_tokens": probe_decode,
        "probe_prompt_tokens": probe_prompt,
        "total_decode_tokens": total_tokens,
        "baseline_decode_tokens": baseline_tokens,
        "stopped": stop is not None,
        "capped": not baseline_complete,
    }


def discover_runs(results_root: Path, phase: str) -> list[Path]:
    runs = []
    for manifest_path in results_root.glob("*/main/run_manifest.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        settings = manifest.get("run_settings", {})
        if settings.get("phase") == phase:
            runs.append(manifest_path.parent)
    return sorted(runs)


def load_probes(main_run: Path, problem_id: int) -> list[dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for directory in (
        main_run.parent / "dense_simple32",
        main_run.parent / "dense_simple32_offset32_stride64",
    ):
        path = directory / "probes" / f"problem_{problem_id}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for probe in payload.get("probes", []):
            records[int(probe["token_position"])] = dict(probe)
    return [records[position] for position in sorted(records)]


def summarize(values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(values)
    if not count:
        raise ValueError("cannot summarize an empty environment")
    average = lambda key: sum(float(row[key]) for row in values) / count
    baseline = average("baseline_decode_tokens")
    total = average("total_decode_tokens")
    return {
        "n": count,
        "accuracy": average("correct"),
        "baseline_accuracy": average("baseline_correct"),
        "accuracy_drop_pp": 100 * (average("baseline_correct") - average("correct")),
        "avg_main_decode_tokens": average("main_decode_tokens"),
        "avg_probe_decode_tokens": average("probe_decode_tokens"),
        "avg_probe_prompt_tokens": average("probe_prompt_tokens"),
        "avg_total_decode_tokens": total,
        "avg_baseline_decode_tokens": baseline,
        "saving_fraction": (baseline - total) / baseline if baseline else 0.0,
        "stop_rate": average("stopped"),
        "capped_rate": average("capped"),
    }


def sweep_rows(
    protocol: Mapping[str, Any],
    rules: Sequence[RuleSpec],
    results_root: Path,
    split_map: Mapping[tuple[str, int], str],
    *,
    phase: str,
) -> Iterable[dict[str, Any]]:
    allowed = set(protocol["selection"]["phase_policy"][phase]["splits"])
    if protocol["selection"]["phase_policy"][phase]["include_external_stress"]:
        allowed.add("external_stress")
    for main_run in discover_runs(results_root, phase):
        manifest = json.loads((main_run / "run_manifest.json").read_text())
        settings = manifest["run_settings"]
        role = str(settings["model_role"])
        permitted_roles = set(
            protocol["selection"]["phase_policy"][phase]["model_roles"]
        )
        if role not in permitted_roles:
            raise ValueError(f"{phase} cannot read model role {role}: {main_run}")
        benchmark = str(settings["dataset"])
        benchmark_spec = protocol_benchmark(protocol, benchmark)
        if any(
            rule.probe.schedule.interval_tokens == 32 for rule in rules
        ) and not (
            main_run.parent
            / "dense_simple32_offset32_stride64"
            / "probe_manifest.json"
        ).exists():
            raise FileNotFoundError(
                "32-token rule replay requires the complementary offset "
                f"probe bank: {main_run.parent}"
            )
        budgets = (
            [int(benchmark_spec["selection_budget"])]
            if phase == "development"
            else [int(value) for value in benchmark_spec["evaluation_budgets"]]
        )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for trajectory_path in sorted((main_run / "traj").glob("problem_*.json")):
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            problem_id = int(trajectory["problem_id"])
            split = split_map.get((benchmark, problem_id))
            if split not in allowed:
                raise ValueError(
                    f"{phase} encountered forbidden/unassigned split {split}: "
                    f"{benchmark}/{problem_id}"
                )
            probes = load_probes(main_run, problem_id)
            correctness = {}
            for probe in probes:
                answer = normalize_answer(probe.get("probe_answer"))
                if answer and answer not in correctness:
                    correctness[answer] = answers_equal(
                        answer, trajectory["target"]
                    )
            grouped[split].append(
                {
                    "trajectory": trajectory,
                    "probes": probes,
                    "answer_correctness": correctness,
                    "schedule_cache": {},
                }
            )
        for split, examples in sorted(grouped.items()):
            for budget in budgets:
                for rule in rules:
                    schedule = rule.probe.schedule
                    schedule_key = (
                        budget,
                        schedule.kind,
                        schedule.start_token,
                        schedule.interval_tokens,
                        schedule.phases,
                        schedule.agreement_trigger_count,
                        schedule.agreement_interval_tokens,
                    )
                    values = []
                    for example in examples:
                        cache = example["schedule_cache"]
                        if schedule_key not in cache:
                            cache[schedule_key] = scheduled_probes(
                                example["probes"], rule, budget
                            )
                        values.append(
                            replay_one(
                                example["trajectory"],
                                cache[schedule_key],
                                rule,
                                benchmark,
                                budget,
                                probes_are_scheduled=True,
                                answer_correctness=example[
                                    "answer_correctness"
                                ],
                            )
                        )
                    yield {
                        "rule_id": rule.rule_id,
                        "phase": phase,
                        "split": split,
                        "model": settings["model"],
                        "model_role": role,
                        "benchmark": benchmark,
                        "seed": int(settings["base_seed"]),
                        "budget": budget,
                        **summarize(values),
                    }


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("-inf")
    index = (len(ordered) - 1) * q
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - index) + ordered[high] * (index - low)


def select_rule(
    rows: Sequence[Mapping[str, Any]],
    rules: Mapping[str, RuleSpec],
    *,
    model_drop: float,
    benchmark_drop: float,
    positive_fraction: float,
) -> tuple[RuleSpec, dict[str, Any]]:
    by_rule: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["phase"] != "development" or row["split"] not in {"train", "dev"}:
            raise ValueError("selection input may contain only development train/dev")
        by_rule[str(row["rule_id"])].append(row)
    eligible = []
    for rule_id, environments in by_rule.items():
        if rule_id not in rules:
            continue
        model_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        benchmark_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        savings = []
        dev_savings = []
        for row in environments:
            drop = float(row["accuracy_drop_pp"])
            split = str(row["split"])
            model_groups[(split, str(row["model"]))].append(drop)
            benchmark_groups[(split, str(row["benchmark"]))].append(drop)
            savings.append(float(row["saving_fraction"]))
            if split == "dev":
                dev_savings.append(float(row["saving_fraction"]))
        max_model = max(statistics.fmean(values) for values in model_groups.values())
        max_benchmark = max(
            statistics.fmean(values) for values in benchmark_groups.values()
        )
        positive = sum(value > 0 for value in savings) / len(savings)
        if (
            max_model <= model_drop
            and max_benchmark <= benchmark_drop
            and positive >= positive_fraction
        ):
            rule = rules[rule_id]
            complexity = (
                (256 // min(rule.probe.schedule.interval_tokens, 256))
                + rule.evidence.window_probes
                + rule.persistence.minimum_consistent_accepts
                + int(rule.certainty.enabled)
                + int(rule.history.maximum_switches is not None)
                + int(rule.history.minimum_stable_span_tokens > 0)
            )
            eligible.append(
                (
                    percentile(dev_savings, 0.2),
                    -complexity,
                    rule_id,
                    {
                        "dev_q20_saving_fraction": percentile(dev_savings, 0.2),
                        "positive_saving_fraction": positive,
                        "max_model_accuracy_drop_pp": max_model,
                        "max_benchmark_accuracy_drop_pp": max_benchmark,
                    },
                )
            )
    if not eligible:
        raise RuntimeError("no rule passes the preregistered operating-point gates")
    _, _, rule_id, diagnostics = max(eligible)
    return rules[rule_id], diagnostics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    sweep = subparsers.add_parser("sweep")
    sweep.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    sweep.add_argument("--rules", type=Path, required=True)
    sweep.add_argument("--split-manifest", type=Path, required=True)
    sweep.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "benchmark/FalseConsensus/results/governor_v2",
    )
    sweep.add_argument("--phase", choices=("development", "confirmation"), required=True)
    sweep.add_argument("--output", type=Path, required=True)
    sweep.add_argument("--shard-index", type=int, default=0)
    sweep.add_argument("--shard-count", type=int, default=1)
    select = subparsers.add_parser("select")
    select.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    select.add_argument("--rules", type=Path, required=True)
    select.add_argument("--metrics", type=Path, nargs="+", required=True)
    select.add_argument("--split-manifest", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--protocol", type=Path, default=HERE / "protocol.json")
    evaluate.add_argument("--frozen", type=Path, required=True)
    evaluate.add_argument("--split-manifest", type=Path, required=True)
    evaluate.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "benchmark/FalseConsensus/results/governor_v2",
    )
    evaluate.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    if args.command == "sweep":
        if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
            raise ValueError("invalid shard index/count")
        rules = [
            RuleSpec.from_dict(row)
            for index, row in enumerate(load_jsonl(args.rules))
            if index % args.shard_count == args.shard_index
        ]
        count = write_jsonl(
            args.output,
            sweep_rows(
                protocol,
                rules,
                args.results_root,
                load_split_map(args.split_manifest),
                phase=args.phase,
            ),
        )
        print(json.dumps({"rules": len(rules), "metric_rows": count}))
        return
    if args.command == "select":
        rules = {
            rule.rule_id: rule
            for rule in (RuleSpec.from_dict(row) for row in load_jsonl(args.rules))
        }
        metrics = [
            row for path in args.metrics for row in load_jsonl(path)
        ]
        selection = protocol["selection"]
        chosen = {}
        diagnostics = {}
        for name, model_gate, benchmark_gate in (
            (
                "conservative",
                selection["conservative_accuracy_drop_pp_max_per_model"],
                selection["conservative_accuracy_drop_pp_max_per_benchmark"],
            ),
            (
                "balanced",
                selection["balanced_accuracy_drop_pp_max_per_model"],
                selection["balanced_accuracy_drop_pp_max_per_benchmark"],
            ),
        ):
            rule, diagnostic = select_rule(
                metrics,
                rules,
                model_drop=float(model_gate),
                benchmark_drop=float(benchmark_gate),
                positive_fraction=float(
                    selection["minimum_fraction_environments_with_positive_saving"]
                ),
            )
            chosen[name] = rule.to_dict()
            diagnostics[name] = diagnostic
        ablations = {}
        for name, rule_payload in chosen.items():
            rule = RuleSpec.from_dict(rule_payload)
            one = one_at_a_time_ablations(
                rule, protocol["ablation"]["reference_dimensions"]
            )
            factorial = factorial_ablations(
                rule,
                protocol["ablation"]["reference_dimensions"],
                protocol["ablation"]["factorial_dimensions"],
            )
            ablations[name] = [item.to_dict() for item in one + factorial]
        atomic_json(
            args.output,
            {
                "schema_version": "governor-v2-frozen-rules-1",
                "protocol_version": protocol["protocol_version"],
                "protocol_sha256": sha256_file(args.protocol),
                "split_manifest_sha256": sha256_file(args.split_manifest),
                "candidate_rules_sha256": sha256_file(args.rules),
                "selection_metrics_sha256": {
                    str(path): sha256_file(path) for path in args.metrics
                },
                "selected_rules": chosen,
                "selection_diagnostics": diagnostics,
                "confirmation_ablations": ablations,
            },
        )
        print(json.dumps({name: rule["rule_id"] for name, rule in chosen.items()}))
        return
    frozen = json.loads(args.frozen.read_text(encoding="utf-8"))
    if frozen["protocol_sha256"] != sha256_file(args.protocol):
        raise ValueError("protocol changed after rule freeze")
    if frozen["split_manifest_sha256"] != sha256_file(args.split_manifest):
        raise ValueError("split manifest changed after rule freeze")
    payloads = list(frozen["selected_rules"].values())
    for variants in frozen.get("confirmation_ablations", {}).values():
        payloads.extend(variants)
    unique = {}
    for payload in payloads:
        rule = RuleSpec.from_dict(payload)
        unique[rule.rule_id] = rule
    count = write_jsonl(
        args.output,
        sweep_rows(
            protocol,
            list(unique.values()),
            args.results_root,
            load_split_map(args.split_manifest),
            phase="confirmation",
        ),
    )
    print(json.dumps({"rules": len(unique), "metric_rows": count}))


if __name__ == "__main__":
    main()
