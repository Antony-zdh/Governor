from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from benchmark.FalseConsensus.governor_v2.build_experiment_matrix import (
    build_matrix,
)
from benchmark.FalseConsensus.governor_v2.dense_probe import (
    checkpoint_positions,
)
from benchmark.FalseConsensus.governor_v2.make_splits import (
    apportion,
    assign_benchmark,
    validate_manifest,
)
from benchmark.FalseConsensus.governor_v2.rule_schema import (
    RULE_DIMENSIONS,
    RuleSpec,
    expand_search_space,
    factorial_ablations,
    one_at_a_time_ablations,
)
from benchmark.FalseConsensus.governor_v2.replay_rules import (
    replay_one,
    window_switches,
)


HERE = Path(__file__).resolve().parents[1]


class SplitTests(unittest.TestCase):
    def test_exact_60_20_20_apportionment(self) -> None:
        ratios = {"train": 0.6, "dev": 0.2, "test": 0.2}
        self.assertEqual(
            apportion(500, ratios),
            {"train": 300, "dev": 100, "test": 100},
        )

    def test_invalid_ratios_fail_fast(self) -> None:
        with self.assertRaises(ValueError):
            apportion(100, {"train": 0.7, "dev": 0.2, "test": 0.2})

    def test_assignment_is_exact_and_reproducible(self) -> None:
        rows = [
            {
                "benchmark": "synthetic",
                "problem_id": str(index),
                "content_hash": f"{index:04d}",
                "stratum": f"level-{index % 5}",
                "strata": {"level": str(index % 5)},
            }
            for index in range(503)
        ]
        config = {
            "ratios": {"train": 0.6, "dev": 0.2, "test": 0.2},
            "seed": 20260726,
            "minimum_ratio_benchmark_size": 250,
        }
        first = copy.deepcopy(rows)
        second = copy.deepcopy(rows)
        benchmark = {"name": "synthetic", "split_policy": "ratio"}
        assign_benchmark(benchmark, first, config)
        assign_benchmark(benchmark, second, config)
        self.assertEqual(
            [row["split"] for row in first],
            [row["split"] for row in second],
        )
        self.assertEqual(
            Counter(row["split"] for row in first),
            Counter(apportion(503, config["ratios"])),
        )
        validate_manifest(first)

    def test_small_benchmark_becomes_external_stress(self) -> None:
        rows = [
            {
                "benchmark": "small",
                "problem_id": str(index),
                "content_hash": f"small-{index}",
                "stratum": "all",
                "strata": {},
            }
            for index in range(40)
        ]
        assign_benchmark(
            {"name": "small", "split_policy": "ratio"},
            rows,
            {
                "ratios": {"train": 0.6, "dev": 0.2, "test": 0.2},
                "seed": 1,
                "minimum_ratio_benchmark_size": 250,
            },
        )
        self.assertEqual({row["split"] for row in rows}, {"external_stress"})


class RuleSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol = json.loads(
            (HERE / "protocol.json").read_text(encoding="utf-8")
        )
        cls.rules = expand_search_space(cls.protocol["rule_search"])

    def test_candidate_grid_is_valid_and_unique(self) -> None:
        self.assertGreater(len(self.rules), 1000)
        self.assertEqual(
            len(self.rules), len({rule.rule_id for rule in self.rules})
        )
        for rule in self.rules:
            rule.validate()
            self.assertEqual(
                set(RULE_DIMENSIONS),
                set(rule.to_dict()) - {"rule_id", "metadata"},
            )

    def test_round_trip(self) -> None:
        rule = self.rules[0]
        self.assertEqual(RuleSpec.from_dict(rule.to_dict()), rule)
        self.assertIn(
            rule.history.switch_window.kind, {"tokens", "probes"}
        )
        self.assertGreater(rule.history.switch_window.size, 0)

    def test_all_dimension_ablations(self) -> None:
        rule = self.rules[-1]
        ablation = self.protocol["ablation"]
        references = ablation["reference_dimensions"]
        one_at_a_time = one_at_a_time_ablations(rule, references)
        self.assertEqual(len(one_at_a_time), 1 + len(RULE_DIMENSIONS))
        factorial = factorial_ablations(
            rule, references, ablation["factorial_dimensions"]
        )
        self.assertEqual(len(factorial), 2 ** len(RULE_DIMENSIONS))
        self.assertEqual(
            {
                item.metadata.get("ablated_dimensions", [None])[0]
                for item in one_at_a_time[1:]
            },
            set(RULE_DIMENSIONS),
        )


class CollectionPreparationTests(unittest.TestCase):
    def test_checkpoint_endpoint_policy(self) -> None:
        self.assertEqual(
            checkpoint_positions(
                256,
                start_token=64,
                interval=64,
                finished_naturally=True,
            ),
            [64, 128, 192],
        )
        self.assertEqual(
            checkpoint_positions(
                256,
                start_token=64,
                interval=64,
                finished_naturally=False,
            ),
            [64, 128, 192, 256],
        )

    def test_matrix_dependencies_and_parameterization(self) -> None:
        protocol = json.loads(
            (HERE / "protocol.json").read_text(encoding="utf-8")
        )
        jobs = build_matrix(protocol)
        main_ids = {
            job["job_id"]
            for job in jobs
            if job["stage"] == "main_generation"
        }
        self.assertEqual(len(jobs), 24)
        self.assertEqual(len(main_ids), 12)
        for job in jobs:
            if job["stage"] == "dense_probe":
                self.assertIn(job["depends_on"], main_ids)
            else:
                self.assertIsNone(job["depends_on"])
        gsm_main = next(
            job
            for job in jobs
            if job["stage"] == "main_generation"
            and job["benchmark"] == "gsm8k"
        )
        self.assertIn("--dataset-path", gsm_main["command"])
        dense32_jobs = build_matrix(protocol, include_32_grid=True)
        self.assertEqual(len(dense32_jobs), 36)
        self.assertEqual(
            sum(
                job["stage"] == "dense_probe_32_offset"
                for job in dense32_jobs
            ),
            12,
        )
        confirmation = build_matrix(protocol, phase="confirmation")
        confirmation_main = [
            job for job in confirmation if job["stage"] == "main_generation"
        ]
        self.assertEqual(len(confirmation), 64)
        self.assertEqual(len(confirmation_main), 32)
        self.assertTrue(
            all(job["phase"] == "confirmation" for job in confirmation)
        )
        self.assertTrue(
            all(
                job["model_role"] == "development"
                for job in jobs
            )
        )
        scale_jobs = [
            job
            for job in confirmation_main
            if job["model_role"] == "heldout_scale"
        ]
        self.assertTrue(scale_jobs)
        self.assertTrue(
            all(job["minimum_bf16_gpus_32gb"] == 4 for job in scale_jobs)
        )


class ReplayTests(unittest.TestCase):
    def test_switch_count_uses_bounded_window(self) -> None:
        history = [(64, "1"), (128, "2"), (192, "1"), (4096, "1")]
        self.assertEqual(window_switches(history, kind="tokens", size=2048), 0)
        self.assertEqual(window_switches(history, kind="probes", size=2), 0)

    def test_replay_counts_probe_decode_cost(self) -> None:
        payload = {
            "rule_id": "synthetic",
            "probe": {
                "style": "simple",
                "output_cap": 32,
                "schedule": {
                    "kind": "fixed",
                    "start_token": 64,
                    "interval_tokens": 64,
                    "phases": [],
                    "agreement_trigger_count": None,
                    "agreement_interval_tokens": None,
                },
            },
            "validity": {"mode": "schema"},
            "maturity": {
                "kind": "none",
                "minimum_tokens": 0,
                "minimum_budget_fraction": 0.0,
                "online_instability_floor_tokens": 0,
            },
            "evidence": {
                "family": "latest",
                "window_probes": 1,
                "minimum_valid_probes": 1,
                "dominant_share_threshold": 1.0,
                "entropy_threshold": None,
                "entropy_scope": "window",
            },
            "persistence": {
                "minimum_consistent_accepts": 2,
                "minimum_consensus_span_tokens": 64,
            },
            "certainty": {
                "enabled": False,
                "minimum_certain_fraction": 0.0,
            },
            "history": {
                "maximum_switches": None,
                "switch_window": {"kind": "tokens", "size": 2048},
                "minimum_stable_span_tokens": 0,
            },
        }
        rule = RuleSpec.from_dict(payload)
        trajectory = {
            "tokens_used": 512,
            "finished_naturally": True,
            "final_correct": True,
            "target": "7",
        }
        probes = [
            {
                "token_position": position,
                "probe_answer": "7",
                "is_certain": True,
                "probe_out_tokens": 4,
                "probe_prompt_tokens": 100,
            }
            for position in (64, 128, 192)
        ]
        result = replay_one(trajectory, probes, rule, "gsm8k", 512)
        self.assertTrue(result["correct"])
        self.assertTrue(result["stopped"])
        self.assertEqual(result["main_decode_tokens"], 128)
        self.assertEqual(result["probe_decode_tokens"], 8)
        self.assertEqual(result["total_decode_tokens"], 136)


if __name__ == "__main__":
    unittest.main()
