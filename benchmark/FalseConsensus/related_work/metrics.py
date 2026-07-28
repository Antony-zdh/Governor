"""Aggregation + paired hierarchical bootstrap for the related-work baselines.

Two cost views are kept for every method (goal §8):

1. paper-style reasoning/main-length metric -- ``main_tokens_through_stop``:
   the frozen reasoning length up to the stop (or the full length if no stop).
2. fair all-generated-token metric -- ``all_generated_tokens``:
   ``main_tokens_through_stop`` + every probe/trial/readout OUTPUT token
   incurred by the method. Probe/trial/readout PROMPT tokens (the re-sent
   prefix) are reported *separately* and are never added to the generated
   count, because they are not newly generated tokens.

Confidence intervals use a deterministic paired *hierarchical* bootstrap
(goal §8): resample seeds with replacement, then resample paired problem rows
within each resampled seed; 10,000 samples, seed ``20260727``. ``numpy`` is
used when available (matching the project convention
``np.random.default_rng``); otherwise a pure-``random`` fallback keeps the
module importable and unit-testable on a bare interpreter. Both paths are
seeded and deterministic.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import common

BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_SEED = 20260727


# --------------------------------------------------------------------------- #
# Per-problem metric extraction
# --------------------------------------------------------------------------- #
def per_problem_metric(replay_record: Mapping[str, Any]) -> dict:
    """Flatten a method replay record into a per-problem metric row.

    ``correct`` is only present when the replay actually graded the delivered
    answer (``answers_equal_target_fn`` was supplied); otherwise it is ``None``
    and accuracy metrics skip that row.
    """
    full = int(replay_record.get("full_main_tokens", 0))
    main_stop = int(replay_record.get("main_tokens_through_stop", full))
    all_gen = int(replay_record.get("all_generated_tokens", main_stop))
    probe_out = int(replay_record.get("probe_out_tokens", 0))
    probe_prompt = int(replay_record.get("probe_prompt_tokens", 0))
    baseline_full = int(replay_record.get("baseline_all_generated_tokens", full))
    correct = replay_record.get("correct")
    baseline_correct = bool(replay_record.get("baseline_correct", False))
    n_aux_calls = int(replay_record.get("n_aux_calls", 0))
    n_readout_calls = int(replay_record.get("n_readout_calls", 0))
    invalid_aux = int(replay_record.get("invalid_aux_responses", 0))
    auxiliary_wall = float(replay_record.get("auxiliary_wall_seconds", 0.0))
    return {
        "method": replay_record.get("method"),
        "model": replay_record.get("model"),
        "dataset": replay_record.get("dataset"),
        "base_seed": replay_record.get("base_seed"),
        "problem_id": replay_record.get("problem_id"),
        "split": replay_record.get("split"),
        "correct": None if correct is None else int(bool(correct)),
        "baseline_correct": int(baseline_correct),
        "delivered_answer": replay_record.get("delivered_answer"),
        "stopped": int(bool(replay_record.get("stopped", False))),
        "capped": int(bool(replay_record.get("capped", False))),
        "recovery_truncated": int(bool(replay_record.get("recovery_truncated", False))),
        "full_main_tokens": full,
        "main_tokens_through_stop": main_stop,
        "all_generated_tokens": all_gen,
        "probe_out_tokens": probe_out,
        "probe_prompt_tokens": probe_prompt,
        "baseline_all_generated_tokens": baseline_full,
        "main_only_saving_fraction": (1 - main_stop / full) if full else 0.0,
        "all_generated_saving_fraction": (1 - all_gen / baseline_full) if baseline_full else 0.0,
        "overthinking_avoided_tokens": int(replay_record.get("overthinking_avoided_tokens", 0)),
        "n_aux_calls": n_aux_calls,
        "n_readout_calls": n_readout_calls,
        "invalid_aux_responses": invalid_aux,
        "auxiliary_wall_seconds": auxiliary_wall,
    }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate(per_problem_rows: Sequence[Mapping[str, Any]]) -> dict:
    """Environment-level (or pooled) summary mirroring the goal §8 metric list."""
    n = len(per_problem_rows)
    if not n:
        raise ValueError("cannot summarize an empty set")
    graded = [r for r in per_problem_rows if r.get("correct") is not None]
    ng = len(graded)
    acc = _mean([r["correct"] for r in graded]) if ng else None
    base_acc = _mean([r["baseline_correct"] for r in graded]) if ng else None
    avg_full = _mean([float(r["full_main_tokens"]) for r in per_problem_rows])
    avg_main_stop = _mean([float(r["main_tokens_through_stop"]) for r in per_problem_rows])
    avg_all = _mean([float(r["all_generated_tokens"]) for r in per_problem_rows])
    avg_baseline_all = _mean([float(r["baseline_all_generated_tokens"]) for r in per_problem_rows])
    avg_probe_out = _mean([float(r["probe_out_tokens"]) for r in per_problem_rows])
    avg_probe_prompt = _mean([float(r["probe_prompt_tokens"]) for r in per_problem_rows])
    total_aux_calls = sum(int(r.get("n_aux_calls", 0)) for r in per_problem_rows)
    total_readout_calls = sum(int(r.get("n_readout_calls", 0)) for r in per_problem_rows)
    total_invalid_aux = sum(int(r.get("invalid_aux_responses", 0)) for r in per_problem_rows)
    total_aux_wall = sum(float(r.get("auxiliary_wall_seconds", 0.0)) for r in per_problem_rows)
    main_saving = 1 - avg_main_stop / avg_full if avg_full else 0.0
    all_saving = 1 - avg_all / avg_baseline_all if avg_baseline_all else 0.0
    return {
        "n": n,
        "n_graded": ng,
        "accuracy": acc,
        "baseline_accuracy": base_acc,
        "accuracy_diff_pp": (100.0 * (acc - base_acc)) if (acc is not None and base_acc is not None) else None,
        "avg_main_tokens": avg_main_stop,
        "avg_full_main_tokens": avg_full,
        "avg_all_generated_tokens": avg_all,
        "avg_baseline_all_generated_tokens": avg_baseline_all,
        "avg_probe_out_tokens": avg_probe_out,
        "avg_probe_prompt_tokens": avg_probe_prompt,
        "main_only_token_saving_fraction": main_saving,
        "all_generated_token_saving_fraction": all_saving,
        "stop_rate": _mean([float(r["stopped"]) for r in per_problem_rows]),
        "capped_rate": _mean([float(r["capped"]) for r in per_problem_rows]),
        "recovery_truncated_rate": _mean([float(r["recovery_truncated"]) for r in per_problem_rows]),
        "overthinking_avoided_rate": _mean([float(r["overthinking_avoided_tokens"] > 0) for r in per_problem_rows]),
        "total_aux_calls": total_aux_calls,
        "avg_aux_calls": total_aux_calls / n,
        "total_readout_calls": total_readout_calls,
        "invalid_aux_responses": total_invalid_aux,
        "invalid_aux_response_rate": (
            total_invalid_aux / total_aux_calls if total_aux_calls else 0.0
        ),
        "auxiliary_wall_seconds": total_aux_wall,
        "aux_calls_per_second": (
            total_aux_calls / total_aux_wall if total_aux_wall else None
        ),
    }


# --------------------------------------------------------------------------- #
# Pooled / macro views
# --------------------------------------------------------------------------- #
def pool_by(per_problem_rows: Sequence[Mapping[str, Any]], *, keys: Sequence[str]) -> Dict[tuple, dict]:
    """Group rows by a tuple key and aggregate each group."""
    groups: Dict[tuple, List[Mapping[str, Any]]] = defaultdict(list)
    for r in per_problem_rows:
        groups[tuple(r.get(k) for k in keys)].append(r)
    return {k: aggregate(rows) for k, rows in sorted(groups.items(), key=lambda kv: tuple(str(x) for x in kv[0]))}


def macro_over_benchmarks(per_problem_rows: Sequence[Mapping[str, Any]], *, keys: Sequence[str]) -> Dict[tuple, dict]:
    """Macro view: average the per-benchmark summaries equally (MATH500 does
    not dominate AMC/AIME by sample count)."""
    grouped = pool_by(per_problem_rows, keys=("dataset", *keys))
    macro: Dict[tuple, List[dict]] = defaultdict(list)
    for (bench, *rest), summary in grouped.items():
        macro[tuple(rest)].append(summary)
    out: Dict[tuple, dict] = {}
    for key, summaries in macro.items():
        out[key] = {
            k: _mean([s[k] for s in summaries if s.get(k) is not None])
            if any(s.get(k) is not None for s in summaries) else None
            for k in ("accuracy", "baseline_accuracy", "accuracy_diff_pp",
                      "main_only_token_saving_fraction",
                      "all_generated_token_saving_fraction", "stop_rate",
                      "capped_rate", "avg_all_generated_tokens")
        }
    return out


# --------------------------------------------------------------------------- #
# Paired hierarchical bootstrap
# --------------------------------------------------------------------------- #
def _have_numpy() -> bool:
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


def paired_hierarchical_ci(
    method_rows: Sequence[Mapping[str, Any]],
    baseline_rows: Sequence[Mapping[str, Any]],
    *,
    n_samples: int = BOOTSTRAP_SAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """95% paired hierarchical bootstrap CI for accuracy difference and token saving.

    Hierarchy (goal §8): resample *seeds* with replacement, then resample
    paired problem rows within each resampled seed. Method and baseline rows
    must be paired 1:1 on ``(seed, problem_id)``; a :class:`ValueError` is
    raised if they are not. ``correct`` may be ``None`` for ungraded rows --
    those are dropped from the accuracy bootstrap (token saving still uses
    every row).

    Returns point estimates and 2.5/97.5 percentile CIs.
    """
    if len(method_rows) != len(baseline_rows):
        raise ValueError("method/baseline row count mismatch (unpaired)")
    # pair on (seed, problem_id)
    def paired_key(r: Mapping[str, Any]) -> tuple:
        return (
            r.get("model"), r.get("dataset"),
            r.get("base_seed"), r.get("problem_id"),
        )

    mkey = {paired_key(r): r for r in method_rows}
    bkey = {paired_key(r): r for r in baseline_rows}
    if set(mkey) != set(bkey):
        raise ValueError("method/baseline problem keys differ (unpaired)")
    keys = sorted(mkey)
    seeds = sorted({k[2] for k in keys})
    seed_to_idx: Dict[Any, List[int]] = defaultdict(list)
    for i, k in enumerate(keys):
        seed_to_idx[k[2]].append(i)

    m_acc = [mkey[k].get("correct") for k in keys]
    b_acc = [bkey[k].get("correct") for k in keys]
    m_tok = [float(mkey[k]["all_generated_tokens"]) for k in keys]
    b_tok = [float(bkey[k]["baseline_all_generated_tokens"]) for k in keys]

    # point estimates
    graded = [i for i in range(len(keys)) if m_acc[i] is not None and b_acc[i] is not None]
    point_acc_diff = (
        _mean([float(m_acc[i]) for i in graded]) - _mean([float(b_acc[i]) for i in graded])
    ) if graded else None
    point_saving = 1 - _mean(m_tok) / _mean(b_tok) if _mean(b_tok) else 0.0

    acc_samples: List[float] = []
    saving_samples: List[float] = []

    if _have_numpy():
        import numpy as np
        rng = np.random.default_rng(seed)
        # pre-index per-seed integer positions
        seed_idx_lists = [seed_to_idx[s] for s in seeds]
        n_seeds = len(seeds)
        for _ in range(n_samples):
            # resample seeds with replacement
            seed_choices = rng.integers(0, n_seeds, size=n_seeds)
            chosen_idx: List[int] = []
            for sj in seed_choices:
                idx_list = seed_idx_lists[int(sj)]
                # resample problem rows within the resampled seed (with replacement)
                picks = rng.integers(0, len(idx_list), size=len(idx_list))
                chosen_idx.extend(idx_list[int(p)] for p in picks)
            arr_m_acc = np.array([m_acc[i] for i in chosen_idx if m_acc[i] is not None and b_acc[i] is not None], dtype=float)
            arr_b_acc = np.array([b_acc[i] for i in chosen_idx if m_acc[i] is not None and b_acc[i] is not None], dtype=float)
            if arr_m_acc.size:
                acc_samples.append(float(arr_m_acc.mean() - arr_b_acc.mean()))
            arr_m_tok = np.array([m_tok[i] for i in chosen_idx], dtype=float)
            arr_b_tok = np.array([b_tok[i] for i in chosen_idx], dtype=float)
            if arr_b_tok.mean():
                saving_samples.append(float(1 - arr_m_tok.mean() / arr_b_tok.mean()))
    else:
        rng = random.Random(seed)
        n_seeds = len(seeds)
        seed_idx_lists = [seed_to_idx[s] for s in seeds]
        for _ in range(n_samples):
            seed_choices = [rng.randrange(n_seeds) for _ in range(n_seeds)]
            chosen_idx: List[int] = []
            for sj in seed_choices:
                idx_list = seed_idx_lists[sj]
                picks = [rng.randrange(len(idx_list)) for _ in range(len(idx_list))]
                chosen_idx.extend(idx_list[p] for p in picks)
            ga = [float(m_acc[i]) for i in chosen_idx if m_acc[i] is not None and b_acc[i] is not None]
            gb = [float(b_acc[i]) for i in chosen_idx if m_acc[i] is not None and b_acc[i] is not None]
            if ga:
                acc_samples.append(_mean(ga) - _mean(gb))
            mt = [m_tok[i] for i in chosen_idx]
            bt = [b_tok[i] for i in chosen_idx]
            if _mean(bt):
                saving_samples.append(1 - _mean(mt) / _mean(bt))

    def ci(samples: Sequence[float]) -> Tuple[float, float]:
        if not samples:
            return float("nan"), float("nan")
        s = sorted(samples)
        lo = s[int(0.025 * (len(s) - 1))]
        hi = s[int(0.975 * (len(s) - 1))]
        return lo, hi

    acc_lo, acc_hi = ci(acc_samples)
    sav_lo, sav_hi = ci(saving_samples)
    return {
        "accuracy_diff": point_acc_diff,
        "accuracy_diff_ci_lo": acc_lo,
        "accuracy_diff_ci_hi": acc_hi,
        "all_generated_token_saving": point_saving,
        "token_saving_ci_lo": sav_lo,
        "token_saving_ci_hi": sav_hi,
        "n_graded": len(graded),
        "n_rows": len(keys),
        "n_samples": n_samples,
        "seed": seed,
        "backend": "numpy" if _have_numpy() else "random",
    }
