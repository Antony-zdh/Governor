from __future__ import annotations

import unittest

from benchmark.FalseConsensus.probe_prompt_ablation.analyze_prompt_timing import (
    paired_diagnostics,
)


def row(
    method: str,
    problem_id: int,
    *,
    stopped: bool,
    stop_position: int | None,
    correct: bool,
    baseline_correct: bool,
) -> dict:
    return {
        "method": method,
        "model": "model-a",
        "dataset": "math500",
        "base_seed": 42,
        "problem_id": problem_id,
        "stopped": stopped,
        "stop_position": stop_position,
        "correct": correct,
        "baseline_correct": baseline_correct,
    }


class PromptTimingDiagnosticsTest(unittest.TestCase):
    def test_delay_and_protected_harm(self) -> None:
        simple = [
            row(
                "simple",
                1,
                stopped=True,
                stop_position=192,
                correct=False,
                baseline_correct=True,
            ),
            row(
                "simple",
                2,
                stopped=True,
                stop_position=320,
                correct=True,
                baseline_correct=True,
            ),
        ]
        certa = [
            row(
                "certa",
                1,
                stopped=True,
                stop_position=384,
                correct=True,
                baseline_correct=True,
            ),
            row(
                "certa",
                2,
                stopped=False,
                stop_position=None,
                correct=True,
                baseline_correct=True,
            ),
        ]
        result = paired_diagnostics(simple, certa)
        self.assertEqual(result["certa_later"], 1)
        self.assertEqual(result["simple_only_stop"], 1)
        self.assertEqual(result["simple_harms_protected"], 1)
        self.assertEqual(result["certa_corrects_simple"], 1)
        self.assertEqual(result["mean_delay_tokens_when_both_stop"], 192)


if __name__ == "__main__":
    unittest.main()
