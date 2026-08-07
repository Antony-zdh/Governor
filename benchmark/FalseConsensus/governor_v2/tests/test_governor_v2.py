from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from pathlib import Path

from benchmark.FalseConsensus.governor_v2.build_experiment_matrix import (
    build_matrix,
)
from benchmark.FalseConsensus.governor_v2.adaptive_probe import (
    entropy_events,
    normalized_topk_entropy,
)
from benchmark.FalseConsensus.governor_v2.dense_probe import (
    checkpoint_positions,
)
from benchmark.FalseConsensus.governor_v2.dense_probe import (
    PROBE_SUFFIXES,
    SIMPLE_SUFFIX,
    DenseProbeCollector,
    parse_args as dense_probe_parse_args,
)
from benchmark.FalseConsensus.governor_v2.boundary_probe import (
    DEER_MODEL_SLUG,
    load_boundary_positions,
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
    scheduled_probes,
    select_operating_points,
    selection_candidates,
    window_switches,
)
from benchmark.FalseConsensus.governor_v2.replay_certaindex import (
    find_certaindex_stop,
    mutually_equivalent,
    replay_problem,
)
from benchmark.FalseConsensus.governor_v2.run_matrix import override_url


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

    def test_preregistered_small_benchmark_can_force_ratio_split(self) -> None:
        rows = [
            {
                "benchmark": "small",
                "problem_id": str(index),
                "content_hash": f"forced-small-{index}",
                "stratum": "all",
                "strata": {},
            }
            for index in range(30)
        ]
        assign_benchmark(
            {
                "name": "small",
                "split_policy": "ratio",
                "force_ratio_split": True,
            },
            rows,
            {
                "ratios": {"train": 0.6, "dev": 0.2, "test": 0.2},
                "seed": 1,
                "minimum_ratio_benchmark_size": 250,
            },
        )
        self.assertEqual(
            Counter(row["split"] for row in rows),
            {"train": 18, "dev": 6, "test": 6},
        )


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
        adaptive = [
            rule
            for rule in self.rules
            if rule.probe.schedule.kind == "event_adaptive"
        ]
        self.assertEqual(len(adaptive), 864)
        self.assertEqual(
            {
                trigger
                for rule in adaptive
                for trigger in rule.probe.schedule.event.trigger_types
            },
            {
                "conclusion_marker",
                "entropy_drop",
                "reflection_transition",
                "answer_candidate",
            },
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

    def test_three_distinct_pareto_operating_points(self) -> None:
        selected_rules = {
            rule.rule_id: rule for rule in self.rules[:4]
        }
        rule_ids = list(selected_rules)
        candidates = [
            {
                "rule_id": rule_ids[0],
                "dev_q20_saving_fraction": 0.10,
                "positive_saving_fraction": 0.90,
                "max_model_accuracy_drop_pp": 1.0,
                "max_benchmark_accuracy_drop_pp": 1.5,
                "complexity": 3,
            },
            {
                "rule_id": rule_ids[1],
                "dev_q20_saving_fraction": 0.20,
                "positive_saving_fraction": 0.85,
                "max_model_accuracy_drop_pp": 2.0,
                "max_benchmark_accuracy_drop_pp": 2.5,
                "complexity": 4,
            },
            {
                "rule_id": rule_ids[2],
                "dev_q20_saving_fraction": 0.30,
                "positive_saving_fraction": 0.75,
                "max_model_accuracy_drop_pp": 3.5,
                "max_benchmark_accuracy_drop_pp": 4.5,
                "complexity": 5,
            },
            {
                "rule_id": rule_ids[3],
                "dev_q20_saving_fraction": 0.05,
                "positive_saving_fraction": 0.60,
                "max_model_accuracy_drop_pp": 5.0,
                "max_benchmark_accuracy_drop_pp": 6.0,
                "complexity": 6,
            },
        ]
        profiles = [
            {
                "name": "conservative",
                "accuracy_drop_pp_max_per_model": 1.5,
                "accuracy_drop_pp_max_per_benchmark": 2.0,
                "minimum_fraction_environments_with_positive_saving": 0.8,
            },
            {
                "name": "balanced",
                "accuracy_drop_pp_max_per_model": 2.5,
                "accuracy_drop_pp_max_per_benchmark": 3.0,
                "minimum_fraction_environments_with_positive_saving": 0.8,
            },
            {
                "name": "token_efficient",
                "accuracy_drop_pp_max_per_model": 4.0,
                "accuracy_drop_pp_max_per_benchmark": 5.0,
                "minimum_fraction_environments_with_positive_saving": 0.7,
            },
        ]
        chosen, _, frontier = select_operating_points(
            candidates,
            selected_rules,
            profiles,
            minimum_distinct=3,
        )
        self.assertEqual(len(frontier), 3)
        self.assertEqual(
            [chosen[name].rule_id for name in chosen],
            rule_ids[:3],
        )
        self.assertEqual(len({rule.rule_id for rule in chosen.values()}), 3)

    def test_selection_rejects_duplicate_metric_rows(self) -> None:
        rule = self.rules[0]
        row = {
            "rule_id": rule.rule_id,
            "phase": "development",
            "split": "dev",
            "model": "synthetic",
            "benchmark": "synthetic",
            "seed": 1,
            "budget": 1024,
            "accuracy_drop_pp": 0.0,
            "saving_fraction": 0.1,
        }
        with self.assertRaisesRegex(ValueError, "duplicate"):
            selection_candidates(
                [row, dict(row)],
                {rule.rule_id: rule},
            )


class CollectionPreparationTests(unittest.TestCase):
    def test_replica_url_override_is_local_to_runner(self) -> None:
        command = ["python", "collector.py", "--url", "http://old/v1"]
        self.assertEqual(
            override_url(command, "http://replica:18001/v1")[-1],
            "http://replica:18001/v1",
        )
        self.assertEqual(command[-1], "http://old/v1")

    def test_entropy_trigger_is_teacher_forced_signal(self) -> None:
        self.assertAlmostEqual(
            normalized_topk_entropy({"a": 0.0}), 0.0
        )
        events = entropy_events(
            [0.9] * 64 + [0.2] * 16,
            [80],
            smooth_window=16,
            reference_window=64,
            minimum_drop=0.1,
        )
        self.assertGreater(events[80]["entropy_drop"], 0.6)
        self.assertGreater(events[80]["entropy_z"], 0.0)

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

    def test_probe_style_simple_matches_original_constant(self) -> None:
        # Arm A must select the identical suffix string the original
        # SIMPLE_SUFFIX constant held -- a whitespace difference invalidates
        # the paired probe-wording experiment.
        self.assertEqual(PROBE_SUFFIXES["simple"], SIMPLE_SUFFIX)
        self.assertEqual(
            SIMPLE_SUFFIX, "**Final Answer**\n\n\\[ \\boxed{"
        )
        self.assertIn("certaindex", PROBE_SUFFIXES)
        self.assertTrue(
            PROBE_SUFFIXES["certaindex"].endswith(SIMPLE_SUFFIX),
            "certaindex suffix must end with the simple suffix verbatim",
        )
        self.assertTrue(
            PROBE_SUFFIXES["certaindex"].startswith(
                "... Oh, I suddenly got the answer to the whole problem, "
            ),
            "certaindex suffix must carry the commitment nudge verbatim",
        )

    def test_parse_args_probe_style_defaults_to_simple(self) -> None:
        import sys

        argv = sys.argv
        try:
            sys.argv = [
                "dense_probe.py",
                "--main-run",
                "/tmp/m",
                "--output",
                "/tmp/o",
            ]
            args = dense_probe_parse_args()
            self.assertEqual(args.probe_style, "simple")
            self.assertIsNone(args.problem_ids)
        finally:
            sys.argv = argv

    def test_parse_args_probe_style_certaindex_selects_arm_b(self) -> None:
        import sys

        argv = sys.argv
        try:
            sys.argv = [
                "dense_probe.py",
                "--main-run",
                "/tmp/m",
                "--output",
                "/tmp/o",
                "--probe-style",
                "certaindex",
                "--problem-ids",
                "/tmp/ids.txt",
            ]
            args = dense_probe_parse_args()
            self.assertEqual(args.probe_style, "certaindex")
            self.assertEqual(args.problem_ids, Path("/tmp/ids.txt"))
        finally:
            sys.argv = argv

    def test_load_problem_ids_parses_one_per_line(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False
        ) as handle:
            handle.write("1\n3\n\n  25  \n32\n")
            path = Path(handle.name)
        try:
            ids = DenseProbeCollector._load_problem_ids(path)
            self.assertEqual(ids, {1, 3, 25, 32})
        finally:
            path.unlink()

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
        self.assertEqual(len(jobs), 54)
        self.assertEqual(len(main_ids), 18)
        dense_ids = {
            job["job_id"]
            for job in jobs
            if job["stage"] == "dense_probe"
        }
        for job in jobs:
            if job["stage"] == "dense_probe":
                self.assertIn(job["depends_on"], main_ids)
            elif job["stage"] == "adaptive_probe":
                self.assertIn(job["depends_on"], dense_ids)
            else:
                self.assertIsNone(job["depends_on"])
        self.assertNotIn("gsm8k", {job["benchmark"] for job in jobs})
        dense32_jobs = build_matrix(protocol, include_32_grid=True)
        self.assertEqual(len(dense32_jobs), 72)
        self.assertEqual(
            sum(
                job["stage"] == "dense_probe_32_offset"
                for job in dense32_jobs
            ),
            18,
        )
        confirmation = build_matrix(protocol, phase="confirmation")
        confirmation_main = [
            job for job in confirmation if job["stage"] == "main_generation"
        ]
        self.assertEqual(len(confirmation), 72)
        self.assertEqual(len(confirmation_main), 24)
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
        self.assertTrue(
            all(job["target_a100_80gb_gpus"] == 2 for job in scale_jobs)
        )
        qwen3_jobs = [
            job
            for job in jobs
            if job["model"] == "Qwen/Qwen3-8B"
        ]
        self.assertTrue(qwen3_jobs)
        self.assertTrue(
            all(job["maximum_model_length"] == 40960 for job in qwen3_jobs)
        )
        self.assertTrue(
            all(
                job["maximum_model_length"] == 49152
                for job in jobs
                if job["model"] != "Qwen/Qwen3-8B"
            )
        )
        small_models = build_matrix(
            protocol,
            phase="confirmation",
            excluded_model_roles=("heldout_scale",),
        )
        self.assertEqual(len(small_models), 63)
        self.assertNotIn(
            "heldout_scale",
            {job["model_role"] for job in small_models},
        )


class BoundaryExtractionTests(unittest.TestCase):
    def test_deer_model_slug_map_covers_dev_models(self) -> None:
        self.assertEqual(
            DEER_MODEL_SLUG["deepseek-ai-deepseek-r1-distill-qwen-7b"],
            "deepseek",
        )
        self.assertEqual(DEER_MODEL_SLUG["qwen-qwen3-8b"], "qwen3")

    def test_load_boundary_positions_caps_and_sorts(self) -> None:
        import gzip
        import tempfile

        records = [
            {
                "problem_id": 1,
                "generated_trial_count": 3,
                "max_attempts": 30,
                "trials": [
                    {"token_position": 464, "candidate_id": 2},
                    {"token_position": 301, "candidate_id": 1},
                    {"token_position": 900, "candidate_id": 3},
                ],
            },
            {
                "problem_id": 2,
                "generated_trial_count": 35,
                "max_attempts": 30,
                # 33 distinct positions -> must be capped at 30
                "trials": [
                    {"token_position": i * 10, "candidate_id": i}
                    for i in range(1, 34)
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            with gzip.open(d / "trials.jsonl.gz", "wt", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
            out = load_boundary_positions(d)
        self.assertEqual(out[1], [301, 464, 900])  # sorted, deduped
        self.assertLessEqual(len(out[2]), 30)  # capped at 30
        self.assertEqual(out[2], sorted(out[2]))


class ReplayTests(unittest.TestCase):
    def test_certaindex_equivalence_preserves_argument_order(self) -> None:
        self.assertTrue(mutually_equivalent(["1/2", "0.5", "\\frac{1}{2}"]))

    def test_certaindex_adapter_uses_math_equivalence_and_three_certain_probes(
        self,
    ) -> None:
        probes = [
            {
                "token_position": position,
                "probe_answer": answer,
                "is_certain": certain,
                "probe_out_tokens": 4,
                "probe_prompt_tokens": 100,
            }
            for position, answer, certain in [
                (64, "1/2", True),
                (128, "0.5", True),
                (192, "\\frac{1}{2}", False),
                (256, "0.5", True),
                (320, "\\frac{1}{2}", True),
                (384, "1/2", True),
            ]
        ]
        stop, answer, decode, prompt, calls = find_certaindex_stop(
            probes, budget=512
        )
        self.assertEqual(stop, 384)
        self.assertEqual(answer, "1/2")
        self.assertEqual(decode, 24)
        self.assertEqual(prompt, 600)
        self.assertEqual(calls, 6)

    def test_certaindex_adapter_counts_probe_cost_and_falls_back_to_full(
        self,
    ) -> None:
        trajectory = {
            "tokens_used": 256,
            "finished_naturally": True,
            "final_answer": "7",
            "target": "7",
            "final_correct": True,
        }
        probes = [
            {
                "token_position": position,
                "probe_answer": answer,
                "is_certain": True,
                "probe_out_tokens": 5,
                "probe_prompt_tokens": 90,
            }
            for position, answer in [(64, "1"), (128, "2"), (192, "3")]
        ]
        outcome = replay_problem(trajectory, probes, budget=512)
        self.assertFalse(outcome["stopped"])
        self.assertTrue(outcome["delivered_correct"])
        self.assertEqual(outcome["main_decode_tokens"], 256)
        self.assertEqual(outcome["probe_decode_tokens"], 15)
        self.assertEqual(outcome["total_decode_tokens"], 271)

    def test_event_adaptive_schedule_filters_the_union_bank(self) -> None:
        base = {
            "rule_id": "adaptive-synthetic",
            "probe": {
                "style": "simple",
                "output_cap": 32,
                "schedule": {
                    "kind": "event_adaptive",
                    "start_token": 256,
                    "interval_tokens": 256,
                    "phases": [],
                    "agreement_trigger_count": None,
                    "agreement_interval_tokens": None,
                    "event": {
                        "trigger_types": [
                            "conclusion_marker",
                            "entropy_drop",
                        ],
                        "marker_profile": "conclusion_strict",
                        "entropy": {
                            "metric": "teacher_forced_topk_entropy",
                            "top_k": 20,
                            "smooth_window_tokens": 16,
                            "reference_window_tokens": 64,
                            "minimum_drop": 0.15,
                            "minimum_z": 1.0,
                        },
                        "alignment": "next_step_boundary",
                        "alignment_lookahead_tokens": 32,
                        "minimum_gap_tokens": 64,
                        "fallback_interval_tokens": 512,
                    },
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
                "minimum_consistent_accepts": 1,
                "minimum_consensus_span_tokens": 0,
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
        rule = RuleSpec.from_dict(base)
        probes = [
            {
                "token_position": 256,
                "trigger_types": ["conclusion_marker"],
                "marker_profiles": ["conclusion_strict"],
            },
            {
                "token_position": 320,
                "trigger_types": ["entropy_drop"],
                "entropy_drop": 0.2,
                "entropy_z": 1.2,
            },
            {
                "token_position": 384,
                "trigger_types": ["reflection_transition"],
            },
            {"token_position": 768},
        ]
        self.assertEqual(
            [
                probe["token_position"]
                for probe in scheduled_probes(probes, rule, 1024)
            ],
            [256, 320, 768],
        )

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
        result = replay_one(trajectory, probes, rule, "math500", 512)
        self.assertTrue(result["correct"])
        self.assertTrue(result["stopped"])
        self.assertEqual(result["main_decode_tokens"], 128)
        self.assertEqual(result["probe_decode_tokens"], 8)
        self.assertEqual(result["total_decode_tokens"], 136)

        cached_baseline = replay_one(
            {
                "tokens_used": 512,
                "finished_naturally": True,
                "final_answer": "intentionally-not-regraded",
                "target": "7",
            },
            [],
            rule,
            "math500",
            512,
            baseline_answer_correctness=True,
        )
        self.assertTrue(cached_baseline["baseline_correct"])
        self.assertTrue(cached_baseline["correct"])


if __name__ == "__main__":
    unittest.main()
