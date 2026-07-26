"""Robust answer grading shared by collection and replay.

`dynasor.core.evaluator.math_equal` alone misgrades references that carry
formatting which `strip_string` would remove — e.g. `\\left( ... \\right)`
tuples, `\\text{east}`, or `x\\in[-2,7]`. Collected model answers are already
stripped, so the reference must be tried in raw, stripped, deprefixed, and
text-unwrapped forms before declaring a mismatch.
"""

from __future__ import annotations

import re
from typing import Any


def robust_answers_equal(answer: Any, raw_target: Any) -> bool:
    from dynasor.core.evaluator import math_equal, strip_string

    answer = "" if answer is None else str(answer)
    raw = "" if raw_target is None else str(raw_target)
    if answer == "" or raw == "":
        return answer == raw

    candidates = [raw]

    def add(candidate: str) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    try:
        add(strip_string(raw))
    except Exception:
        pass
    deprefixed = re.sub(r"^\s*[a-zA-Z]\s*\\in\s*", "", raw)
    if deprefixed != raw:
        add(deprefixed)
        try:
            add(strip_string(deprefixed))
        except Exception:
            pass

    for candidate in candidates:
        if answer == candidate:
            return True
        try:
            if math_equal(answer, candidate):
                return True
        except Exception:
            continue

    unwrapped = re.sub(r"\\text\s*\{([^{}]*)\}", r"\1", raw).strip()
    return (
        unwrapped != ""
        and unwrapped != raw
        and answer.strip().lower() == unwrapped.lower()
    )
