from __future__ import annotations

import unittest

from benchmark.FalseConsensus.related_work.analyze_false_stops import (
    analyze,
    summarize,
)
from benchmark.FalseConsensus.related_work import certaindex_mid


def row(
    problem_id: int,
    *,
    correct: bool,
    baseline_correct: bool,
    stopped: bool = True,
) -> dict:
    return {
        "method": "deer_frozen",
        "model": "model-a",
        "dataset": "math500",
        "base_seed": 42,
        "problem_id": problem_id,
        "split": "test" if problem_id == 4 else "train",
        "correct": correct,
        "baseline_correct": baseline_correct,
        "stopped": stopped,
        "all_generated_tokens": 50,
        "baseline_all_generated_tokens": 100,
    }


class FalseStopAnalysisTest(unittest.TestCase):
    def test_direction_counts_and_false_stop_denominator(self) -> None:
        rows = [
            row(1, correct=False, baseline_correct=True),   # harm
            row(2, correct=True, baseline_correct=False),   # rescue
            row(3, correct=True, baseline_correct=True),
            row(4, correct=False, baseline_correct=False),  # persistent wrong
            row(5, correct=True, baseline_correct=True, stopped=False),
        ]
        summary = summarize(rows)
        self.assertEqual(summary["stopped"], 4)
        self.assertEqual(summary["false_stops"], 2)
        self.assertEqual(summary["harm"], 1)
        self.assertEqual(summary["rescue"], 1)
        self.assertEqual(summary["both_correct"], 1)
        self.assertEqual(summary["both_wrong"], 1)
        self.assertAlmostEqual(summary["false_stop_rate_given_stop"], 0.5)
        self.assertAlmostEqual(summary["harm_rescue_ratio"], 1.0)
        self.assertAlmostEqual(summary["all_generated_token_saving"], 0.5)

    def test_analysis_pools_split_labels(self) -> None:
        rows = [
            row(1, correct=False, baseline_correct=True),
            row(4, correct=True, baseline_correct=True),
        ]
        result = analyze(rows)
        self.assertEqual(result["scope"]["rows"], 2)
        self.assertNotIn("split", result["methods"]["deer_frozen"])


def probe(position: int, answer: str, *, certain: bool = True, out: int = 10) -> dict:
    return {
        "token_position": position,
        "probe_id": position // 64,
        "probe_answer": answer,
        "is_certain": certain,
        "probe_out_tokens": out,
        "probe_prompt_tokens": 100,
        "probe_latency_seconds": 0.1,
    }


def trajectory(
    *,
    tokens: int = 2000,
    target: str = "5",
    final: str = "5",
    finished: bool = True,
    budget: int = 16384,
) -> dict:
    return {
        "run_settings": {
            "model": "M",
            "dataset": "math500",
            "base_seed": 42,
            "budget": budget,
        },
        "problem_id": 0,
        "tokens_used": tokens,
        "finished_naturally": finished,
        "final_answer": final,
        "final_correct": final == target,
        "target": target,
        "model": "M",
        "dataset": "math500",
        "base_seed": 42,
    }


def fake_equal_group(answers) -> bool:
    values = [answer.strip() for answer in answers if answer]
    return len(values) == len(answers) and len(set(values)) == 1


def fake_count_not_empty(answers) -> int:
    return sum(1 for answer in answers if answer)


def fake_grade(delivered, target) -> bool:
    return bool(delivered) and delivered.strip() == str(target).strip()


def replay(traj: dict, probes: list[dict]) -> dict:
    return certaindex_mid.replay(
        traj,
        probes,
        patience=3,
        answers_equal_fn=fake_equal_group,
        count_not_empty_fn=fake_count_not_empty,
        answers_equal_target_fn=fake_grade,
    )


class CertaIndexReplayTest(unittest.TestCase):
    def test_stop_delivers_window_answer_and_excludes_future_main_tokens(self) -> None:
        probes = [
            probe(64, "5", out=10),
            probe(128, "5", out=12),
            probe(192, "5", out=8),
            probe(256, "5", out=20),
        ]
        result = replay(trajectory(), probes)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["stop_position"], 192)
        self.assertEqual(result["delivered_answer"], "5")
        self.assertTrue(result["correct"])
        self.assertTrue(result["baseline_correct"])
        self.assertEqual(result["probe_out_tokens"], 50)
        self.assertEqual(result["all_generated_tokens"], 242)

    def test_no_stop_delivers_frozen_full_answer(self) -> None:
        result = replay(
            trajectory(tokens=2000, final="5", target="5"),
            [probe(64, "5"), probe(128, "6")],
        )
        self.assertFalse(result["stopped"])
        self.assertEqual(result["delivered_answer"], "5")
        self.assertTrue(result["correct"])

    def test_no_stop_capped_trajectory_has_no_deliverable_answer(self) -> None:
        result = replay(
            trajectory(tokens=2000, final="", target="5", finished=False),
            [probe(64, "5"), probe(128, "6")],
        )
        self.assertFalse(result["stopped"])
        self.assertEqual(result["delivered_answer"], "")
        self.assertFalse(result["correct"])

    def test_harm_when_stop_breaks_correct_baseline(self) -> None:
        probes = [probe(64, "6"), probe(128, "6"), probe(192, "6")]
        result = replay(trajectory(final="5", target="5"), probes)
        self.assertTrue(result["stopped"])
        self.assertTrue(result["baseline_correct"])
        self.assertFalse(result["correct"])

    def test_rescue_when_stop_fixes_wrong_baseline(self) -> None:
        probes = [probe(64, "5"), probe(128, "5"), probe(192, "5")]
        result = replay(trajectory(final="6", target="5"), probes)
        self.assertTrue(result["stopped"])
        self.assertFalse(result["baseline_correct"])
        self.assertTrue(result["correct"])


if __name__ == "__main__":
    unittest.main()
