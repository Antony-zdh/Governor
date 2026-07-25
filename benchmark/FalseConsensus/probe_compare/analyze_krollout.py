"""Stage 9 §7.5.3 within-problem K-rollout root-cause analysis.

The primary consensus definition reproduces Stage 4:

* last-five-probe window;
* at least three non-empty probe answers;
* mathematical-equivalence dominant share >= 0.8;
* consensus time is the first qualifying probe token position.

The script separates within-problem and between-problem consensus-time
effects (Mundlak/group-mean centering), decomposes consensus correctness from
terminality and final correctness, and runs token-cap, dataset, validity, and
online-proxy sensitivity analyses.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import warnings
from collections import Counter
from functools import lru_cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import spearmanr


FC_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = FC_DIR.parents[1]
sys.path.insert(0, str(REPO_DIR))

from dynasor.core.evaluator import math_equal, strip_string  # noqa: E402

try:
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
except ImportError as exc:  # pragma: no cover - environment guidance
    raise SystemExit(
        "statsmodels is required. Install it in an isolated environment, then "
        "rerun this script."
    ) from exc


WINDOW = 5
MIN_VALID = 3
CONSENSUS_SHARE = 0.8
SENSITIVITY_WINDOWS = [3, 5, 8]
SENSITIVITY_SHARES = [0.6, 0.8, 1.0]
BUDGET = 16384
CT_BINS = [0, 512, 1024, 2048, 4096, np.inf]
CT_LABELS = ["<512", "512–1k", "1k–2k", "2k–4k", ">4k"]
SCHEMA_INVALID_RE = re.compile(r"^[A-Da-d]$")


@lru_cache(maxsize=None)
def eq(a: str, b: str) -> bool:
    a, b = str(a), str(b)
    if a == "" or b == "":
        return a == b
    if a == b:
        return True
    try:
        return bool(math_equal(a, b))
    except Exception:
        return False


@lru_cache(maxsize=None)
def normalized_string(value: str) -> str:
    try:
        return strip_string(value)
    except Exception:
        return value.strip()


def normalized(value: object) -> str:
    return normalized_string("" if value is None else str(value))


def unwrap_text(value: str) -> str:
    match = re.fullmatch(r"\s*\\text\{(.*)\}\s*", str(value), re.DOTALL)
    return "" if match is None else match.group(1).strip()


def answer_correct(answer: object, raw_target: object) -> bool:
    # Probe and final answers were already stripped at collection time.
    # Re-running strip_string on every probe is both redundant and expensive.
    answer = "" if answer is None else str(answer).strip()
    raw = str(raw_target)
    target = normalized(raw)
    if eq(answer, target) or eq(answer, raw):
        return True
    deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", raw)
    if deprefixed != raw and eq(answer, normalized(deprefixed)):
        return True
    unwrapped = unwrap_text(raw)
    return bool(unwrapped) and answer.strip().lower() == unwrapped.lower()


def group_answers(answers: list[str]) -> tuple[list[int], list[str]]:
    representatives: list[str] = []
    counts: list[int] = []
    for answer in answers:
        for index, representative in enumerate(representatives):
            if eq(answer, representative):
                counts[index] += 1
                break
        else:
            representatives.append(answer)
            counts.append(1)
    return counts, representatives


def valid_answer(answer: object, mode: str) -> str:
    # `probe_answer` is already the collector's strip_string output.
    answer = "" if pd.isna(answer) else str(answer).strip()
    if answer == "":
        return ""
    if mode == "schema" and SCHEMA_INVALID_RE.fullmatch(answer):
        return ""
    return answer


def local_window(
    answers: list[str],
    end: int,
    window: int = WINDOW,
    minimum_valid: int = MIN_VALID,
) -> tuple[float | None, str]:
    nonempty = [
        x for x in answers[max(0, end - window + 1) : end + 1] if x
    ]
    if len(nonempty) < minimum_valid:
        return None, ""
    counts, representatives = group_answers(nonempty)
    winner = int(np.argmax(counts))
    return counts[winner] / len(nonempty), representatives[winner]


def first_consensus(
    stream: pd.DataFrame,
    mode: str,
    threshold: float = CONSENSUS_SHARE,
    window: int = WINDOW,
    minimum_valid: int = MIN_VALID,
) -> dict[str, object]:
    answers = [valid_answer(x, mode) for x in stream["probe_answer"]]
    for end in range(minimum_valid - 1, len(stream)):
        share, dominant = local_window(
            answers, end, window=window, minimum_valid=minimum_valid
        )
        if share is not None and share >= threshold:
            row = stream.iloc[end]
            return {
                "reached": True,
                "time": int(row["token_position"]),
                "probe_index": int(row["probe_id"]),
                "answer": dominant,
                "share": float(share),
                "certain": bool(row["is_certain"]),
            }
    return {
        "reached": False,
        "time": np.nan,
        "probe_index": np.nan,
        "answer": "",
        "share": np.nan,
        "certain": False,
    }


def switches(answers: list[str]) -> int:
    nonempty = [answer for answer in answers if answer]
    return sum(not eq(left, right) for left, right in zip(nonempty, nonempty[1:]))


def build_rollout_frame(input_dir: Path) -> pd.DataFrame:
    probes = pd.read_csv(input_dir / "probes.csv", keep_default_na=False)
    probes["is_certain"] = (
        probes["is_certain"].astype(str).str.lower() == "true"
    )
    trajectories = {}
    for path in sorted((input_dir / "traj").glob("*.json")):
        data = json.loads(path.read_text())
        key = (
            str(data["dataset"]),
            int(data["problem_id"]),
            int(data["rollout_id"]),
        )
        trajectories[key] = data
    level_by_problem = {}
    selection_path = input_dir / "selected_problems.json"
    if selection_path.exists():
        selection = json.loads(selection_path.read_text())
        for level, problem_ids in selection.get("math500", {}).get(
            "by_level", {}
        ).items():
            for problem_id in problem_ids:
                level_by_problem[("math500", int(problem_id))] = int(level)

    rows = []
    group_cols = ["dataset", "problem_id", "rollout_id"]
    for key, stream in probes.groupby(group_cols, sort=True):
        stream = stream.sort_values("probe_id").reset_index(drop=True)
        trajectory = trajectories[key]
        primary = first_consensus(stream, "nonempty")
        schema = first_consensus(stream, "schema")
        relaxed = first_consensus(stream, "nonempty", threshold=0.6)
        grid = {
            f"grid_w{window}_s{int(share * 10):02d}_": first_consensus(
                stream,
                "nonempty",
                threshold=share,
                window=window,
                minimum_valid=min(3, window),
            )
            for window in SENSITIVITY_WINDOWS
            for share in SENSITIVITY_SHARES
        }
        early = stream.iloc[:4]
        early_answers = [
            valid_answer(value, "schema") for value in early["probe_answer"]
        ]
        final_answer = str(trajectory["final_answer"]).strip()
        target = trajectory["target"]

        row = {
            "dataset": key[0],
            "problem_id": key[1],
            "rollout_id": key[2],
            "problem_key": f"{key[0]}__{key[1]}",
            "math_level": level_by_problem.get((key[0], key[1]), np.nan),
            "final_correct": bool(trajectory["final_correct"]),
            "final_answer": final_answer,
            "tokens_used": int(trajectory["tokens_used"]),
            "finished_naturally": bool(trajectory["finished_naturally"]),
            "hit_token_cap": int(trajectory["tokens_used"]) == BUDGET,
            "n_probes": len(stream),
            "problem_chars": len(str(trajectory["problem"])),
            "early_entropy_mean": float(early["entropy"].mean()),
            "early_entropy_last": float(early["entropy"].iloc[-1]),
            "early_switches": switches(early_answers),
            "early_invalid_rate": float(
                np.mean([answer == "" for answer in early_answers])
            ),
            "early_unique_answers": len(
                group_answers([x for x in early_answers if x])[1]
            ),
            "early_share": float(early["share"].iloc[-1]),
        }

        consensus_definitions = [
            ("", primary),
            ("schema_", schema),
            ("relaxed_", relaxed),
            *grid.items(),
        ]
        for prefix, consensus in consensus_definitions:
            reached = bool(consensus["reached"])
            answer = str(consensus["answer"])
            row[f"{prefix}reached_consensus"] = reached
            row[f"{prefix}consensus_time"] = consensus["time"]
            row[f"{prefix}consensus_probe_index"] = consensus["probe_index"]
            row[f"{prefix}consensus_answer"] = answer
            row[f"{prefix}consensus_share"] = consensus["share"]
            row[f"{prefix}consensus_certain"] = bool(consensus["certain"])
            row[f"{prefix}consensus_correct"] = (
                answer_correct(answer, target) if reached else np.nan
            )
            row[f"{prefix}terminal"] = (
                eq(answer, final_answer) if reached else np.nan
            )
            row[f"{prefix}recovery"] = (
                bool(not answer_correct(answer, target) and row["final_correct"])
                if reached
                else np.nan
            )
            row[f"{prefix}overthinking"] = (
                bool(answer_correct(answer, target) and not row["final_correct"])
                if reached
                else np.nan
            )
        rows.append(row)
        if len(rows) % 100 == 0:
            print(f"  derived {len(rows)}/640 rollouts", flush=True)

    frame = pd.DataFrame(rows)
    if len(frame) != 640:
        raise ValueError(f"Expected 640 rollouts, found {len(frame)}")
    if frame[group_cols].duplicated().any():
        raise ValueError("Duplicate rollout keys")
    if not np.array_equal(
        frame["hit_token_cap"].to_numpy(),
        (~frame["finished_naturally"]).to_numpy(),
    ):
        raise ValueError("Token-cap and natural-finish flags disagree")

    sensitivity_prefixes = [
        f"grid_w{window}_s{int(share * 10):02d}_"
        for window in SENSITIVITY_WINDOWS
        for share in SENSITIVITY_SHARES
    ]
    for prefix in ["", "schema_", "relaxed_", *sensitivity_prefixes]:
        ct = f"{prefix}consensus_time"
        log_ct = f"{prefix}ct_log2"
        mean_ct = f"{prefix}ct_problemmean"
        within_ct = f"{prefix}ct_within"
        frame[log_ct] = np.log2(frame[ct].astype(float))
        frame[mean_ct] = frame.groupby("problem_key")[log_ct].transform("mean")
        frame[within_ct] = frame[log_ct] - frame[mean_ct]
        raw_mean = f"{prefix}ct_raw_problemmean"
        raw_within = f"{prefix}ct_raw_within"
        frame[raw_mean] = frame.groupby("problem_key")[ct].transform("mean")
        frame[raw_within] = frame[ct] - frame[raw_mean]

    problem_pass = frame.groupby("problem_key")["final_correct"].transform("sum")
    frame["pass_rate"] = problem_pass / 8
    frame["pass_rate_loo"] = (
        problem_pass - frame["final_correct"].astype(int)
    ) / 7

    for column in [
        "early_entropy_mean",
        "early_entropy_last",
        "early_switches",
        "early_invalid_rate",
        "early_unique_answers",
        "early_share",
    ]:
        std = float(frame[column].std())
        frame[f"z_{column}"] = (
            frame[column] - float(frame[column].mean())
        ) / (std if std > 0 else 1)
    frame["z_log_problem_chars"] = (
        np.log1p(frame["problem_chars"])
        - np.log1p(frame["problem_chars"]).mean()
    ) / np.log1p(frame["problem_chars"]).std()
    return frame.sort_values(group_cols).reset_index(drop=True)


def model_formula(
    outcome: str,
    within: str,
    between: str,
    data: pd.DataFrame,
    proxies: bool = False,
    cap_interaction: bool = False,
    quadratic: bool = False,
) -> str:
    terms = [within, between]
    if data["dataset"].nunique() > 1:
        terms.append("C(dataset)")
    if proxies:
        terms.extend(
            [
                "z_early_entropy_mean",
                "z_early_switches",
                "z_early_invalid_rate",
                "z_early_unique_answers",
                "z_log_problem_chars",
            ]
        )
    if cap_interaction:
        terms.extend(["hit_token_cap", f"{within}:hit_token_cap"])
    if quadratic:
        terms.append(f"I({within} ** 2)")
    return f"{outcome} ~ " + " + ".join(terms)


def average_probability_change(
    data: pd.DataFrame,
    model,
    term: str,
) -> float:
    exog = np.asarray(model.model.exog, dtype=float)
    names = list(model.model.exog_names)
    if term not in names:
        return float("nan")
    index = names.index(term)
    beta = np.asarray(model.params, dtype=float)
    if not np.isfinite(exog).all() or not np.isfinite(beta).all():
        return float("nan")
    shifted = exog.copy()
    shifted[:, index] += 1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with np.errstate(over="ignore", invalid="ignore"):
            return float(np.mean(expit(shifted @ beta) - expit(exog @ beta)))


def fit_gee(
    data: pd.DataFrame,
    outcome: str,
    within: str,
    between: str,
    analysis: str,
    proxies: bool = False,
    cap_interaction: bool = False,
    quadratic: bool = False,
) -> tuple[list[dict], object | None]:
    columns = [
        outcome,
        within,
        between,
        "problem_key",
        "dataset",
        "hit_token_cap",
    ]
    if proxies:
        columns.extend(
            [
                "z_early_entropy_mean",
                "z_early_switches",
                "z_early_invalid_rate",
                "z_early_unique_answers",
                "z_log_problem_chars",
            ]
        )
    used = data.dropna(subset=list(dict.fromkeys(columns))).copy()
    used[outcome] = used[outcome].astype(int)
    if used[outcome].nunique() < 2 or used["problem_key"].nunique() < 5:
        return [], None
    formula = model_formula(
        outcome, within, between, used, proxies, cap_interaction, quadratic
    )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = smf.gee(
                formula,
                groups="problem_key",
                data=used,
                family=sm.families.Binomial(),
                cov_struct=sm.cov_struct.Exchangeable(),
            ).fit(maxiter=300)
    except Exception as exc:
        return [
            {
                "analysis": analysis,
                "model": "GEE",
                "outcome": outcome,
                "term": "__ERROR__",
                "error": repr(exc),
                "n": len(used),
                "n_problems": used["problem_key"].nunique(),
            }
        ], None

    confidence = result.conf_int()
    rows = []
    for term in result.params.index:
        beta = float(result.params[term])
        rows.append(
            {
                "analysis": analysis,
                "model": "GEE",
                "outcome": outcome,
                "term": term,
                "beta": beta,
                "se": float(result.bse[term]),
                "ci_lo": float(confidence.loc[term, 0]),
                "ci_hi": float(confidence.loc[term, 1]),
                "odds_ratio": math.exp(beta),
                "or_ci_lo": math.exp(float(confidence.loc[term, 0])),
                "or_ci_hi": math.exp(float(confidence.loc[term, 1])),
                "p_value": float(result.pvalues[term]),
                "avg_probability_change": (
                    average_probability_change(used, result, term)
                    if term in {within, between}
                    else np.nan
                ),
                "n": len(used),
                "n_problems": used["problem_key"].nunique(),
                "formula": formula,
            }
        )
    return rows, result


def fit_glmm(
    data: pd.DataFrame,
    outcome: str,
    within: str,
    between: str,
    analysis: str,
) -> list[dict]:
    used = data.dropna(
        subset=[outcome, within, between, "problem_key", "dataset"]
    ).copy()
    used[outcome] = used[outcome].astype(int)
    if used[outcome].nunique() < 2 or used["problem_key"].nunique() < 5:
        return []
    formula = model_formula(outcome, within, between, used)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = BinomialBayesMixedGLM.from_formula(
                formula,
                {"problem_intercept": "0 + C(problem_key)"},
                used,
            )
            result = model.fit_vb(
                minim_opts={"maxiter": 2000, "gtol": 1e-6}
            )
    except Exception as exc:
        return [
            {
                "analysis": analysis,
                "model": "GLMM_VB",
                "outcome": outcome,
                "term": "__ERROR__",
                "error": repr(exc),
                "n": len(used),
                "n_problems": used["problem_key"].nunique(),
            }
        ]

    rows = []
    for index, term in enumerate(model.exog_names):
        beta = float(result.fe_mean[index])
        se = float(result.fe_sd[index])
        lo, hi = beta - 1.96 * se, beta + 1.96 * se
        rows.append(
            {
                "analysis": analysis,
                "model": "GLMM_VB",
                "outcome": outcome,
                "term": term,
                "beta": beta,
                "se": se,
                "ci_lo": lo,
                "ci_hi": hi,
                "odds_ratio": math.exp(beta),
                "or_ci_lo": math.exp(lo),
                "or_ci_hi": math.exp(hi),
                "p_value": np.nan,
                "avg_probability_change": np.nan,
                "n": len(used),
                "n_problems": used["problem_key"].nunique(),
                "formula": formula,
            }
        )
    return rows


def run_models(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    reached = frame[frame["reached_consensus"]].copy()
    model_specs = [
        ("main_final", reached, "final_correct", False, False),
        ("main_consensus", reached, "consensus_correct", False, False),
        ("main_terminal", reached, "terminal", False, False),
        (
            "natural_finish_final",
            reached[reached["finished_naturally"]],
            "final_correct",
            False,
            False,
        ),
        (
            "natural_finish_consensus",
            reached[reached["finished_naturally"]],
            "consensus_correct",
            False,
            False,
        ),
        (
            "math_final",
            reached[reached["dataset"] == "math500"],
            "final_correct",
            False,
            False,
        ),
        (
            "math_consensus",
            reached[reached["dataset"] == "math500"],
            "consensus_correct",
            False,
            False,
        ),
        (
            "aime_final",
            reached[reached["dataset"] == "aime24"],
            "final_correct",
            False,
            False,
        ),
        (
            "cap_interaction_final",
            reached,
            "final_correct",
            False,
            True,
        ),
        (
            "online_proxy_final",
            reached,
            "final_correct",
            True,
            False,
        ),
        (
            "online_proxy_consensus",
            reached,
            "consensus_correct",
            True,
            False,
        ),
    ]
    for analysis, data, outcome, proxies, cap_interaction in model_specs:
        gee_rows, _ = fit_gee(
            data,
            outcome,
            "ct_within",
            "ct_problemmean",
            analysis,
            proxies=proxies,
            cap_interaction=cap_interaction,
        )
        rows.extend(gee_rows)
        if not proxies and not cap_interaction:
            rows.extend(
                fit_glmm(
                    data,
                    outcome,
                    "ct_within",
                    "ct_problemmean",
                    analysis,
                )
            )

    for outcome in ["final_correct", "consensus_correct", "terminal"]:
        gee_rows, _ = fit_gee(
            reached,
            outcome,
            "ct_within",
            "ct_problemmean",
            f"nonlinear_{outcome}",
            quadratic=True,
        )
        rows.extend(gee_rows)

    schema_reached = frame[frame["schema_reached_consensus"]].copy()
    for outcome in [
        "final_correct",
        "schema_consensus_correct",
        "schema_terminal",
    ]:
        analysis = f"schema_{outcome}"
        gee_rows, _ = fit_gee(
            schema_reached,
            outcome,
            "schema_ct_within",
            "schema_ct_problemmean",
            analysis,
        )
        rows.extend(gee_rows)
        rows.extend(
            fit_glmm(
                schema_reached,
                outcome,
                "schema_ct_within",
                "schema_ct_problemmean",
                analysis,
            )
        )

    relaxed = frame[frame["relaxed_reached_consensus"]].copy()
    for outcome in [
        "final_correct",
        "relaxed_consensus_correct",
        "relaxed_terminal",
    ]:
        analysis = f"relaxed_{outcome}"
        gee_rows, _ = fit_gee(
            relaxed,
            outcome,
            "relaxed_ct_within",
            "relaxed_ct_problemmean",
            analysis,
        )
        rows.extend(gee_rows)
        rows.extend(
            fit_glmm(
                relaxed,
                outcome,
                "relaxed_ct_within",
                "relaxed_ct_problemmean",
                analysis,
            )
        )

    for window in SENSITIVITY_WINDOWS:
        for share in SENSITIVITY_SHARES:
            prefix = f"grid_w{window}_s{int(share * 10):02d}_"
            grid_reached = frame[
                frame[f"{prefix}reached_consensus"]
            ].copy()
            outcomes = [
                ("all_final", grid_reached, "final_correct"),
                (
                    "natural_final",
                    grid_reached[grid_reached["finished_naturally"]],
                    "final_correct",
                ),
                (
                    "all_consensus",
                    grid_reached,
                    f"{prefix}consensus_correct",
                ),
                ("all_terminal", grid_reached, f"{prefix}terminal"),
                (
                    "math_easy_final",
                    grid_reached[
                        (grid_reached["dataset"] == "math500")
                        & (grid_reached["math_level"] <= 3)
                    ],
                    "final_correct",
                ),
                (
                    "math_hard_final",
                    grid_reached[
                        (grid_reached["dataset"] == "math500")
                        & (grid_reached["math_level"] >= 4)
                    ],
                    "final_correct",
                ),
            ]
            for label, subset, outcome in outcomes:
                log_rows, _ = fit_gee(
                    subset,
                    outcome,
                    f"{prefix}ct_within",
                    f"{prefix}ct_problemmean",
                    f"{prefix}{label}_log2",
                )
                rows.extend(log_rows)
                raw_rows, _ = fit_gee(
                    subset,
                    outcome,
                    f"{prefix}ct_raw_within",
                    f"{prefix}ct_raw_problemmean",
                    f"{prefix}{label}_raw",
                )
                rows.extend(raw_rows)
    return pd.DataFrame(rows)


def descriptive_tables(
    frame: pd.DataFrame,
    out_dir: Path,
) -> dict[str, object]:
    reached = frame[frame["reached_consensus"]].copy()
    reached["ct_bin"] = pd.cut(
        reached["consensus_time"],
        CT_BINS,
        labels=CT_LABELS,
        right=False,
    )
    pooled = (
        reached.groupby("ct_bin", observed=False)
        .agg(
            n=("final_correct", "size"),
            final_accuracy=("final_correct", "mean"),
            consensus_accuracy=("consensus_correct", "mean"),
            terminal_rate=("terminal", "mean"),
            cap_rate=("hit_token_cap", "mean"),
            mean_ct=("consensus_time", "mean"),
        )
        .reset_index()
    )
    pooled.to_csv(out_dir / "pooled_ct_bins.csv", index=False)

    reached["within_rank"] = reached.groupby("problem_key")[
        "consensus_time"
    ].rank(method="average", pct=True)
    reached["within_quintile"] = pd.cut(
        reached["within_rank"],
        bins=[0, 0.2, 0.4, 0.6, 0.8, 1.000001],
        labels=["earliest", "early", "middle", "late", "latest"],
        include_lowest=True,
    )
    within = (
        reached.groupby("within_quintile", observed=False)
        .agg(
            n=("final_correct", "size"),
            mean_ct_within=("ct_within", "mean"),
            final_accuracy=("final_correct", "mean"),
            consensus_accuracy=("consensus_correct", "mean"),
            terminal_rate=("terminal", "mean"),
            cap_rate=("hit_token_cap", "mean"),
        )
        .reset_index()
    )
    within.to_csv(out_dir / "within_ct_quintiles.csv", index=False)

    problem = (
        frame.groupby(["problem_key", "dataset"])
        .agg(
            pass_rate=("final_correct", "mean"),
            mean_consensus_time=("consensus_time", "mean"),
            reached_rate=("reached_consensus", "mean"),
            cap_rate=("hit_token_cap", "mean"),
        )
        .reset_index()
    )
    finite_problem = problem.dropna(subset=["mean_consensus_time"])
    correlation = spearmanr(
        finite_problem["pass_rate"],
        finite_problem["mean_consensus_time"],
    )
    problem["difficulty_quintile"] = pd.qcut(
        problem["pass_rate"].rank(method="first"),
        q=5,
        labels=["hardest", "hard", "middle", "easy", "easiest"],
    )
    problem.to_csv(out_dir / "per_problem_difficulty.csv", index=False)

    transition_rows = []
    for subset_name, subset in [
        ("all_reached", reached),
        ("natural_finish", reached[reached["finished_naturally"]]),
        ("math500", reached[reached["dataset"] == "math500"]),
        ("aime24", reached[reached["dataset"] == "aime24"]),
        ("capped", reached[reached["hit_token_cap"]]),
    ]:
        transition_rows.append(
            {
                "subset": subset_name,
                "n": len(subset),
                "consensus_accuracy": subset["consensus_correct"].mean(),
                "terminal_rate": subset["terminal"].mean(),
                "final_accuracy": subset["final_correct"].mean(),
                "cap_rate": subset["hit_token_cap"].mean(),
                "recovery_count": int(subset["recovery"].sum()),
                "overthinking_count": int(subset["overthinking"].sum()),
            }
        )
    never = frame[~frame["reached_consensus"]]
    transition_rows.append(
        {
            "subset": "never_consensus",
            "n": len(never),
            "consensus_accuracy": np.nan,
            "terminal_rate": np.nan,
            "final_accuracy": never["final_correct"].mean(),
            "cap_rate": never["hit_token_cap"].mean(),
            "recovery_count": 0,
            "overthinking_count": 0,
        }
    )
    transitions = pd.DataFrame(transition_rows)
    transitions.to_csv(out_dir / "outcome_transitions.csv", index=False)

    return {
        "reached_n": int(frame["reached_consensus"].sum()),
        "never_n": int((~frame["reached_consensus"]).sum()),
        "schema_reached_n": int(frame["schema_reached_consensus"].sum()),
        "relaxed_reached_n": int(frame["relaxed_reached_consensus"].sum()),
        "within_variable_problems": int(
            reached.groupby("problem_key")["ct_log2"]
            .nunique()
            .gt(1)
            .sum()
        ),
        "problem_count": int(frame["problem_key"].nunique()),
        "pass_rate_ct_spearman": float(correlation.statistic),
        "pass_rate_ct_p": float(correlation.pvalue),
    }


def coefficient(
    models: pd.DataFrame,
    analysis: str,
    outcome: str,
    term: str,
    model: str = "GEE",
) -> dict[str, float] | None:
    match = models[
        (models["analysis"] == analysis)
        & (models["outcome"] == outcome)
        & (models["term"] == term)
        & (models["model"] == model)
    ]
    if len(match) != 1:
        return None
    row = match.iloc[0]
    return {
        key: float(row[key])
        for key in [
            "beta",
            "ci_lo",
            "ci_hi",
            "odds_ratio",
            "or_ci_lo",
            "or_ci_hi",
            "p_value",
            "avg_probability_change",
            "n",
            "n_problems",
        ]
    }


def make_figures(
    frame: pd.DataFrame,
    models: pd.DataFrame,
    out_dir: Path,
) -> None:
    pooled = pd.read_csv(out_dir / "pooled_ct_bins.csv")
    within = pd.read_csv(out_dir / "within_ct_quintiles.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for outcome, label, color in [
        ("final_accuracy", "Final accuracy", "#2b6cb0"),
        ("consensus_accuracy", "Consensus-answer accuracy", "#c05621"),
        ("terminal_rate", "Terminality", "#2f855a"),
    ]:
        axes[0].plot(
            pooled["ct_bin"],
            pooled[outcome],
            marker="o",
            label=label,
            color=color,
        )
        axes[1].plot(
            within["within_quintile"],
            within[outcome],
            marker="o",
            label=label,
            color=color,
        )
    axes[0].set_title("Pooled: difficulty-confounded")
    axes[0].set_xlabel("Absolute consensus time")
    axes[1].set_title("Within-problem centered")
    axes[1].set_xlabel("Relative consensus time")
    for axis in axes:
        axis.set_ylim(0, 1)
        axis.set_ylabel("Rate")
        axis.grid(alpha=0.25)
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "pooled_vs_within.png", dpi=200)
    plt.close(fig)

    effects = models[
        (models["model"] == "GEE")
        & (models["analysis"].isin(["main_final", "main_consensus", "main_terminal"]))
        & (models["term"].isin(["ct_within", "ct_problemmean"]))
    ].copy()
    if len(effects):
        labels = []
        values = []
        lower = []
        upper = []
        for _, row in effects.iterrows():
            labels.append(
                f"{row['outcome']} · "
                f"{'within' if row['term']=='ct_within' else 'between'}"
            )
            values.append(row["odds_ratio"])
            lower.append(row["odds_ratio"] - row["or_ci_lo"])
            upper.append(row["or_ci_hi"] - row["odds_ratio"])
        y = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(7.2, 4.8))
        ax.errorbar(
            values,
            y,
            xerr=[lower, upper],
            fmt="o",
            capsize=3,
            color="#2b6cb0",
        )
        ax.axvline(1, color="#555", linestyle="--", linewidth=1)
        ax.set_yticks(y, labels)
        ax.set_xlabel("Odds ratio per doubling of consensus time")
        ax.set_title("Within–between root-cause decomposition")
        ax.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        fig.savefig(out_dir / "within_between_effects.png", dpi=200)
        plt.close(fig)


def write_report(
    frame: pd.DataFrame,
    models: pd.DataFrame,
    diagnostics: dict[str, object],
    out_dir: Path,
) -> dict[str, object]:
    reached = frame[frame["reached_consensus"]]
    main = {}
    for outcome, analysis in [
        ("final_correct", "main_final"),
        ("consensus_correct", "main_consensus"),
        ("terminal", "main_terminal"),
    ]:
        main[outcome] = {
            "within_gee": coefficient(
                models, analysis, outcome, "ct_within", "GEE"
            ),
            "between_gee": coefficient(
                models, analysis, outcome, "ct_problemmean", "GEE"
            ),
            "within_glmm": coefficient(
                models, analysis, outcome, "ct_within", "GLMM_VB"
            ),
            "between_glmm": coefficient(
                models, analysis, outcome, "ct_problemmean", "GLMM_VB"
            ),
        }

    sensitivity = {}
    for analysis, outcome in [
        ("natural_finish_final", "final_correct"),
        ("math_final", "final_correct"),
        ("aime_final", "final_correct"),
        ("online_proxy_final", "final_correct"),
        ("online_proxy_consensus", "consensus_correct"),
        ("schema_final_correct", "final_correct"),
        ("schema_schema_consensus_correct", "schema_consensus_correct"),
        ("schema_schema_terminal", "schema_terminal"),
        ("relaxed_final_correct", "final_correct"),
        (
            "relaxed_relaxed_consensus_correct",
            "relaxed_consensus_correct",
        ),
        ("relaxed_relaxed_terminal", "relaxed_terminal"),
    ]:
        if analysis.startswith("schema_"):
            term = "schema_ct_within"
        elif analysis.startswith("relaxed_"):
            term = "relaxed_ct_within"
        else:
            term = "ct_within"
        sensitivity[analysis] = coefficient(
            models, analysis, outcome, term, "GEE"
        )

    nonlinear = {}
    for outcome in ["final_correct", "consensus_correct", "terminal"]:
        analysis = f"nonlinear_{outcome}"
        nonlinear[outcome] = {
            "linear": coefficient(
                models, analysis, outcome, "ct_within", "GEE"
            ),
            "quadratic": coefficient(
                models,
                analysis,
                outcome,
                "I(ct_within ** 2)",
                "GEE",
            ),
        }

    root = {
        "protocol": {
            "consensus_window": 5,
            "minimum_nonempty_answers": 3,
            "primary_dominant_share": 0.8,
            "relaxed_dominant_share": 0.6,
            "consensus_time_scale": "log2(tokens)",
            "primary_estimator": "GEE clustered by problem",
            "random_intercept_sensitivity": "BinomialBayesMixedGLM",
        },
        "diagnostics": diagnostics,
        "main_effects": main,
        "nonlinear_effects": nonlinear,
        "sensitivity": sensitivity,
        "descriptives": {
            "n": len(frame),
            "reached_consensus": int(frame["reached_consensus"].sum()),
            "natural_finish_rate": float(frame["finished_naturally"].mean()),
            "cap_rate": float(frame["hit_token_cap"].mean()),
            "final_accuracy": float(frame["final_correct"].mean()),
            "consensus_accuracy_reached": float(
                reached["consensus_correct"].mean()
            ),
            "terminal_rate_reached": float(reached["terminal"].mean()),
            "recovery_count": int(reached["recovery"].sum()),
            "overthinking_count": int(reached["overthinking"].sum()),
        },
    }
    (out_dir / "root_cause_summary.json").write_text(
        json.dumps(root, indent=2, ensure_ascii=False) + "\n"
    )

    def effect_text(effect: dict[str, float] | None) -> str:
        if effect is None:
            return "N/A"
        delta = (
            ""
            if not np.isfinite(effect["avg_probability_change"])
            else f", Δp={effect['avg_probability_change'] * 100:+.1f}pp"
        )
        return (
            f"OR {effect['odds_ratio']:.3f} "
            f"[{effect['or_ci_lo']:.3f}, {effect['or_ci_hi']:.3f}], "
            f"p={effect['p_value']:.3g}{delta}"
        )

    def rate_text(value: float) -> str:
        return "N/A" if pd.isna(value) else f"{value:.1%}"

    transitions = pd.read_csv(out_dir / "outcome_transitions.csv")
    pooled = pd.read_csv(out_dir / "pooled_ct_bins.csv")
    within = pd.read_csv(out_dir / "within_ct_quintiles.csv")
    lines = [
        "# Stage 9 §7.5.3 — Why is late agreement unreliable?",
        "",
        "Primary consensus: first last-5 window with at least 3 non-empty "
        "answers and mathematical-equivalence share ≥0.8. Consensus time is "
        "modeled on log2(tokens), so an odds ratio is the effect of doubling "
        "consensus time.",
        "",
        "## Data and identification checks",
        "",
        f"- rollouts: **{len(frame)}** across "
        f"**{diagnostics['problem_count']}** problems",
        f"- reached consensus: **{diagnostics['reached_n']}**; never: "
        f"**{diagnostics['never_n']}**",
        f"- relaxed share≥0.6 replication: "
        f"**{diagnostics['relaxed_reached_n']}** reached (the remote 621-row "
        "summary used this threshold despite labeling it ≥0.8)",
        f"- problems with within-problem consensus-time variation: "
        f"**{diagnostics['within_variable_problems']}/"
        f"{diagnostics['problem_count']}**",
        f"- pass-rate vs problem mean consensus time: Spearman "
        f"ρ={diagnostics['pass_rate_ct_spearman']:.3f}, "
        f"p={diagnostics['pass_rate_ct_p']:.3g}",
        "",
        "## Main within–between results (GEE, problem-clustered)",
        "",
        "| Outcome | Within effect | Between/problem effect |",
        "|---|---|---|",
    ]
    for outcome, label in [
        ("final_correct", "Final correctness"),
        ("consensus_correct", "Consensus-answer correctness"),
        ("terminal", "Terminality"),
    ]:
        lines.append(
            f"| {label} | {effect_text(main[outcome]['within_gee'])} | "
            f"{effect_text(main[outcome]['between_gee'])} |"
        )

    lines.extend(
        [
            "",
            "Random-intercept Bayesian GLMM estimates are stored alongside the "
            "GEE table in `model_results.csv`; agreement in direction is used "
            "as a robustness check.",
            "",
            "## Root-cause result",
            "",
            "- The pooled decline is primarily a **between-problem difficulty "
            "effect**: problems with later mean consensus have lower final "
            "accuracy.",
            "- Within the same problem, later consensus does **not** predict "
            "lower final accuracy; the point estimate is slightly positive "
            "and non-significant.",
            "- Within the same problem, later consensus is significantly more "
            "likely to be correct at the consensus point and more likely to "
            "be terminal. This reverses the naive pooled interpretation.",
            "- The within relation is non-linear: very early consensus is "
            "often transient, the middle is safest, and extremely late "
            "trajectories weaken again.",
            "- The main failure mode is therefore not 'late agreement is "
            "intrinsically unreliable'; it is **hard-problem mixing plus "
            "premature transient consensus**, amplified by token caps.",
            "",
            "## Non-linearity check",
            "",
            "| Outcome | Linear within term | Quadratic within term |",
            "|---|---|---|",
        ]
    )
    for outcome, label in [
        ("final_correct", "Final correctness"),
        ("consensus_correct", "Consensus-answer correctness"),
        ("terminal", "Terminality"),
    ]:
        lines.append(
            f"| {label} | {effect_text(nonlinear[outcome]['linear'])} | "
            f"{effect_text(nonlinear[outcome]['quadratic'])} |"
        )

    lines.extend(
        [
            "",
            "## Outcome decomposition",
            "",
            "| Subset | N | Consensus accuracy | Terminality | Final accuracy | Cap | Recovery | Overthinking |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in transitions.iterrows():
        lines.append(
            f"| {row['subset']} | {int(row['n'])} | "
            f"{rate_text(row['consensus_accuracy'])} | "
            f"{rate_text(row['terminal_rate'])} | "
            f"{rate_text(row['final_accuracy'])} | "
            f"{rate_text(row['cap_rate'])} | "
            f"{int(row['recovery_count'])} | "
            f"{int(row['overthinking_count'])} |"
        )

    lines.extend(
        [
            "",
            "## Sensitivity: within effect on correctness",
            "",
            "| Analysis | Within effect |",
            "|---|---|",
        ]
    )
    for analysis, effect in sensitivity.items():
        lines.append(f"| {analysis} | {effect_text(effect)} |")

    lines.extend(
        [
            "",
            "## Descriptive pooled curve",
            "",
            "| CT bin | N | Consensus accuracy | Terminality | Final accuracy | Cap rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in pooled.iterrows():
        lines.append(
            f"| {row['ct_bin']} | {int(row['n'])} | "
            f"{row['consensus_accuracy']:.1%} | "
            f"{row['terminal_rate']:.1%} | "
            f"{row['final_accuracy']:.1%} | {row['cap_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Descriptive within-problem curve",
            "",
            "| Relative CT | N | Consensus accuracy | Terminality | Final accuracy | Cap rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in within.iterrows():
        lines.append(
            f"| {row['within_quintile']} | {int(row['n'])} | "
            f"{row['consensus_accuracy']:.1%} | "
            f"{row['terminal_rate']:.1%} | "
            f"{row['final_accuracy']:.1%} | {row['cap_rate']:.1%} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- The within effect is observational: difficulty is locked by "
            "problem, but consensus time is not experimentally manipulated.",
            "- Never-converged rollouts are excluded from conditional CT "
            "models and reported separately.",
            "- AIME retains substantial token-cap censoring; natural-finish "
            "and MATH-only analyses are required before attributing a CT effect "
            "to trajectory dynamics.",
            "- Do not divide logistic coefficients to claim a percentage "
            "decomposition; use odds ratios and average probability changes.",
            "",
        ]
    )
    (out_dir / "report.md").write_text("\n".join(lines))
    return root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=FC_DIR / "results/stage9_krollout",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FC_DIR / "results/stage9_krollout_analysis",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("Building per-rollout analysis frame...")
    frame = build_rollout_frame(args.input_dir)
    frame.to_csv(args.out_dir / "per_rollout.csv", index=False)

    print("Fitting within-between models...")
    models = run_models(frame)
    models.to_csv(args.out_dir / "model_results.csv", index=False)
    models[
        models["analysis"].astype(str).str.startswith("grid_")
    ].to_csv(args.out_dir / "window_threshold_sensitivity.csv", index=False)

    print("Building descriptive and sensitivity tables...")
    diagnostics = descriptive_tables(frame, args.out_dir)
    root = write_report(frame, models, diagnostics, args.out_dir)
    make_figures(frame, models, args.out_dir)

    print(
        json.dumps(
            {
                "output": str(args.out_dir),
                "reached": root["descriptives"]["reached_consensus"],
                "main_within_final": root["main_effects"]["final_correct"][
                    "within_gee"
                ],
                "main_between_final": root["main_effects"]["final_correct"][
                    "between_gee"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
