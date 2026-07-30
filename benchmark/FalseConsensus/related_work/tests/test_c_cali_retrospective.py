from __future__ import annotations

import math
import unittest

from benchmark.FalseConsensus.related_work.analyze_c_cali_retrospective import (
    first_official_stop,
    geometric_mean,
    mean_absolute_deviation,
    token_probabilities,
)


class CCaliRetrospectiveTest(unittest.TestCase):
    def test_token_probabilities_skip_first_token(self) -> None:
        trial = {
            "logprobs": [
                {"token": "{", "logprob": math.log(0.5)},
                {"token": "4", "logprob": math.log(0.8)},
                {"token": "2", "logprob": math.log(0.6)},
            ]
        }
        self.assertEqual(len(token_probabilities(trial)), 2)
        self.assertAlmostEqual(token_probabilities(trial)[0], 0.8)
        self.assertAlmostEqual(token_probabilities(trial)[1], 0.6)

    def test_mad_and_geometric_mean(self) -> None:
        self.assertAlmostEqual(mean_absolute_deviation([0.8, 0.6]), 0.1)
        self.assertAlmostEqual(geometric_mean([0.8, 0.6]), math.sqrt(0.48))

    def test_first_official_stop_is_strict(self) -> None:
        trials = [
            {"candidate_id": 1, "confidence": 0.95},
            {"candidate_id": 2, "confidence": 0.951},
        ]
        self.assertEqual(first_official_stop(trials)["candidate_id"], 2)


if __name__ == "__main__":
    unittest.main()
