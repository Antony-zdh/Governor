from __future__ import annotations

import unittest

from benchmark.FalseConsensus.related_work.analyze_false_stops import (
    analyze,
    summarize,
)


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


if __name__ == "__main__":
    unittest.main()
