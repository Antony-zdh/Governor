#!/usr/bin/env python3
"""Replay the frozen Governor v1 policies on the Governor-v2 trajectory bank.

This is a local, model-free evaluation.  It deliberately uses only the dense
simple@32 probe bank, downsampled from the recorded 64-token cadence to the
original Governor 128-token cadence.  No test problem is read or evaluated.

The three complete-grid policies are:

* naive agreement (the frozen v1 diagnostic);
* conservative (the frozen non-MATH primary);
* task-aware balanced: frozen Balanced-MATH on MATH500 and the explicitly
  predeclared fixed-1536 non-MATH secondary on AMC23/AIME24.

Outputs include per-problem rows, the standard related-work aggregate views,
and a combined matched comparison with vanilla/CertaIndex/TJE/DEER.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from benchmark.FalseConsensus.governor_v2 import replay_rules
from benchmark.FalseConsensus.related_work import aggregate_all, common, metrics


REPO = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = REPO / "benchmark/FalseConsensus/results/governor_v2"
DEFAULT_SPLITS = (
    REPO / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
)
DEFAULT_V1_PROTOCOL = REPO / "benchmark/FalseConsensus/final_eval/protocol.json"
DEFAULT_RELATED = REPO / "benchmark/FalseConsensus/results/related_work/full/_replay"
DEFAULT_OUTPUT = (
    REPO / "benchmark/FalseConsensus/results/governor_v2/existing_methods_matched"
)

METHOD_NAIVE = "governor_naive_agreement"
METHOD_CONSERVATIVE = "governor_conservative"
METHOD_BALANCED = "governor_balanced_task_aware_secondary"
METHOD_VANILLA = "vanilla_full_generation"

DISPLAY_NAMES = {
    METHOD_VANILLA: "Vanilla (full generation)",
    "certaindex_mid_frozen": "CertaIndex",
    "tje_frozen": "TJE",
    "deer_frozen": "DEER",
    METHOD_NAIVE: "Governor — Naive agreement",
    METHOD_CONSERVATIVE: "Governor — Conservative",
    METHOD_BALANCED: "Governor — Balanced task-aware†",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    lines = [json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows]
    common.atomic_write_text(path, "".join(lines))
    return len(lines)


def _equivalence_ids(answers: Sequence[str]) -> list[int]:
    representatives: list[str] = []
    answer_ids: list[int] = []
    for answer in answers:
        if not answer:
            answer_ids.append(-1)
            continue
        answer_id = next(
            (
                index
                for index, representative in enumerate(representatives)
                if replay_rules.answers_equal(answer, representative)
            ),
            None,
        )
        if answer_id is None:
            answer_id = len(representatives)
            representatives.append(answer)
        answer_ids.append(answer_id)
    return answer_ids


def _valid(answer: str, benchmark: str, mode: str) -> bool:
    answer = replay_rules.normalize_answer(answer)
    if not answer:
        return False
    if mode == "nonempty":
        return True
    if mode != "schema":
        raise ValueError(f"unknown validity mode: {mode}")
    if benchmark == "math500":
        return re.fullmatch(r"[A-Da-d]", answer) is None
    # AMC/AIME answers are numeric.  This mirrors Governor-v2's preregistered
    # task-aware schema and rejects prose-only/choice-letter probe failures.
    return any(character.isdigit() for character in answer)


def _minimum_tokens(
    config: Mapping[str, Any], trajectory: Mapping[str, Any], benchmark: str
) -> int:
    if config["floor_kind"] == "fixed":
        return int(config["easy_min"])
    if config["floor_kind"] != "level" or benchmark != "math500":
        raise ValueError(f"unsupported floor for {benchmark}: {config['floor_kind']}")
    level = int(trajectory.get("level", 0))
    return int(config["hard_min"] if level >= 4 else config["easy_min"])


def decide_stop(
    probes: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
    trajectory: Mapping[str, Any],
    benchmark: str,
) -> int | None:
    """Return the probe-list index at which the frozen consecutive rule stops."""
    answers = [
        replay_rules.normalize_answer(probe.get("probe_answer", ""))
        for probe in probes
    ]
    raw_ids = _equivalence_ids(answers)
    ids = [
        answer_id if _valid(answer, benchmark, str(config["validity_mode"])) else -1
        for answer, answer_id in zip(answers, raw_ids)
    ]
    patience = int(config["patience"])
    minimum = _minimum_tokens(config, trajectory, benchmark)
    for end in range(patience - 1, len(probes)):
        if int(probes[end]["token_position"]) < minimum:
            continue
        start = end - patience + 1
        window = ids[start : end + 1]
        if any(answer_id < 0 for answer_id in window):
            continue
        if len(set(window)) != 1:
            continue
        if bool(config["require_certain"]) and not all(
            bool(probe.get("is_certain", False)) for probe in probes[start : end + 1]
        ):
            continue
        return end
    return None


def scheduled_dense_probes(payload: Mapping[str, Any], full_tokens: int) -> list[dict]:
    """Select the exact original fixed start=128, interval=128 schedule."""
    return [
        dict(probe)
        for probe in sorted(
            payload.get("probes", []), key=lambda item: int(item["token_position"])
        )
        if 128 <= int(probe["token_position"]) <= full_tokens
        and (int(probe["token_position"]) - 128) % 128 == 0
    ]


def _configs(v1_protocol: Mapping[str, Any], benchmark: str) -> list[tuple[str, dict]]:
    frozen = v1_protocol["frozen_methods"]
    naive = dict(frozen["naive_agreement"])
    conservative = dict(frozen["conservative"])
    if benchmark == "math500":
        balanced = dict(frozen["balanced_math"])
        balanced["variant"] = "balanced_math"
    else:
        balanced = dict(
            v1_protocol["non_math_policy"]["optional_general_balanced_candidate"]
        )
        balanced.pop("status", None)
        balanced["validity_mode"] = "schema"
        balanced["variant"] = "balanced_general_secondary"
    return [
        (METHOD_NAIVE, naive),
        (METHOD_CONSERVATIVE, conservative),
        (METHOD_BALANCED, balanced),
    ]


def replay_one(
    trajectory: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
    *,
    method: str,
    config: Mapping[str, Any],
    split: str,
) -> dict[str, Any]:
    run = trajectory["run_settings"]
    benchmark = str(run["dataset"])
    full_tokens = int(trajectory["tokens_used"])
    budget = int(run.get("budget", full_tokens))
    stop_index = decide_stop(probes, config, trajectory, benchmark)
    consumed = list(probes if stop_index is None else probes[: stop_index + 1])
    stopped = stop_index is not None
    if stopped:
        stop_probe = consumed[-1]
        main_tokens = int(stop_probe["token_position"])
        delivered = replay_rules.normalize_answer(stop_probe.get("probe_answer", ""))
        capped = False
    else:
        main_tokens = full_tokens
        finished = bool(trajectory.get("finished_naturally", False))
        capped = not finished or full_tokens > budget
        delivered = (
            replay_rules.normalize_answer(trajectory.get("final_answer", ""))
            if not capped
            else ""
        )

    correct = bool(
        delivered
        and replay_rules.answers_equal(delivered, trajectory.get("target", ""))
    )
    probe_out = sum(int(probe.get("probe_out_tokens", 0)) for probe in consumed)
    probe_prompt = sum(int(probe.get("probe_prompt_tokens", 0)) for probe in consumed)
    invalid = sum(
        1
        for probe in consumed
        if "error" in probe
        or not _valid(
            replay_rules.normalize_answer(probe.get("probe_answer", "")),
            benchmark,
            str(config["validity_mode"]),
        )
    )
    auxiliary_wall = sum(
        float(probe.get("probe_latency_seconds", 0.0)) for probe in consumed
    )
    raw = {
        "method": method,
        "model": run["model"],
        "dataset": benchmark,
        "base_seed": int(run["base_seed"]),
        "problem_id": int(trajectory["problem_id"]),
        "split": split,
        "correct": correct,
        "baseline_correct": bool(trajectory.get("final_correct", False)),
        "delivered_answer": delivered,
        "stopped": stopped,
        "capped": capped,
        # Keep the same operational meaning used by the related-work replays:
        # a stop truncates the recoverable continuation, regardless of outcome.
        "recovery_truncated": stopped,
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_tokens,
        "all_generated_tokens": main_tokens + probe_out,
        "probe_out_tokens": probe_out,
        "probe_prompt_tokens": probe_prompt,
        "baseline_all_generated_tokens": full_tokens,
        "overthinking_avoided_tokens": max(0, full_tokens - main_tokens) if stopped else 0,
        "n_aux_calls": len(consumed),
        "n_readout_calls": 0,
        "invalid_aux_responses": invalid,
        "auxiliary_wall_seconds": auxiliary_wall,
        "governor_variant": config.get("variant", method),
        "probe_schedule": "simple@32,start128,interval128",
    }
    return metrics.per_problem_metric(raw) | {
        "governor_variant": raw["governor_variant"],
        "probe_schedule": raw["probe_schedule"],
    }


def vanilla_row(trajectory: Mapping[str, Any], split: str) -> dict[str, Any]:
    run = trajectory["run_settings"]
    full_tokens = int(trajectory["tokens_used"])
    finished = bool(trajectory.get("finished_naturally", False))
    budget = int(run.get("budget", full_tokens))
    capped = not finished or full_tokens > budget
    # This is the explicit representation of the already frozen vanilla
    # baseline used by every related-work row.  Preserve its audited
    # ``final_correct`` even when collection reached the capture cap; otherwise
    # the visible vanilla line would not equal the paired baseline against
    # which every method's accuracy delta is computed.
    delivered = replay_rules.normalize_answer(trajectory.get("final_answer", ""))
    raw = {
        "method": METHOD_VANILLA,
        "model": run["model"],
        "dataset": run["dataset"],
        "base_seed": int(run["base_seed"]),
        "problem_id": int(trajectory["problem_id"]),
        "split": split,
        "correct": bool(trajectory.get("final_correct", False)),
        "baseline_correct": bool(trajectory.get("final_correct", False)),
        "delivered_answer": delivered,
        "stopped": False,
        "capped": capped,
        "recovery_truncated": False,
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": full_tokens,
        "all_generated_tokens": full_tokens,
        "probe_out_tokens": 0,
        "probe_prompt_tokens": 0,
        "baseline_all_generated_tokens": full_tokens,
        "overthinking_avoided_tokens": 0,
        "n_aux_calls": 0,
        "n_readout_calls": 0,
        "invalid_aux_responses": 0,
        "auxiliary_wall_seconds": 0.0,
    }
    return metrics.per_problem_metric(raw)


def collect_rows(
    results_root: Path,
    split_manifest: Path,
    v1_protocol_path: Path,
) -> tuple[list[dict], list[dict], dict]:
    bank = common.validate_frozen_bank(results_root, split_manifest)
    split_map = common.load_split_map(split_manifest)
    protocol = load_json(v1_protocol_path)
    governor_rows: list[dict] = []
    vanilla_rows: list[dict] = []
    env_count = 0
    for env in sorted(results_root.glob("development__*")):
        if not env.is_dir():
            continue
        manifest = load_json(env / "main/run_manifest.json")
        run = manifest["run_settings"]
        benchmark = str(run["dataset"])
        env_count += 1
        for trajectory_path in common.trajectory_paths(env / "main"):
            trajectory = load_json(trajectory_path)
            problem_id = int(trajectory["problem_id"])
            split = split_map[(benchmark, problem_id)]
            if split == "test":
                raise ValueError(f"test leakage: {benchmark}/{problem_id}")
            probe_path = env / "dense_simple32/probes" / trajectory_path.name
            if not probe_path.exists():
                raise FileNotFoundError(probe_path)
            probes = scheduled_dense_probes(
                load_json(probe_path), int(trajectory["tokens_used"])
            )
            vanilla_rows.append(vanilla_row(trajectory, split))
            for method, config in _configs(protocol, benchmark):
                governor_rows.append(
                    replay_one(
                        trajectory,
                        probes,
                        method=method,
                        config=config,
                        split=split,
                    )
                )
    if env_count != common.EXPECTED_ENV_COUNT:
        raise ValueError(f"environment count {env_count} != {common.EXPECTED_ENV_COUNT}")
    return governor_rows, vanilla_rows, bank


def _fmt_percent(value: Any) -> str:
    return "—" if value is None else f"{100 * float(value):.2f}%"


def _fmt_pp(value: Any) -> str:
    return "—" if value is None else f"{float(value):+.2f}"


def comparison_markdown(views: Mapping[str, Any]) -> str:
    macro = list(views["dev_macro"])
    pooled = list(views["dev_pooled"])
    methods = list(DISPLAY_NAMES)
    models = common.DEVELOPMENT_MODELS
    lines = [
        "# Matched Governor / related-work comparison",
        "",
        "Primary reporting uses only the frozen **development split**. All methods "
        "share the same main trajectories, model/benchmark/seed cells, answer grader, "
        "and fair all-generated-token accounting. No test example was read.",
        "",
        "## Benchmark-macro development results",
        "",
        "| Model | Method | Accuracy | Δ accuracy vs vanilla (pp) | Fair token saving | Main-only saving | Stop rate |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        by_method = {row["method"]: row for row in macro if row["model"] == model}
        for method in methods:
            row = by_method[method]
            lines.append(
                f"| {model.split('/')[-1]} | {DISPLAY_NAMES[method]} | "
                f"{_fmt_percent(row['accuracy'])} | {_fmt_pp(row['accuracy_diff_pp'])} | "
                f"{_fmt_percent(row['all_generated_token_saving_fraction'])} | "
                f"{_fmt_percent(row['main_only_token_saving_fraction'])} | "
                f"{_fmt_percent(row['stop_rate'])} |"
            )

    lines += [
        "",
        "## Per-benchmark development results",
        "",
        "| Model | Benchmark | Method | Accuracy | Δ accuracy (pp) | Fair token saving | Main-only saving | Stop rate |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        for dataset in common.DEVELOPMENT_BENCHMARKS:
            by_method = {
                row["method"]: row
                for row in pooled
                if row["model"] == model and row["dataset"] == dataset
            }
            for method in methods:
                row = by_method[method]
                lines.append(
                    f"| {model.split('/')[-1]} | {dataset.upper()} | "
                    f"{DISPLAY_NAMES[method]} | {_fmt_percent(row['accuracy'])} | "
                    f"{_fmt_pp(row['accuracy_diff_pp'])} | "
                    f"{_fmt_percent(row['all_generated_token_saving_fraction'])} | "
                    f"{_fmt_percent(row['main_only_token_saving_fraction'])} | "
                    f"{_fmt_percent(row['stop_rate'])} |"
                )
    lines += [
        "",
        "† `Governor — Balanced task-aware` uses the frozen Balanced-MATH level "
        "floor on MATH500. On AMC23/AIME24 it uses the old protocol's explicitly "
        "predeclared fixed-1536 non-MATH candidate, which is a **secondary analysis**, "
        "not the frozen non-MATH primary. Conservative remains the frozen non-MATH primary.",
        "",
        "Fair saving counts all newly generated main and probe output tokens; re-sent "
        "probe prompt tokens are reported separately in the CSV/JSON artifacts.",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--split-manifest", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--v1-protocol", type=Path, default=DEFAULT_V1_PROTOCOL)
    parser.add_argument("--related-replay-root", type=Path, default=DEFAULT_RELATED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bootstrap-samples", type=int, default=metrics.BOOTSTRAP_SAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=metrics.BOOTSTRAP_SEED)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    governor_rows, vanilla_rows, bank = collect_rows(
        args.results_root, args.split_manifest, args.v1_protocol
    )
    args.output.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output / "governor_replay_rows.jsonl", governor_rows)
    write_jsonl(args.output / "vanilla_rows.jsonl", vanilla_rows)

    governor_coverage = aggregate_all.validate_coverage(
        governor_rows,
        require_all_methods=False,
        split_manifest=args.split_manifest,
    )
    governor_views = aggregate_all.build_views(
        governor_rows,
        n_samples=args.bootstrap_samples,
        seed=args.bootstrap_seed,
    )
    governor_views["coverage"] = governor_coverage
    common.atomic_write_json(args.output / "governor_aggregate.json", governor_views)
    for name in (
        "environment_split",
        "dev_pooled",
        "train_dev_diagnostic",
        "dev_macro",
    ):
        aggregate_all.write_csv(
            args.output / f"governor_{name}.csv", governor_views[name]
        )

    related_paths = sorted(args.related_replay_root.glob("*/replay_rows.jsonl"))
    if len(related_paths) != 54:
        raise ValueError(f"expected 54 related-work replays, found {len(related_paths)}")
    related_rows = aggregate_all.load_rows(related_paths)
    combined = related_rows + vanilla_rows + governor_rows
    combined_coverage = aggregate_all.validate_coverage(
        combined,
        require_all_methods=False,
        split_manifest=args.split_manifest,
    )
    combined_views = aggregate_all.build_views(
        combined,
        n_samples=args.bootstrap_samples,
        seed=args.bootstrap_seed,
    )
    combined_views["coverage"] = combined_coverage
    combined_views["provenance"] = {
        "frozen_bank": bank,
        "v1_protocol": str(args.v1_protocol.relative_to(REPO)),
        "v1_protocol_sha256": common.sha256_file(args.v1_protocol),
        "split_manifest": str(args.split_manifest.relative_to(REPO)),
        "split_manifest_sha256": common.sha256_file(args.split_manifest),
        "related_replay_files": len(related_paths),
        "governor_probe_source": "dense_simple32 downsampled to start=128, interval=128",
        "test_read": False,
        "main_generation_changed": False,
        "balanced_non_math_status": "predeclared secondary analysis",
    }
    common.atomic_write_json(args.output / "matched_aggregate.json", combined_views)
    for name in (
        "environment_split",
        "dev_pooled",
        "train_dev_diagnostic",
        "dev_macro",
    ):
        aggregate_all.write_csv(
            args.output / f"matched_{name}.csv", combined_views[name]
        )
    common.atomic_write_text(
        args.output / "comparison.md", comparison_markdown(combined_views)
    )
    common.atomic_write_json(
        args.output / "manifest.json",
        {
            "schema_version": "governor-existing-methods-matched-1",
            "governor_rows": len(governor_rows),
            "vanilla_rows": len(vanilla_rows),
            "related_rows": len(related_rows),
            "combined_rows": len(combined),
            "methods": combined_views["methods"],
            "bootstrap_samples": args.bootstrap_samples,
            "bootstrap_seed": args.bootstrap_seed,
            "coverage": combined_coverage,
            **combined_views["provenance"],
        },
    )
    print(
        json.dumps(
            {
                "governor_rows": len(governor_rows),
                "combined_rows": len(combined),
                "methods": combined_views["methods"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
