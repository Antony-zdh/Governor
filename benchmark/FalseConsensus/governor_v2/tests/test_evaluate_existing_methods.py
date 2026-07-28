from __future__ import annotations

import unittest

from benchmark.FalseConsensus.governor_v2.evaluate_existing_methods import (
    decide_stop,
    scheduled_dense_probes,
)


def probe(position: int, answer: str, *, certain: bool = True) -> dict:
    return {
        "token_position": position,
        "probe_answer": answer,
        "is_certain": certain,
        "probe_out_tokens": 4,
        "probe_prompt_tokens": position,
    }


class ExistingGovernorReplayTests(unittest.TestCase):
    def test_dense_stream_is_exactly_downsampled_to_original_schedule(self):
        payload = {
            "probes": [
                probe(64, "1"),
                probe(128, "1"),
                probe(192, "1"),
                probe(256, "1"),
                probe(320, "1"),
            ]
        }
        selected = scheduled_dense_probes(payload, 300)
        self.assertEqual([item["token_position"] for item in selected], [128, 256])

    def test_uncertain_probe_invalidates_the_consecutive_window(self):
        probes = [
            probe(128, "7"),
            probe(256, "7", certain=False),
            probe(384, "7"),
            probe(512, "7"),
            probe(640, "7"),
        ]
        config = {
            "family": "consecutive",
            "patience": 3,
            "floor_kind": "fixed",
            "easy_min": 0,
            "hard_min": 0,
            "require_certain": True,
            "validity_mode": "schema",
        }
        trajectory = {"level": 0}
        self.assertEqual(decide_stop(probes, config, trajectory, "amc23"), 4)

    def test_non_numeric_nonmath_answer_invalidates_the_window(self):
        probes = [probe(128, "A"), probe(256, "A"), probe(384, "A")]
        config = {
            "family": "consecutive",
            "patience": 3,
            "floor_kind": "fixed",
            "easy_min": 0,
            "hard_min": 0,
            "require_certain": False,
            "validity_mode": "schema",
        }
        self.assertIsNone(decide_stop(probes, config, {"level": 0}, "aime24"))


if __name__ == "__main__":
    unittest.main()
