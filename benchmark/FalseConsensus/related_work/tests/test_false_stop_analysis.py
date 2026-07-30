#!/usr/bin/env python3
"""Tests for the false-stop / Harm-Rescue accounting that the prompt-timing
ablation analysis builds on. Validates ``certaindex_mid.replay`` (the shared
replay used by both arms) with injected equivalence and grading, so it runs
without sympy/server.
"""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.related_work import certaindex_mid  # noqa: E402


def probe(pos, ans, certain=True, out=10):
    return {"token_position": pos, "probe_id": pos // 64, "probe_answer": ans,
            "is_certain": certain, "probe_out_tokens": out,
            "probe_prompt_tokens": 100, "probe_latency_seconds": 0.1}


def traj(tokens=2000, target="5", final="5", finished=True, budget=16384):
    return {"run_settings": {"model": "M", "dataset": "math500",
                             "base_seed": 42, "budget": budget},
            "problem_id": 0, "tokens_used": tokens,
            "finished_naturally": finished, "final_answer": final,
            "final_correct": (final == target), "target": target,
            "model": "M", "dataset": "math500", "base_seed": 42}


def fake_eqaul_group(answers):
    vals = [a.strip() for a in answers if a]
    return len(vals) == len(answers) and len(set(vals)) == 1


def fake_count_not_empty(answers):
    return sum(1 for a in answers if a)


def fake_grade(delivered, target):
    return bool(delivered) and delivered.strip() == str(target).strip()


def replay(t, ps):
    return certaindex_mid.replay(t, ps, patience=3,
                                 answers_equal_fn=fake_eqaul_group,
                                 count_not_empty_fn=fake_count_not_empty,
                                 answers_equal_target_fn=fake_grade)


class TestFalseStopReplay(unittest.TestCase):
    def test_stop_delivers_window_answer_and_excludes_future_cost(self):
        ps = [probe(64, "5", out=10), probe(128, "5", out=12),
              probe(192, "5", out=8), probe(256, "5", out=20)]
        r = replay(traj(), ps)
        self.assertTrue(r["stopped"])
        self.assertEqual(r["stop_position"], 192)
        self.assertEqual(r["delivered_answer"], "5")
        self.assertTrue(r["correct"])
        self.assertTrue(r["baseline_correct"])
        # replay sums ALL probe out tokens (full bank); the analysis truncates
        # consumed tax separately, but the no-stop/full-bank accounting must hold
        self.assertEqual(r["probe_out_tokens"], 10 + 12 + 8 + 20)
        self.assertEqual(r["all_generated_tokens"], 192 + (10 + 12 + 8 + 20))

    def test_no_stop_delivers_frozen_full_answer(self):
        ps = [probe(64, "5"), probe(128, "6")]  # no 3-consensus
        r = replay(traj(tokens=2000, final="5", target="5"), ps)
        self.assertFalse(r["stopped"])
        self.assertEqual(r["delivered_answer"], "5")
        self.assertTrue(r["correct"])

    def test_no_stop_capped_trajectory_no_deliverable(self):
        ps = [probe(64, "5"), probe(128, "6")]
        r = replay(traj(tokens=2000, final="", target="5", finished=False), ps)
        self.assertFalse(r["stopped"])
        self.assertEqual(r["delivered_answer"], "")  # right-censored
        self.assertFalse(r["correct"])

    def test_harm_when_stop_breaks_correct_baseline(self):
        # baseline correct (final=5, target=5); stop delivers wrong (6)
        ps = [probe(64, "6", out=10), probe(128, "6", out=10), probe(192, "6", out=10)]
        r = replay(traj(tokens=2000, final="5", target="5"), ps)
        self.assertTrue(r["stopped"])
        self.assertTrue(r["baseline_correct"])
        self.assertFalse(r["correct"])  # harm: correct baseline -> wrong delivered

    def test_rescue_when_stop_saves_wrong_baseline(self):
        # baseline wrong (final=6 != target=5); stop delivers correct (5)
        ps = [probe(64, "5", out=10), probe(128, "5", out=10), probe(192, "5", out=10)]
        r = replay(traj(tokens=2000, final="6", target="5"), ps)
        self.assertTrue(r["stopped"])
        self.assertFalse(r["baseline_correct"])
        self.assertTrue(r["correct"])  # rescue: wrong baseline -> correct delivered


if __name__ == "__main__":
    unittest.main(verbosity=2)
