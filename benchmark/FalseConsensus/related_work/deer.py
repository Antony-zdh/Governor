"""DEER frozen-trajectory reproduction collector + replay.

Reproduces the official DEER base method (``iie-ycx/DEER``) on the frozen
Governor v2 main trajectories, pinned to upstream commit
``c9dd19fbffa27f841cfe47502d015b63811b4d1b`` (default branch ``main``).

Protocol (verbatim from ``vllm-deer.py`` / ``vllm-deer-qwen3.py`` at that
commit):
    * transition point:   ``--points 1`` -> ``Wait`` (``continue_str``);
    * max attempts:        ``--max_judge_steps 10`` prob_checks per problem;
    * threshold:           ``--threshold 0.95``;
    * trial-answer cap:    ``--prob_check_max_tokens 20``;
    * answer inducer:      ``"\n**Final Answer**\n\\boxed"`` (verbatim);
    * confidence:          average of per-token max prob (``exp(logprob)``)
                            over the trial-answer tokens, computed from
                            index 1 to the last token (the first generated
                            token is skipped, faithful to the released code);
    * DeepSeek (base):     ``--policy avg1`` = arithmetic mean; trial probe
                            ``stop`` = the ``\boxed{}``-closing variants;
                            early exit iff ``confidence > 0.95``;
    * Qwen3:               ``--policy avg2`` = geometric mean; trial probe
                            ``stop = ['</think>']``; the released
                            ``calculate_average_max_prob_from_logprobs`` adds
                            the official Qwen3 condition -- the confidence is
                            returned *only if the last generated token decodes
                            to ``</think>``*, otherwise it is forced to ``0.0``
                            (this is the "model must generate ``</think>`` after
                            the trial answer" requirement); early exit iff
                            ``confidence > 0.95``;
    * on early exit:       switch to the answer phase -- the final answer is
                            read out from ``prompt + prefix + "\n</think>\n\n"``
                            and that readout output cost is recorded;
    * on regular end:      the model reached ``</think>`` naturally (no early
                            exit) -> the frozen natural full answer is the
                            delivered answer.

Frozen-trajectory adaptation (labeled, not concealed):
    DEER's online controller interleaves thinking chunks and trial-answer
    prob_checks at the ``Wait`` transition markers, appending ``Wait`` and
    continuing when below threshold. Here the main trajectory is *frozen*, so
    the ``Wait`` markers are independently recomputed from the frozen
    ``full_text`` and the first ``max_judge_steps`` (10) are probed in order.
    Replaying official DEER probes on a frozen pre-generated path is not
    identical to running the entire online controller from the original prompt;
    the result is labeled ``deer_frozen``.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from . import common
from .common import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEER_ANSWER_INDUCER,
    DEER_CONTINUE_STR,
    DEER_MAX_JUDGE_STEPS,
    DEER_PRED_PROB_STOP_TOKENS,
    DEER_THINK_CLOSE,
    DEER_THRESHOLD,
    DEER_TRIAL_CAP,
    atomic_write_json,
    env_metadata,
    find_think_close_positions,
    find_wait_positions,
    load_main_manifest,
    load_tokenizer,
    make_openai_client,
    method_provenance,
    now_iso,
    obtain_boxed_answer,
    sha256_bytes,
    trajectory_paths,
)

METHOD = "deer_frozen"
REPRODUCTION_CLASS = "frozen-trajectory DEER reproduction (official probes on frozen prefix)"
SOURCE_COMMIT = "c9dd19fbffa27f841cfe47502d015b63811b4d1b"
SOURCE_URL = "https://github.com/iie-ycx/DEER"
PROBE_SCHEMA = "related-work-deer-trial-1"
RUN_SCHEMA = "related-work-deer-run-1"
RECORD_FIELDS = (
    "candidate_id",
    "trigger_type",
    "trigger_char_position",
    "token_position",
    "trial_answer",
    "confidence",
    "policy",
    "last_token_decoded",
    "think_close_emitted",
    "meets_threshold",
    "trial_out_tokens",
    "trial_prompt_tokens",
    "trial_latency_seconds",
)


# --------------------------------------------------------------------------- #
# Pure confidence logic (no torch; faithful to vllm-deer.py:100-155)
# --------------------------------------------------------------------------- #
def _prob(logprob: float) -> float:
    return math.exp(logprob)


def calculate_confidence(
    logprobs: Sequence[Tuple[str, float]],
    *,
    policy: str = "avg1",
    require_think_close: bool = False,
) -> float:
    """Faithful reproduction of DEER ``calculate_average_max_prob_from_logprobs``.

    ``logprobs`` is the per-generated-token sequence of ``(decoded_token,
    logprob)`` for the *top* logprob entry at each position (what the released
    code reads via ``list(logprobs_list[i].values())[0]``). The mean is taken
    from index 1 to the last token (the first generated token is skipped,
    exactly as in the released code -- ``start_index=1, end_index=num_tokens``).

    * ``avg1``: arithmetic mean of ``exp(logprob)``;
    * ``avg2``: geometric mean = ``exp(mean(log(prob)))`` with ``prob`` floored
      at ``1e-10`` (verbatim);
    * Qwen3 (``require_think_close=True``): the result is returned *only if*
      the last generated token decodes to ``</think>``; otherwise ``0.0``.
      This is the official additional Qwen3 early-exit condition.
    """
    num_tokens = len(logprobs)
    if num_tokens < 1:
        return 0.0
    start_index = 1
    end_index = num_tokens
    total_prob_sum = 0.0
    log_prob_sum = 0.0
    count = 0
    for i in range(start_index, end_index):
        if i < num_tokens:
            _token, logprob = logprobs[i]
            prob = _prob(logprob)
            total_prob_sum += prob
            log_prob_sum += math.log(max(prob, 1e-10))
            count += 1
    if count == 0:
        return 0.0
    if policy == "min":
        result = min(_prob(l) for _, l in logprobs[1:end_index])
    elif policy == "avg1":
        result = total_prob_sum / count
    elif policy == "avg2":
        result = math.exp(log_prob_sum / count)
    else:
        raise ValueError(f"unknown DEER policy {policy!r}")
    if require_think_close:
        last_token = logprobs[-1][0] if logprobs else ""
        return result if last_token == DEER_THINK_CLOSE else 0.0
    return result


def policy_for_model(model: str) -> str:
    """Official model-specific policy: avg1 for DeepSeek, avg2 for Qwen3."""
    return "avg2" if "qwen3" in model.lower() else "avg1"


def require_think_close_for_model(model: str) -> bool:
    """The additional ``</think>`` condition applies only to Qwen3."""
    return "qwen3" in model.lower()


def trial_stop_tokens(model: str) -> List[str]:
    """Official trial-answer stop tokens: boxed-close variants (base) vs
    ``</think>`` (Qwen3)."""
    if require_think_close_for_model(model):
        return [DEER_THINK_CLOSE]
    return list(DEER_PRED_PROB_STOP_TOKENS)


def find_candidates(text: str, *, max_attempts: int = DEER_MAX_JUDGE_STEPS) -> List[dict]:
    """The first ``max_attempts`` whole-word ``Wait`` positions (transition
    candidates). DEER probes these in order; after exhaustion it continues to
    ``</think>`` (regular end)."""
    out = []
    for off in find_wait_positions(text):
        out.append({
            "trigger_type": "wait",
            "trigger_char_position": off,
            # Official DEER stops before emitting the transition string,
            # performs the probability check, and appends Wait only when the
            # check is below threshold.
            "trigger_char_end": off,
        })
        if len(out) >= max_attempts:
            break
    for i, t in enumerate(out, start=1):
        t["candidate_id"] = i
    return out


def parse_trial_response(trial_text: str, *, obtain_answer_fn: Callable[[str], str] = obtain_boxed_answer) -> str:
    """Extract the trial answer after DEER's ``\\boxed`` (no opening brace).

    The official inducer ends at ``\\boxed``, so a normal completion starts
    with ``{answer}``. CertaIndex's parser instead expects the prompt to have
    already supplied ``{``; support both shapes explicitly.
    """
    stripped = str(trial_text).lstrip()
    if stripped.startswith("{"):
        depth = 0
        answer: List[str] = []
        for char in stripped:
            if char == "{":
                if depth:
                    answer.append(char)
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return "".join(answer)
                answer.append(char)
            elif depth:
                answer.append(char)
        return ""
    return obtain_answer_fn(stripped) or ""


def decide_stop(
    trial_records: Sequence[Mapping[str, Any]],
    *,
    threshold: float = DEER_THRESHOLD,
) -> Optional[dict]:
    """First candidate whose confidence exceeds ``threshold``; else None."""
    for t in trial_records:
        if float(t.get("confidence", 0.0)) > threshold:
            return {
                "stop_candidate_id": t["candidate_id"],
                "stop_position": int(t.get("token_position", 0)),
                "confidence": float(t["confidence"]),
                "policy": t.get("policy"),
            }
    return None


def replay(
    trajectory: Mapping[str, Any],
    trial_records: Sequence[Mapping[str, Any]],
    *,
    threshold: float = DEER_THRESHOLD,
    readout: Optional[Mapping[str, Any]] = None,
    answers_equal_target_fn: Optional[Callable[[Any, Any], bool]] = None,
    split: Optional[str] = None,
) -> dict:
    """Compute delivered answer + two-view token accounting for one trajectory."""
    full_tokens = int(trajectory.get("tokens_used", 0))
    finished_naturally = bool(trajectory.get("finished_naturally", False))
    budget = int(trajectory.get("run_settings", {}).get("budget", full_tokens or 2**31))
    full_answer = trajectory.get("final_answer", "")
    full_correct = bool(trajectory.get("final_correct", False))

    decision = decide_stop(trial_records, threshold=threshold)
    trial_out = sum(int(t.get("trial_out_tokens", 0)) for t in trial_records)
    trial_prompt = sum(int(t.get("trial_prompt_tokens", 0)) for t in trial_records)
    readout_out = int(readout.get("readout_out_tokens", 0)) if readout else 0
    readout_prompt = int(readout.get("readout_prompt_tokens", 0)) if readout else 0
    readout_calls = 1 if readout is not None else 0
    invalid_aux = sum(
        1 for t in trial_records
        if "error" in t or not t.get("logprobs") or not t.get("trial_answer")
    )
    if readout is not None and ("error" in readout or readout.get("readout_valid") is False):
        invalid_aux += 1
    auxiliary_wall = sum(
        float(t.get("trial_latency_seconds", 0.0)) for t in trial_records
    ) + (float(readout.get("readout_latency_seconds", 0.0)) if readout else 0.0)

    if decision is not None:
        stopped = True
        main_through_stop = decision["stop_position"]
        capped = False
        delivered = (readout or {}).get("readout_answer", "") or ""
        recovery_truncated = True
        overthinking_avoided = max(0, full_tokens - main_through_stop)
    else:
        # No early exit within max_attempts -> regular end at </think>: the
        # model naturally concluded, so the frozen natural full answer stands.
        stopped = False
        main_through_stop = full_tokens
        capped = not finished_naturally or full_tokens > budget
        if finished_naturally and full_tokens <= budget:
            delivered = full_answer
        else:
            delivered = ""
        recovery_truncated = False
        overthinking_avoided = 0

    if answers_equal_target_fn is not None and delivered:
        try:
            correct = bool(answers_equal_target_fn(delivered, trajectory.get("target")))
        except Exception:
            correct = False
    else:
        correct = None

    return {
        **common.trajectory_identity(trajectory),
        "split": split,
        "method": METHOD,
        "reproduction_class": REPRODUCTION_CLASS,
        "threshold": threshold,
        "stopped": stopped,
        "capped": capped,
        "recovery_truncated": recovery_truncated,
        "overthinking_avoided_tokens": overthinking_avoided,
        "delivered_answer": delivered,
        "correct": correct,
        "baseline_correct": full_correct,
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_through_stop,
        "trial_out_tokens": trial_out,
        "trial_prompt_tokens": trial_prompt,
        "readout_out_tokens": readout_out,
        "readout_prompt_tokens": readout_prompt,
        "probe_out_tokens": trial_out + readout_out,
        "probe_prompt_tokens": trial_prompt + readout_prompt,
        "all_generated_tokens": main_through_stop + trial_out + readout_out,
        "baseline_all_generated_tokens": full_tokens,
        "n_candidates": len(trial_records),
        "n_aux_calls": len(trial_records) + readout_calls,
        "n_readout_calls": readout_calls,
        "invalid_aux_responses": invalid_aux,
        "auxiliary_wall_seconds": auxiliary_wall,
        "max_attempts": DEER_MAX_JUDGE_STEPS,
        "stop_position": decision["stop_position"] if decision else None,
        "stop_candidate_id": decision["stop_candidate_id"] if decision else None,
    }


# --------------------------------------------------------------------------- #
# Live collector (needs an endpoint; never runs in CPU-only validation)
# --------------------------------------------------------------------------- #
class DEERCollector:
    PROBE_SCHEMA = PROBE_SCHEMA
    RUN_SCHEMA = RUN_SCHEMA

    def __init__(self, args: argparse.Namespace, main_manifest: Mapping[str, Any]):
        self.args = args
        self.main_settings = dict(main_manifest["run_settings"])
        self.model = args.model or str(self.main_settings["model"])
        if self.model != self.main_settings["model"]:
            raise ValueError("--model disagrees with main trajectory manifest")
        if not common.is_40hex(args.model_revision):
            raise ValueError(f"--model-revision must be a 40-hex SHA, got {args.model_revision!r}")
        self.model_revision = args.model_revision
        self.dataset = str(self.main_settings["dataset"])
        self.base_seed = int(self.main_settings["base_seed"])
        # Official DEER CLI defaults for its controller/readout are greedy
        # temperature=0.0, top_p=1.0 (vllm-deer*.py argparse defaults).
        self.temperature = 0.0
        self.top_p = 1.0
        self.threshold = float(args.threshold)
        self.max_attempts = int(args.max_attempts)
        self.trial_cap = int(args.trial_cap)
        self.readout_cap = int(args.readout_cap)
        self.policy = args.policy or policy_for_model(self.model)
        self.require_think_close = require_think_close_for_model(self.model) if not args.force_policy else (self.policy == "avg2")
        self.stop_tokens = trial_stop_tokens(self.model) if not args.force_policy else ([DEER_THINK_CLOSE] if self.policy == "avg2" else list(DEER_PRED_PROB_STOP_TOKENS))
        self.client = make_openai_client(args.url, args.api_key, timeout=600)
        self.tokenizer = load_tokenizer(self.model, self.model_revision)
        self.output = Path(args.output)
        self.trial_dir = self.output / "trials"
        self.trial_dir.mkdir(parents=True, exist_ok=True)
        main_run = Path(args.main_run)
        split_manifest = Path(args.split_manifest)
        traj_files = trajectory_paths(main_run)
        self.settings = {
            "collection_schema": self.PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "main_run": str(args.main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "answer_inducer": DEER_ANSWER_INDUCER,
            "answer_inducer_sha256": sha256_bytes(DEER_ANSWER_INDUCER.encode("utf-8")),
            "transition_point": DEER_CONTINUE_STR,
            "max_attempts": self.max_attempts,
            "threshold": self.threshold,
            "trial_cap": self.trial_cap,
            "readout_output_cap": self.readout_cap,
            "policy": self.policy,
            "require_think_close": self.require_think_close,
            "trial_stop_tokens": self.stop_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "deer_source_commit": SOURCE_COMMIT,
            "model_revision": self.model_revision,
            "main_manifest_sha256": common.sha256_file(main_run / "run_manifest.json"),
            "input_trajectory_bank_sha256": common.sha256_path_set(
                traj_files, root=main_run
            ),
            "split_manifest": str(split_manifest),
            "split_manifest_sha256": common.sha256_file(split_manifest),
            "expected_problem_count": common.EXPECTED_PROBLEM_COUNTS[self.dataset],
        }
        self.provenance = method_provenance(
            METHOD,
            reproduction_class=REPRODUCTION_CLASS,
            source_commit=SOURCE_COMMIT,
            source_url=SOURCE_URL,
            prompt_text=DEER_ANSWER_INDUCER,
            trigger_definition=f"first {self.max_attempts} case-insensitive whole-word Wait positions",
            output_cap=self.trial_cap,
            temperature=self.temperature,
            top_p=self.top_p,
            seed_policy="base_seed (deterministic frozen-replay adaptation)",
            extra={"policy": self.policy, "threshold": self.threshold,
                   "max_attempts": self.max_attempts,
                   "require_think_close": self.require_think_close,
                   "readout_output_cap": self.readout_cap},
        )
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "trial_manifest.json"
        if path.exists():
            existing = common.load_json(path)
            if existing.get("trial_settings") != self.settings:
                raise ValueError("existing DEER output has different settings")
            return
        atomic_write_json(path, {
            "schema_version": self.RUN_SCHEMA,
            "trial_settings": self.settings,
            "provenance": self.provenance,
            "protocol_version": self.main_settings.get("protocol_version"),
            "api_key_recorded": False,
            "runtime": common.runtime_versions(),
            "created_at": now_iso(),
        })

    def complete(self, prompt: str, *, max_tokens: int, stop: Optional[List[str]] = None,
                 logprobs: Optional[int] = None, extra_body: Optional[dict] = None):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                # DEER prob_check uses greedy decoding (temperature commented
                # out in vllm-deer.py); the trial answer is greedy + logprobs=1.
                kwargs = dict(model=self.model, prompt=prompt, max_tokens=max_tokens,
                              temperature=self.temperature, top_p=self.top_p,
                              seed=self.base_seed, stream=False)
                if stop:
                    kwargs["stop"] = stop
                if logprobs:
                    kwargs["logprobs"] = logprobs
                if extra_body:
                    kwargs["extra_body"] = extra_body
                response = self.client.completions.create(**kwargs)
                return response, time.perf_counter() - started, attempt
            except Exception as error:
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def _extract_logprobs(self, response) -> List[Tuple[str, float]]:
        """Normalize the vLLM/OpenAI logprobs payload into (decoded, logprob)."""
        choice = response.choices[0]
        lp = getattr(choice, "logprobs", None)
        if not lp:
            return []
        tokens = getattr(lp, "tokens", None)
        token_logprobs = getattr(lp, "token_logprobs", None)
        top_logprobs = getattr(lp, "top_logprobs", None)
        if tokens is not None and token_logprobs is not None:
            out: List[Tuple[str, float]] = []
            for index, (token, chosen_lp) in enumerate(zip(tokens, token_logprobs)):
                top = top_logprobs[index] if top_logprobs and index < len(top_logprobs) else None
                if isinstance(top, dict) and top:
                    top_token, top_lp = next(iter(top.items()))
                    out.append((str(top_token), float(top_lp)))
                elif chosen_lp is not None:
                    out.append((str(token), float(chosen_lp)))
            return out
        out: List[Tuple[str, float]] = []
        for pos in lp:
            # pos is a dict {decoded_token: Logprob} (top entry) for vLLM;
            # OpenAI returns dict of {token_str: Logprob}.
            if isinstance(pos, dict):
                key = next(iter(pos))
                obj = pos[key]
                logprob = getattr(obj, "logprob", None)
                decoded = getattr(obj, "decoded_token", None) or key
                out.append((decoded, float(logprob)))
        return out

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.trial_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            try:
                existing = common.load_json(output_path)
                required = {
                    "schema_version": self.PROBE_SCHEMA,
                    "method": METHOD,
                    "problem_id": problem_id,
                    "dataset": self.dataset,
                    "model": self.model,
                    "base_seed": self.base_seed,
                    "policy": self.policy,
                    "threshold": self.threshold,
                    "require_think_close": self.require_think_close,
                }
                trial_rows = existing.get("trials")
                readout_row = existing.get("readout")
                # A fully recorded readout with finish_reason stop/length, no
                # error, no context overflow/budget -- is a COMPLETE method
                # outcome even when readout_valid is False. Only null finish,
                # request errors, context overflow/budget, corrupt identity,
                # and malformed rows are hard failures.
                def _readout_is_corrupt(ro):
                    if ro is None:
                        return False  # missing readout = valid no-stop/no-exit
                    if not isinstance(ro, dict):
                        return True  # present non-dict = malformed
                    if "error" in ro:
                        return True
                    if ro.get("readout_context_overflow"):
                        return True
                    if ro.get("readout_context_budget_exceeded"):
                        return True
                    fr = ro.get("readout_finish_reason")
                    if fr not in ("stop", "length"):
                        return True  # finish must be exactly stop or length
                    return False
                has_errors = (
                    any("error" in row for row in trial_rows)
                    if isinstance(trial_rows, list) else True
                ) or _readout_is_corrupt(readout_row)
                if all(existing.get(k) == v for k, v in required.items()) and isinstance(
                    trial_rows, list
                ) and not has_errors:
                    return problem_id
                raise ValueError("incomplete or identity-mismatched DEER output")
            except Exception:
                output_path.rename(output_path.with_suffix(".json.corrupt"))
        full_text = trajectory["full_text"]
        candidates = find_candidates(full_text, max_attempts=self.max_attempts)
        encoded = self.tokenizer(
            full_text, add_special_tokens=False, return_offsets_mapping=True
        )
        token_ids = list(encoded["input_ids"])
        offsets = list(encoded["offset_mapping"])
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        chat = common.apply_chat_template(str(trajectory["problem"]).strip(), self.model)
        records: List[dict] = []
        readout: Optional[dict] = None
        for cand in candidates:
            tok_pos = common.token_position_for_char_end(
                offsets, cand["trigger_char_end"]
            )
            prefix = self.tokenizer.decode(token_ids[:tok_pos])
            prompt = chat + prefix + DEER_ANSWER_INDUCER
            try:
                response, latency, retry_count = self.complete(
                    prompt, max_tokens=self.trial_cap,
                    stop=self.stop_tokens, logprobs=1,
                    # include the stop string in the output so the trial boxed
                    # answer (and the Qwen3 皖think/ gate token) are retained in
                    # the text for parsing; stopping semantics and logprobs are
                    # unchanged.
                    extra_body={"include_stop_str_in_output": True}
                )
            except Exception as error:  # record + continue; do not abort the problem
                records.append({
                    "candidate_id": cand["candidate_id"], "trigger_type": cand["trigger_type"],
                    "trigger_char_position": cand["trigger_char_position"], "token_position": tok_pos,
                    "trial_text": "", "trial_answer": "", "logprobs": [], "confidence": 0.0,
                    "policy": self.policy, "last_token_decoded": "", "think_close_emitted": False,
                    "meets_threshold": False, "trial_out_tokens": 0, "trial_prompt_tokens": 0,
                    "trial_latency_seconds": 0.0, "error": str(error),
                    "retry_count": 3,
                })
                continue
            text = str(response.choices[0].text)
            logprobs = self._extract_logprobs(response)
            answer = parse_trial_response(text)
            conf = calculate_confidence(logprobs, policy=self.policy,
                                         require_think_close=self.require_think_close)
            last_decoded = logprobs[-1][0] if logprobs else ""
            meets = conf > self.threshold
            records.append({
                "candidate_id": cand["candidate_id"],
                "trigger_type": cand["trigger_type"],
                "trigger_char_position": cand["trigger_char_position"],
                "token_position": tok_pos,
                "trial_text": text,
                "trial_answer": answer,
                "logprobs": [{"token": t, "logprob": l} for t, l in logprobs],
                "confidence": conf,
                "policy": self.policy,
                "last_token_decoded": last_decoded,
                "think_close_emitted": last_decoded == DEER_THINK_CLOSE,
                "meets_threshold": meets,
                "trial_out_tokens": int(response.usage.completion_tokens),
                "trial_prompt_tokens": int(response.usage.prompt_tokens),
                "trial_finish_reason": common.finish_reason_of(response),
                "trial_latency_seconds": latency,
                "retry_count": retry_count,
            })
            if meets and readout is None:
                readout_prompt = chat + prefix + "\n</think>\n\n"
                try:
                    rresp, rlat, rretry = self.complete(readout_prompt, max_tokens=self.readout_cap)
                    rtext = str(rresp.choices[0].text)
                    rv = common.readout_validity(rtext, common.finish_reason_of(rresp), self.dataset)
                    readout = {
                        "readout_answer": rv["readout_answer"],
                        "readout_text": rtext,
                        "readout_valid": rv["readout_valid"],
                        "readout_truncated": rv["readout_truncated"],
                        "readout_completed_boxed": rv["readout_completed_boxed"],
                        "readout_finish_reason": rv["readout_finish_reason"],
                        "readout_out_tokens": int(rresp.usage.completion_tokens),
                        "readout_prompt_tokens": int(rresp.usage.prompt_tokens),
                        "readout_latency_seconds": rlat,
                        "at_candidate_id": cand["candidate_id"],
                        "retry_count": rretry,
                    }
                except Exception as error:  # readout failed; mark and stop probing
                    readout = {"readout_answer": "", "readout_text": "",
                               "readout_valid": False, "readout_truncated": False,
                               "readout_completed_boxed": False, "readout_finish_reason": None,
                               "readout_out_tokens": 0, "readout_prompt_tokens": 0,
                               "readout_latency_seconds": 0.0,
                               "at_candidate_id": cand["candidate_id"], "error": str(error)}
                    readout["retry_count"] = 3
                break
        payload = {
            "schema_version": self.PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": len(token_ids),
            "token_alignment": alignment,
            "chat_template_sha256": sha256_bytes(chat.encode("utf-8")),
            "policy": self.policy,
            "threshold": self.threshold,
            "require_think_close": self.require_think_close,
            "trials": records,
            "readout": readout,
        }
        atomic_write_json(output_path, payload)
        return problem_id


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DEER frozen-trajectory reproduction collector")
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:18000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--model-revision", required=True,
        help="exact 40-hex Hugging Face commit SHA; pinned into the tokenizer and manifest",
    )
    parser.add_argument("--readout-cap", type=int, default=4096,
                        help="max tokens for the final-answer readout (default 4096)")
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=common.GOVERNOR_V2 / "generated" / "split_manifest.json",
    )
    parser.add_argument("--threshold", type=float, default=DEER_THRESHOLD)
    parser.add_argument("--max-attempts", type=int, default=DEER_MAX_JUDGE_STEPS)
    parser.add_argument("--trial-cap", type=int, default=DEER_TRIAL_CAP)
    parser.add_argument("--policy", default=None, help="avg1 (DeepSeek) or avg2 (Qwen3); auto by model")
    parser.add_argument("--force-policy", action="store_true", help="use --policy overrides instead of model-specific auto")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="collect only the first N trajectories (0=all; smoke use only)",
    )
    parser.add_argument(
        "--problem-id", type=int, action="append", default=[],
        help="collect only selected problem ID(s); repeat for smoke cases",
    )
    parser.add_argument("--flatten-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    if args.flatten_only:
        rows = []
        for path in sorted((args.output / "trials").glob("problem_*.json")):
            payload = common.load_json(path)
            meta = {k: payload[k] for k in ("problem_id", "dataset", "model", "base_seed")}
            for rec in payload["trials"]:
                rows.append({**meta, **{k: rec.get(k) for k in RECORD_FIELDS}})
        from .common import atomic_write_csv
        n = atomic_write_csv(args.output / "trials.csv", rows, RECORD_FIELDS)
        print(f"flattened {n} trials")
        return
    manifest = load_main_manifest(args.main_run)
    collector = DEERCollector(args, manifest)
    paths = list(trajectory_paths(args.main_run))
    if args.problem_id:
        selected = set(args.problem_id)
        paths = [
            path for path in paths
            if int(path.stem.removeprefix("problem_")) in selected
        ]
    if args.limit:
        paths = paths[:args.limit]
    started = time.perf_counter()
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, p) for p in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            pid = future.result()
            print(f"[{index}/{len(paths)}] problem {pid}", flush=True)
    print(f"collected {len(paths)} trajectories")
    completion = common.finalize_collection_manifest(
        args.output / "trial_manifest.json",
        (args.output / "trials").glob("problem_*.json"),
        records_key="trials",
        expected_problem_count=common.EXPECTED_PROBLEM_COUNTS[collector.dataset],
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")


if __name__ == "__main__":
    main()
