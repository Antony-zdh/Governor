"""Restartable deployment-style online controller for the DEER experiment."""

from __future__ import annotations

import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from benchmark.FalseConsensus.related_work import common as related_common
from benchmark.FalseConsensus.related_work.common import (
    DEER_ANSWER_INDUCER,
    DEER_THINK_CLOSE,
)
from benchmark.FalseConsensus.related_work.deer import trial_stop_tokens

from . import PROTOCOL_VERSION, SCHEMA_VERSION
from .common import (
    ProbeSchedule,
    atomic_write_json,
    branch_commit,
    branch_is_allowed,
    derive_accounting,
    expected_dev_count,
    expected_split_count,
    formal_dev_ids,
    formal_split_ids,
    load_config,
    load_json,
    load_jsonl,
    make_trial_record,
    now_iso,
    quarantine,
    response_finish_reason,
    response_stop_reason,
    response_text,
    response_usage,
    sha256_json,
    sha256_text,
    split_at_terminal_wait,
    stable_seed,
    stage1_action,
    token_len,
    validate_result_identity,
    verification_cue,
    WAIT_STOP_STRINGS,
)


METHOD_PROPOSED = "deer_inspired_online_v1"
METHOD_REFERENCE = "deer_online_reference"
METHODS = (METHOD_PROPOSED, METHOD_REFERENCE)


class ExactRequestError(RuntimeError):
    """All retries of an identical request failed."""


class OnlineController:
    """One model/benchmark/method live controller.

    Dependencies can be injected for CPU unit tests. Formal runs lazily load
    OpenAI, the pinned tokenizer, chat template, answer extractor and grader.
    """

    def __init__(
        self,
        *,
        method: str,
        model: str,
        model_revision: str,
        benchmark: str,
        base_seed: int,
        cap: int,
        max_model_len: int,
        output: Path,
        config: Mapping[str, Any],
        url: str,
        api_key: str = "token-abc123",
        server_command: str = "",
        client: Any = None,
        tokenizer: Any = None,
        apply_chat_template_fn: Any = None,
        extract_answer_fn: Any = None,
        answers_equal_fn: Any = None,
        sleep_fn: Any = time.sleep,
        allow_nonformal_seed: bool = False,
        split: str = "dev",
    ):
        if method not in METHODS:
            raise ValueError(f"unknown method {method!r}")
        # Formal result is hard-locked to seed 42. A declared robustness diagnostic
        # (seeds 43/44) may opt out via allow_nonformal_seed; such runs are stamped
        # non-formal and must be kept in a separate, clearly labelled output tree.
        if base_seed != 42 and not allow_nonformal_seed:
            raise ValueError("formal online experiment is hard-locked to seed 42")
        if len(model_revision) != 40:
            raise ValueError("model revision must be an exact 40-character commit SHA")
        self.method = method
        self.model = model
        self.model_revision = model_revision
        self.benchmark = benchmark
        self.base_seed = int(base_seed)
        self.allow_nonformal_seed = bool(allow_nonformal_seed)
        self.split = str(split)
        self.cap = int(cap)
        self.max_model_len = int(max_model_len)
        self.output = Path(output)
        self.config = dict(config)
        self.config_hash = sha256_json(config)
        self.url = url
        self.api_key = api_key
        self.server_command = server_command
        self.sleep_fn = sleep_fn
        self.client = client or related_common.make_openai_client(url, api_key, timeout=600)
        self.tokenizer = tokenizer or related_common.load_tokenizer(model, model_revision)
        self.apply_chat_template = (
            apply_chat_template_fn or related_common.apply_chat_template
        )
        self.extract_answer = extract_answer_fn or related_common.extract_generated_answer
        self.answers_equal = answers_equal_fn or related_common.real_answers_equal
        self.results_dir = self.output / "problems"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.write_lock = threading.Lock()

    def _seed(self, problem_id: int, candidate_id: int, role: str) -> int:
        if role == "main" and candidate_id == 0:
            return self.base_seed + int(problem_id)
        return stable_seed(
            PROTOCOL_VERSION,
            self.model,
            self.benchmark,
            self.base_seed,
            int(problem_id),
            int(candidate_id),
            role,
        )

    def _complete(
        self,
        *,
        role: str,
        problem_id: int,
        candidate_id: int,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        stop: Optional[Sequence[str]] = None,
        logprobs: Optional[int] = None,
        include_stop: bool = False,
    ) -> tuple[Any, dict[str, Any]]:
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        seed = self._seed(problem_id, candidate_id, role)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "seed": seed,
            "stream": False,
        }
        if stop:
            kwargs["stop"] = list(stop)
        if logprobs:
            kwargs["logprobs"] = int(logprobs)
        if include_stop:
            kwargs["extra_body"] = {"include_stop_str_in_output": True}
        errors: list[str] = []
        for retry in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(**kwargs)
                latency = time.perf_counter() - started
                prompt_tokens, output_tokens = response_usage(response)
                return response, {
                    "role": role,
                    "seed": seed,
                    "request_hash": sha256_json(kwargs),
                    "max_tokens": int(max_tokens),
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "stop": list(stop or []),
                    "include_stop_str_in_output": bool(include_stop),
                    "prompt_tokens": prompt_tokens,
                    "output_tokens": output_tokens,
                    "latency_seconds": latency,
                    "retry_count": retry,
                    "prior_errors": errors,
                }
            except Exception as error:
                errors.append(f"{type(error).__name__}: {error}")
                if retry < 3:
                    self.sleep_fn(5 * (retry + 1))
        raise ExactRequestError("; ".join(errors))

    def _context_allowance(self, prompt: str, desired: int) -> int:
        prompt_tokens = token_len(self.tokenizer, prompt)
        return max(0, min(int(desired), self.max_model_len - prompt_tokens - 32))

    def _trial(
        self,
        *,
        problem_id: int,
        candidate_id: int,
        role: str,
        prompt: str,
    ) -> dict[str, Any]:
        response, request = self._complete(
            role=role,
            problem_id=problem_id,
            candidate_id=candidate_id,
            prompt=prompt + DEER_ANSWER_INDUCER,
            max_tokens=20,
            temperature=0.0,
            top_p=1.0,
            stop=trial_stop_tokens(self.model),
            logprobs=1,
            include_stop=True,
        )
        record = make_trial_record(response, model=self.model)
        record.update(request)
        return record

    def _readout(
        self,
        *,
        problem_id: int,
        candidate_id: int,
        clean_prompt: str,
    ) -> dict[str, Any]:
        prompt = clean_prompt + "\n</think>\n\n"
        allowance = self._context_allowance(prompt, 4096)
        if allowance < 32:
            return {
                "valid": False,
                "answer": "",
                "context_budget_exceeded": True,
                "prompt_tokens": token_len(self.tokenizer, prompt),
                "output_tokens": 0,
            }
        response, request = self._complete(
            role="reference_readout",
            problem_id=problem_id,
            candidate_id=candidate_id,
            prompt=prompt,
            max_tokens=allowance,
            temperature=0.0,
            top_p=1.0,
        )
        text = response_text(response)
        validity = related_common.readout_validity(
            text, response_finish_reason(response), self.benchmark
        )
        return {
            **request,
            "text": text,
            "answer": validity["readout_answer"],
            "valid": validity["readout_valid"],
            "truncated": validity["readout_truncated"],
            "completed_boxed": validity["readout_completed_boxed"],
            "finish_reason": validity["readout_finish_reason"],
            "context_budget_exceeded": False,
        }

    def collect_problem(
        self, problem_id: int, problem: str, target: Any, metadata: Mapping[str, Any]
    ) -> int:
        output_path = self.results_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            try:
                existing = load_json(output_path)
                if validate_result_identity(
                    existing,
                    method=self.method,
                    model=self.model,
                    benchmark=self.benchmark,
                    seed=self.base_seed,
                    problem_id=problem_id,
                    config_hash=self.config_hash,
                ):
                    return problem_id
                quarantine(output_path)
            except Exception:
                quarantine(output_path)

        chat = self.apply_chat_template(str(problem).strip(), self.model)
        native_main_text = ""
        context_tail = ""
        main_segments: list[dict[str, Any]] = []
        waits: list[dict[str, Any]] = []
        branches: list[dict[str, Any]] = []
        reference_readout: Optional[dict[str, Any]] = None
        schedule = ProbeSchedule()
        reference_attempts = 0
        last_branch_position: Optional[int] = None
        retained_verification_tokens = 0
        main_call_index = 0
        candidate_id = 0
        terminal_state = ""
        delivered_answer = ""
        capped = False
        infrastructure_errors: list[str] = []

        def commit_wait_once(wait_text: str) -> bool:
            nonlocal native_main_text, context_tail
            projected = token_len(self.tokenizer, native_main_text + wait_text)
            if projected + retained_verification_tokens > self.cap:
                return False
            native_main_text += wait_text
            context_tail += wait_text
            return True

        while not terminal_state:
            native_position = token_len(self.tokenizer, native_main_text)
            remaining = self.cap - native_position - retained_verification_tokens
            if remaining <= 0:
                terminal_state, capped = "capped", True
                break
            prompt = chat + context_tail
            allowance = self._context_allowance(prompt, remaining)
            if allowance <= 0:
                terminal_state, capped = "context_capped", True
                break
            try:
                response, request = self._complete(
                    role="main",
                    problem_id=problem_id,
                    candidate_id=main_call_index,
                    prompt=prompt,
                    max_tokens=allowance,
                    temperature=0.6,
                    top_p=0.95,
                    stop=WAIT_STOP_STRINGS,
                    include_stop=True,
                )
            except ExactRequestError as error:
                infrastructure_errors.append(str(error))
                terminal_state = "request_error"
                break
            main_call_index += 1
            text = response_text(response)
            finish_reason = response_finish_reason(response)
            stop_reason = response_stop_reason(response)
            segment = {
                **request,
                "text": text,
                "finish_reason": finish_reason,
                "stop_reason": stop_reason,
                "main_call_index": main_call_index - 1,
            }
            main_segments.append(segment)
            try:
                clean_piece, wait_text = split_at_terminal_wait(text, stop_reason)
            except ValueError as error:
                infrastructure_errors.append(str(error))
                terminal_state = "protocol_error"
                break

            native_main_text += clean_piece
            context_tail += clean_piece
            native_position = token_len(self.tokenizer, native_main_text)

            if not wait_text:
                if finish_reason == "length":
                    capped = True
                    terminal_state = "capped"
                else:
                    terminal_state = "natural"
                    delivered_answer = self.extract_answer(
                        native_main_text, self.benchmark
                    )
                break

            candidate_id += 1
            wait_record: dict[str, Any] = {
                "candidate_id": candidate_id,
                "observed_text": wait_text,
                "native_main_token_position": native_position,
                "probed": False,
                "schedule_mode": None,
                "skip_reason": None,
            }

            if self.method == METHOD_REFERENCE:
                should_probe = reference_attempts < 10
                schedule_mode = "official_first_10"
                skip_reason = None if should_probe else "official_max_10_reached"
            else:
                should_probe, decision = schedule.decide(native_position)
                schedule_mode = decision if should_probe else None
                skip_reason = None if should_probe else decision
            wait_record["schedule_mode"] = schedule_mode
            wait_record["skip_reason"] = skip_reason

            if not should_probe:
                if commit_wait_once(wait_text):
                    wait_record["action"] = "commit_wait_continue"
                else:
                    wait_record["action"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                waits.append(wait_record)
                if terminal_state:
                    break
                continue

            wait_record["probed"] = True
            if self.method == METHOD_REFERENCE:
                reference_attempts += 1
            else:
                schedule.record_attempt(native_position)
            try:
                trial = self._trial(
                    problem_id=problem_id,
                    candidate_id=candidate_id,
                    role="stage1_trial",
                    prompt=chat + context_tail,
                )
                wait_record["trial"] = trial
            except ExactRequestError as error:
                wait_record["trial"] = {"error": str(error), "output_tokens": 0}
                wait_record["action"] = "trial_error_commit_wait_continue"
                infrastructure_errors.append(str(error))
                if not commit_wait_once(wait_text):
                    wait_record["action"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                waits.append(wait_record)
                if terminal_state:
                    break
                continue

            if self.method == METHOD_REFERENCE:
                if float(trial["confidence"]) > 0.95:
                    wait_record["action"] = "reference_readout"
                    try:
                        reference_readout = self._readout(
                            problem_id=problem_id,
                            candidate_id=candidate_id,
                            clean_prompt=chat + context_tail,
                        )
                    except ExactRequestError as error:
                        reference_readout = {
                            "error": str(error),
                            "valid": False,
                            "answer": "",
                            "output_tokens": 0,
                            "prompt_tokens": 0,
                        }
                        infrastructure_errors.append(str(error))
                    delivered_answer = (
                        str(reference_readout.get("answer", ""))
                        if reference_readout.get("valid")
                        else ""
                    )
                    terminal_state = "reference_readout"
                    waits.append(wait_record)
                    break
                if commit_wait_once(wait_text):
                    wait_record["action"] = "commit_wait_continue"
                else:
                    wait_record["action"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                waits.append(wait_record)
                if terminal_state:
                    break
                continue

            action = stage1_action(bool(trial["valid"]), float(trial["confidence"]))
            if action == "fast_commit":
                delivered_answer = str(trial["answer"])
                terminal_state = "fast_commit"
                wait_record["action"] = action
                waits.append(wait_record)
                break
            if action != "branch":
                if commit_wait_once(wait_text):
                    wait_record["action"] = "commit_wait_continue"
                else:
                    wait_record["action"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                waits.append(wait_record)
                if terminal_state:
                    break
                continue
            if not branch_is_allowed(native_position, last_branch_position):
                if commit_wait_once(wait_text):
                    wait_record["action"] = "commit_wait_continue"
                else:
                    wait_record["action"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                wait_record["skip_reason"] = "verification_gap_lt_512"
                waits.append(wait_record)
                if terminal_state:
                    break
                continue

            last_branch_position = native_position
            answer_a = str(trial["answer"])
            cue = verification_cue(answer_a)
            cue_tokens = token_len(self.tokenizer, cue)
            branch_record: dict[str, Any] = {
                "candidate_id": candidate_id,
                "native_main_token_position": native_position,
                "answer_a": answer_a,
                "confidence_a": trial["confidence"],
                "cue_template": verification_cue("<ANSWER_A>"),
                "cue": cue,
                "cue_tokens": cue_tokens,
                "verification_retained": False,
            }
            verification_prompt = chat + context_tail + cue
            cap_remaining = self.cap - native_position - retained_verification_tokens
            verification_allowance = self._context_allowance(
                verification_prompt, min(64, cap_remaining)
            )
            if verification_allowance <= 0:
                branch_record["verification"] = {
                    "error": "context_budget_exceeded",
                    "output_tokens": 0,
                    "prompt_tokens": token_len(self.tokenizer, verification_prompt),
                }
                branch_record["outcome"] = "verification_error_commit_wait"
                branches.append(branch_record)
                if not commit_wait_once(wait_text):
                    branch_record["outcome"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                wait_record["action"] = branch_record["outcome"]
                waits.append(wait_record)
                if terminal_state:
                    break
                continue
            try:
                vresponse, vrequest = self._complete(
                    role="verification_reasoning",
                    problem_id=problem_id,
                    candidate_id=candidate_id,
                    prompt=verification_prompt,
                    max_tokens=verification_allowance,
                    temperature=0.6,
                    top_p=0.95,
                    stop=[DEER_THINK_CLOSE]
                    if "qwen3" in self.model.lower()
                    else None,
                    include_stop=False,
                )
            except ExactRequestError as error:
                branch_record["verification"] = {
                    "error": str(error),
                    "output_tokens": 0,
                    "prompt_tokens": token_len(self.tokenizer, verification_prompt),
                }
                branch_record["outcome"] = "verification_error_commit_wait"
                infrastructure_errors.append(str(error))
                branches.append(branch_record)
                if not commit_wait_once(wait_text):
                    branch_record["outcome"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                wait_record["action"] = branch_record["outcome"]
                waits.append(wait_record)
                if terminal_state:
                    break
                continue
            verification_text = response_text(vresponse)
            verification_finish = response_finish_reason(vresponse)
            if not verification_text or verification_finish not in {"stop", "length"}:
                branch_record["verification"] = {
                    **vrequest,
                    "text": verification_text,
                    "finish_reason": verification_finish,
                    "error": "empty_or_invalid_verification_output",
                }
                branch_record["outcome"] = "verification_error_commit_wait"
                infrastructure_errors.append("empty_or_invalid_verification_output")
                branches.append(branch_record)
                if not commit_wait_once(wait_text):
                    branch_record["outcome"] = "cap_before_wait_commit"
                    terminal_state, capped = "capped", True
                wait_record["action"] = branch_record["outcome"]
                waits.append(wait_record)
                if terminal_state:
                    break
                continue
            if (
                "qwen3" in self.model.lower()
                and DEER_THINK_CLOSE in verification_text
            ):
                infrastructure_errors.append("Qwen verification leaked </think> into context")
                terminal_state = "protocol_error"
                break
            verification = {
                **vrequest,
                "text": verification_text,
                "finish_reason": verification_finish,
                "stop_reason": response_stop_reason(vresponse),
            }
            branch_record["verification"] = verification
            branch_record["verification_retained"] = True
            context_tail += cue + verification_text
            retained_verification_tokens += int(verification["output_tokens"])
            branch_record["retained_context_hash"] = sha256_text(context_tail)

            try:
                stage2 = self._trial(
                    problem_id=problem_id,
                    candidate_id=candidate_id,
                    role="stage2_trial",
                    prompt=chat + context_tail,
                )
            except ExactRequestError as error:
                stage2 = {"error": str(error), "valid": False, "output_tokens": 0}
                infrastructure_errors.append(str(error))
            branch_record["stage2"] = stage2
            equivalent = bool(
                stage2.get("valid")
                and self.answers_equal(answer_a, str(stage2.get("answer", "")))
            )
            branch_record["answers_equivalent"] = equivalent
            passed = branch_commit(
                bool(stage2.get("valid")),
                float(stage2.get("confidence", 0.0)),
                equivalent,
            )
            if passed:
                delivered_answer = str(stage2["answer"])
                terminal_state = "branch_commit"
                branch_record["outcome"] = "commit"
                wait_record["action"] = "branch_commit"
                branches.append(branch_record)
                waits.append(wait_record)
                break
            branch_record["outcome"] = "fail_retain_verification"
            wait_record["action"] = "branch_fail_retain_verification"
            branches.append(branch_record)
            waits.append(wait_record)
            # Deliberately do not append Wait after a normal branch failure.

        accounting = derive_accounting(
            main_segments=main_segments,
            waits=waits,
            branches=branches,
            reference_readout=reference_readout,
            tokenizer=self.tokenizer,
            native_main_text=native_main_text,
        )
        correct = bool(delivered_answer and self.answers_equal(delivered_answer, target))
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "method": self.method,
            "config_hash": self.config_hash,
            "model": self.model,
            "model_revision": self.model_revision,
            "dtype": "bfloat16",
            "server_command": self.server_command,
            "benchmark": self.benchmark,
            "base_seed": self.base_seed,
            "formal": (
                self.base_seed == 42
                and self.split == "dev"
                and not self.allow_nonformal_seed
            ),
            "problem_id": int(problem_id),
            "split": self.split,
            "problem": problem,
            "target": target,
            "metadata": dict(metadata),
            "chat_template_sha256": sha256_text(chat),
            "main_segments": main_segments,
            "wait_events": waits,
            "branches": branches,
            "reference_readout": reference_readout,
            "native_main_text": native_main_text,
            "native_main_text_sha256": sha256_text(native_main_text),
            "terminal_state": terminal_state,
            "delivered_answer": delivered_answer,
            "correct": correct,
            "capped": capped,
            "right_censored": capped,
            "infrastructure_errors": infrastructure_errors,
            "accounting": accounting,
            "created_at": now_iso(),
        }
        with self.write_lock:
            atomic_write_json(output_path, payload)
        return problem_id


def _dataset(config: Mapping[str, Any], benchmark: str) -> list[dict[str, Any]]:
    path = Path(config["benchmarks"][benchmark]["dataset_path"])
    if path.suffix != ".jsonl":
        raise ValueError("formal datasets must be JSONL")
    return load_jsonl(path)


def _manifest_path(output: Path) -> Path:
    return output / "run_manifest.json"


def run(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if args.seed != 42 and not args.allow_nonformal_seed:
        raise ValueError("formal runner rejects base_seed != 42")
    if args.smoke and not args.problem_id:
        raise ValueError("--smoke requires at least one --problem-id")
    if not args.smoke and args.problem_id:
        raise ValueError("--problem-id is smoke-only; formal runs cover all Dev IDs")
    model_cfg = config["models"][args.model]
    bench_cfg = config["benchmarks"][args.benchmark]
    if args.model_revision != model_cfg["revision"]:
        raise ValueError("model revision differs from frozen config")
    split = args.split
    if split == "test" and not args.allow_test_read:
        raise ValueError(
            "reading the held-out test split requires --allow-test-read "
            "(preregistration confirmation gate)"
        )
    dataset = _dataset(config, args.benchmark)
    split_ids = formal_split_ids(Path(config["split_manifest"]), args.benchmark, split)
    if len(split_ids) != expected_split_count(args.benchmark, split):
        raise ValueError(f"split manifest {split} count mismatch")
    selected = set(args.problem_id) if args.smoke else split_ids
    if not selected <= split_ids:
        raise ValueError(f"problem ID outside requested {split} split supplied to runner")
    output = Path(args.output)
    settings = {
        "protocol_version": PROTOCOL_VERSION,
        "method": args.method,
        "model": args.model,
        "model_revision": args.model_revision,
        "benchmark": args.benchmark,
        "base_seed": args.seed,
        "formal": (
            args.seed == 42 and split == "dev" and not args.allow_nonformal_seed
        ),
        "test_read": split == "test",
        "dtype": "bfloat16",
        "cap": bench_cfg["cap"],
        "max_model_len": model_cfg["max_model_len"],
        "split": split,
        "config_hash": sha256_json(config),
        "smoke": bool(args.smoke),
        "problem_ids": sorted(selected) if args.smoke else None,
    }
    manifest_path = _manifest_path(output)
    if manifest_path.exists():
        existing = load_json(manifest_path)
        if existing.get("run_settings") != settings:
            raise ValueError("existing output has incompatible run settings")
    else:
        atomic_write_json(
            manifest_path,
            {
                "schema_version": "deer-inspired-online-run-1",
                "run_settings": settings,
                "created_at": now_iso(),
            },
        )
    controller = OnlineController(
        method=args.method,
        model=args.model,
        model_revision=args.model_revision,
        benchmark=args.benchmark,
        base_seed=args.seed,
        cap=int(bench_cfg["cap"]),
        max_model_len=int(model_cfg["max_model_len"]),
        output=output,
        config=config,
        url=args.url,
        api_key=args.api_key,
        server_command=args.server_command,
        allow_nonformal_seed=args.allow_nonformal_seed,
        split=split,
    )
    try:
        served = controller.client.models.list()
        served_ids = {str(item.id) for item in getattr(served, "data", [])}
    except Exception as error:
        raise RuntimeError(f"vLLM readiness check failed: {error}") from error
    if args.model not in served_ids:
        raise RuntimeError(
            f"formal model {args.model!r} not present at endpoint; served={sorted(served_ids)}"
        )
    started = time.perf_counter()
    futures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for problem_id in sorted(selected):
            row = dataset[problem_id]
            problem = str(row.get("problem", row.get("question", "")))
            futures.append(
                pool.submit(
                    controller.collect_problem,
                    problem_id,
                    problem,
                    row["answer"],
                    {
                        key: row.get(key)
                        for key in ("id", "unique_id", "level", "subject", "url")
                    },
                )
            )
        for index, future in enumerate(as_completed(futures), start=1):
            problem_id = future.result()
            print(f"[{index}/{len(futures)}] problem {problem_id}", flush=True)
    result_paths = list((output / "problems").glob("problem_*.json"))
    observed = len(result_paths)
    failed_results = []
    for result_path in result_paths:
        result = load_json(result_path)
        if result.get("infrastructure_errors") or result.get("terminal_state") in {
            "request_error",
            "protocol_error",
        }:
            failed_results.append(int(result["problem_id"]))
    manifest = load_json(manifest_path)
    manifest["completion"] = {
        "expected_problem_count": len(selected),
        "observed_problem_count": observed,
        "missing_problem_count": len(selected) - observed,
        "failed_problem_ids": sorted(failed_results),
        "elapsed_seconds": time.perf_counter() - started,
        "complete": observed == len(selected) and not failed_results,
        "finished_at": now_iso(),
    }
    atomic_write_json(manifest_path, manifest)
    if observed != len(selected) or failed_results:
        raise RuntimeError(
            f"formal collection incomplete: observed={observed}/{len(selected)}, "
            f"failed={sorted(failed_results)}"
        )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--benchmark", choices=("math500", "amc23", "aime24"), required=True)
    parser.add_argument("--split", choices=("train", "dev", "test"), default="dev")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--server-command", default="")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--problem-id", type=int, action="append", default=[])
    parser.add_argument(
        "--allow-nonformal-seed",
        action="store_true",
        help="permit seeds other than 42 for a declared, non-formal robustness "
        "diagnostic; runs are stamped formal=false and must use a separate output tree",
    )
    parser.add_argument(
        "--allow-test-read",
        action="store_true",
        help="required to read the held-out test split; stamps test_read=true and "
        "must use a separate output tree (preregistration confirmation gate)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    run(parse_args(argv))


if __name__ == "__main__":
    main()
