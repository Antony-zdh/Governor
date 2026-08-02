"""Collect a threshold-agnostic DEER confidence bank over frozen trajectories.

This module deliberately does *not* modify the faithful ``deer.py`` baseline.
It reuses compatible trials from that baseline, probes every missing whole-word
``Wait`` position up to ``max_attempts`` (30 by default), never performs a
formal readout, and never exits early.  The resulting bank supports an offline
direct-commit threshold frontier:

    first valid trial with confidence > threshold -> submit trial_answer

The collector is GPU-backed, while all threshold selection and grading remain
CPU-only downstream work.
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from . import common, deer
from .common import (
    DEER_ANSWER_INDUCER,
    atomic_write_json,
    load_main_manifest,
    method_provenance,
    now_iso,
    sha256_bytes,
    trajectory_paths,
)


METHOD = "deer_confidence_bank_cap30"
REPRODUCTION_CLASS = (
    "threshold-agnostic frozen-trajectory DEER confidence bank "
    "(direct-submit analysis; no readout)"
)
PROBE_SCHEMA = "related-work-deer-confidence-bank-problem-1"
RUN_SCHEMA = "related-work-deer-confidence-bank-run-1"
DEFAULT_MAX_ATTEMPTS = 30

RECORD_FIELDS = (
    "candidate_id",
    "trigger_type",
    "trigger_char_position",
    "token_position",
    "trial_text",
    "trial_answer",
    "logprobs",
    "confidence",
    "policy",
    "last_token_decoded",
    "think_close_emitted",
    "trial_out_tokens",
    "trial_prompt_tokens",
    "trial_finish_reason",
    "trial_latency_seconds",
    "retry_count",
    "record_source",
)


def _identity(payload: Mapping[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(payload.get("model", "")),
        str(payload.get("dataset", "")),
        int(payload.get("base_seed", -1)),
        int(payload.get("problem_id", -1)),
    )


# GPT2/Llama BPE bytes_to_unicode map and its inverse. When a frozen trajectory
# stores ``full_text`` as the concatenation of token *pieces* (with ``Ġ``/``Ċ``
# metacharacters) instead of the byte-decoded text, ``\bWait\b`` finds no word
# boundary (``Ġ`` is U+0120, a letter) and the re-encoded token count diverges.
# Applying the inverse map recovers the true decoded text -- exactly what the
# tokenizer's own ``decode`` produces -- and is a strict no-op (byte-identical)
# on already-decoded text that contains no metacharacters.
def _bytes_to_unicode() -> dict[int, str]:
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("¡"), ord("¬") + 1))
        + list(range(ord("®"), ord("ÿ") + 1))
    )
    cs = bs[:]
    n = 0
    for b in range(2 ** 8):
        if b not in bs:
            bs.append(b)
            cs.append(2 ** 8 + n)
            n += 1
    return dict(zip(bs, [chr(c) for c in cs]))


_BPE_CHAR_TO_BYTE = {v: k for k, v in _bytes_to_unicode().items()}


def recover_bpe_decoded_text(text: str) -> str:
    """Recover the true decoded text from a BPE-piece ``full_text``.

    Inverts the GPT2/Llama ``bytes_to_unicode`` mapping; characters not in the
    map (normal ASCII, real Unicode math symbols) are passed through verbatim as
    UTF-8. A no-op on already-decoded text.

    The inverse map collides with Latin-1 supplement characters that appear
    legitimately in decoded math text (e.g. ``×`` U+00D7, ``²`` U+00B2), so
    recovery is gated on the presence of the BPE space marker ``Ġ`` (U+0120),
    which never occurs in decoded reasoning text. Already-decoded trajectories
    (no ``Ġ``) are returned byte-identical; only BPE-piece trajectories are
    recovered.
    """
    if "Ġ" not in text:
        return text
    out = bytearray()
    for ch in text:
        byte = _BPE_CHAR_TO_BYTE.get(ch)
        if byte is not None:
            out.append(byte)
        else:
            out.extend(ch.encode("utf-8"))
    return out.decode("utf-8", errors="replace")



def reusable_trial(
    row: Mapping[str, Any],
    *,
    candidate_id: int,
    token_position: int,
    policy: str,
) -> bool:
    """Return whether an old DEER trial can be copied into this bank."""
    if "error" in row:
        return False
    if int(row.get("candidate_id", -1)) != candidate_id:
        return False
    if int(row.get("token_position", -1)) != token_position:
        return False
    if str(row.get("policy", "")) != policy:
        return False
    if not isinstance(row.get("logprobs"), list) or not row["logprobs"]:
        return False
    try:
        float(row.get("confidence"))
    except (TypeError, ValueError):
        return False
    return True


def copied_trial(row: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the durable trial fields and label their provenance."""
    copied = {field: row.get(field) for field in RECORD_FIELDS if field != "record_source"}
    copied["record_source"] = "reused_faithful_deer_0p95"
    return copied


def direct_submit_decision(
    trials: Sequence[Mapping[str, Any]],
    *,
    threshold: float,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Optional[dict[str, Any]]:
    """First valid direct-submit trial strictly above ``threshold``."""
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must lie in [0, 1]")
    for row in trials:
        candidate_id = int(row.get("candidate_id", -1))
        if candidate_id > max_attempts:
            break
        answer = str(row.get("trial_answer", "")).strip()
        if answer and float(row.get("confidence", 0.0)) > threshold:
            return {
                "candidate_id": candidate_id,
                "token_position": int(row.get("token_position", 0)),
                "confidence": float(row["confidence"]),
                "trial_answer": answer,
            }
    return None


class DEERConfidenceBankCollector(deer.DEERCollector):
    """DEER trial collector that exhausts the configured Wait budget."""

    def __init__(self, args: argparse.Namespace, main_manifest: Mapping[str, Any]):
        self.reuse_dir = Path(args.reuse_dir) if args.reuse_dir else None
        # The parent initializes the pinned tokenizer/client/model mechanics.
        # A threshold above the probability range is a defense-in-depth guard;
        # this subclass never consults it and never calls a readout.
        args.threshold = 2.0
        args.max_attempts = int(args.max_attempts)
        args.readout_cap = 0
        super().__init__(args, main_manifest)

    @property
    def manifest_path(self) -> Path:
        return self.output / "bank_manifest.json"

    def _initialize_manifest(self) -> None:
        main_run = Path(self.settings["main_run"])
        input_paths = trajectory_paths(main_run)
        reuse_manifest = (
            self.reuse_dir / "trial_manifest.json"
            if self.reuse_dir is not None
            else None
        )
        reuse_manifest_sha = (
            common.sha256_file(reuse_manifest)
            if reuse_manifest is not None and reuse_manifest.exists()
            else None
        )
        self.settings = {
            "collection_schema": PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "main_run": str(main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "answer_inducer": DEER_ANSWER_INDUCER,
            "answer_inducer_sha256": sha256_bytes(
                DEER_ANSWER_INDUCER.encode("utf-8")
            ),
            "transition_point": common.DEER_CONTINUE_STR,
            "max_attempts": self.max_attempts,
            "trial_cap": self.trial_cap,
            "policy": self.policy,
            "require_think_close": self.require_think_close,
            "trial_stop_tokens": self.stop_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "confidence_threshold": None,
            "early_exit": False,
            "formal_readout": False,
            "direct_submit_analysis": True,
            "validity_gate": "non-empty parsed trial_answer",
            "deer_source_commit": deer.SOURCE_COMMIT,
            "model_revision": self.model_revision,
            "main_manifest_sha256": common.sha256_file(
                main_run / "run_manifest.json"
            ),
            "input_trajectory_bank_sha256": common.sha256_path_set(
                input_paths, root=main_run
            ),
            "split_manifest": str(self.args.split_manifest),
            "split_manifest_sha256": common.sha256_file(
                Path(self.args.split_manifest)
            ),
            "expected_problem_count": len(input_paths),
            "reuse_dir": str(self.reuse_dir) if self.reuse_dir else None,
            "reuse_manifest_sha256": reuse_manifest_sha,
        }
        self.provenance = method_provenance(
            METHOD,
            reproduction_class=REPRODUCTION_CLASS,
            source_commit=deer.SOURCE_COMMIT,
            source_url=deer.SOURCE_URL,
            prompt_text=DEER_ANSWER_INDUCER,
            trigger_definition=(
                f"first {self.max_attempts} case-insensitive whole-word Wait "
                "positions; exhaust bank regardless of confidence"
            ),
            output_cap=self.trial_cap,
            temperature=self.temperature,
            top_p=self.top_p,
            seed_policy="base_seed (deterministic frozen-prefix DEER trials)",
            extra={
                "policy": self.policy,
                "require_think_close": self.require_think_close,
                "confidence_threshold": None,
                "early_exit": False,
                "formal_readout": False,
                "direct_submit_analysis": True,
                "reuse_manifest_sha256": reuse_manifest_sha,
            },
        )
        if self.manifest_path.exists():
            existing = common.load_json(self.manifest_path)
            if existing.get("bank_settings") != self.settings:
                raise ValueError("existing confidence-bank output has different settings")
            return
        atomic_write_json(
            self.manifest_path,
            {
                "schema_version": RUN_SCHEMA,
                "bank_settings": self.settings,
                "provenance": self.provenance,
                "protocol_version": self.main_settings.get("protocol_version"),
                "api_key_recorded": False,
                "runtime": common.runtime_versions(),
                "created_at": now_iso(),
            },
        )

    def _load_reuse(self, problem_id: int, expected_identity: tuple) -> dict[int, dict]:
        if self.reuse_dir is None:
            return {}
        path = self.reuse_dir / "trials" / f"problem_{problem_id}.json"
        if not path.exists():
            return {}
        payload = common.load_json(path)
        if _identity(payload) != expected_identity:
            raise ValueError(f"reuse identity mismatch: {path}")
        if str(payload.get("policy")) != self.policy:
            raise ValueError(f"reuse policy mismatch: {path}")
        if bool(payload.get("require_think_close")) != self.require_think_close:
            raise ValueError(f"reuse think-close policy mismatch: {path}")
        return {
            int(row["candidate_id"]): row
            for row in payload.get("trials", [])
            if isinstance(row, dict) and "candidate_id" in row
        }

    def _completed_payload_is_valid(
        self,
        payload: Mapping[str, Any],
        *,
        expected_identity: tuple,
        expected_candidates: int,
    ) -> bool:
        rows = payload.get("trials")
        if (
            payload.get("schema_version") != PROBE_SCHEMA
            or payload.get("method") != METHOD
            or _identity(payload) != expected_identity
            or payload.get("policy") != self.policy
            or bool(payload.get("require_think_close")) != self.require_think_close
            or int(payload.get("max_attempts", -1)) != self.max_attempts
            or not isinstance(rows, list)
            or len(rows) != expected_candidates
            or any("error" in row for row in rows)
        ):
            return False
        return [int(row.get("candidate_id", -1)) for row in rows] == list(
            range(1, expected_candidates + 1)
        )

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        expected_identity = (
            self.model,
            self.dataset,
            self.base_seed,
            problem_id,
        )
        full_text = recover_bpe_decoded_text(str(trajectory["full_text"]))
        candidates = deer.find_candidates(
            full_text, max_attempts=self.max_attempts
        )
        output_path = self.trial_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            try:
                existing = common.load_json(output_path)
                if self._completed_payload_is_valid(
                    existing,
                    expected_identity=expected_identity,
                    expected_candidates=len(candidates),
                ):
                    return problem_id
                raise ValueError("incomplete or identity-mismatched bank output")
            except Exception:
                corrupt = output_path.with_suffix(".json.corrupt")
                if corrupt.exists():
                    corrupt = output_path.with_suffix(
                        f".json.corrupt.{int(time.time())}"
                    )
                output_path.rename(corrupt)

        encoded = self.tokenizer(
            full_text, add_special_tokens=False, return_offsets_mapping=True
        )
        token_ids = list(encoded["input_ids"])
        offsets = list(encoded["offset_mapping"])
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        chat = common.apply_chat_template(
            str(trajectory["problem"]).strip(), self.model
        )
        reuse = self._load_reuse(problem_id, expected_identity)
        records: list[dict[str, Any]] = []
        reused_count = 0
        generated_count = 0

        for candidate in candidates:
            candidate_id = int(candidate["candidate_id"])
            token_position = common.token_position_for_char_end(
                offsets, candidate["trigger_char_end"]
            )
            prior = reuse.get(candidate_id)
            if prior is not None and reusable_trial(
                prior,
                candidate_id=candidate_id,
                token_position=token_position,
                policy=self.policy,
            ):
                records.append(copied_trial(prior))
                reused_count += 1
                continue

            prefix = self.tokenizer.decode(token_ids[:token_position])
            prompt = chat + prefix + DEER_ANSWER_INDUCER
            try:
                response, latency, retry_count = self.complete(
                    prompt,
                    max_tokens=self.trial_cap,
                    stop=self.stop_tokens,
                    logprobs=1,
                    extra_body={"include_stop_str_in_output": True},
                )
            except Exception as error:
                records.append(
                    {
                        "candidate_id": candidate_id,
                        "trigger_type": candidate["trigger_type"],
                        "trigger_char_position": candidate[
                            "trigger_char_position"
                        ],
                        "token_position": token_position,
                        "trial_text": "",
                        "trial_answer": "",
                        "logprobs": [],
                        "confidence": 0.0,
                        "policy": self.policy,
                        "last_token_decoded": "",
                        "think_close_emitted": False,
                        "trial_out_tokens": 0,
                        "trial_prompt_tokens": 0,
                        "trial_finish_reason": None,
                        "trial_latency_seconds": 0.0,
                        "retry_count": 3,
                        "record_source": "new_cap30_probe",
                        "error": str(error),
                    }
                )
                continue

            text = str(response.choices[0].text)
            logprobs = self._extract_logprobs(response)
            confidence = deer.calculate_confidence(
                logprobs,
                policy=self.policy,
                require_think_close=self.require_think_close,
            )
            last_decoded = logprobs[-1][0] if logprobs else ""
            records.append(
                {
                    "candidate_id": candidate_id,
                    "trigger_type": candidate["trigger_type"],
                    "trigger_char_position": candidate[
                        "trigger_char_position"
                    ],
                    "token_position": token_position,
                    "trial_text": text,
                    "trial_answer": deer.parse_trial_response(text),
                    "logprobs": [
                        {"token": token, "logprob": logprob}
                        for token, logprob in logprobs
                    ],
                    "confidence": confidence,
                    "policy": self.policy,
                    "last_token_decoded": last_decoded,
                    "think_close_emitted": (
                        last_decoded == common.DEER_THINK_CLOSE
                    ),
                    "trial_out_tokens": int(
                        response.usage.completion_tokens
                    ),
                    "trial_prompt_tokens": int(response.usage.prompt_tokens),
                    "trial_finish_reason": common.finish_reason_of(response),
                    "trial_latency_seconds": latency,
                    "retry_count": retry_count,
                    "record_source": "new_cap30_probe",
                }
            )
            generated_count += 1

        atomic_write_json(
            output_path,
            {
                "schema_version": PROBE_SCHEMA,
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
                "require_think_close": self.require_think_close,
                "max_attempts": self.max_attempts,
                "expected_candidate_count": len(candidates),
                "reused_trial_count": reused_count,
                "generated_trial_count": generated_count,
                "direct_submit_analysis": True,
                "formal_readout": False,
                "trials": records,
            },
        )
        return problem_id


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Threshold-agnostic DEER confidence-bank collector"
    )
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-dir", type=Path, default=None)
    parser.add_argument("--url", default="http://localhost:18000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=common.GOVERNOR_V2 / "generated" / "split_manifest.json",
    )
    parser.add_argument(
        "--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS
    )
    parser.add_argument("--trial-cap", type=int, default=common.DEER_TRIAL_CAP)
    parser.add_argument("--policy", default=None)
    parser.add_argument("--force-policy", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--problem-id", type=int, action="append", default=[])
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    if args.max_attempts <= 0:
        raise ValueError("--max-attempts must be positive")
    manifest = load_main_manifest(args.main_run)
    collector = DEERConfidenceBankCollector(args, manifest)
    paths = list(trajectory_paths(args.main_run))
    if args.problem_id:
        selected = set(args.problem_id)
        paths = [
            path
            for path in paths
            if int(path.stem.removeprefix("problem_")) in selected
        ]
    if args.limit:
        paths = paths[: args.limit]
    if not paths:
        raise ValueError("no input trajectories selected")

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, path) for path in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            problem_id = future.result()
            print(
                f"[{index}/{len(paths)}] problem {problem_id}",
                flush=True,
            )

    completion = common.finalize_collection_manifest(
        collector.manifest_path,
        (args.output / "trials").glob("problem_*.json"),
        records_key="trials",
        expected_problem_count=len(paths),
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")
    if not completion["complete"]:
        raise RuntimeError("confidence-bank collection did not complete cleanly")


if __name__ == "__main__":
    main()
