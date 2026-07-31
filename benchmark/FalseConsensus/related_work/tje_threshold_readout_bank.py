"""Collect missing TJE readouts for a discrete confidence-threshold frontier.

The faithful TJE run stores every confidence label up to the first
``Almost certain`` trigger (or all triggers when that label never appears).
That is sufficient to replay every *lower* confidence threshold without
regenerating confidence probes.  This collector reuses those labels and the
faithful readout, then generates only the missing readouts required by the
top-2 through top-6 confidence policies.
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from . import common, tje


METHOD = "tje_threshold_readout_bank_top1_6"
REPRODUCTION_CLASS = (
    "frozen-trajectory TJE discrete-threshold readout bank "
    "(faithful confidence labels; top-1 through top-6 policies)"
)
PROBE_SCHEMA = "related-work-tje-threshold-readout-bank-problem-1"
RUN_SCHEMA = "related-work-tje-threshold-readout-bank-run-1"

# Highest K official confidence classes are accepted.
TOP_K_THRESHOLDS = {
    1: "Almost certain",
    2: "Highly likely",
    3: "Very good chance",
    4: "Likely",
    5: "Better than even",
    6: "Less than even",
}

TRIGGER_FIELDS = (
    "trigger_id",
    "trigger_type",
    "trigger_char_position",
    "token_position",
    "confidence_response",
    "confidence_label",
    "confidence_out_tokens",
    "confidence_prompt_tokens",
    "confidence_finish_reason",
    "confidence_latency_seconds",
    "retry_count",
)


def _identity(payload: Mapping[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(payload.get("model", "")),
        str(payload.get("dataset", "")),
        int(payload.get("base_seed", -1)),
        int(payload.get("problem_id", -1)),
    )


def first_crossing(
    triggers: Sequence[Mapping[str, Any]], threshold_label: str
) -> Optional[Mapping[str, Any]]:
    threshold_index = tje.label_index(threshold_label)
    if threshold_index < 0:
        raise ValueError(f"unknown TJE threshold label: {threshold_label}")
    for row in triggers:
        if tje.label_index(row.get("confidence_label")) >= threshold_index:
            return row
    return None


def threshold_decisions(
    triggers: Sequence[Mapping[str, Any]],
) -> dict[int, Optional[Mapping[str, Any]]]:
    return {
        top_k: first_crossing(triggers, label)
        for top_k, label in TOP_K_THRESHOLDS.items()
    }


def reusable_readout(
    readout: Any, *, trigger_id: int
) -> bool:
    if not isinstance(readout, Mapping):
        return False
    if int(readout.get("at_trigger_id", -1)) != trigger_id:
        return False
    if "error" in readout:
        return False
    if readout.get("readout_context_overflow"):
        return False
    if readout.get("readout_context_budget_exceeded"):
        return False
    return readout.get("readout_finish_reason") in {"stop", "length"}


def copy_readout(readout: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(readout)
    copied["record_source"] = "reused_faithful_tje_top1"
    return copied


class TJEThresholdReadoutBankCollector(tje.TJECollector):
    """Reuse faithful labels and collect only threshold-specific readouts."""

    def __init__(
        self, args: argparse.Namespace, main_manifest: Mapping[str, Any]
    ):
        self.source_tje_dir = Path(args.source_tje_dir)
        args.threshold_label = common.TJE_THRESHOLD_LABEL
        args.include_think_close = True
        super().__init__(args, main_manifest)
        self.readout_dir = self.output / "readouts"
        self.readout_dir.mkdir(parents=True, exist_ok=True)

    @property
    def manifest_path(self) -> Path:
        return self.output / "bank_manifest.json"

    def _initialize_manifest(self) -> None:
        main_run = Path(self.settings["main_run"])
        source_manifest = self.source_tje_dir / "trigger_manifest.json"
        if not source_manifest.exists():
            raise FileNotFoundError(source_manifest)
        input_paths = common.trajectory_paths(main_run)
        self.settings = {
            "collection_schema": PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "main_run": str(main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "include_think_close": True,
            "top_k_thresholds": {
                str(key): value
                for key, value in TOP_K_THRESHOLDS.items()
            },
            "confidence_collection": "reuse faithful TJE labels only",
            "readout_collection": (
                "reuse faithful top-1 readout; generate missing unique "
                "first-crossing readouts for top-2 through top-6"
            ),
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "readout_output_cap": self.readout_cap,
            "max_model_len": self.max_model_len,
            "model_revision": self.model_revision,
            "main_manifest_sha256": common.sha256_file(
                main_run / "run_manifest.json"
            ),
            "input_trajectory_bank_sha256": common.sha256_path_set(
                input_paths, root=main_run
            ),
            "source_tje_dir": str(self.source_tje_dir),
            "source_tje_manifest_sha256": common.sha256_file(source_manifest),
            "split_manifest": str(self.args.split_manifest),
            "split_manifest_sha256": common.sha256_file(
                Path(self.args.split_manifest)
            ),
            "expected_problem_count": len(input_paths),
        }
        self.provenance = common.method_provenance(
            METHOD,
            reproduction_class=REPRODUCTION_CLASS,
            source_commit=tje.SOURCE_COMMIT,
            source_url=tje.SOURCE_URL,
            prompt_text=common.TJE_SYSTEM_PROMPT,
            trigger_definition=(
                "all faithful TJE whole-word Wait triggers plus final "
                "</think>; no artificial maximum trigger count"
            ),
            output_cap=self.readout_cap,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            seed_policy="base_seed (matched to faithful TJE)",
            extra={
                "top_k_thresholds": self.settings["top_k_thresholds"],
                "confidence_queries_generated": 0,
                "source_tje_manifest_sha256": self.settings[
                    "source_tje_manifest_sha256"
                ],
            },
        )
        if self.manifest_path.exists():
            existing = common.load_json(self.manifest_path)
            if existing.get("bank_settings") != self.settings:
                raise ValueError(
                    "existing TJE readout bank has different settings"
                )
            return
        common.atomic_write_json(
            self.manifest_path,
            {
                "schema_version": RUN_SCHEMA,
                "bank_settings": self.settings,
                "provenance": self.provenance,
                "protocol_version": self.main_settings.get(
                    "protocol_version"
                ),
                "api_key_recorded": False,
                "runtime": common.runtime_versions(),
                "created_at": common.now_iso(),
            },
        )

    def _completed_payload_is_valid(
        self,
        payload: Mapping[str, Any],
        *,
        expected_identity: tuple[str, str, int, int],
        expected_readout_ids: set[int],
    ) -> bool:
        readouts = payload.get("readouts")
        if (
            payload.get("schema_version") != PROBE_SCHEMA
            or payload.get("method") != METHOD
            or _identity(payload) != expected_identity
            or not isinstance(readouts, list)
            or {
                int(row.get("at_trigger_id", -1))
                for row in readouts
                if isinstance(row, Mapping)
            }
            != expected_readout_ids
            or any("error" in row for row in readouts)
        ):
            return False
        return True

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        problem_id = int(trajectory["problem_id"])
        expected_identity = (
            self.model,
            self.dataset,
            self.base_seed,
            problem_id,
        )
        source_path = (
            self.source_tje_dir
            / "triggers"
            / f"problem_{problem_id}.json"
        )
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        source = common.load_json(source_path)
        if _identity(source) != expected_identity:
            raise ValueError(f"source TJE identity mismatch: {source_path}")
        if source.get("include_think_close") is not True:
            raise ValueError(f"source TJE is not primary variant: {source_path}")
        if source.get("threshold_label") != common.TJE_THRESHOLD_LABEL:
            raise ValueError(
                f"source TJE threshold mismatch: {source_path}"
            )
        source_triggers = source.get("triggers")
        if not isinstance(source_triggers, list):
            raise ValueError(f"malformed source triggers: {source_path}")
        if any("error" in row for row in source_triggers):
            raise ValueError(f"source TJE contains trigger error: {source_path}")

        decisions = threshold_decisions(source_triggers)
        needed_ids = {
            int(row["trigger_id"])
            for row in decisions.values()
            if row is not None
        }
        output_path = self.readout_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            try:
                existing = common.load_json(output_path)
                if self._completed_payload_is_valid(
                    existing,
                    expected_identity=expected_identity,
                    expected_readout_ids=needed_ids,
                ):
                    return problem_id
                raise ValueError("incomplete bank payload")
            except Exception:
                corrupt = output_path.with_suffix(
                    f".json.corrupt.{int(time.time())}"
                )
                output_path.rename(corrupt)

        full_text = str(trajectory["full_text"])
        encoded = self.tokenizer(
            full_text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        token_ids = list(encoded["input_ids"])
        offsets = list(encoded["offset_mapping"])
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        recomputed = {
            int(row["trigger_id"]): row
            for row in tje.find_triggers(
                full_text, include_think_close=True
            )
        }
        source_by_id = {
            int(row["trigger_id"]): row for row in source_triggers
        }
        chat = tje.build_system_chat(
            self.tokenizer, str(trajectory["problem"]).strip()
        )
        source_readout = source.get("readout")
        readouts: list[dict[str, Any]] = []
        reused = generated = 0

        for trigger_id in sorted(needed_ids):
            source_trigger = source_by_id[trigger_id]
            if reusable_readout(
                source_readout, trigger_id=trigger_id
            ):
                readouts.append(copy_readout(source_readout))
                reused += 1
                continue

            trigger = recomputed.get(trigger_id)
            if trigger is None:
                raise ValueError(
                    f"missing recomputed trigger {trigger_id}: {source_path}"
                )
            token_position = common.token_position_for_char_end(
                offsets, trigger["trigger_char_end"]
            )
            if token_position != int(source_trigger["token_position"]):
                raise ValueError(
                    f"trigger token-position mismatch: {source_path} "
                    f"trigger={trigger_id}"
                )
            prefix = self.tokenizer.decode(token_ids[:token_position])
            confidence_prompt = tje.build_confidence_prompt(chat, prefix)
            label = str(source_trigger["confidence_label"])
            readout_prompt = tje.build_readout_prompt(
                confidence_prompt, label
            )
            prompt_sha = common.sha256_bytes(
                readout_prompt.encode("utf-8")
            )
            estimated_prompt_tokens = len(
                self.tokenizer.encode(
                    readout_prompt, add_special_tokens=False
                )
            )
            allowance_record = common.compute_readout_allowance(
                estimated_prompt_tokens,
                readout_cap=self.readout_cap,
                max_model_len=self.max_model_len,
            )
            allowance = int(allowance_record["allowance"])
            if allowance_record["context_budget_exceeded"]:
                readouts.append(
                    {
                        "readout_answer": "",
                        "readout_text": "",
                        "readout_valid": False,
                        "readout_truncated": False,
                        "readout_completed_boxed": False,
                        "readout_finish_reason": None,
                        "readout_out_tokens": 0,
                        "readout_prompt_tokens": 0,
                        "readout_allowance": 0,
                        "readout_prompt_tokens_estimate": (
                            estimated_prompt_tokens
                        ),
                        "readout_context_budget_exceeded": True,
                        "readout_remaining": allowance_record["remaining"],
                        "readout_triggering_label": label,
                        "readout_confidence_event": (
                            "\\confidence{" + label + "}"
                        ),
                        "readout_prompt_sha256": prompt_sha,
                        "readout_latency_seconds": 0.0,
                        "at_trigger_id": trigger_id,
                        "retry_count": 0,
                        "record_source": "new_threshold_readout",
                    }
                )
                generated += 1
                continue

            response, latency, retry_count = self.complete(
                readout_prompt,
                max_tokens=allowance,
                extra_body={"top_k": self.top_k},
            )
            text = str(response.choices[0].text)
            finish_reason = common.finish_reason_of(response)
            validity = common.readout_validity(
                text, finish_reason, self.dataset
            )
            actual_prompt_tokens = int(response.usage.prompt_tokens)
            overflow = (
                actual_prompt_tokens + allowance
            ) > self.max_model_len
            if overflow:
                raise ValueError(
                    f"readout context overflow: problem={problem_id} "
                    f"trigger={trigger_id}"
                )
            readouts.append(
                {
                    "readout_answer": validity["readout_answer"],
                    "readout_text": text,
                    "readout_valid": validity["readout_valid"],
                    "readout_truncated": validity["readout_truncated"],
                    "readout_completed_boxed": validity[
                        "readout_completed_boxed"
                    ],
                    "readout_finish_reason": validity[
                        "readout_finish_reason"
                    ],
                    "readout_out_tokens": int(
                        response.usage.completion_tokens
                    ),
                    "readout_prompt_tokens": actual_prompt_tokens,
                    "readout_allowance": allowance,
                    "readout_prompt_tokens_estimate": (
                        estimated_prompt_tokens
                    ),
                    "readout_context_overflow": False,
                    "readout_triggering_label": label,
                    "readout_confidence_event": (
                        "\\confidence{" + label + "}"
                    ),
                    "readout_prompt_sha256": prompt_sha,
                    "readout_latency_seconds": latency,
                    "at_trigger_id": trigger_id,
                    "retry_count": retry_count,
                    "record_source": "new_threshold_readout",
                }
            )
            generated += 1

        copied_triggers = [
            {field: row.get(field) for field in TRIGGER_FIELDS}
            for row in source_triggers
        ]
        decision_rows = {
            str(top_k): (
                {
                    "threshold_label": TOP_K_THRESHOLDS[top_k],
                    "stop_trigger_id": int(row["trigger_id"]),
                    "stop_position": int(row["token_position"]),
                    "confidence_label": row["confidence_label"],
                }
                if row is not None
                else {
                    "threshold_label": TOP_K_THRESHOLDS[top_k],
                    "stop_trigger_id": None,
                    "stop_position": None,
                    "confidence_label": None,
                }
            )
            for top_k, row in decisions.items()
        }
        common.atomic_write_json(
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
                "chat_template_sha256": common.sha256_bytes(
                    chat.encode("utf-8")
                ),
                "source_tje_sha256": common.sha256_file(source_path),
                "source_trigger_count": len(copied_triggers),
                "confidence_queries_generated": 0,
                "top_k_decisions": decision_rows,
                "expected_unique_readout_count": len(needed_ids),
                "reused_readout_count": reused,
                "generated_readout_count": generated,
                "confidence_triggers": copied_triggers,
                "readouts": readouts,
            },
        )
        return problem_id


def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect TJE top-1..top-6 threshold readout bank"
    )
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-tje-dir", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:18000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--readout-cap", type=int, default=8192)
    parser.add_argument("--max-model-len", type=int, default=34816)
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=(
            common.GOVERNOR_V2
            / "generated/split_manifest.json"
        ),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--problem-id", type=int, action="append", default=[]
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    manifest = common.load_main_manifest(args.main_run)
    collector = TJEThresholdReadoutBankCollector(args, manifest)
    paths = list(common.trajectory_paths(args.main_run))
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
        futures = [
            pool.submit(collector.collect, path) for path in paths
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            problem_id = future.result()
            print(
                f"[{index}/{len(paths)}] problem {problem_id}",
                flush=True,
            )
    completion = common.finalize_collection_manifest(
        collector.manifest_path,
        (collector.readout_dir).glob("problem_*.json"),
        records_key="readouts",
        expected_problem_count=len(paths),
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")


if __name__ == "__main__":
    main()
