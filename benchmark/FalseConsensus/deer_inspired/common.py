"""Pure protocol helpers for the online DEER and DEER-inspired controllers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from benchmark.FalseConsensus.related_work.deer import (
    calculate_confidence,
    parse_trial_response,
    policy_for_model,
    require_think_close_for_model,
    trial_stop_tokens,
)
from benchmark.FalseConsensus.related_work.common import DEER_THINK_CLOSE

from . import PROTOCOL_VERSION, SCHEMA_VERSION


WAIT_RE = re.compile(r"(?i)\bwait\b")
# vLLM accepts a list of strings, not a regex. These cover the casing produced
# by the two formal models; a whole-word check is still applied after return.
WAIT_STOP_STRINGS = tuple(
    "".join(chars)
    for mask in range(16)
    for chars in [
        tuple(
            character.upper() if mask & (1 << index) else character.lower()
            for index, character in enumerate("wait")
        )
    ]
)
VALID_FINISH_REASONS = {"stop", "length"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_seed(*parts: Any) -> int:
    """Derive a role-isolated vLLM seed in the signed 31-bit range."""
    digest = hashlib.sha256(canonical_json(list(parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def wait_matches(text: str) -> list[re.Match[str]]:
    return list(WAIT_RE.finditer(text))


def split_at_terminal_wait(text: str, stop_reason: Optional[str] = None) -> tuple[str, str]:
    """Return ``(clean_before_wait, exact_wait)`` for a terminal Wait stop.

    A non-terminal match is a protocol error: continuing from text generated
    after a trigger would leak a future suffix into the online controller.
    """
    matches = wait_matches(text)
    if matches:
        match = matches[-1]
        if text[match.end() :].strip():
            raise ValueError("main response contains generated text after Wait trigger")
        return text[: match.start()], match.group(0)
    if stop_reason and WAIT_RE.fullmatch(str(stop_reason)):
        # With include_stop_str_in_output=True a substring stop can fire inside
        # "await"/"Waited". It is not a whole-word trigger; retain it as native
        # text and resume without probing. If the server excluded the stop
        # string, restore it exactly once below.
        if text.endswith(str(stop_reason)):
            return text, ""
        return text, str(stop_reason)
    return text, ""


def token_len(tokenizer: Any, text: str) -> int:
    encoded = tokenizer.encode(text, add_special_tokens=False)
    return len(encoded)


def completion_logprobs(response: Any) -> list[tuple[str, float]]:
    """Normalize OpenAI/vLLM completion logprobs to chosen token/logprob."""
    choice = response.choices[0]
    payload = getattr(choice, "logprobs", None)
    if payload is None:
        return []
    tokens = getattr(payload, "tokens", None)
    chosen = getattr(payload, "token_logprobs", None)
    top = getattr(payload, "top_logprobs", None)
    if tokens is not None and chosen is not None:
        rows: list[tuple[str, float]] = []
        for index, (token, logprob) in enumerate(zip(tokens, chosen)):
            top_row = top[index] if top and index < len(top) else None
            if isinstance(top_row, dict) and top_row:
                top_token, top_logprob = next(iter(top_row.items()))
                rows.append((str(top_token), float(top_logprob)))
            elif logprob is not None:
                rows.append((str(token), float(logprob)))
        return rows
    rows = []
    try:
        iterator = list(payload)
    except TypeError:
        iterator = []
    for position in iterator:
        if not isinstance(position, dict) or not position:
            continue
        key = next(iter(position))
        item = position[key]
        logprob = getattr(item, "logprob", item if isinstance(item, (int, float)) else None)
        decoded = getattr(item, "decoded_token", None) or key
        if logprob is not None:
            rows.append((str(decoded), float(logprob)))
    return rows


def response_text(response: Any) -> str:
    return str(response.choices[0].text)


def response_finish_reason(response: Any) -> Optional[str]:
    value = getattr(response.choices[0], "finish_reason", None)
    return None if value is None else str(value)


def response_stop_reason(response: Any) -> Optional[str]:
    value = getattr(response.choices[0], "stop_reason", None)
    if value is None:
        value = getattr(response.choices[0], "stop", None)
    return None if value is None else str(value)


def response_usage(response: Any) -> tuple[int, int]:
    usage = response.usage
    return int(usage.prompt_tokens), int(usage.completion_tokens)


def is_complete_boxed_trial(text: str) -> bool:
    """Trial is valid only when the inducer-following box closes."""
    stripped = str(text).lstrip()
    if stripped.startswith("{"):
        depth = 0
        for char in stripped:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return True
                if depth < 0:
                    return False
        return False
    # DeepSeek may emit content directly after ``\\boxed``; its first unmatched
    # closing brace terminates the box, matching the pinned DEER parser.
    return bool(parse_trial_response(stripped))


def make_trial_record(response: Any, *, model: str) -> dict[str, Any]:
    text = response_text(response)
    rows = completion_logprobs(response)
    policy = policy_for_model(model)
    require_close = require_think_close_for_model(model)
    last_token = rows[-1][0] if rows else ""
    answer = parse_trial_response(text)
    finish_reason = response_finish_reason(response)
    confidence = calculate_confidence(
        rows, policy=policy, require_think_close=require_close
    )
    prompt_tokens, output_tokens = response_usage(response)
    valid = bool(
        answer
        and is_complete_boxed_trial(text)
        and rows
        and len(rows) == output_tokens
        and finish_reason in VALID_FINISH_REASONS
        and (not require_close or last_token == DEER_THINK_CLOSE)
    )
    return {
        "text": text,
        "answer": answer if valid else "",
        "raw_parsed_answer": answer,
        "confidence": confidence,
        "valid": valid,
        "policy": policy,
        "require_think_close": require_close,
        "last_token_decoded": last_token,
        "think_close_emitted": last_token == DEER_THINK_CLOSE,
        "logprobs": [{"token": token, "logprob": value} for token, value in rows],
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
    }


def stage1_action(valid: bool, confidence: float) -> str:
    """Frozen strict-threshold order for the proposed method."""
    if not valid:
        return "continue"
    if confidence > 0.995:
        return "fast_commit"
    if confidence > 0.97:
        return "branch"
    return "continue"


def branch_commit(valid: bool, confidence: float, equivalent: bool) -> bool:
    return bool(valid and confidence > 0.99 and equivalent)


@dataclass
class ProbeSchedule:
    actual_attempts: int = 0
    last_probe_position: Optional[int] = None

    def decide(self, position: int, *, minimum_tokens: int = 1024) -> tuple[bool, str]:
        if position < minimum_tokens:
            return False, "before_minimum_tokens"
        if self.actual_attempts < 10:
            return True, "dense"
        assert self.last_probe_position is not None
        if position - self.last_probe_position >= 512:
            return True, "sparse"
        return False, "post_dense_gap_lt_512"

    def record_attempt(self, position: int) -> None:
        self.actual_attempts += 1
        self.last_probe_position = int(position)


def branch_is_allowed(position: int, previous_position: Optional[int]) -> bool:
    return previous_position is None or position - previous_position >= 512


def verification_cue(answer: str) -> str:
    return (
        f"\nCandidate answer: \\boxed{{{answer}}}\n"
        "I will quickly verify within 64 tokens whether this answer satisfies every "
        "requirement of the problem."
    )


def derive_accounting(
    *,
    main_segments: Sequence[Mapping[str, Any]],
    waits: Sequence[Mapping[str, Any]],
    branches: Sequence[Mapping[str, Any]],
    reference_readout: Optional[Mapping[str, Any]],
    tokenizer: Any,
    native_main_text: str,
) -> dict[str, Any]:
    main_generated = sum(int(row.get("output_tokens", 0)) for row in main_segments)
    stage1 = sum(
        int(row.get("trial", {}).get("output_tokens", 0))
        for row in waits
        if isinstance(row.get("trial"), Mapping)
    )
    verification = sum(
        int(row.get("verification", {}).get("output_tokens", 0)) for row in branches
    )
    stage2 = sum(
        int(row.get("stage2", {}).get("output_tokens", 0)) for row in branches
    )
    readout = int((reference_readout or {}).get("output_tokens", 0))
    all_prompt = sum(int(row.get("prompt_tokens", 0)) for row in main_segments)
    all_prompt += sum(
        int(row.get("trial", {}).get("prompt_tokens", 0))
        for row in waits
        if isinstance(row.get("trial"), Mapping)
    )
    all_prompt += sum(
        int(row.get("verification", {}).get("prompt_tokens", 0))
        + int(row.get("stage2", {}).get("prompt_tokens", 0))
        for row in branches
    )
    all_prompt += int((reference_readout or {}).get("prompt_tokens", 0))
    cue_tokens = sum(int(row.get("cue_tokens", 0)) for row in branches)
    native_committed = token_len(tokenizer, native_main_text)
    retained_verification = verification
    # Main request usage is retained separately for API accounting. The fair
    # protocol view uses committed native text, avoiding double-counting
    # retained verification as a later main prompt.
    return {
        "native_committed_main_output_tokens": native_committed,
        "main_request_output_tokens": main_generated,
        "stage1_trial_output_tokens": stage1,
        "verification_output_tokens": verification,
        "stage2_trial_output_tokens": stage2,
        "reference_readout_output_tokens": readout,
        "all_generated_tokens": native_committed + stage1 + verification + stage2 + readout,
        "all_prompt_tokens": all_prompt,
        "controller_cue_tokens": cue_tokens,
        "committed_reasoning_model_tokens": native_committed + retained_verification,
        "committed_reasoning_context_tokens": native_committed
        + retained_verification
        + cue_tokens,
    }


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if config.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError("protocol_version mismatch")
    if config.get("formal_seed") != 42:
        raise ValueError("formal config must use seed 42")
    return config


def formal_split_ids(split_manifest: Path, benchmark: str, split: str = "dev") -> set[int]:
    payload = load_json(split_manifest)
    assignments = payload["assignments"] if isinstance(payload, dict) else payload
    return {
        int(row["dataset_index"])
        for row in assignments
        if row["benchmark"] == benchmark and row["split"] == split
    }


def formal_dev_ids(split_manifest: Path, benchmark: str) -> set[int]:
    return formal_split_ids(split_manifest, benchmark, "dev")


def expected_dev_count(benchmark: str) -> int:
    return expected_split_count(benchmark, "dev")


def expected_split_count(benchmark: str, split: str = "dev") -> int:
    counts = {
        "train": {"math500": 300, "amc23": 24, "aime24": 18},
        "dev": {"math500": 100, "amc23": 8, "aime24": 6},
        "test": {"math500": 100, "amc23": 8, "aime24": 6},
    }
    return counts[split][benchmark]


def quarantine(path: Path) -> Path:
    suffix = time.strftime("%Y%m%d%H%M%S", time.localtime())
    target = path.with_name(path.name + f".corrupt.{suffix}")
    counter = 1
    while target.exists():
        target = path.with_name(path.name + f".corrupt.{suffix}.{counter}")
        counter += 1
    path.rename(target)
    return target


def validate_result_identity(
    payload: Mapping[str, Any],
    *,
    method: str,
    model: str,
    benchmark: str,
    seed: int,
    problem_id: int,
    config_hash: str,
) -> bool:
    expected = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "method": method,
        "model": model,
        "benchmark": benchmark,
        "base_seed": seed,
        "problem_id": problem_id,
        "config_hash": config_hash,
    }
    terminal = payload.get("terminal_state")
    return bool(
        all(payload.get(key) == value for key, value in expected.items())
        and terminal
        and terminal not in {"request_error", "protocol_error"}
        and not payload.get("infrastructure_errors")
    )


def percentile(values: Iterable[float], q: float) -> float:
    rows = sorted(float(value) for value in values)
    if not rows:
        return 0.0
    index = (len(rows) - 1) * q
    lo, hi = int(index), min(int(index) + 1, len(rows) - 1)
    weight = index - lo
    return rows[lo] * (1 - weight) + rows[hi] * weight
