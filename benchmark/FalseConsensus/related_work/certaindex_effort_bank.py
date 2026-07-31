"""Extend faithful CertaIndex ``mid`` probes to the ``mild`` effort level.

The source collector stops as soon as patience 3 fires.  This restartable
collector reuses that exact per-problem prefix and generates only the missing
interval-64 probes until patience 8 fires or the frozen trajectory ends.  The
completed bank supports CPU replay of official mild/low/mid/high settings.
The official crazy setting is supplied by the separate CertaIndex@32 bank.
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence

from . import common, certaindex_mid


METHOD = "certaindex_effort_bank"
PROBE_SCHEMA = "related-work-certaindex-effort-bank-problem-1"
RUN_SCHEMA = "related-work-certaindex-effort-bank-run-1"
TARGET_PATIENCE = 8


class CertaIndexEffortBankCollector(
    certaindex_mid.CertaIndexMidCollector
):
    """Reuse the faithful mid prefix and collect only later probes."""

    PROBE_SCHEMA = PROBE_SCHEMA
    RUN_SCHEMA = RUN_SCHEMA

    @property
    def source_mid_dir(self) -> Path:
        return Path(self.args.source_mid_dir)

    def _initialize_manifest(self) -> None:
        source_manifest_path = self.source_mid_dir / "probe_manifest.json"
        if not source_manifest_path.exists():
            raise FileNotFoundError(source_manifest_path)
        source_manifest = common.load_json(source_manifest_path)
        source_settings = source_manifest.get("probe_settings", {})
        expected_source = {
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_interval": 64,
            "start_token": 64,
            "probe_tokens": 20,
            "patience": 3,
            "probe_suffix_sha256": common.sha256_bytes(
                self.suffix.encode("utf-8")
            ),
            "model_revision": self.model_revision,
        }
        mismatches = {
            key: (source_settings.get(key), expected)
            for key, expected in expected_source.items()
            if source_settings.get(key) != expected
        }
        if mismatches:
            raise ValueError(
                "source is not the matching faithful CertaIndex mid bank: "
                f"{mismatches}"
            )
        self.settings.update(
            {
                "method": METHOD,
                "collection_schema": PROBE_SCHEMA,
                "patience": TARGET_PATIENCE,
                "source_mid_dir": str(self.source_mid_dir),
                "source_mid_manifest_sha256": common.sha256_file(
                    source_manifest_path
                ),
                "resume_policy": (
                    "reuse exact faithful patience-3 prefix; generate only "
                    "later interval-64 probes until patience 8"
                ),
            }
        )
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = common.load_json(path)
            if existing.get("probe_settings") != self.settings:
                raise ValueError(
                    "existing effort-bank output has different settings"
                )
            return
        common.atomic_write_json(
            path,
            {
                "schema_version": RUN_SCHEMA,
                "probe_settings": self.settings,
                "provenance": {
                    **self.provenance,
                    "method": METHOD,
                    "extension_target": "official mild=(patience 8, interval 64)",
                    "source_mid_manifest_sha256": self.settings[
                        "source_mid_manifest_sha256"
                    ],
                },
                "protocol_version": self.main_settings.get(
                    "protocol_version"
                ),
                "api_key_recorded": False,
                "runtime": common.runtime_versions(),
                "created_at": common.now_iso(),
            },
        )

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.probe_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            existing = common.load_json(output_path)
            if (
                existing.get("schema_version") == PROBE_SCHEMA
                and existing.get("method") == METHOD
                and existing.get("problem_id") == problem_id
                and isinstance(existing.get("probes"), list)
                and not any(
                    "error" in row for row in existing.get("probes", [])
                )
            ):
                return problem_id
            output_path.rename(output_path.with_suffix(".json.corrupt"))

        token_ids = self.tokenizer.encode(
            trajectory["full_text"], add_special_tokens=False
        )
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        positions = common.checkpoint_positions(
            min(
                len(token_ids),
                int(self.main_settings.get("budget", len(token_ids))),
            ),
            start_token=64,
            interval=64,
            finished_naturally=bool(trajectory["finished_naturally"]),
        )
        source_path = (
            self.source_mid_dir
            / "probes"
            / f"problem_{problem_id}.json"
        )
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        source = common.load_json(source_path)
        expected_identity = {
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
        }
        identity_mismatches = {
            key: (source.get(key), expected)
            for key, expected in expected_identity.items()
            if source.get(key) != expected
        }
        if identity_mismatches:
            raise ValueError(
                f"source identity mismatch: {identity_mismatches}"
            )
        source_records = source.get("probes")
        if not isinstance(source_records, list):
            raise ValueError(f"invalid source probes: {source_path}")
        if any("error" in row for row in source_records):
            raise ValueError(f"source contains errors: {source_path}")
        if len(source_records) > len(positions):
            raise ValueError(
                f"source exceeds checkpoint schedule: {source_path}"
            )

        records: List[dict] = []
        for index, row in enumerate(source_records):
            if (
                int(row.get("token_position", -1)) != positions[index]
                or int(row.get("probe_id", -1)) != index + 1
            ):
                raise ValueError(
                    "source is not a prefix of the requested schedule: "
                    f"{source_path}"
                )
            copied = dict(row)
            copied["record_source"] = "reused_faithful_mid"
            records.append(copied)

        chat = common.apply_chat_template(
            str(trajectory["problem"]).strip(), self.model
        )
        answers_equal_fn = common.real_eqaul_group
        count_not_empty_fn = common.real_count_not_empty
        strip_fn = common.real_strip_string()
        for probe_id, position in enumerate(
            positions[len(records):], start=len(records) + 1
        ):
            prefix = self.tokenizer.decode(token_ids[:position])
            try:
                response, latency, retry_count = self.complete(
                    certaindex_mid.build_probe_prompt(
                        chat, prefix, suffix=self.suffix
                    )
                )
            except Exception as error:
                records.append(
                    {
                        "token_position": position,
                        "probe_id": probe_id,
                        "probe_text": "",
                        "probe_answer": "",
                        "is_certain": False,
                        "probe_out_tokens": 0,
                        "probe_prompt_tokens": 0,
                        "probe_latency_seconds": 0.0,
                        "error": str(error),
                        "retry_count": 3,
                        "record_source": "new_mild_extension",
                    }
                )
                continue
            probe_text = str(response.choices[0].text)
            parsed = certaindex_mid.parse_probe_response(
                probe_text, strip_fn=strip_fn
            )
            records.append(
                {
                    "token_position": position,
                    "probe_id": probe_id,
                    "probe_text": probe_text,
                    "probe_answer": parsed["probe_answer"],
                    "is_certain": parsed["is_certain"],
                    "probe_out_tokens": int(
                        response.usage.completion_tokens
                    ),
                    "probe_prompt_tokens": int(
                        response.usage.prompt_tokens
                    ),
                    "probe_finish_reason": common.finish_reason_of(response),
                    "probe_latency_seconds": latency,
                    "retry_count": retry_count,
                    "record_source": "new_mild_extension",
                }
            )
            if len(records) >= TARGET_PATIENCE:
                window = records[-TARGET_PATIENCE:]
                answers = [row["probe_answer"] for row in window]
                if (
                    count_not_empty_fn(answers) == TARGET_PATIENCE
                    and answers_equal_fn(answers)
                    and sum(
                        1 for row in window if row["is_certain"]
                    )
                    == TARGET_PATIENCE
                ):
                    break

        common.atomic_write_json(
            output_path,
            {
                "schema_version": PROBE_SCHEMA,
                "method": METHOD,
                "reproduction_class": (
                    "faithful CertaIndex frozen-trajectory effort bank"
                ),
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
                "source_mid_file_sha256": common.sha256_file(source_path),
                "reused_probe_count": len(source_records),
                "new_probe_count": len(records) - len(source_records),
                "probes": records,
            },
        )
        return problem_id


def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extend CertaIndex mid probes to official mild effort"
    )
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--source-mid-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--problem-id", type=int, action="append", default=[]
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    # Parent initialization consumes these protocol fields.
    args.interval = 64
    args.start_token = 64
    args.probe_tokens = 20
    args.patience = TARGET_PATIENCE
    manifest = common.load_main_manifest(args.main_run)
    collector = CertaIndexEffortBankCollector(args, manifest)
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
        collector.output / "probe_manifest.json",
        collector.probe_dir.glob("problem_*.json"),
        records_key="probes",
        expected_problem_count=int(
            collector.settings["expected_problem_count"]
        ),
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")


if __name__ == "__main__":
    main()
