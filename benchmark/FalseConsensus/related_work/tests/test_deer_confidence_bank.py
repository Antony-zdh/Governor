"""CPU-only regression tests for the DEER cap-30 confidence bank."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from benchmark.FalseConsensus.related_work import (
    audit_deer_confidence_bank as audit,
    deer_confidence_bank as bank,
    launch_deer_confidence_bank as launcher,
)


class DirectSubmitTests(unittest.TestCase):
    def test_strict_threshold_and_validity_gate(self):
        trials = [
            {
                "candidate_id": 1,
                "token_position": 100,
                "confidence": 0.999,
                "trial_answer": "",
            },
            {
                "candidate_id": 2,
                "token_position": 200,
                "confidence": 0.995,
                "trial_answer": "7",
            },
            {
                "candidate_id": 3,
                "token_position": 300,
                "confidence": 0.996,
                "trial_answer": "8",
            },
        ]
        decision = bank.direct_submit_decision(trials, threshold=0.995)
        self.assertEqual(decision["candidate_id"], 3)
        self.assertEqual(decision["trial_answer"], "8")

    def test_cap_is_enforced(self):
        trials = [
            {
                "candidate_id": 31,
                "token_position": 3100,
                "confidence": 1.0,
                "trial_answer": "9",
            }
        ]
        self.assertIsNone(
            bank.direct_submit_decision(
                trials, threshold=0.5, max_attempts=30
            )
        )

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            bank.direct_submit_decision([], threshold=1.1)


class ReuseTests(unittest.TestCase):
    def test_compatible_trial_is_reused(self):
        row = {
            "candidate_id": 2,
            "token_position": 512,
            "policy": "avg1",
            "confidence": 0.9,
            "logprobs": [{"token": "7", "logprob": -0.1}],
        }
        self.assertTrue(
            bank.reusable_trial(
                row,
                candidate_id=2,
                token_position=512,
                policy="avg1",
            )
        )
        copied = bank.copied_trial(row)
        self.assertEqual(
            copied["record_source"], "reused_faithful_deer_0p95"
        )

    def test_error_or_position_mismatch_is_not_reused(self):
        row = {
            "candidate_id": 2,
            "token_position": 512,
            "policy": "avg1",
            "confidence": 0.9,
            "logprobs": [{"token": "7", "logprob": -0.1}],
            "error": "request failed",
        }
        self.assertFalse(
            bank.reusable_trial(
                row,
                candidate_id=2,
                token_position=512,
                policy="avg1",
            )
        )
        row.pop("error")
        self.assertFalse(
            bank.reusable_trial(
                row,
                candidate_id=2,
                token_position=513,
                policy="avg1",
            )
        )


class ShardingTests(unittest.TestCase):
    def _job(self, index: int, count: int) -> launcher.Job:
        path = Path(f"/tmp/job_{index}")
        return launcher.Job(
            scope="full",
            model_key="deepseek",
            benchmark="math500",
            seed=index,
            main_run=path,
            reuse_dir=path,
            output=path,
            problem_count=count,
        )

    def test_balanced_shards_are_complete_and_deterministic(self):
        jobs = [self._job(i, count) for i, count in enumerate([400, 400, 100, 32, 24])]
        first = launcher.balanced_shards(jobs, 3)
        second = launcher.balanced_shards(jobs, 3)
        self.assertEqual(first, second)
        flattened = [job for shard in first for job in shard]
        self.assertCountEqual(flattened, jobs)
        loads = [sum(job.problem_count for job in shard) for shard in first]
        self.assertLessEqual(max(loads) - min(loads), 300)


class AuditAndPackTests(unittest.TestCase):
    def _payload(self, problem_id: int) -> dict:
        trials = [
            {
                "candidate_id": 1,
                "token_position": 100,
                "confidence": 0.996,
                "trial_answer": "7",
                "logprobs": [{"token": "7", "logprob": -0.01}],
                "record_source": "new_cap30_probe",
            },
            {
                "candidate_id": 2,
                "token_position": 200,
                "confidence": 0.99,
                "trial_answer": "7",
                "logprobs": [{"token": "7", "logprob": -0.02}],
                "record_source": "new_cap30_probe",
            },
        ]
        return {
            "schema_version": bank.PROBE_SCHEMA,
            "method": bank.METHOD,
            "model": "model",
            "dataset": "math500",
            "base_seed": 42,
            "problem_id": problem_id,
            "policy": "avg1",
            "require_think_close": False,
            "max_attempts": 30,
            "formal_readout": False,
            "expected_candidate_count": 2,
            "reused_trial_count": 0,
            "generated_trial_count": 2,
            "trials": trials,
        }

    def test_pack_and_audit(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = (
                Path(temporary)
                / "full"
                / "deepseek__math500__seed_42"
            )
            trial_dir = environment / "trials"
            trial_dir.mkdir(parents=True)
            (trial_dir / "problem_0.json").write_text(
                json.dumps(self._payload(0)), encoding="utf-8"
            )
            manifest = {
                "schema_version": bank.RUN_SCHEMA,
                "bank_settings": {
                    "method": bank.METHOD,
                    "max_attempts": 30,
                    "formal_readout": False,
                    "early_exit": False,
                    "expected_problem_count": 1,
                },
                "completion": {
                    "complete": True,
                    "expected_problem_count": 1,
                    "observed_problem_count": 1,
                    "missing_problem_count": 0,
                    "recorded_failures": 0,
                },
            }
            (environment / audit.MANIFEST_NAME).write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            packed = audit.pack_environment(environment)
            self.assertEqual(packed["rows"], 1)
            self.assertTrue((environment / audit.ARCHIVE_NAME).exists())
            environment_row, rows = audit.audit_environment(environment)
            self.assertEqual(environment_row["problems"], 1)
            archived_environment_row, archived_rows = audit.audit_environment(
                environment, archives_only=True
            )
            self.assertEqual(archived_environment_row["problems"], 1)
            self.assertEqual(archived_rows, rows)
            summary = audit.summarize_rows(rows)["all__all"]
            self.assertEqual(summary["raw_hit_10"]["hits"], 1)
            self.assertEqual(summary["valid_hit_30"]["hits"], 1)


if __name__ == "__main__":
    unittest.main()
