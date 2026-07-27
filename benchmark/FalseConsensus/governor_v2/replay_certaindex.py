#!/usr/bin/env python3
"""Replay the CertaIndex/Dynasor stopping rule on Governor v2 probe banks.

This is a CPU-only, prompt-adapted baseline.  It reproduces the public
Dynasor ``mid`` stopping logic (64-token checkpoints, three mutually
equivalent non-empty answers, and certainty at every checkpoint), but reads
the already collected Governor v2 ``simple@32`` probes.  It is therefore not
the end-to-end faithful CertaIndex prompt/cap configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmark/TokenDeprivation"))

from benchmark.FalseConsensus.governor_v2.replay_rules import (  # noqa: E402
    answers_equal,
    discover_runs,
    load_split_map,
    normalize_answer,
    protocol_benchmark,
    sha256_file,
)


METHOD_ID = "certaindex_mid_stop_logic_on_simple32"
SOURCE_METHOD = "CertaIndex/Dynasor CoT, effort_level('mid')"
PATIENCE = 3
INTERVAL = 64
START_TOKEN = 64
ADAPTED_PROBE_STYLE = "simple"
ADAPTED_PROBE_CAP = 32
ORIGINAL_PROBE_CAP = 20
UNCERTAIN_WORDS = ("wait", "hold", "but", "okay", "no", "hmm")


def require_formal_evaluator() -> dict[str, Any]:
    """Fail fast unless the public Dynasor evaluator is fully importable."""
    try:
        from dynasor.core.evaluator import eqaul_group, math_equal
    except (ImportError, ModuleNotFoundError) as error:
        raise RuntimeError(
            "formal CertaIndex replay requires the full project evaluator; "
            "install the repository dependencies (for example `pip install "
            "-e .`) instead of using the unit-test fallback"
        ) from error
    # Exercise both symbols so a partially importable evaluator cannot pass
    # preflight and silently change the formal result.
    if not math_equal("1/2", "0.5") or not eqaul_group(
        ["1/2", "0.5", "\\frac{1}{2}"]
    ):
        raise RuntimeError("Dynasor evaluator failed the formal replay smoke test")
    versions = {}
    for distribution in ("latex2sympy2", "sympy", "word2number", "regex"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "unknown"
    return {
        "name": "dynasor.core.evaluator",
        "answer_equivalence": "eqaul_group/math_equal",
        "dependency_versions": versions,
        "fallback_allowed": False,
    }


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    fieldnames = list(rows[0])
    if any(list(row) != fieldnames for row in rows):
        raise ValueError("CSV rows do not share an identical ordered schema")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def file_hashes(paths: Iterable[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(REPO_ROOT)): sha256_file(path)
        for path in sorted(set(paths))
    }


@lru_cache(maxsize=100_000)
def _cached_certaindex_answers_equal(left: str, right: str) -> bool:
    """Match Dynasor's pairwise ``math_equal`` comparison.

    The exact normalized fallback only keeps the replay running when the
    symbolic parser rejects malformed model output.
    """
    if left == right:
        return True
    try:
        from dynasor.core.evaluator import math_equal

        return bool(math_equal(left, right))
    except ModuleNotFoundError:
        # Minimal-dependency fallback for unit tests and preflight only.
        # Formal replay environments should install the project dependencies
        # and therefore execute the public Dynasor evaluator above.
        def numeric(value: str) -> Fraction | None:
            text = value.replace(",", "")
            if text.startswith("\\frac{") and "}{" in text and text.endswith("}"):
                numerator, denominator = text[6:-1].split("}{", 1)
                text = f"{numerator}/{denominator}"
            try:
                return Fraction(text)
            except (ValueError, ZeroDivisionError):
                return None

        left_number, right_number = numeric(left), numeric(right)
        if left_number is not None and right_number is not None:
            return left_number == right_number
        return left == right
    except Exception:
        return left == right


def certaindex_answers_equal(left: Any, right: Any) -> bool:
    left_text = normalize_answer(left)
    right_text = normalize_answer(right)
    return _cached_certaindex_answers_equal(left_text, right_text)


def mutually_equivalent(answers: Sequence[Any]) -> bool:
    # Preserve the public evaluator's answer/representative argument order
    # while caching repeated mathematical comparisons across trajectories.
    representatives: list[Any] = []
    for answer in answers:
        if any(
            certaindex_answers_equal(answer, representative)
            for representative in representatives
        ):
            continue
        representatives.append(answer)
    return len(representatives) == 1


def find_certaindex_stop(
    probes: Sequence[Mapping[str, Any]],
    *,
    budget: int,
    patience: int = PATIENCE,
) -> tuple[int | None, str | None, int, int, int]:
    """Return stop token/answer and costs incurred through the decision."""
    eligible = sorted(
        (
            dict(probe)
            for probe in probes
            if START_TOKEN <= int(probe["token_position"]) <= budget
            and (int(probe["token_position"]) - START_TOKEN) % INTERVAL == 0
        ),
        key=lambda probe: int(probe["token_position"]),
    )
    probe_decode = 0
    probe_prompt = 0
    for end, probe in enumerate(eligible):
        probe_decode += int(probe.get("probe_out_tokens", 0))
        probe_prompt += int(probe.get("probe_prompt_tokens", 0))
        if end + 1 < patience:
            continue
        window = eligible[end - patience + 1 : end + 1]
        answers = [
            normalize_answer(item.get("probe_answer"))
            for item in window
        ]
        if (
            all(answers)
            and all(bool(item.get("is_certain")) for item in window)
            and mutually_equivalent(answers)
        ):
            return (
                int(probe["token_position"]),
                answers[-1],
                probe_decode,
                probe_prompt,
                end + 1,
            )
    return None, None, probe_decode, probe_prompt, len(eligible)


def replay_problem(
    trajectory: Mapping[str, Any],
    probes: Sequence[Mapping[str, Any]],
    *,
    budget: int,
) -> dict[str, Any]:
    full_tokens = int(trajectory["tokens_used"])
    baseline_complete = (
        bool(trajectory["finished_naturally"]) and full_tokens <= budget
    )
    if baseline_complete:
        if "final_answer" in trajectory:
            baseline_correct = answers_equal(
                trajectory["final_answer"], trajectory["target"]
            )
        else:
            baseline_correct = bool(trajectory["final_correct"])
    else:
        baseline_correct = False
    baseline_tokens = min(full_tokens, budget)

    stop, stop_answer, probe_decode, probe_prompt, probe_calls = (
        find_certaindex_stop(probes, budget=budget)
    )
    if stop is None:
        delivered_correct = baseline_correct
        main_decode = baseline_tokens
    else:
        delivered_correct = answers_equal(stop_answer, trajectory["target"])
        main_decode = stop
    total_decode = main_decode + probe_decode
    return {
        "baseline_correct": bool(baseline_correct),
        "delivered_correct": bool(delivered_correct),
        "stopped": stop is not None,
        "stop_token": stop,
        "stop_answer": stop_answer,
        "stop_correct": (
            bool(delivered_correct) if stop is not None else None
        ),
        "baseline_main_decode_tokens": baseline_tokens,
        "main_decode_tokens": main_decode,
        "probe_decode_tokens": probe_decode,
        "total_decode_tokens": total_decode,
        "probe_prompt_tokens": probe_prompt,
        "probe_calls": probe_calls,
        "capped": not baseline_complete,
        "recovery_truncated": bool(
            stop is not None and baseline_correct and not delivered_correct
        ),
        "overthinking_avoided": bool(
            stop is not None and delivered_correct and not baseline_correct
        ),
    }


def load_dense_probes(
    run_root: Path, problem_id: int
) -> tuple[list[dict[str, Any]], Path]:
    path = (
        run_root
        / "dense_simple32"
        / "probes"
        / f"problem_{problem_id}.json"
    )
    if not path.exists():
        raise FileNotFoundError(f"missing dense probe trajectory: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload["problem_id"]) != problem_id:
        raise ValueError(f"probe problem_id mismatch: {path}")
    return list(payload["probes"]), path


def validate_run(main_run: Path) -> tuple[dict[str, Any], list[Path]]:
    main_manifest_path = main_run / "run_manifest.json"
    probe_manifest_path = (
        main_run.parent / "dense_simple32" / "probe_manifest.json"
    )
    if not probe_manifest_path.exists():
        raise FileNotFoundError(f"missing dense probe manifest: {probe_manifest_path}")
    main_manifest = json.loads(main_manifest_path.read_text(encoding="utf-8"))
    probe_manifest = json.loads(
        probe_manifest_path.read_text(encoding="utf-8")
    )
    main = main_manifest["run_settings"]
    probe = probe_manifest["probe_settings"]
    expected = {
        "model": main["model"],
        "dataset": main["dataset"],
        "base_seed": int(main["base_seed"]),
        "probe_style": ADAPTED_PROBE_STYLE,
        "probe_tokens": ADAPTED_PROBE_CAP,
        "dense_interval": INTERVAL,
        "start_token": START_TOKEN,
    }
    observed = {
        "model": probe["model"],
        "dataset": probe["dataset"],
        "base_seed": int(probe["base_seed"]),
        "probe_style": probe["probe_style"],
        "probe_tokens": int(probe["probe_tokens"]),
        "dense_interval": int(probe["dense_interval"]),
        "start_token": int(probe["start_token"]),
    }
    if observed != expected:
        raise ValueError(
            f"incompatible CertaIndex adapter bank at {main_run.parent}: "
            f"expected={expected}, observed={observed}"
        )
    return main_manifest, [main_manifest_path, probe_manifest_path]


def quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    index = (len(ordered) - 1) * probability
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return ordered[low]
    return (
        ordered[low] * (high - index)
        + ordered[high] * (index - low)
    )


def hierarchical_paired_ci(
    rows: Sequence[Mapping[str, Any]],
    *,
    samples: int,
    seed: int,
) -> dict[str, float]:
    by_seed: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_seed[int(row["seed"])].append(row)
    seed_values = sorted(by_seed)
    if not seed_values or samples <= 0:
        return {
            "accuracy_diff_pp_ci_lo": math.nan,
            "accuracy_diff_pp_ci_hi": math.nan,
            "saving_fraction_ci_lo": math.nan,
            "saving_fraction_ci_hi": math.nan,
        }
    rng = random.Random(seed)
    accuracy_diffs: list[float] = []
    savings: list[float] = []
    for _ in range(samples):
        sampled_rows: list[Mapping[str, Any]] = []
        for _ in seed_values:
            selected_seed = rng.choice(seed_values)
            source = by_seed[selected_seed]
            sampled_rows.extend(rng.choice(source) for _ in source)
        baseline_correct = statistics.fmean(
            float(row["baseline_correct"]) for row in sampled_rows
        )
        delivered_correct = statistics.fmean(
            float(row["delivered_correct"]) for row in sampled_rows
        )
        baseline_tokens = sum(
            int(row["baseline_main_decode_tokens"])
            for row in sampled_rows
        )
        method_tokens = sum(
            int(row["total_decode_tokens"]) for row in sampled_rows
        )
        accuracy_diffs.append(
            100.0 * (delivered_correct - baseline_correct)
        )
        savings.append(
            (baseline_tokens - method_tokens) / baseline_tokens
            if baseline_tokens
            else 0.0
        )
    return {
        "accuracy_diff_pp_ci_lo": quantile(accuracy_diffs, 0.025),
        "accuracy_diff_pp_ci_hi": quantile(accuracy_diffs, 0.975),
        "saving_fraction_ci_lo": quantile(savings, 0.025),
        "saving_fraction_ci_hi": quantile(savings, 0.975),
    }


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot summarize empty CertaIndex rows")
    n = len(rows)
    baseline_accuracy = statistics.fmean(
        float(row["baseline_correct"]) for row in rows
    )
    accuracy = statistics.fmean(
        float(row["delivered_correct"]) for row in rows
    )
    baseline_tokens = sum(
        int(row["baseline_main_decode_tokens"]) for row in rows
    )
    method_tokens = sum(int(row["total_decode_tokens"]) for row in rows)
    return {
        "n": n,
        "baseline_accuracy": baseline_accuracy,
        "accuracy": accuracy,
        "accuracy_diff_pp": 100.0 * (accuracy - baseline_accuracy),
        "avg_baseline_main_decode_tokens": baseline_tokens / n,
        "avg_main_decode_tokens": statistics.fmean(
            int(row["main_decode_tokens"]) for row in rows
        ),
        "avg_probe_decode_tokens": statistics.fmean(
            int(row["probe_decode_tokens"]) for row in rows
        ),
        "avg_total_decode_tokens": method_tokens / n,
        "saving_fraction": (
            (baseline_tokens - method_tokens) / baseline_tokens
            if baseline_tokens
            else 0.0
        ),
        "stop_rate": statistics.fmean(
            float(row["stopped"]) for row in rows
        ),
        "capped_rate": statistics.fmean(
            float(row["capped"]) for row in rows
        ),
        "recovery_truncated_rate": statistics.fmean(
            float(row["recovery_truncated"]) for row in rows
        ),
        "overthinking_avoided_rate": statistics.fmean(
            float(row["overthinking_avoided"]) for row in rows
        ),
        "avg_probe_calls": statistics.fmean(
            int(row["probe_calls"]) for row in rows
        ),
        "avg_probe_prompt_tokens": statistics.fmean(
            int(row["probe_prompt_tokens"]) for row in rows
        ),
    }


def aggregate(
    details: Sequence[Mapping[str, Any]],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in details:
        grouped[
            (
                row["split"],
                row["model"],
                row["benchmark"],
                int(row["seed"]),
                int(row["budget"]),
            )
        ].append(row)
    summaries = []
    for key, rows in sorted(grouped.items()):
        split, model, benchmark, seed, budget = key
        summaries.append(
            {
                "method": METHOD_ID,
                "reproduction_class": "prompt_adapted_cpu_replay",
                "phase": "development",
                "split": split,
                "model": model,
                "benchmark": benchmark,
                "seed": seed,
                "budget": budget,
                **summarize_rows(rows),
                "accuracy_diff_pp_ci_lo": math.nan,
                "accuracy_diff_pp_ci_hi": math.nan,
                "saving_fraction_ci_lo": math.nan,
                "saving_fraction_ci_hi": math.nan,
            }
        )

    pooled: dict[
        tuple[str, str, str, int], list[Mapping[str, Any]]
    ] = defaultdict(list)
    for row in details:
        pooled[
            (
                str(row["split"]),
                str(row["model"]),
                str(row["benchmark"]),
                int(row["budget"]),
            )
        ].append(row)
        pooled[
            (
                "train+dev",
                str(row["model"]),
                str(row["benchmark"]),
                int(row["budget"]),
            )
        ].append(row)
    for index, (key, rows) in enumerate(sorted(pooled.items())):
        split, model, benchmark, budget = key
        summaries.append(
            {
                "method": METHOD_ID,
                "reproduction_class": "prompt_adapted_cpu_replay",
                "phase": "development",
                "split": split,
                "model": model,
                "benchmark": benchmark,
                "seed": "pooled",
                "budget": budget,
                **summarize_rows(rows),
                **hierarchical_paired_ci(
                    rows,
                    samples=bootstrap_samples,
                    seed=bootstrap_seed + index,
                ),
            }
        )
    return summaries


def markdown_report(
    summaries: Sequence[Mapping[str, Any]],
    *,
    detail_count: int,
    run_count: int,
    bootstrap_samples: int,
) -> str:
    dev = [
        row
        for row in summaries
        if row["split"] == "dev" and row["seed"] == "pooled"
    ]
    train_dev = [
        row
        for row in summaries
        if row["split"] == "train+dev" and row["seed"] == "pooled"
    ]
    lines = [
        "# CertaIndex baseline：development 本地回放",
        "",
        "## 结论与口径",
        "",
        (
            f"本次对 {run_count} 个完整 development 环境、{detail_count} 条"
            " model-seed-problem 轨迹进行了 CPU-only 回放；没有模型调用，也没有读取"
            " test。规则忠实采用公开 Dynasor `effort_level('mid')` 的停止条件："
            "每 64 个主生成 token 检查一次，最近 3 个答案均非空、均无显式犹豫词，"
            "且按项目数学等价判定属于同一答案类时停止。"
        ),
        "",
        (
            "**重要限制：这是 prompt-adapted baseline，不是端到端 faithful "
            "reproduction。** 原实现使用 CertaIndex 顿悟式 suffix 和 20-token "
            "probe；本次使用已采集的 `simple@32`。因此方法 ID 明确写为 "
            f"`{METHOD_ID}`。"
        ),
        "",
        (
            "Token saving 以 full generation 的主输出 token 为分母；方法成本包含"
            "停止前所有主输出 token 与 probe 输出 token。probe prompt token 单列，"
            "不混入 generated-token saving。准确率差定义为 CertaIndex − full，"
            "正数表示提高。区间为按 seed、再按题目重采样的成对 hierarchical "
            f"bootstrap（{bootstrap_samples:,} 次）。"
        ),
        "",
        "## 主对比口径：dev 跨 seed 汇总",
        "",
        (
            "| Model | Benchmark | N | Full acc. | CertaIndex acc. | Δacc. "
            "(95% CI) | Token saving (95% CI) | Stop rate | Avg probe calls |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in dev:
        model = str(row["model"]).split("/")[-1]
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    str(row["benchmark"]),
                    str(row["n"]),
                    f"{100 * float(row['baseline_accuracy']):.2f}%",
                    f"{100 * float(row['accuracy']):.2f}%",
                    (
                        f"{float(row['accuracy_diff_pp']):+.2f}pp "
                        f"[{float(row['accuracy_diff_pp_ci_lo']):+.2f}, "
                        f"{float(row['accuracy_diff_pp_ci_hi']):+.2f}]"
                    ),
                    (
                        f"{100 * float(row['saving_fraction']):+.2f}% "
                        f"[{100 * float(row['saving_fraction_ci_lo']):+.2f}, "
                        f"{100 * float(row['saving_fraction_ci_hi']):+.2f}]"
                    ),
                    f"{100 * float(row['stop_rate']):.2f}%",
                    f"{float(row['avg_probe_calls']):.1f}",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 诊断口径：train+dev 跨 seed 汇总",
            "",
            (
                "| Model | Benchmark | N | Full acc. | CertaIndex acc. | "
                "Δacc. | Token saving | Stop rate |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in train_dev:
        model = str(row["model"]).split("/")[-1]
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    str(row["benchmark"]),
                    str(row["n"]),
                    f"{100 * float(row['baseline_accuracy']):.2f}%",
                    f"{100 * float(row['accuracy']):.2f}%",
                    f"{float(row['accuracy_diff_pp']):+.2f}pp",
                    f"{100 * float(row['saving_fraction']):+.2f}%",
                    f"{100 * float(row['stop_rate']):.2f}%",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            (
                "在 `simple@32` 上，CertaIndex `mid` 停止逻辑几乎总会触发，"
                "因此换来很大的 token saving，但准确率明显下降。这个结果只能说明"
                "停止逻辑直接迁移到本项目 simple probe 时过于激进；它不能替代"
                " CertaIndex 原 prompt/cap 的 faithful GPU 复现。"
            ),
            "",
            "## 可复现性",
            "",
            "- `details.jsonl`：逐轨迹的停止点、交付正确性与 token accounting。",
            "- `metrics.csv`：逐 split/model/benchmark/seed 环境及跨 seed 汇总。",
            "- `manifest.json`：方法定义、输入文件 SHA-256、覆盖率和运行参数。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol", type=Path, default=HERE / "protocol.json"
    )
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=HERE / "generated/split_manifest.json",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=REPO_ROOT / "benchmark/FalseConsensus/results/governor_v2",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            REPO_ROOT
            / "benchmark/FalseConsensus/results/related_work"
            / METHOD_ID
        ),
    )
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260727)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bootstrap_samples < 0:
        raise ValueError("--bootstrap-samples must be non-negative")
    evaluator_backend = require_formal_evaluator()
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    split_map = load_split_map(args.split_manifest)
    allowed_splits = set(
        protocol["selection"]["phase_policy"]["development"]["splits"]
    )
    details: list[dict[str, Any]] = []
    input_paths: list[Path] = [args.protocol, args.split_manifest]
    run_count = 0
    expected_run_keys = set()

    for main_run in discover_runs(args.results_root, "development"):
        manifest, manifest_paths = validate_run(main_run)
        input_paths.extend(manifest_paths)
        settings = manifest["run_settings"]
        model = str(settings["model"])
        benchmark = str(settings["dataset"])
        seed = int(settings["base_seed"])
        budget = int(protocol_benchmark(protocol, benchmark)["selection_budget"])
        run_key = (model, benchmark, seed)
        if run_key in expected_run_keys:
            raise ValueError(f"duplicate development run: {run_key}")
        expected_run_keys.add(run_key)
        run_count += 1

        for trajectory_path in sorted((main_run / "traj").glob("problem_*.json")):
            trajectory = json.loads(
                trajectory_path.read_text(encoding="utf-8")
            )
            problem_id = int(trajectory["problem_id"])
            split = split_map.get((benchmark, problem_id))
            if split not in allowed_splits:
                raise ValueError(
                    "CertaIndex development replay encountered forbidden or "
                    f"unassigned split {split}: {benchmark}/{problem_id}"
                )
            probes, probe_path = load_dense_probes(
                main_run.parent, problem_id
            )
            input_paths.extend([trajectory_path, probe_path])
            outcome = replay_problem(
                trajectory, probes, budget=budget
            )
            details.append(
                {
                    "method": METHOD_ID,
                    "reproduction_class": "prompt_adapted_cpu_replay",
                    "phase": "development",
                    "split": split,
                    "model": model,
                    "benchmark": benchmark,
                    "seed": seed,
                    "budget": budget,
                    "problem_id": problem_id,
                    **outcome,
                }
            )

    if not details:
        raise ValueError(f"no development runs found under {args.results_root}")

    summaries = aggregate(
        details,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "details.jsonl", details)
    write_csv(args.output_dir / "metrics.csv", summaries)
    report = markdown_report(
        summaries,
        detail_count=len(details),
        run_count=run_count,
        bootstrap_samples=args.bootstrap_samples,
    )
    (args.output_dir / "report.md").write_text(report, encoding="utf-8")

    source_paths = [
        REPO_ROOT / "dynasor/core/cot.py",
        REPO_ROOT / "dynasor/core/evaluator.py",
        HERE / "grading.py",
        HERE / "replay_rules.py",
        Path(__file__).resolve(),
    ]
    atomic_json(
        args.output_dir / "manifest.json",
        {
            "schema_version": "related-work-certaindex-replay-1",
            "method_id": METHOD_ID,
            "source_method": SOURCE_METHOD,
            "reproduction_class": "prompt_adapted_cpu_replay",
            "test_data_read": False,
            "model_calls_made": False,
            "evaluator_backend": evaluator_backend,
            "original_method": {
                "source": "dynasor/core/cot.py effort_level('mid')",
                "probe_interval_tokens": INTERVAL,
                "probe_output_cap": ORIGINAL_PROBE_CAP,
                "patience": PATIENCE,
                "validity": "nonempty",
                "certainty": {
                    "required_for_every_probe_in_window": True,
                    "uncertain_words": list(UNCERTAIN_WORDS),
                },
                "answer_equivalence": "dynasor.core.evaluator.math_equal",
            },
            "adapter": {
                "probe_style": ADAPTED_PROBE_STYLE,
                "probe_output_cap": ADAPTED_PROBE_CAP,
                "probe_start_token": START_TOKEN,
                "probe_interval_tokens": INTERVAL,
                "reason_not_faithful": (
                    "Existing Governor v2 bank uses simple@32 rather than "
                    "the CertaIndex suffix with a 20-token output cap."
                ),
            },
            "accounting": {
                "saving_denominator": "full-generation main decode tokens",
                "method_generated_tokens": (
                    "main decode through stop/full plus every probe decode "
                    "incurred through stop/full"
                ),
                "probe_prompt_tokens": "reported separately",
            },
            "bootstrap": {
                "kind": "paired hierarchical: resample seeds, then rows within seed",
                "samples": args.bootstrap_samples,
                "seed": args.bootstrap_seed,
            },
            "coverage": {
                "run_count": run_count,
                "detail_row_count": len(details),
                "environment_metric_row_count": sum(
                    row["seed"] != "pooled" for row in summaries
                ),
                "split_pooled_metric_row_count": sum(
                    row["seed"] == "pooled"
                    and row["split"] in {"train", "dev"}
                    for row in summaries
                ),
                "combined_pooled_metric_row_count": sum(
                    row["seed"] == "pooled"
                    and row["split"] == "train+dev"
                    for row in summaries
                ),
                "run_keys": [
                    {"model": model, "benchmark": benchmark, "seed": seed}
                    for model, benchmark, seed in sorted(expected_run_keys)
                ],
            },
            "source_sha256": file_hashes(source_paths),
            "input_sha256": file_hashes(input_paths),
        },
    )
    print(
        json.dumps(
            {
                "method_id": METHOD_ID,
                "runs": run_count,
                "details": len(details),
                "metrics": len(summaries),
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
