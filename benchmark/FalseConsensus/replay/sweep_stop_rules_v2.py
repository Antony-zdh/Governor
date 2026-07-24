"""Stage 10 v1 offline rule sweep on the paired simple@32 probe stream.

The script extends the Stage-7 replay with:

- actual per-probe output cost from simple@32;
- schema-aware validity filtering;
- fixed, MATH-level-adaptive, and online-instability-adaptive token floors;
- history stability constraints;
- a deterministic 60/20/20 problem split;
- selection on validation, one-shot reporting on test;
- Qwen3-8B transfer using its available simple@10 stream.

No model calls are made. Qwen does not have a paired simple@32 stream, so its
result tests rule transfer, not a probe-design-matched compute comparison.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FC_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = FC_DIR.parents[1]
sys.path.insert(0, str(REPO_DIR))

from dynasor.core.evaluator import math_equal, strip_string  # noqa: E402


SINGLE_LETTER_RE = re.compile(r"^[A-Da-d]$")
VALIDITY_MODES = ("nonempty", "schema")


@lru_cache(maxsize=None)
def eq(a: str, b: str) -> bool:
    a, b = str(a), str(b)
    if a == b:
        return True
    try:
        return bool(math_equal(a, b))
    except Exception:
        return False


def normalized(answer: object) -> str:
    answer = str(answer)
    try:
        return strip_string(answer)
    except Exception:
        return answer.strip()


def answer_equal(a: object, b: object) -> bool:
    return eq(normalized(a), normalized(b)) or eq(str(a), str(b))


def correct(answer: object, target: object) -> bool:
    answer, target = str(answer), str(target)
    if answer_equal(answer, target):
        return True
    deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", target)
    if deprefixed != target and answer_equal(answer, deprefixed):
        return True
    match = re.fullmatch(r"\s*\\text\{(.*)\}\s*", target, flags=re.DOTALL)
    return bool(match) and answer.strip().lower() == match.group(1).strip().lower()


def as_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes"}


def equivalence_ids(answers: list[str]) -> tuple[list[int], list[str]]:
    representatives: list[str] = []
    ids: list[int] = []
    for answer in answers:
        if answer == "":
            ids.append(-1)
            continue
        found = None
        for answer_id, representative in enumerate(representatives):
            if answer_equal(answer, representative):
                found = answer_id
                break
        if found is None:
            found = len(representatives)
            representatives.append(answer)
        ids.append(found)
    return ids, representatives


def valid_id(answer: str, answer_id: int, mode: str) -> int:
    if answer_id < 0:
        return -1
    if mode == "schema" and SINGLE_LETTER_RE.fullmatch(answer):
        return -1
    if mode not in VALIDITY_MODES:
        raise ValueError(mode)
    return answer_id


def history_features(
    tokens: list[int], answer_ids: list[int]
) -> tuple[list[int], list[int]]:
    switches = []
    stable_spans = []
    last_id = None
    last_switch_token = None
    first_valid_token = None
    count = 0
    for token, answer_id in zip(tokens, answer_ids):
        if answer_id >= 0:
            if first_valid_token is None:
                first_valid_token = token
            if last_id is not None and answer_id != last_id:
                count += 1
                last_switch_token = token
            last_id = answer_id
        anchor = last_switch_token if last_switch_token is not None else first_valid_token
        switches.append(count)
        stable_spans.append(0 if anchor is None else token - anchor)
    return switches, stable_spans


def online_hard(answer_ids: list[int]) -> bool:
    early = answer_ids[:4]
    valid = [answer_id for answer_id in early if answer_id >= 0]
    invalid_share = 1 - len(valid) / max(1, len(early))
    switches = sum(a != b for a, b in zip(valid, valid[1:]))
    return invalid_share >= 0.5 or len(set(valid)) >= 3 or switches >= 2


def prepare_problem(
    pid: int,
    stream: pd.DataFrame,
    trajectory: dict,
    level: int,
    subject: str,
    default_probe_cost: int | None = None,
) -> dict:
    stream = stream.sort_values("probe_id").reset_index(drop=True)
    tokens = [int(x) for x in stream["token_position"]]
    answers = [str(x) for x in stream["probe_answer"]]
    certain = [as_bool(x) for x in stream["is_certain"]]
    if "probe_out_tokens" in stream:
        probe_costs = [int(x) for x in stream["probe_out_tokens"]]
    elif default_probe_cost is not None:
        probe_costs = [default_probe_cost] * len(stream)
    else:
        raise ValueError("Probe costs are unavailable")

    raw_ids, representatives = equivalence_ids(answers)
    validity = {}
    switches = {}
    stable_spans = {}
    online = {}
    for mode in VALIDITY_MODES:
        ids = [
            valid_id(answer, answer_id, mode)
            for answer, answer_id in zip(answers, raw_ids)
        ]
        validity[mode] = ids
        switches[mode], stable_spans[mode] = history_features(tokens, ids)
        online[mode] = online_hard(ids)

    target = trajectory["target"]
    representative_correct = {
        answer_id: correct(answer, target)
        for answer_id, answer in enumerate(representatives)
    }
    return {
        "pid": pid,
        "level": int(level),
        "subject": subject,
        "tokens": tokens,
        "answers": answers,
        "certain": certain,
        "probe_costs": probe_costs,
        "representatives": representatives,
        "representative_correct": representative_correct,
        "validity": validity,
        "switches": switches,
        "stable_spans": stable_spans,
        "online_hard": online,
        "full_tokens": int(trajectory["tokens_used"]),
        "final_answer": str(trajectory["final_answer"]),
        "final_correct": bool(trajectory["final_correct"]),
        "probe1_correct": correct(answers[0], target) if answers else False,
    }


def load_trajectories(path: Path) -> dict[int, dict]:
    trajectories = {}
    for file in path.glob("problem_*.json"):
        data = json.loads(file.read_text())
        trajectories[int(data["problem_id"])] = data
    return trajectories


def load_deepseek_problems(
    paired_csv: Path,
    traj_dir: Path,
    difficulty_csv: Path,
) -> dict[int, dict]:
    df = pd.read_csv(paired_csv, keep_default_na=False)
    df = df[df["variant"] == "simple__32"].copy()
    trajectories = load_trajectories(traj_dir)
    difficulty = pd.read_csv(difficulty_csv, keep_default_na=False).set_index(
        "problem_id"
    )
    problems = {}
    for pid, stream in df.groupby("problem_id"):
        pid = int(pid)
        row = difficulty.loc[pid]
        problems[pid] = prepare_problem(
            pid,
            stream,
            trajectories[pid],
            int(row["level"]),
            str(row["subject"]),
        )
    return problems


def load_qwen_problems(
    probes_csv: Path,
    traj_dir: Path,
    difficulty_csv: Path,
) -> dict[int, dict]:
    df = pd.read_csv(probes_csv, keep_default_na=False)
    trajectories = load_trajectories(traj_dir)
    difficulty = pd.read_csv(difficulty_csv, keep_default_na=False).set_index(
        "problem_id"
    )
    problems = {}
    for pid, stream in df.groupby("problem_id"):
        pid = int(pid)
        row = difficulty.loc[pid]
        problems[pid] = prepare_problem(
            pid,
            stream,
            trajectories[pid],
            int(row["level"]),
            str(row["subject"]),
            default_probe_cost=10,
        )
    return problems


def build_split(problems: dict[int, dict], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for level in sorted({problem["level"] for problem in problems.values()}):
        ids = np.array(
            sorted(pid for pid, problem in problems.items() if problem["level"] == level)
        )
        rng.shuffle(ids)
        n = len(ids)
        n_train = int(round(0.60 * n))
        n_val = int(round(0.20 * n))
        assignments = (
            ["train"] * n_train
            + ["validation"] * n_val
            + ["test"] * (n - n_train - n_val)
        )
        rows.extend(
            {"problem_id": int(pid), "level": level, "split": split}
            for pid, split in zip(ids, assignments)
        )
    return pd.DataFrame(rows).sort_values("problem_id").reset_index(drop=True)


def floor_specs() -> list[dict]:
    specs = [
        {"floor_kind": "fixed", "easy_min": value, "hard_min": value}
        for value in [0, 512, 768, 1024, 1280, 1536, 2048]
    ]
    for kind in ["level", "online"]:
        specs.extend(
            {"floor_kind": kind, "easy_min": easy, "hard_min": hard}
            for easy, hard in [
                (512, 1024),
                (512, 1536),
                (768, 1536),
                (768, 2048),
                (1024, 2048),
            ]
        )
    return specs


def floor_id(spec: dict) -> str:
    if spec["floor_kind"] == "fixed":
        return f"fixed{spec['easy_min']}"
    return f"{spec['floor_kind']}{spec['easy_min']}-{spec['hard_min']}"


def build_configs() -> list[dict]:
    configs = []
    for mode in VALIDITY_MODES:
        for require_certain in [False, True]:
            for patience in [3, 4, 5, 6, 8]:
                for floor in floor_specs():
                    configs.append(
                        {
                            "config_id": (
                                f"consec_p{patience}_{floor_id(floor)}_"
                                f"cert{int(require_certain)}_valid{mode}"
                            ),
                            "family": "consecutive",
                            "patience": patience,
                            "require_certain": require_certain,
                            "validity_mode": mode,
                            **floor,
                        }
                    )

    history_floors = [
        spec
        for spec in floor_specs()
        if (
            spec["floor_kind"] == "fixed"
            and spec["easy_min"] in {512, 768, 1024, 1536}
        )
        or (
            spec["floor_kind"] in {"level", "online"}
            and (spec["easy_min"], spec["hard_min"])
            in {(512, 1536), (768, 2048)}
        )
    ]
    stability_specs = [
        {"max_switches": None, "stable_span": 0},
        {"max_switches": 2, "stable_span": 256},
        {"max_switches": 1, "stable_span": 512},
    ]
    for mode in VALIDITY_MODES:
        for require_certain in [False, True]:
            for window_size, min_valid in [(5, 3), (5, 5), (8, 5)]:
                for share in [0.8, 1.0]:
                    for floor in history_floors:
                        for stability in stability_specs:
                            switch_id = (
                                "any"
                                if stability["max_switches"] is None
                                else stability["max_switches"]
                            )
                            configs.append(
                                {
                                    "config_id": (
                                        f"hist_w{window_size}_mv{min_valid}_s{share}_"
                                        f"{floor_id(floor)}_sw{switch_id}_"
                                        f"span{stability['stable_span']}_"
                                        f"cert{int(require_certain)}_valid{mode}"
                                    ),
                                    "family": "history",
                                    "window_size": window_size,
                                    "min_valid": min_valid,
                                    "share": share,
                                    "require_certain": require_certain,
                                    "validity_mode": mode,
                                    **floor,
                                    **stability,
                                }
                            )
    return configs


def required_min_tokens(config: dict, problem: dict) -> int:
    kind = config["floor_kind"]
    if kind == "fixed":
        return int(config["easy_min"])
    if kind == "level":
        hard = problem["level"] >= 4
    elif kind == "online":
        hard = problem["online_hard"][config["validity_mode"]]
    else:
        raise ValueError(kind)
    return int(config["hard_min"] if hard else config["easy_min"])


def simulate(config: dict, problem: dict) -> tuple[int | None, int | None]:
    mode = config["validity_mode"]
    ids = problem["validity"][mode]
    tokens = problem["tokens"]
    certain = problem["certain"]
    minimum = required_min_tokens(config, problem)

    if config["family"] == "consecutive":
        patience = config["patience"]
        for end in range(patience - 1, len(ids)):
            if tokens[end] < minimum:
                continue
            window_ids = ids[end - patience + 1 : end + 1]
            if any(answer_id < 0 for answer_id in window_ids):
                continue
            if len(set(window_ids)) != 1:
                continue
            if config["require_certain"] and not all(
                certain[end - patience + 1 : end + 1]
            ):
                continue
            return end, window_ids[-1]
        return None, None

    if config["family"] == "history":
        for end in range(len(ids)):
            if tokens[end] < minimum:
                continue
            start = max(0, end - config["window_size"] + 1)
            window_ids = ids[start : end + 1]
            valid_positions = [
                offset
                for offset, answer_id in enumerate(window_ids)
                if answer_id >= 0
            ]
            valid_ids = [window_ids[offset] for offset in valid_positions]
            if len(valid_ids) < config["min_valid"]:
                continue
            counts = Counter(valid_ids)
            dominant_id, dominant_count = counts.most_common(1)[0]
            if dominant_count / len(valid_ids) < config["share"]:
                continue
            if config["require_certain"] and not all(
                certain[start + offset] for offset in valid_positions
            ):
                continue
            max_switches = config["max_switches"]
            if (
                max_switches is not None
                and problem["switches"][mode][end] > max_switches
            ):
                continue
            if problem["stable_spans"][mode][end] < config["stable_span"]:
                continue
            return end, dominant_id
        return None, None

    raise ValueError(config["family"])


def evaluate_rows(
    config: dict | None,
    problems: dict[int, dict],
    problem_ids: set[int],
    method: str,
) -> pd.DataFrame:
    rows = []
    for pid in sorted(problem_ids):
        problem = problems[pid]
        if config is None:
            stop_index, answer_id = None, None
            delivered_correct = problem["final_correct"]
            main_tokens = problem["full_tokens"]
            probe_tokens = 0
            probe_calls = 0
            stopped = False
            stop_correct = None
        else:
            stop_index, answer_id = simulate(config, problem)
            stopped = stop_index is not None
            if stopped:
                assert answer_id is not None
                stop_correct = bool(problem["representative_correct"][answer_id])
                delivered_correct = stop_correct
                main_tokens = problem["tokens"][stop_index]
                probe_tokens = sum(problem["probe_costs"][: stop_index + 1])
                probe_calls = stop_index + 1
            else:
                stop_correct = None
                delivered_correct = problem["final_correct"]
                main_tokens = problem["full_tokens"]
                probe_tokens = sum(problem["probe_costs"])
                probe_calls = len(problem["probe_costs"])
        rows.append(
            {
                "method": method,
                "config_id": "vanilla" if config is None else config["config_id"],
                "problem_id": pid,
                "level": problem["level"],
                "subject": problem["subject"],
                "delivered_correct": bool(delivered_correct),
                "final_correct": problem["final_correct"],
                "stopped": stopped,
                "stop_correct": stop_correct,
                "main_tokens": main_tokens,
                "probe_tokens": probe_tokens,
                "probe_calls": probe_calls,
                "total_tokens": main_tokens + probe_tokens,
                "recovery_truncated": bool(
                    stopped and problem["final_correct"] and not stop_correct
                ),
                "overthinking_avoided": bool(
                    stopped and stop_correct and not problem["final_correct"]
                ),
            }
        )
    return pd.DataFrame(rows)


def aggregate(rows: pd.DataFrame) -> dict:
    stopped = rows[rows["stopped"]]
    return {
        "config_id": str(rows["config_id"].iloc[0]),
        "n_problems": int(len(rows)),
        "overall_accuracy": float(rows["delivered_correct"].mean()),
        "avg_main_tokens": float(rows["main_tokens"].mean()),
        "avg_probe_output_tokens": float(rows["probe_tokens"].mean()),
        "avg_total_generated_tokens": float(rows["total_tokens"].mean()),
        "avg_probe_calls": float(rows["probe_calls"].mean()),
        "stop_coverage": float(rows["stopped"].mean()),
        "false_stop_rate": (
            float(1 - stopped["stop_correct"].astype(bool).mean())
            if len(stopped)
            else None
        ),
        "recovery_truncated": int(rows["recovery_truncated"].sum()),
        "overthinking_avoided": int(rows["overthinking_avoided"].sum()),
    }


def evaluate_grid(
    configs: list[dict],
    problems: dict[int, dict],
    split_ids: dict[str, set[int]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_rows = []
    validation_rows = []
    for index, config in enumerate(configs, start=1):
        train_rows.append(
            aggregate(
                evaluate_rows(
                    config, problems, split_ids["train"], method="simple@32"
                )
            )
        )
        validation_rows.append(
            aggregate(
                evaluate_rows(
                    config,
                    problems,
                    split_ids["validation"],
                    method="simple@32",
                )
            )
        )
        if index % 100 == 0:
            print(f"evaluated {index}/{len(configs)} configs")
    return pd.DataFrame(train_rows), pd.DataFrame(validation_rows)


def select_points(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    vanilla_train_accuracy: float,
    vanilla_validation_accuracy: float,
) -> dict[str, str]:
    frame = train.merge(
        validation, on="config_id", suffixes=("_train", "_validation")
    )
    frame["drop_train"] = (
        vanilla_train_accuracy - frame["overall_accuracy_train"]
    )
    frame["drop_validation"] = (
        vanilla_validation_accuracy - frame["overall_accuracy_validation"]
    )
    n_train = frame["n_problems_train"].iloc[0]
    n_validation = frame["n_problems_validation"].iloc[0]
    frame["dev_tokens"] = (
        frame["avg_total_generated_tokens_train"] * n_train
        + frame["avg_total_generated_tokens_validation"] * n_validation
    ) / (n_train + n_validation)
    frame["dev_accuracy"] = (
        frame["overall_accuracy_train"] * n_train
        + frame["overall_accuracy_validation"] * n_validation
    ) / (n_train + n_validation)
    selected = {}
    for name, bound in [("conservative", 0.01), ("balanced", 0.03)]:
        candidates = frame[
            (frame["drop_train"] <= bound)
            & (frame["drop_validation"] <= bound)
        ]
        if len(candidates):
            row = candidates.sort_values(
                ["dev_tokens", "dev_accuracy"],
                ascending=[True, False],
            ).iloc[0]
            selected[name] = str(row["config_id"])
    selected["aggressive"] = str(
        frame.sort_values(
            ["dev_tokens", "dev_accuracy"],
            ascending=[True, False],
        ).iloc[0]["config_id"]
    )
    return selected


def make_figure(
    validation: pd.DataFrame,
    vanilla: dict,
    selected: dict[str, str],
    path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(7, 5.2))
    ax.scatter(
        validation["avg_total_generated_tokens"],
        validation["overall_accuracy"],
        s=10,
        alpha=0.35,
        color="#2b6cb0",
    )
    ax.scatter(
        [vanilla["avg_total_generated_tokens"]],
        [vanilla["overall_accuracy"]],
        marker="*",
        s=130,
        color="#dd6b20",
        label="Vanilla (no probes)",
        zorder=4,
    )
    colors = {
        "conservative": "#2f855a",
        "balanced": "#805ad5",
        "aggressive": "#c53030",
    }
    for name, config_id in selected.items():
        row = validation[validation["config_id"] == config_id].iloc[0]
        ax.scatter(
            [row["avg_total_generated_tokens"]],
            [row["overall_accuracy"]],
            s=70,
            color=colors[name],
            label=name,
            zorder=5,
        )
    ax.set_xlabel("Average total generated tokens (main + probe output)")
    ax.set_ylabel("Validation accuracy")
    ax.set_title("Rule sweep on simple@32")
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def selected_result_rows(
    selected: dict[str, str],
    config_by_id: dict[str, dict],
    problems: dict[int, dict],
    ids: set[int],
    dataset_label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summaries = []
    problem_rows = []
    vanilla_rows = evaluate_rows(None, problems, ids, method=dataset_label)
    vanilla_summary = aggregate(vanilla_rows)
    vanilla_summary.update(
        {"operating_point": "vanilla", "dataset": dataset_label}
    )
    summaries.append(vanilla_summary)
    problem_rows.append(vanilla_rows.assign(operating_point="vanilla"))
    for point, config_id in selected.items():
        rows = evaluate_rows(
            config_by_id[config_id], problems, ids, method=dataset_label
        )
        summary = aggregate(rows)
        summary.update({"operating_point": point, "dataset": dataset_label})
        summaries.append(summary)
        problem_rows.append(rows.assign(operating_point=point))
    all_problem_rows = pd.concat(problem_rows, ignore_index=True)
    summary = add_paired_intervals(
        pd.DataFrame(summaries), all_problem_rows, seed=20260724
    )
    return summary, all_problem_rows


def add_paired_intervals(
    summaries: pd.DataFrame,
    problem_rows: pd.DataFrame,
    seed: int,
    n_bootstrap: int = 5000,
) -> pd.DataFrame:
    summaries = summaries.copy()
    for column in [
        "accuracy_diff_vs_vanilla",
        "accuracy_diff_ci_lo",
        "accuracy_diff_ci_hi",
        "total_token_saving_vs_vanilla",
        "token_saving_ci_lo",
        "token_saving_ci_hi",
    ]:
        summaries[column] = np.nan

    baseline = (
        problem_rows[problem_rows["operating_point"] == "vanilla"]
        .sort_values("problem_id")
        .reset_index(drop=True)
    )
    baseline_accuracy = baseline["delivered_correct"].astype(float).to_numpy()
    baseline_tokens = baseline["total_tokens"].astype(float).to_numpy()
    rng = np.random.default_rng(seed)
    indices = rng.integers(
        0, len(baseline), size=(n_bootstrap, len(baseline))
    )

    for row_index, summary in summaries.iterrows():
        point = summary["operating_point"]
        if point == "vanilla":
            summaries.loc[
                row_index,
                [
                    "accuracy_diff_vs_vanilla",
                    "accuracy_diff_ci_lo",
                    "accuracy_diff_ci_hi",
                    "total_token_saving_vs_vanilla",
                    "token_saving_ci_lo",
                    "token_saving_ci_hi",
                ],
            ] = [0, 0, 0, 0, 0, 0]
            continue

        method = (
            problem_rows[problem_rows["operating_point"] == point]
            .sort_values("problem_id")
            .reset_index(drop=True)
        )
        if not np.array_equal(
            baseline["problem_id"].to_numpy(), method["problem_id"].to_numpy()
        ):
            raise ValueError(f"Unpaired problem rows for {point}")
        method_accuracy = method["delivered_correct"].astype(float).to_numpy()
        method_tokens = method["total_tokens"].astype(float).to_numpy()

        accuracy_diff = method_accuracy.mean() - baseline_accuracy.mean()
        token_saving = 1 - method_tokens.mean() / baseline_tokens.mean()
        boot_accuracy_diff = (
            method_accuracy[indices].mean(axis=1)
            - baseline_accuracy[indices].mean(axis=1)
        )
        boot_token_saving = 1 - (
            method_tokens[indices].mean(axis=1)
            / baseline_tokens[indices].mean(axis=1)
        )
        summaries.loc[
            row_index,
            [
                "accuracy_diff_vs_vanilla",
                "accuracy_diff_ci_lo",
                "accuracy_diff_ci_hi",
                "total_token_saving_vs_vanilla",
                "token_saving_ci_lo",
                "token_saving_ci_hi",
            ],
        ] = [
            accuracy_diff,
            *np.quantile(boot_accuracy_diff, [0.025, 0.975]),
            token_saving,
            *np.quantile(boot_token_saving, [0.025, 0.975]),
        ]
    return summaries


def difficulty_breakdown(problem_rows: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (point, level), group in problem_rows.groupby(
        ["operating_point", "level"]
    ):
        rows.append(
            {
                "operating_point": point,
                "level": int(level),
                "n": len(group),
                "accuracy": float(group["delivered_correct"].mean()),
                "avg_total_tokens": float(group["total_tokens"].mean()),
                "stop_coverage": float(group["stopped"].mean()),
                "recovery_truncated": int(group["recovery_truncated"].sum()),
                "overthinking_avoided": int(
                    group["overthinking_avoided"].sum()
                ),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    path: Path,
    split: pd.DataFrame,
    selected: dict[str, str],
    validation_selected: pd.DataFrame,
    test: pd.DataFrame,
    qwen: pd.DataFrame,
    config_by_id: dict[str, dict],
) -> None:
    split_counts = split["split"].value_counts()
    lines = [
        "# Stage 10 v1 — simple@32 rule sweep",
        "",
        "This is an offline replay; no model calls were made.",
        "",
        "## Protocol",
        "",
        f"- split: train {split_counts.get('train', 0)}, validation "
        f"{split_counts.get('validation', 0)}, test {split_counts.get('test', 0)}, "
        "stratified by MATH level",
        "- selection: conservative/balanced bounds must hold independently on "
        "both train and validation; among qualifying rules, minimize pooled "
        "development cost. Test is reported only for selected rules",
        "- primary cost: vanilla has no probe cost; controller methods include "
        "actual simple@32 probe output tokens",
        "- validity filter: `schema` removes empty and single-letter A–D answers "
        "for this non-multiple-choice dataset",
        "- difficulty floors: fixed, MATH-level adaptive, and an online early-"
        "instability proxy based on the first four probes",
        "- frozen baselines evaluated on test without selection: naive p3, "
        "Stage-7 Conservative p8+1024, and Stage-7 Balanced p6+1024; the two "
        "Stage-7 rules receive the same schema filter as Governor++ v0",
        "",
        "The Stage-6 human audit has only 100 completed labels and audited the "
        "old @10 probe, so it is not used as if it were a full per-probe label "
        "set for @32. The schema filter is the available evidence-backed "
        "deterministic filter.",
        "",
        "## Selected configurations",
        "",
    ]
    for point, config_id in selected.items():
        lines.append(f"- **{point}**: `{config_id}`")
        lines.append(f"  - `{json.dumps(config_by_id[config_id], sort_keys=True)}`")

    def table(frame: pd.DataFrame) -> list[str]:
        output = [
            "| Point | Accuracy | Δ accuracy [95% CI] | Total tokens | Saving [95% CI] | Coverage | False-stop | Recovery cut | Overthinking saved |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for _, row in frame.iterrows():
            false_stop = (
                "N/A"
                if pd.isna(row["false_stop_rate"])
                else f"{row['false_stop_rate']:.1%}"
            )
            if pd.isna(row.get("accuracy_diff_vs_vanilla", np.nan)):
                accuracy_diff = "N/A"
                token_saving = "N/A"
            else:
                accuracy_diff = (
                    f"{row['accuracy_diff_vs_vanilla'] * 100:+.1f}pp "
                    f"[{row['accuracy_diff_ci_lo'] * 100:+.1f}, "
                    f"{row['accuracy_diff_ci_hi'] * 100:+.1f}]"
                )
                token_saving = (
                    f"{row['total_token_saving_vs_vanilla']:.1%} "
                    f"[{row['token_saving_ci_lo']:.1%}, "
                    f"{row['token_saving_ci_hi']:.1%}]"
                )
            output.append(
                f"| {row['operating_point']} | {row['overall_accuracy']:.1%} | "
                f"{accuracy_diff} | "
                f"{row['avg_total_generated_tokens']:.0f} | {token_saving} | "
                f"{row['stop_coverage']:.1%} | {false_stop} | "
                f"{int(row['recovery_truncated'])} | "
                f"{int(row['overthinking_avoided'])} |"
            )
        return output

    lines.extend(["", "## Validation operating points", "", *table(validation_selected)])
    lines.extend(["", "## Held-out DeepSeek test", "", *table(test)])
    lines.extend(
        [
            "",
            "## Qwen3-8B transfer hold-out",
            "",
            *table(qwen),
            "",
            "## Decision",
            "",
            "The expanded difficulty-adaptive p3 rules pass the development "
            "constraints but fail to preserve accuracy on DeepSeek test and "
            "Qwen. They therefore do not qualify as Governor++ operating points.",
            "",
            "The frozen Stage-7 Conservative v0 is the only tested rule that "
            "preserves accuracy on both DeepSeek test and Qwen. Its DeepSeek "
            "test saving is modest, and on Qwen its probe overhead cancels the "
            "main-token saving. The frozen Balanced v0 saves more on DeepSeek "
            "but incurs a clear Qwen accuracy loss. Thus this sweep does not "
            "demonstrate a cross-model Pareto improvement beyond the existing "
            "conservative rule; the accuracy–compute ceiling remains.",
            "",
            "Because the rule upgrade failed held-out transfer, do not train or "
            "promote a calibrator from this sweep alone. A matched Qwen @32 "
            "stream and/or new seed is needed for the next clean validation.",
            "",
            "Qwen has only a `simple@10` probe stream. This section tests whether "
            "the selected rule transfers without tuning, but it is not a clean "
            "simple@32 compute comparison. A matched Qwen simple@32 re-probe is "
            "required before making a cross-model probe-cost claim.",
            "",
            "Full train/validation grids and per-problem selected outputs are "
            "stored beside this report.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paired-csv",
        type=Path,
        default=FC_DIR / "results/probe_paired_2x2/reprobe_paired.csv",
    )
    parser.add_argument(
        "--stage1-traj",
        type=Path,
        default=FC_DIR / "results/stage1_logging/traj",
    )
    parser.add_argument(
        "--difficulty-csv",
        type=Path,
        default=FC_DIR
        / "results/stage9_difficulty/per_problem_with_difficulty.csv",
    )
    parser.add_argument(
        "--qwen-probes",
        type=Path,
        default=FC_DIR
        / "results/stage11_cross_model/qwen3_8b_math500/probes.csv",
    )
    parser.add_argument(
        "--qwen-traj",
        type=Path,
        default=FC_DIR / "results/stage11_cross_model/qwen3_8b_math500/traj",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FC_DIR / "results/stage10_rule_sweep",
    )
    parser.add_argument("--split-seed", type=int, default=42)
    args = parser.parse_args()

    print("Loading DeepSeek simple@32...")
    deepseek = load_deepseek_problems(
        args.paired_csv, args.stage1_traj, args.difficulty_csv
    )
    split = build_split(deepseek, args.split_seed)
    split_ids = {
        name: set(split.loc[split["split"] == name, "problem_id"].astype(int))
        for name in ["train", "validation", "test"]
    }

    configs = build_configs()
    config_by_id = {config["config_id"]: config for config in configs}
    print(f"Sweeping {len(configs)} configurations...")
    train, validation = evaluate_grid(configs, deepseek, split_ids)

    vanilla_train = aggregate(
        evaluate_rows(
            None, deepseek, split_ids["train"], method="deepseek_simple@32"
        )
    )
    vanilla_validation = aggregate(
        evaluate_rows(
            None, deepseek, split_ids["validation"], method="deepseek_simple@32"
        )
    )
    selected = select_points(
        train,
        validation,
        vanilla_train["overall_accuracy"],
        vanilla_validation["overall_accuracy"],
    )
    validation_selected = pd.DataFrame(
        [
            {
                **validation[validation["config_id"] == config_id]
                .iloc[0]
                .to_dict(),
                "operating_point": point,
            }
            for point, config_id in selected.items()
        ]
    )
    vanilla_validation.update(
        {"operating_point": "vanilla", "dataset": "deepseek_validation"}
    )
    validation_selected["dataset"] = "deepseek_validation"
    validation_selected = pd.concat(
        [pd.DataFrame([vanilla_validation]), validation_selected],
        ignore_index=True,
        sort=False,
    )

    evaluation_points = {
        "naive": "consec_p3_fixed0_cert1_validnonempty",
        "stage7_conservative_v0": "consec_p8_fixed1024_cert1_validschema",
        "stage7_balanced_v0": "consec_p6_fixed1024_cert0_validschema",
        **selected,
    }
    test, test_problem_rows = selected_result_rows(
        evaluation_points,
        config_by_id,
        deepseek,
        split_ids["test"],
        "deepseek_test_simple@32",
    )

    print("Loading Qwen simple@10 transfer hold-out...")
    qwen_problems = load_qwen_problems(
        args.qwen_probes, args.qwen_traj, args.difficulty_csv
    )
    qwen, qwen_problem_rows = selected_result_rows(
        evaluation_points,
        config_by_id,
        qwen_problems,
        set(qwen_problems),
        "qwen_holdout_simple@10",
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    split.to_csv(args.out_dir / "split_manifest.csv", index=False)
    train.to_csv(args.out_dir / "sweep_train.csv", index=False)
    validation.to_csv(args.out_dir / "sweep_validation.csv", index=False)
    validation_selected.to_csv(
        args.out_dir / "selected_validation.csv", index=False
    )
    test.to_csv(args.out_dir / "selected_test.csv", index=False)
    qwen.to_csv(args.out_dir / "selected_qwen_holdout.csv", index=False)
    test_problem_rows.to_csv(
        args.out_dir / "per_problem_test.csv", index=False
    )
    qwen_problem_rows.to_csv(
        args.out_dir / "per_problem_qwen_holdout.csv", index=False
    )
    difficulty_breakdown(test_problem_rows).to_csv(
        args.out_dir / "difficulty_breakdown_test.csv", index=False
    )
    difficulty_breakdown(qwen_problem_rows).to_csv(
        args.out_dir / "difficulty_breakdown_qwen.csv", index=False
    )
    (args.out_dir / "selected_configs.json").write_text(
        json.dumps(
            {
                point: config_by_id[config_id]
                for point, config_id in selected.items()
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    make_figure(
        validation,
        vanilla_validation,
        selected,
        args.out_dir / "pareto_validation.png",
    )
    write_report(
        args.out_dir / "report.md",
        split,
        selected,
        validation_selected,
        test,
        qwen,
        config_by_id,
    )

    print("Selected:", json.dumps(selected, indent=2))
    print(test.to_string(index=False))
    print(qwen.to_string(index=False))


if __name__ == "__main__":
    main()
