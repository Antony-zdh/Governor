"""Factored production predicates shared by the smoke audit and the regression
tests, so the audit cannot drift from the tested logic.

* :func:`near_max_probe_passes` -- a near-max-context semantic probe passes only
  when: status is ok; the prefix fraction is >=0.95; ``finish_reason`` is
  non-null; latency is positive and finite; the production parser returned a
  valid member (CertaIndex truthy boxed answer; TJE a label in the official
  ten-label set AND ``finish_reason != "length"``; DEER a truthy trial answer,
  finite confidence, hand-recompute equality, full logprob sequence stored, and
  the exact Qwen3 ``皖think/`` iff gate).
* :func:`readout_is_valid` (re-exported from :mod:`common`) -- a delivered
  readout is acceptable only when completed and task-valid with no context
  overflow.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import common, deer, tje

THINK = common.DEER_THINK_CLOSE
TJE_LABEL_NAMES = tje.TJE_LABEL_NAMES


def near_max_probe_passes(probe: Mapping[str, Any]) -> bool:
    """Hard predicate for a single near-max semantic probe."""
    if probe.get("status") != "ok":
        return False
    if (probe.get("fraction") or 0) < 0.95:
        return False
    fr = probe.get("finish_reason")
    if not fr:  # non-null required for every method
        return False
    lat = probe.get("latency_seconds")
    if not (isinstance(lat, (int, float)) and lat > 0):
        return False
    method = probe.get("method")
    if method == "certaindex_mid":
        # truthy boxed answer
        return bool(probe.get("parsed_answer"))
    if method == "tje":
        # a length finish is a failure even when a label parsed
        if fr == "length":
            return False
        return probe.get("parsed_label") in TJE_LABEL_NAMES
    if method == "deer":
        # truthy trial answer (not merely not-None)
        if not bool(probe.get("parsed_answer")):
            return False
        if not probe.get("confidence_finite"):
            return False
        if not probe.get("confidence_recomputed_matches"):
            return False
        # full logprob sequence stored, not a truncated prefix
        if probe.get("n_logprob_tokens", 0) != len(probe.get("logprobs", [])):
            return False
        if probe.get("require_think_close"):
            last = probe.get("last_token_decoded")
            conf = probe.get("confidence") or 0.0
            # EXACT iff: (last==THINK and conf>0) or (last!=THINK and conf==0.0)
            return ((last == THINK and conf > 0) or
                    (last != THINK and conf == 0.0))
        return True
    return False


def near_max_probe_detail(probe: Mapping[str, Any]) -> dict:
    """Return the per-field evidence dict (for audit reporting) plus a pass flag."""
    fr = probe.get("finish_reason")
    detail = {
        "model": probe.get("model"), "method": probe.get("method"),
        "status_ok": probe.get("status") == "ok",
        "prefix_fraction": probe.get("fraction"), "frac_ge_0.95": (probe.get("fraction") or 0) >= 0.95,
        "finish_reason": fr, "finish_reason_non_null": bool(fr),
        "latency_seconds": probe.get("latency_seconds"),
        "latency_positive_finite": isinstance(probe.get("latency_seconds"), (int, float)) and (probe.get("latency_seconds") or 0) > 0,
        "prompt_tokens": probe.get("prompt_tokens"),
        "parsed_answer": probe.get("parsed_answer"), "parsed_label": probe.get("parsed_label"),
    }
    if probe.get("method") == "deer":
        detail.update({
            "policy": probe.get("policy"), "confidence": probe.get("confidence"),
            "confidence_finite": probe.get("confidence_finite"),
            "confidence_recomputed_matches": probe.get("confidence_recomputed_matches"),
            "last_token_decoded": probe.get("last_token_decoded"),
            "n_logprob_tokens": probe.get("n_logprob_tokens"),
            "full_logprobs_stored": probe.get("n_logprob_tokens", 0) == len(probe.get("logprobs", [])),
            "require_think_close": probe.get("require_think_close"),
        })
        if probe.get("require_think_close"):
            last = probe.get("last_token_decoded"); conf = probe.get("confidence") or 0.0
            detail["qwen3_gate_exact"] = ((last == THINK and conf > 0) or
                                           (last != THINK and conf == 0.0))
    detail["pass"] = near_max_probe_passes(probe)
    return detail


readout_is_valid = common.readout_is_valid
