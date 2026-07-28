"""Think Just Enough (TJE) frozen-trajectory reproduction.

Reproduces the TJE confidence-driven early-exit rule
(https://aclanthology.org/2026.findings-eacl.263/, Figure 2 + Section 2.2)
on the frozen Governor v2 main trajectories.

Protocol (authoritative extraction from the official PDF):
    * confidence instruction: the verbatim Figure-2 system prompt with all
      ten confidence labels (preserved in ``common.TJE_SYSTEM_PROMPT`` and
      ``common.TJE_CONFIDENCE_LABELS``);
    * structured response: ``\\confidence{X}`` where X is the class name only;
    * triggers: case-insensitive whole-word "Wait" (reflective marker) and
      the closing tag ``</think>``;
    * primary policy for this preregistered evaluation: Wait triggers plus the
      final ``</think>`` confidence check;
    * at a trigger, the confidence query is conditioned on the complete frozen
      reasoning prefix, and the additional prompt injects the token
      ``\\confidence{`` *already included* to force the structured label and
      prevent a new reasoning continuation inside the confidence response;
    * threshold: "Almost certain";
    * below threshold at ``</think>``: replace the tag with the continuation
      cue "Wait" (online); at threshold: insert ``</think>`` and proceed to the
      final answer, recording that extra readout output cost;
    * decoding (Section 3.1.4): temperature 0.6, top_p 0.95, top_k 20.

Frozen-trajectory adaptation (labeled, not concealed):
    TJE normally supplies its confidence instruction as part of the live
    generation and can alter the online trajectory. Here the main trajectory is
    *frozen* (it was generated without the TJE instruction), so the confidence
    query is re-issued on the frozen prefix at each independently recomputed
    trigger. This is a **frozen-trajectory TJE reproduction**, not an
    end-to-end faithful run. The two analysis variants are kept explicitly
    separable: ``include_think_close=True`` (preregistered primary) vs
    ``include_think_close=False`` (optional Wait-only diagnostic).
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

from . import common
from .common import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DEFAULT_TOP_K,
    TJE_CONFIDENCE_FORCE_PREFIX,
    TJE_CONFIDENCE_LABELS,
    TJE_SYSTEM_PROMPT,
    TJE_TEMPERATURE,
    TJE_THRESHOLD_LABEL,
    TJE_TOP_K,
    TJE_TOP_P,
    TJE_WAIT_TRIGGER,
    atomic_write_json,
    env_metadata,
    find_think_close_positions,
    find_wait_positions,
    load_main_manifest,
    load_tokenizer,
    make_openai_client,
    method_provenance,
    now_iso,
    sha256_bytes,
    trajectory_paths,
)

METHOD = "tje_frozen"
REPRODUCTION_CLASS = "frozen-trajectory TJE reproduction (confidence re-issued on frozen prefix)"
SOURCE_COMMIT = "aclanthology:2026.findings-eacl.263"
SOURCE_URL = "https://aclanthology.org/2026.findings-eacl.263/"
PROBE_SCHEMA = "related-work-tje-trigger-1"
RUN_SCHEMA = "related-work-tje-run-1"
TRIGGER_FIELDS = (
    "trigger_id",
    "trigger_type",
    "trigger_char_position",
    "token_position",
    "confidence_response",
    "confidence_label",
    "meets_threshold",
    "confidence_out_tokens",
    "confidence_prompt_tokens",
    "confidence_latency_seconds",
)

# Regex for the forced confidence completion. The injected prefix already
# contains "\confidence{", so the model typically completes "Almost certain}";
# we also accept a self-contained "\confidence{...}" in case the model emits
# the full token. Captures the class name only (no probability range).
_CONFIDENCE_RE = re.compile(r"\\confidence\s*\{([^{}]*)\}")

# The ten official class names, used as the vLLM ``structured_outputs.choice``
# constraint so the confidence completion is always exactly one label (never a
# length-truncated unconstrained completion / null). Verified against the
# installed vLLM 0.26.0 ``StructuredOutputsParams.choice`` field.
TJE_LABEL_NAMES: List[str] = [n for n, _l, _h in TJE_CONFIDENCE_LABELS]



# --------------------------------------------------------------------------- #
# Pure logic (no heavy deps)
# --------------------------------------------------------------------------- #
def label_index(label: Optional[str]) -> int:
    """Ordinal of a confidence label (0=lowest). -1 if unknown/none."""
    if not label:
        return -1
    label = label.strip()
    for i, (name, _lo, _hi) in enumerate(TJE_CONFIDENCE_LABELS):
        if label.lower() == name.lower():
            return i
    # tolerate a trailing quote/period from the model
    cleaned = re.sub(r"[\"'.]", "", label).strip()
    for i, (name, _lo, _hi) in enumerate(TJE_CONFIDENCE_LABELS):
        if cleaned.lower() == name.lower():
            return i
    return -1


def parse_confidence_response(text: str) -> Optional[str]:
    """Extract the confidence class name from a forced confidence response.

    The collector injects ``\\confidence{`` so the model only completes the
    label; this parser also accepts a full ``\\confidence{X}``. Returns the
    official class name (canonicalized) or ``None`` if unparseable.
    """
    if not text:
        return None
    m = _CONFIDENCE_RE.search(text)
    candidate = m.group(1).strip() if m else text.strip()
    # the forced-prefix case: completion is e.g. "Almost certain}" -> strip braces
    candidate = candidate.strip().rstrip("}").strip().strip('"').strip("'").strip()
    # match against official labels, allowing a trailing range like "(0.9-1.0)"
    candidate_no_range = re.sub(r"\s*\([^()]*\)\s*$", "", candidate).strip()
    for name, _lo, _hi in TJE_CONFIDENCE_LABELS:
        if candidate_no_range.lower() == name.lower():
            return name
    # fuzzy: label appears as a prefix of the candidate
    for name, _lo, _hi in TJE_CONFIDENCE_LABELS:
        if name.lower() in candidate_no_range.lower():
            return name
    return None


def label_meets_threshold(label: Optional[str], threshold_label: str = TJE_THRESHOLD_LABEL) -> bool:
    """True iff ``label`` is at or above the threshold's confidence level."""
    return label_index(label) >= label_index(threshold_label)


def find_triggers(text: str, *, include_think_close: bool = True) -> List[dict]:
    """Ordered trigger records by character offset.

    ``include_think_close=True`` (default) is the preregistered primary;
    ``False`` is the optional Wait-only diagnostic.

    Each record carries ``trigger_type`` ("wait"/"think_close") and the
    character offset; the collector later maps offsets to token positions via
    the tokenizer's offset mapping.
    """
    triggers: List[dict] = []
    for off in find_wait_positions(text):
        triggers.append({
            "trigger_type": "wait",
            "trigger_char_position": off,
            "trigger_char_end": off + len(TJE_WAIT_TRIGGER),
        })
    if include_think_close:
        for off in find_think_close_positions(text):
            triggers.append({
                "trigger_type": "think_close",
                "trigger_char_position": off,
                # TJE pauses before the closing tag, queries confidence, then
                # either inserts </think> or replaces it with Wait.
                "trigger_char_end": off,
            })
    triggers.sort(key=lambda r: (r["trigger_char_position"], r["trigger_type"]))
    for i, t in enumerate(triggers, start=1):
        t["trigger_id"] = i
    return triggers


def build_system_chat(tokenizer: Any, problem: str, *, system: str = TJE_SYSTEM_PROMPT) -> str:
    """Serialize TJE's instruction as an actual system-role message.

    DeepSeek's tokenizer template emits both a textual BOS marker (which the
    vLLM completion server adds itself) and a forced ``<think>`` prefix (which
    is already present in every frozen trajectory). Remove only those two
    duplicated boundaries; preserve the tokenizer's model-specific role
    formatting exactly.
    """
    rendered = str(tokenizer.apply_chat_template(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": problem},
        ],
        tokenize=False,
        add_generation_prompt=True,
    ))
    bos = str(getattr(tokenizer, "bos_token", "") or "")
    if bos and rendered.startswith(bos):
        rendered = rendered[len(bos):]
    if rendered.endswith("<think>\n"):
        rendered = rendered[:-len("<think>\n")]
    return rendered


def build_confidence_prompt(chat: str, prefix: str, *, system: str = "",
                            force_prefix: str = TJE_CONFIDENCE_FORCE_PREFIX) -> str:
    """Confidence query = system-aware chat + frozen prefix + forced token.

    The ``\\confidence{`` token is injected *already included* so the model can
    only complete the label and cannot start a new reasoning continuation
    (Section 2.2). The frozen reasoning prefix is the complete prefix up to the
    trigger; the confidence instruction is re-supplied because the frozen main
    trajectory was generated without it.
    """
    system_suffix = f"{system}\n\n" if system else ""
    return f"{chat}{system_suffix}{prefix} {force_prefix}"


def build_readout_prompt(confidence_prompt: str, label: str = "") -> str:
    """Final-answer readout prompt (TJE Figure 1 / Section 2.2).

    Reconstruct the EXACT confidence-query context that is already in the
    loop (build_confidence_prompt(chat, prefix) = system chat + prefix +
    the exact space + the forced \confidence{ prefix), close the parsed
    confidence label, then insert the think-close tag and the final-response
    boundary. This preserves the system chat, the exact space/forced prefix,
    and the actual parsed choice -- no lossy reconstruction, no plain_chat,
    no answer-inducing instruction::

        ... Wait, \confidence{<label>}
         <think-close>
        Final Answer: \boxed{...}
    """
    return confidence_prompt + (label or "") + "}" + "\n" + common.DEER_THINK_CLOSE + "\n\n"


def decide_stop(
    trigger_records: Sequence[Mapping[str, Any]],
    *,
    threshold_label: str = TJE_THRESHOLD_LABEL,
) -> Optional[dict]:
    """First trigger whose confidence meets the threshold; else None."""
    for t in trigger_records:
        if t.get("meets_threshold"):
            return {
                "stop_trigger_id": t["trigger_id"],
                "stop_position": int(t.get("token_position", 0)),
                "stop_trigger_type": t["trigger_type"],
                "confidence_label": t.get("confidence_label"),
            }
    return None


def replay(
    trajectory: Mapping[str, Any],
    trigger_records: Sequence[Mapping[str, Any]],
    *,
    threshold_label: str = TJE_THRESHOLD_LABEL,
    readout: Optional[Mapping[str, Any]] = None,
    answers_equal_target_fn: Optional[Callable[[Any, Any], bool]] = None,
    split: Optional[str] = None,
    include_think_close: bool = True,
) -> dict:
    """Compute delivered answer + two-view token accounting for one trajectory."""
    full_tokens = int(trajectory.get("tokens_used", 0))
    finished_naturally = bool(trajectory.get("finished_naturally", False))
    budget = int(trajectory.get("run_settings", {}).get("budget", full_tokens or 2**31))
    full_answer = trajectory.get("final_answer", "")
    full_correct = bool(trajectory.get("final_correct", False))

    decision = decide_stop(trigger_records, threshold_label=threshold_label)
    confidence_out = sum(int(t.get("confidence_out_tokens", 0)) for t in trigger_records)
    confidence_prompt = sum(int(t.get("confidence_prompt_tokens", 0)) for t in trigger_records)
    readout_out = int(readout.get("readout_out_tokens", 0)) if readout else 0
    readout_prompt = int(readout.get("readout_prompt_tokens", 0)) if readout else 0
    readout_calls = 1 if readout is not None else 0
    invalid_aux = sum(
        1 for t in trigger_records
        if "error" in t or t.get("confidence_label") is None
    )
    if readout is not None and ("error" in readout or readout.get("readout_valid") is False):
        invalid_aux += 1
    auxiliary_wall = sum(
        float(t.get("confidence_latency_seconds", 0.0)) for t in trigger_records
    ) + (float(readout.get("readout_latency_seconds", 0.0)) if readout else 0.0)

    if decision is not None:
        stopped = True
        main_through_stop = decision["stop_position"]
        capped = False
        delivered = (readout or {}).get("readout_answer", "") or ""
        recovery_truncated = True
        overthinking_avoided = max(0, full_tokens - main_through_stop)
    else:
        stopped = False
        main_through_stop = full_tokens
        capped = not finished_naturally or full_tokens > budget
        # No early stop: deliver the legitimate frozen natural answer (if any).
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
        "threshold_label": threshold_label,
        "include_think_close": include_think_close,
        "stopped": stopped,
        "capped": capped,
        "recovery_truncated": recovery_truncated,
        "overthinking_avoided_tokens": overthinking_avoided,
        "delivered_answer": delivered,
        "correct": correct,
        "baseline_correct": full_correct,
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_through_stop,
        "confidence_out_tokens": confidence_out,
        "confidence_prompt_tokens": confidence_prompt,
        "readout_out_tokens": readout_out,
        "readout_prompt_tokens": readout_prompt,
        "probe_out_tokens": confidence_out + readout_out,
        "probe_prompt_tokens": confidence_prompt + readout_prompt,
        "all_generated_tokens": main_through_stop + confidence_out + readout_out,
        "baseline_all_generated_tokens": full_tokens,
        "n_triggers": len(trigger_records),
        "n_aux_calls": len(trigger_records) + readout_calls,
        "n_readout_calls": readout_calls,
        "invalid_aux_responses": invalid_aux,
        "auxiliary_wall_seconds": auxiliary_wall,
        "stop_position": decision["stop_position"] if decision else None,
        "stop_trigger_id": decision["stop_trigger_id"] if decision else None,
    }


# --------------------------------------------------------------------------- #
# Live collector (needs an endpoint; never runs in CPU-only validation)
# --------------------------------------------------------------------------- #
class TJECollector:
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
        self.temperature = TJE_TEMPERATURE
        self.top_p = TJE_TOP_P
        self.top_k = TJE_TOP_K
        self.readout_cap = int(args.readout_cap)
        self.max_model_len = int(args.max_model_len)
        self.include_think_close = bool(args.include_think_close)
        self.threshold_label = args.threshold_label
        self.client = make_openai_client(args.url, args.api_key, timeout=600)
        self.tokenizer = load_tokenizer(self.model, self.model_revision)
        self.output = Path(args.output)
        self.trigger_dir = self.output / "triggers"
        self.trigger_dir.mkdir(parents=True, exist_ok=True)
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
            "system_prompt_sha256": sha256_bytes(TJE_SYSTEM_PROMPT.encode("utf-8")),
            "force_prefix": TJE_CONFIDENCE_FORCE_PREFIX,
            "threshold_label": self.threshold_label,
            "include_think_close": self.include_think_close,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "confidence_output_cap": 20,
            "confidence_choice_constraint": TJE_LABEL_NAMES,
            "readout_output_cap": self.readout_cap,
            "max_model_len": self.max_model_len,
            "trigger_policy": "wait_only" if not self.include_think_close else "wait_and_think_close",
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
            prompt_text=TJE_SYSTEM_PROMPT,
            trigger_definition=("case-insensitive whole-word Wait"
                                + ("" if not self.include_think_close else " + </think> closing tag")),
            output_cap=None,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            seed_policy="base_seed (prompt-matched to main run)",
            extra={"threshold_label": self.threshold_label,
                   "include_think_close": self.include_think_close,
                   "ten_labels": [n for n, _l, _h in TJE_CONFIDENCE_LABELS],
                   "confidence_choice_constraint": TJE_LABEL_NAMES,
                   "confidence_output_cap": 20,
                   "readout_output_cap": self.readout_cap,
                   "max_model_len": self.max_model_len},
        )
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "trigger_manifest.json"
        if path.exists():
            existing = common.load_json(path)
            if existing.get("trigger_settings") != self.settings:
                raise ValueError("existing TJE output has different settings")
            return
        atomic_write_json(path, {
            "schema_version": self.RUN_SCHEMA,
            "trigger_settings": self.settings,
            "provenance": self.provenance,
            "protocol_version": self.main_settings.get("protocol_version"),
            "api_key_recorded": False,
            "runtime": common.runtime_versions(),
            "created_at": now_iso(),
        })

    def complete(self, prompt: str, *, max_tokens: int, stop: Optional[List[str]] = None,
                 extra_body: Optional[dict] = None):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                kwargs = dict(model=self.model, prompt=prompt, max_tokens=max_tokens,
                              temperature=self.temperature, top_p=self.top_p,
                              seed=self.base_seed, stream=False)
                if stop:
                    kwargs["stop"] = stop
                if extra_body:
                    kwargs["extra_body"] = extra_body
                response = self.client.completions.create(**kwargs)
                return response, time.perf_counter() - started, attempt
            except Exception as error:
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.trigger_dir / f"problem_{problem_id}.json"
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
                    "include_think_close": self.include_think_close,
                    "threshold_label": self.threshold_label,
                }
                trigger_rows = existing.get("triggers")
                readout_row = existing.get("readout")
                # A fully recorded readout with finish_reason stop/length, no
                # error, no context overflow/budget -- is a COMPLETE method
                # outcome even when readout_valid is False (capped/natural
                # invalid). Only null finish, request errors, context overflow/
                # budget, corrupt identity, and malformed rows are hard failures.
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
                    any("error" in row for row in trigger_rows)
                    if isinstance(trigger_rows, list) else True
                ) or _readout_is_corrupt(readout_row)
                if all(existing.get(k) == v for k, v in required.items()) and isinstance(
                    trigger_rows, list
                ) and not has_errors:
                    return problem_id
                raise ValueError("incomplete or identity-mismatched TJE output")
            except Exception:
                output_path.rename(output_path.with_suffix(".json.corrupt"))
        full_text = trajectory["full_text"]
        triggers = find_triggers(full_text, include_think_close=self.include_think_close)
        encoded = self.tokenizer(
            full_text, add_special_tokens=False, return_offsets_mapping=True
        )
        token_ids = list(encoded["input_ids"])
        offsets = list(encoded["offset_mapping"])
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        chat = build_system_chat(
            self.tokenizer, str(trajectory["problem"]).strip()
        )
        # The system-role chat (with the TJE instruction) is used for BOTH the
        # confidence checks and the final-answer readout (per Figure 1: the
        # final-response context retains the system prompt and the triggering
        # confidence event before the think-close tag).
        records: List[dict] = []
        readout: Optional[dict] = None
        for trig in triggers:
            tok_pos = common.token_position_for_char_end(
                offsets, trig["trigger_char_end"]
            )
            prefix = self.tokenizer.decode(token_ids[:tok_pos])
            prompt = build_confidence_prompt(chat, prefix)
            try:
                response, latency, retry_count = self.complete(
                    prompt, max_tokens=20, stop=["}"],
                    extra_body={"top_k": self.top_k,
                                "structured_outputs": {"choice": TJE_LABEL_NAMES}}
                )
            except Exception as error:  # record + continue
                records.append({
                    "trigger_id": trig["trigger_id"], "trigger_type": trig["trigger_type"],
                    "trigger_char_position": trig["trigger_char_position"], "token_position": tok_pos,
                    "confidence_response": "", "confidence_label": None, "meets_threshold": False,
                    "confidence_out_tokens": 0, "confidence_prompt_tokens": 0,
                    "confidence_latency_seconds": 0.0, "error": str(error),
                    "retry_count": 3,
                })
                continue
            text = str(response.choices[0].text)
            label = parse_confidence_response(text)
            meets = label_meets_threshold(label, self.threshold_label)
            rec = {
                "trigger_id": trig["trigger_id"],
                "trigger_type": trig["trigger_type"],
                "trigger_char_position": trig["trigger_char_position"],
                "token_position": tok_pos,
                "confidence_response": text,
                "confidence_label": label,
                "meets_threshold": meets,
                "confidence_out_tokens": int(response.usage.completion_tokens),
                "confidence_prompt_tokens": int(response.usage.prompt_tokens),
                "confidence_finish_reason": common.finish_reason_of(response),
                "confidence_latency_seconds": latency,
                "retry_count": retry_count,
            }
            records.append(rec)
            if meets and readout is None:
                # Reconstruct the triggering confidence event (Figure 1: the
                # actual \confidence{<label>} that terminated reasoning) and
                # include it in the readout prompt before the think-close tag.
                triggering_label = label or ""
                # Reconstruct the EXACT confidence-query context already in the
                # loop (Figure 1): confidence_prompt + label + "}" closes the
                # parsed confidence event, then the think-close tag and final
                # response boundary. Preserves system chat, exact space/forced
                # prefix, and the actual parsed choice -- no lossy reconstruction.
                readout_prompt = build_readout_prompt(prompt, triggering_label)
                readout_prompt_sha = sha256_bytes(readout_prompt.encode("utf-8"))
                # Context-safe allowance: compute the ACTUAL readout-prompt token
                # length with the pinned tokenizer (same add_special_tokens=False
                # semantics used throughout the frozen-trajectory convention), then
                # bound generation so prompt+generation never exceeds max_model_len.
                # If the remaining allowance is below the justified minimum, record
                # a context-budget error and never issue an over-context request.
                est_prompt_tok = len(self.tokenizer.encode(
                    readout_prompt, add_special_tokens=False))
                al = common.compute_readout_allowance(
                    est_prompt_tok, readout_cap=self.readout_cap,
                    max_model_len=self.max_model_len)
                allowance = al["allowance"]
                if al["context_budget_exceeded"]:
                    readout = {"readout_answer": "", "readout_text": "",
                               "readout_valid": False, "readout_truncated": False,
                               "readout_completed_boxed": False, "readout_finish_reason": None,
                               "readout_out_tokens": 0, "readout_prompt_tokens": 0,
                               "readout_allowance": 0,
                               "readout_prompt_tokens_estimate": est_prompt_tok,
                               "readout_context_budget_exceeded": True,
                               "readout_remaining": al["remaining"],
                               "readout_latency_seconds": 0.0,
                               "at_trigger_id": trig["trigger_id"],
                               "error": (f"context budget exceeded: est_prompt_tokens={est_prompt_tok}, "
                                          f"max_model_len={self.max_model_len}, remaining={al['remaining']}")}
                    readout["retry_count"] = 0
                    break  # threshold met but no readout fits; stop probing
                try:
                    rresp, rlat, rretry = self.complete(
                        readout_prompt, max_tokens=allowance,
                        extra_body={"top_k": self.top_k},
                    )
                    rtext = str(rresp.choices[0].text)
                    actual_prompt_tok = int(rresp.usage.prompt_tokens)
                    overflow = (actual_prompt_tok + allowance) > self.max_model_len
                    rv = common.readout_validity(rtext, common.finish_reason_of(rresp), self.dataset)
                    # An actual context overflow invalidates the readout (hard failure),
                    # not merely a recorded flag: the request exceeded server context.
                    if overflow:
                        rv["readout_valid"] = False
                        rv["readout_answer"] = ""
                    rv["readout_allowance"] = allowance
                    rv["readout_prompt_tokens_estimate"] = est_prompt_tok
                    rv["readout_prompt_tokens_actual"] = actual_prompt_tok
                    rv["readout_context_overflow"] = overflow
                    readout = {
                        "readout_answer": rv["readout_answer"],
                        "readout_text": rtext,
                        "readout_valid": rv["readout_valid"],
                        "readout_truncated": rv["readout_truncated"],
                        "readout_completed_boxed": rv["readout_completed_boxed"],
                        "readout_finish_reason": rv["readout_finish_reason"],
                        "readout_out_tokens": int(rresp.usage.completion_tokens),
                        "readout_prompt_tokens": actual_prompt_tok,
                        "readout_allowance": allowance,
                        "readout_prompt_tokens_estimate": est_prompt_tok,
                        "readout_context_overflow": overflow,
                        "readout_triggering_label": triggering_label,
                        "readout_confidence_event": "\\confidence{" + triggering_label + "}",
                        "readout_prompt_sha256": readout_prompt_sha,
                        "readout_latency_seconds": rlat,
                        "at_trigger_id": trig["trigger_id"],
                        "retry_count": rretry,
                    }
                except Exception as error:  # readout failed; mark and keep probing
                    readout = {"readout_answer": "", "readout_text": "",
                               "readout_valid": False, "readout_truncated": False,
                               "readout_completed_boxed": False, "readout_finish_reason": None,
                               "readout_out_tokens": 0, "readout_prompt_tokens": 0,
                               "readout_allowance": allowance,
                               "readout_prompt_tokens_estimate": est_prompt_tok,
                               "readout_latency_seconds": 0.0,
                               "at_trigger_id": trig["trigger_id"], "error": str(error)}
                    readout["retry_count"] = 3
                break  # threshold met: no further triggers probed
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
            "include_think_close": self.include_think_close,
            "threshold_label": self.threshold_label,
            "triggers": records,
            "readout": readout,
        }
        atomic_write_json(output_path, payload)
        return problem_id


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TJE frozen-trajectory reproduction collector")
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:18000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--model-revision", required=True,
        help="exact 40-hex Hugging Face commit SHA; pinned into the tokenizer and manifest",
    )
    parser.add_argument("--readout-cap", type=int, default=8192,
                        help="max tokens for the final-answer readout (default 8192; the readout is valid only if a \\boxed{...} is completed before truncation)")
    parser.add_argument("--max-model-len", type=int, default=34816,
                        help="server max-model-len; the readout allowance is bounded so prompt+generation never exceeds it")
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=common.GOVERNOR_V2 / "generated" / "split_manifest.json",
    )
    parser.set_defaults(include_think_close=True)
    parser.add_argument("--include-think-close", dest="include_think_close", action="store_true",
                        help="include the final </think> check (default; preregistered primary)")
    parser.add_argument("--wait-only", dest="include_think_close", action="store_false",
                        help="optional diagnostic that omits final </think> confidence checks")
    parser.add_argument("--threshold-label", default=TJE_THRESHOLD_LABEL)
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
        for path in sorted((args.output / "triggers").glob("problem_*.json")):
            payload = common.load_json(path)
            meta = {k: payload[k] for k in ("problem_id", "dataset", "model", "base_seed")}
            for rec in payload["triggers"]:
                rows.append({**meta, **rec})
        from .common import atomic_write_csv
        n = atomic_write_csv(args.output / "triggers.csv", rows, TRIGGER_FIELDS)
        print(f"flattened {n} triggers")
        return
    manifest = load_main_manifest(args.main_run)
    collector = TJECollector(args, manifest)
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
        args.output / "trigger_manifest.json",
        (args.output / "triggers").glob("problem_*.json"),
        records_key="triggers",
        expected_problem_count=common.EXPECTED_PROBLEM_COUNTS[collector.dataset],
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")


if __name__ == "__main__":
    main()
