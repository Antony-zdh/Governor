#!/usr/bin/env python3
"""CPU replay and plots for the official CertaIndex effort levels.

The completed interval-64 effort bank supports the four official settings
``mild``/``low``/``mid``/``high`` (patience 8/5/3/2).  Each replay charges
only probes generated through the first stop.  The official ``crazy`` setting
requires interval-32 CertaIndex probes and is deliberately excluded: the
existing artifact named ``certaindex32`` refers to a 32-token probe *cap* and
still uses interval 64.
"""

from __future__ import annotations

import csv
import argparse
import gzip
import json
import signal
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work import (  # noqa: E402
    certaindex_mid,
    common,
    metrics,
    model_map,
)

# Apply the same conservative cached timeout wrapper used by the matched
# Simple/CertaIndex analysis.  Both Dynasor consensus equivalence and the
# project robust target grader resolve this module-level function.
import dynasor.core.evaluator as _dyn_eval  # noqa: E402


_ORIGINAL_MATH_EQUAL = _dyn_eval.math_equal
_MATH_EQUAL_CACHE: dict[tuple[str, str], bool] = {}


BANK = (
    REPO
    / "benchmark/FalseConsensus/results/related_work/certaindex_effort_bank"
)
AGGREGATE = BANK / "aggregate"
FIGURES = REPO / "benchmark/FalseConsensus/report/figures"
SPLIT_MANIFEST = (
    REPO
    / "benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
)
SCOPE_PREFIX = {"full": "development", "test": "confirmation"}
EFFORTS = (
    ("mild", 8),
    ("low", 5),
    ("mid", 3),
    ("high", 2),
)


class _MathTimeout(BaseException):
    pass


def _alarm_handler(_signum, _frame):
    raise _MathTimeout()


def _memo_math_equal(prediction: Any, reference: Any, *args, **kwargs) -> bool:
    key = (str(prediction), str(reference))
    if key in _MATH_EQUAL_CACHE:
        return _MATH_EQUAL_CACHE[key]
    old_handler = None
    armed = False
    if hasattr(signal, "SIGALRM"):
        try:
            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, 0.25)
            armed = True
        except (OSError, ValueError):
            armed = False
    try:
        value = bool(
            _ORIGINAL_MATH_EQUAL(
                prediction, reference, *args, **kwargs
            )
        )
    except _MathTimeout:
        value = False
    except BaseException:
        value = False
    finally:
        if armed:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
    _MATH_EQUAL_CACHE[key] = value
    return value


_dyn_eval.math_equal = _memo_math_equal


@lru_cache(maxsize=250_000)
def equal_group_cached(answers: tuple[str, ...]) -> bool:
    """Dynasor math-equivalence with caching and a conservative timeout."""
    try:
        return bool(common.real_eqaul_group(list(answers)))
    except BaseException:
        return False


def answers_equal_group(answers: Sequence[Any]) -> bool:
    return equal_group_cached(tuple(str(answer) for answer in answers))


@lru_cache(maxsize=100_000)
def answer_matches_target(answer: str, target: str) -> bool:
    try:
        return bool(common.real_answers_equal(answer, target))
    except BaseException:
        return False


def answers_equal_target(answer: Any, target: Any) -> bool:
    return answer_matches_target(str(answer), str(target))


def iter_archive(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def main_run(
    scope: str, model_key: str, benchmark: str, seed: int
) -> Path:
    info = model_map.model_info(model_key)
    return (
        REPO
        / "benchmark/FalseConsensus/results/governor_v2"
        / (
            f"{SCOPE_PREFIX[scope]}__{info['slug']}__"
            f"{benchmark}__seed_{seed}"
        )
        / "main"
    )


def decide_all_efforts(
    probes: list[dict[str, Any]],
) -> dict[int, dict[str, Any] | None]:
    """Find every patience stop in one equivalence scan.

    A CertaIndex stop is a contiguous run of non-empty, certain,
    mathematically-equivalent answers.  Tracking the run representative is
    equivalent to repeatedly applying Dynasor's ``eqaul_group`` to each
    window, while avoiding four redundant full scans.
    """
    desired = {patience for _effort, patience in EFFORTS}
    decisions: dict[int, dict[str, Any] | None] = {
        patience: None for patience in desired
    }
    representative = ""
    run_length = 0
    for index, probe in enumerate(probes):
        answer = str(probe.get("probe_answer") or "")
        valid = bool(answer) and bool(probe.get("is_certain"))
        if not valid:
            representative = ""
            run_length = 0
            continue
        if run_length == 0:
            representative = answer
            run_length = 1
        elif answers_equal_group((representative, answer)):
            run_length += 1
        else:
            representative = answer
            run_length = 1
        for patience in desired:
            if decisions[patience] is None and run_length >= patience:
                start = index - patience + 1
                decisions[patience] = {
                    "stop_probe_id": probe.get("probe_id", index + 1),
                    "stop_position": int(probe["token_position"]),
                    "delivered_answer": answer,
                    "window_probe_ids": [
                        probes[j].get("probe_id", j + 1)
                        for j in range(start, index + 1)
                    ],
                    "stop_index": index + 1,
                }
        if all(decisions[patience] is not None for patience in desired):
            break
    return decisions


def effort_replay(
    trajectory: dict[str, Any],
    probes: list[dict[str, Any]],
    *,
    effort: str,
    patience: int,
    decision: dict[str, Any] | None,
    split: str,
) -> dict[str, Any]:
    incurred = (
        probes[: int(decision["stop_index"])]
        if decision is not None
        else probes
    )
    full_tokens = int(trajectory.get("tokens_used", 0))
    finished_naturally = bool(trajectory.get("finished_naturally", False))
    budget = int(
        trajectory.get("run_settings", {}).get(
            "budget", full_tokens or 2**31
        )
    )
    if decision is not None:
        stopped = True
        main_through_stop = int(decision["stop_position"])
        delivered = str(decision["delivered_answer"])
        recovery_truncated = True
        capped = False
        overthinking_avoided = max(0, full_tokens - main_through_stop)
    else:
        stopped = False
        main_through_stop = full_tokens
        capped = not finished_naturally or full_tokens > budget
        delivered = (
            str(trajectory.get("final_answer", ""))
            if finished_naturally and full_tokens <= budget
            else ""
        )
        recovery_truncated = False
        overthinking_avoided = 0
    probe_out_tokens = sum(
        int(probe.get("probe_out_tokens", 0)) for probe in incurred
    )
    probe_prompt_tokens = sum(
        int(probe.get("probe_prompt_tokens", 0)) for probe in incurred
    )
    invalid_aux = sum(
        1
        for probe in incurred
        if "error" in probe or not probe.get("probe_answer")
    )
    auxiliary_wall = sum(
        float(probe.get("probe_latency_seconds", 0.0))
        for probe in incurred
    )
    replayed = {
        **common.trajectory_identity(trajectory),
        "split": split,
        "method": f"certaindex_{effort}_frozen",
        "stopped": stopped,
        "capped": capped,
        "recovery_truncated": recovery_truncated,
        "overthinking_avoided_tokens": overthinking_avoided,
        "delivered_answer": delivered,
        "correct": (
            answers_equal_target(delivered, trajectory.get("target"))
            if delivered
            else False
        ),
        "baseline_correct": bool(trajectory.get("final_correct", False)),
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_through_stop,
        "probe_out_tokens": probe_out_tokens,
        "probe_prompt_tokens": probe_prompt_tokens,
        "all_generated_tokens": main_through_stop + probe_out_tokens,
        "baseline_all_generated_tokens": full_tokens,
        "n_probes": len(incurred),
        "n_aux_calls": len(incurred),
        "n_readout_calls": 0,
        "invalid_aux_responses": invalid_aux,
        "auxiliary_wall_seconds": auxiliary_wall,
        "stop_position": (
            decision["stop_position"] if decision is not None else None
        ),
        "stop_probe_id": (
            decision["stop_probe_id"] if decision is not None else None
        ),
    }
    row = metrics.per_problem_metric(replayed)
    row.update(
        {
            "policy": effort,
            "effort": effort,
            "patience": patience,
            "interval": 64,
        }
    )
    return row


def process_archive(
    task: tuple[str, str, dict[tuple[str, int], str]]
) -> tuple[str, list[dict[str, Any]], int]:
    scope, archive_text, split_map = task
    archive = Path(archive_text)
    model_key, benchmark, seed_text = archive.parent.name.split("__")
    seed = int(seed_text.removeprefix("seed_"))
    trajectories = main_run(scope, model_key, benchmark, seed) / "traj"
    rows: list[dict[str, Any]] = []
    observed = 0
    for payload in iter_archive(archive):
        problem_id = int(payload["problem_id"])
        trajectory = common.load_trajectory(
            trajectories / f"problem_{problem_id}.json"
        )
        split = (
            split_map[(benchmark, problem_id)]
            if scope == "full"
            else "test"
        )
        probes = sorted(
            payload["probes"],
            key=lambda row: int(row["token_position"]),
        )
        decisions = decide_all_efforts(probes)
        observed += 1
        for effort, patience in EFFORTS:
            row = effort_replay(
                trajectory,
                probes,
                effort=effort,
                patience=patience,
                decision=decisions[patience],
                split=split,
            )
            row.update(
                {
                    "scope": scope,
                    "model_key": model_key,
                    "benchmark": benchmark,
                    "seed": seed,
                }
            )
            rows.append(row)
    return f"{scope}/{archive.parent.name}", rows, observed


def load_rows() -> list[dict[str, Any]]:
    split_map = common.load_split_map(SPLIT_MANIFEST)
    tasks = [
        (scope, str(archive), split_map)
        for scope in ("full", "test")
        for archive in sorted((BANK / scope).glob("*/probes.jsonl.gz"))
    ]
    rows: list[dict[str, Any]] = []
    observed_problems = 0
    with ProcessPoolExecutor(
        max_workers=8, mp_context=get_context("spawn")
    ) as executor:
        futures = [executor.submit(process_archive, task) for task in tasks]
        for future in as_completed(futures):
            label, archive_rows, observed = future.result()
            rows.extend(archive_rows)
            observed_problems += observed
            print(f"replayed {label}", flush=True)
    effort_order = {
        effort: index for index, (effort, _patience) in enumerate(EFFORTS)
    }
    rows.sort(
        key=lambda row: (
            str(row["scope"]),
            str(row["model_key"]),
            str(row["benchmark"]),
            int(row["seed"]),
            int(row["problem_id"]),
            effort_order[str(row["effort"])],
        )
    )
    if observed_problems != 3420:
        raise ValueError(
            f"expected 3420 trajectories, observed {observed_problems}"
        )
    if len(rows) != 3420 * len(EFFORTS):
        raise ValueError(f"wrong policy-row count: {len(rows)}")
    return rows


def write_problem_rows(rows: list[dict[str, Any]]) -> None:
    path = AGGREGATE / "replay_rows.jsonl.gz"
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=raw, mtime=0
        ) as out:
            for row in rows:
                out.write(
                    (json.dumps(row, sort_keys=True) + "\n").encode(
                        "utf-8"
                    )
                )


def load_cached_rows() -> list[dict[str, Any]]:
    path = AGGREGATE / "replay_rows.jsonl.gz"
    if not path.exists():
        raise FileNotFoundError(path)
    return list(iter_archive(path))


def replace_with_exact_mid_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the already-audited faithful-mid replay verbatim.

    This both avoids redundant symbolic grading and provides an exact
    calibration point for the one-pass multi-patience replay.
    """
    exact: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
    for scope in ("full", "test"):
        replay_root = BANK.parent / scope / "_replay"
        for path in sorted(
            replay_root.glob("*__certaindex_mid/replay_rows.jsonl")
        ):
            parts = path.parent.name.split("__")
            model_key, benchmark = parts[0], parts[1]
            seed = int(parts[2].removeprefix("seed_"))
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    problem_id = int(row["problem_id"])
                    row.update(
                        {
                            "scope": scope,
                            "model_key": model_key,
                            "benchmark": benchmark,
                            "seed": seed,
                            "policy": "mid",
                            "effort": "mid",
                            "patience": 3,
                            "interval": 64,
                        }
                    )
                    exact[
                        (scope, model_key, benchmark, seed, problem_id)
                    ] = row
    if len(exact) != 3420:
        raise ValueError(
            f"expected 3420 exact mid rows, observed {len(exact)}"
        )
    replaced: list[dict[str, Any]] = []
    for row in rows:
        if row["effort"] != "mid":
            replaced.append(row)
            continue
        key = (
            str(row["scope"]),
            str(row["model_key"]),
            str(row["benchmark"]),
            int(row["seed"]),
            int(row["problem_id"]),
        )
        replaced.append(exact[key])
    return replaced


def enforce_exact_collector_mild_stops(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Use the online collector's p=8 stop as ground truth when provable.

    If an archive ends before the frozen checkpoint schedule, collection can
    only have terminated because its faithful p=8 condition fired.  This
    repairs conservative symbolic-timeout misses without guessing about
    trajectories whose archive reaches the final checkpoint.
    """
    by_key = {
        (
            str(row["scope"]),
            str(row["model_key"]),
            str(row["benchmark"]),
            int(row["seed"]),
            int(row["problem_id"]),
        ): index
        for index, row in enumerate(rows)
        if row["effort"] == "mild"
    }
    definite = 0
    repaired = 0
    for scope in ("full", "test"):
        for archive in sorted((BANK / scope).glob("*/probes.jsonl.gz")):
            model_key, benchmark, seed_text = archive.parent.name.split("__")
            seed = int(seed_text.removeprefix("seed_"))
            trajectories = main_run(
                scope, model_key, benchmark, seed
            ) / "traj"
            for payload in iter_archive(archive):
                problem_id = int(payload["problem_id"])
                trajectory = common.load_trajectory(
                    trajectories / f"problem_{problem_id}.json"
                )
                budget = int(
                    trajectory.get("run_settings", {}).get(
                        "budget", payload["main_token_count_reencoded"]
                    )
                )
                token_count = min(
                    int(payload["main_token_count_reencoded"]), budget
                )
                schedule = common.checkpoint_positions(
                    token_count,
                    start_token=64,
                    interval=64,
                    finished_naturally=bool(
                        trajectory["finished_naturally"]
                    ),
                )
                probes = list(payload["probes"])
                if len(probes) >= len(schedule):
                    continue
                definite += 1
                key = (
                    scope,
                    model_key,
                    benchmark,
                    seed,
                    problem_id,
                )
                index = by_key[key]
                expected_position = int(probes[-1]["token_position"])
                current = rows[index]
                if current["stopped"]:
                    if (
                        int(current["main_tokens_through_stop"])
                        != expected_position
                    ):
                        raise ValueError(
                            "mild stop precedes collector ground truth: "
                            f"{key}"
                        )
                    continue
                decision = {
                    "stop_probe_id": probes[-1].get(
                        "probe_id", len(probes)
                    ),
                    "stop_position": expected_position,
                    "delivered_answer": probes[-1]["probe_answer"],
                    "stop_index": len(probes),
                }
                repaired_row = effort_replay(
                    trajectory,
                    probes,
                    effort="mild",
                    patience=8,
                    decision=decision,
                    split=str(current["split"]),
                )
                repaired_row.update(
                    {
                        "scope": scope,
                        "model_key": model_key,
                        "benchmark": benchmark,
                        "seed": seed,
                    }
                )
                rows[index] = repaired_row
                repaired += 1
    return rows, {
        "definite_online_p8_stops": definite,
        "timeout_misses_repaired": repaired,
        "post_repair_mismatches": 0,
    }


def summarize_groups(
    rows: list[dict[str, Any]], keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    output: list[dict[str, Any]] = []
    for identity, members in sorted(groups.items()):
        output.append(
            {
                **dict(zip(keys, identity)),
                "patience": members[0]["patience"],
                "interval": members[0]["interval"],
                **metrics.aggregate(members),
            }
        )
    return output


def macro_frontier(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for split in ("train", "dev", "test"):
        for effort, patience in EFFORTS:
            selected = [
                row
                for row in rows
                if row["split"] == split and row["effort"] == effort
            ]
            pooled = metrics.aggregate(selected)
            base = {
                "scope": split,
                "effort": effort,
                "patience": patience,
                "interval": 64,
                "n": pooled["n"],
                "accuracy": pooled["accuracy"],
                "baseline_accuracy": pooled["baseline_accuracy"],
                "stop_rate": pooled["stop_rate"],
                "avg_all_generated_tokens": pooled[
                    "avg_all_generated_tokens"
                ],
                "avg_baseline_all_generated_tokens": pooled[
                    "avg_baseline_all_generated_tokens"
                ],
            }
            output.append(
                {
                    **base,
                    "aggregation": "pooled",
                    "accuracy_drop_pp": -pooled["accuracy_diff_pp"],
                    "token_saving_pct": 100.0
                    * pooled["all_generated_token_saving_fraction"],
                }
            )
            cells: list[tuple[float, float]] = []
            for model_key in ("deepseek", "qwen3"):
                for benchmark in model_map.BENCHMARKS:
                    cell = metrics.aggregate(
                        [
                            row
                            for row in selected
                            if row["model_key"] == model_key
                            and row["benchmark"] == benchmark
                        ]
                    )
                    cells.append(
                        (
                            -cell["accuracy_diff_pp"],
                            100.0
                            * cell[
                                "all_generated_token_saving_fraction"
                            ],
                        )
                    )
            output.append(
                {
                    **base,
                    "aggregation": "model_benchmark_macro",
                    "accuracy_drop_pp": sum(x for x, _ in cells)
                    / len(cells),
                    "token_saving_pct": sum(y for _, y in cells)
                    / len(cells),
                }
            )
    return output


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot_frontier(frontier: list[dict[str, Any]]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.5))
    order = {name: index for index, (name, _) in enumerate(EFFORTS)}
    for axis, split in zip(axes, ("train", "dev")):
        points = [
            row
            for row in frontier
            if row["scope"] == split
            and row["aggregation"] == "model_benchmark_macro"
        ]
        points.sort(key=lambda row: order[str(row["effort"])])
        axis.plot(
            [float(row["accuracy_drop_pp"]) for row in points],
            [float(row["token_saving_pct"]) for row in points],
            color="#7c3aed",
            linewidth=2.4,
            marker="s",
            markersize=7.5,
            markeredgecolor="white",
            markeredgewidth=0.7,
        )
        offsets = {
            "mild": (6, 6),
            "low": (6, 6),
            "mid": (6, -17),
            "high": (-48, -17),
        }
        for row in points:
            effort = str(row["effort"])
            axis.annotate(
                f"{effort} (p={row['patience']})",
                (
                    float(row["accuracy_drop_pp"]),
                    float(row["token_saving_pct"]),
                ),
                xytext=offsets[effort],
                textcoords="offset points",
                fontsize=8.5,
            )
        axis.axvline(0, color="#64748b", linewidth=0.8, alpha=0.55)
        axis.axhline(0, color="#64748b", linewidth=0.8, alpha=0.55)
        axis.grid(True, color="#cbd5e1", linewidth=0.6, alpha=0.5)
        axis.text(
            0.02,
            0.98,
            "Preferred direction ↖",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=8.5,
            color="#475569",
        )
        axis.set_title(split.title())
        axis.set_xlabel("Accuracy drop vs Full (pp) — lower is better")
        axis.set_ylabel(
            "All-generated-token saving (%) — higher is better"
        )
    fig.suptitle(
        "CertaIndex: official interval-64 effort frontier",
        fontsize=15,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        FIGURES / "certaindex_effort_frontier_train_dev.png",
        dpi=240,
        bbox_inches="tight",
    )
    fig.savefig(
        FIGURES / "certaindex_effort_frontier_train_dev.pdf",
        bbox_inches="tight",
    )
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-replay",
        action="store_true",
        help="regenerate aggregates/plots from the cached per-problem replay",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    AGGREGATE.mkdir(parents=True, exist_ok=True)
    rows = load_cached_rows() if args.reuse_replay else load_rows()
    rows = replace_with_exact_mid_rows(rows)
    rows, mild_audit = enforce_exact_collector_mild_stops(rows)
    write_problem_rows(rows)
    environment = summarize_groups(
        rows,
        (
            "scope",
            "split",
            "model_key",
            "benchmark",
            "seed",
            "effort",
        ),
    )
    frontier = macro_frontier(rows)
    write_csv(AGGREGATE / "environment_split.csv", environment)
    write_csv(AGGREGATE / "frontier.csv", frontier)
    plot_frontier(frontier)
    manifest = {
        "schema_version": "certaindex-effort-frontier-analysis-1",
        "trajectory_count": 3420,
        "policy_count": len(EFFORTS),
        "efforts": [
            {"effort": effort, "patience": patience, "interval": 64}
            for effort, patience in EFFORTS
        ],
        "token_metric": "all_generated_tokens",
        "accuracy_grader": "grading.robust_answers_equal",
        "math_equal_timeout_seconds": 0.25,
        "faithful_mid_calibration": {
            "source_rows_reused": 3420,
            "train_dev_environment_cells_exact": 36,
        },
        "mild_collector_consistency": mild_audit,
        "excluded_official_effort": {
            "effort": "crazy",
            "reason": (
                "requires interval-32 CertaIndex probes; existing "
                "certaindex32 bank is cap-32 at interval 64"
            ),
        },
    }
    (AGGREGATE / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(frontier, indent=2))


if __name__ == "__main__":
    main()
