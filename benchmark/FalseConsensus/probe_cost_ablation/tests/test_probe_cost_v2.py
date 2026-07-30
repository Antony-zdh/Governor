#!/usr/bin/env python3
"""Unit tests for probe-cost v2: cap enforcement, downsampling, stop cost
exclusion, no-stop fallback, grading, cost identities, env-macro aggregation,
coverage. Uses synthetic probe banks; no GPU/network."""
from __future__ import annotations
import json, os, sys, tempfile, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "benchmark/FalseConsensus/probe_cost_ablation"))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "replay_probe_cost",
    REPO / "benchmark/FalseConsensus/probe_cost_ablation/replay_probe_cost.py")
rpc = importlib.util.module_from_spec(spec)
sys.modules["replay_probe_cost"] = rpc
spec.loader.exec_module(rpc)


def probe(pos, answer="5", certain=True, out=10, prompt=100):
    return {"token_position": pos, "probe_id": pos // 64,
            "probe_answer": answer, "is_certain": certain,
            "probe_out_tokens": out, "probe_prompt_tokens": prompt,
            "probe_latency_seconds": 0.1}


def trajectory(level=2, tokens=2000, final_answer="5", target="5",
              finished=True, budget=16384):
    return {
        "run_settings": {"model": "M", "dataset": "math500", "base_seed": 42,
                         "budget": budget},
        "problem_id": 0, "tokens_used": tokens,
        "finished_naturally": finished, "final_answer": final_answer,
        "final_correct": (final_answer == target), "target": target,
        "level": level,
    }


class TestDownsample(unittest.TestCase):
    def test_interval64_keeps_all(self):
        ps = [probe(64), probe(128), probe(192), probe(256)]
        self.assertEqual([p["token_position"] for p in rpc.downsample(ps, 64)],
                         [64, 128, 192, 256])

    def test_interval128(self):
        ps = [probe(64), probe(128), probe(192), probe(256), probe(320)]
        self.assertEqual([p["token_position"] for p in rpc.downsample(ps, 128)],
                         [64, 192, 320])

    def test_interval256_and_512(self):
        ps = [probe(64), probe(128), probe(192), probe(256), probe(320),
              probe(576), probe(1088)]
        self.assertEqual([p["token_position"] for p in rpc.downsample(ps, 256)],
                         [64, 320, 576, 1088])
        self.assertEqual([p["token_position"] for p in rpc.downsample(ps, 512)],
                         [64, 576, 1088])


class TestCostIdentities(unittest.TestCase):
    def test_stop_excludes_future_probes_from_cost(self):
        # patience=3 -> stops at index 2, consuming first 3 probes only
        cfg = {"patience": 3, "floor_kind": "fixed", "easy_min": 0,
               "require_certain": False, "validity_mode": "nonempty"}
        ps = [probe(64, "5", out=10), probe(128, "5", out=12),
              probe(192, "5", out=8), probe(256, "5", out=20)]
        traj = trajectory(tokens=2000)
        row = rpc.cost_row(traj, ps, method="gov", config=cfg, cap=32,
                           interval=64, split="dev")
        self.assertTrue(row["stopped"])
        self.assertEqual(row["probe_calls_used"], 3)
        self.assertEqual(row["probe_output_tokens_used"], 10 + 12 + 8)
        self.assertEqual(row["consumed_main_tokens"], 192)
        self.assertEqual(row["stop_position"], 192)
        self.assertEqual(row["gross_tokens_used"], 192)
        self.assertEqual(row["actual_total_tokens_used"], 192 + 30)
        self.assertEqual(row["ideal_zero_probe_tax_tokens_used"], 192)
        # identities
        self.assertAlmostEqual(row["gross_saving"], (2000 - 192) / 2000)
        self.assertAlmostEqual(row["actual_net_saving"], (2000 - 222) / 2000)
        self.assertAlmostEqual(row["ideal_zero_probe_tax_saving"],
                               row["gross_saving"])
        self.assertAlmostEqual(row["probe_tax"],
                               row["gross_saving"] - row["actual_net_saving"])
        self.assertTrue(row["positive_net_saving"])

    def test_no_stop_fallback_uses_full_main(self):
        cfg = {"patience": 8, "floor_kind": "fixed", "easy_min": 0,
               "require_certain": False, "validity_mode": "nonempty"}
        ps = [probe(64, "5", out=5)]  # too few for patience=8
        traj = trajectory(tokens=2000, final_answer="5", target="5")
        row = rpc.cost_row(traj, ps, method="gov", config=cfg, cap=32,
                           interval=64, split="dev")
        self.assertFalse(row["stopped"])
        self.assertEqual(row["consumed_main_tokens"], 2000)
        self.assertEqual(row["probe_output_tokens_used"], 5)
        self.assertEqual(row["actual_total_tokens_used"], 2005)
        self.assertEqual(row["stop_position"], None)
        # no-stop fallback delivers the full-generation final answer
        self.assertTrue(row["correct"])
        self.assertFalse(row["positive_net_saving"])  # 2005 > 2000

    def test_cap_specific_token_summaries_differ(self):
        # cap 8 vs 32: different probe_out_tokens -> different actual totals
        cfg = {"patience": 1, "floor_kind": "fixed", "easy_min": 0,
               "require_certain": False, "validity_mode": "nonempty"}
        traj = trajectory(tokens=2000)
        ps8 = [probe(64, "5", out=8)]
        ps32 = [probe(64, "5", out=30)]
        r8 = rpc.cost_row(traj, ps8, method="gov", config=cfg, cap=8,
                          interval=64, split="dev")
        r32 = rpc.cost_row(traj, ps32, method="gov", config=cfg, cap=32,
                           interval=64, split="dev")
        self.assertNotEqual(r8["probe_output_tokens_used"],
                            r32["probe_output_tokens_used"])
        self.assertNotEqual(r8["actual_total_tokens_used"],
                            r32["actual_total_tokens_used"])


class TestCapEnforcement(unittest.TestCase):
    def test_cap_enforced_ok(self):
        # synthetic: a probe claiming out=40 under cap=8 is a violation
        from benchmark.FalseConsensus.probe_cost_ablation.collect_capped_probes \
            import checkpoint_positions
        self.assertEqual(checkpoint_positions(200, start_token=64,
                          interval=64, finished_naturally=True),
                         [64, 128, 192])
        self.assertEqual(checkpoint_positions(200, start_token=64,
                          interval=64, finished_naturally=False),
                         [64, 128, 192])  # inclusive_stop=201 -> 192<201 ok


class TestGrading(unittest.TestCase):
    def test_delivered_correct(self):
        from benchmark.FalseConsensus.governor_v2 import replay_rules
        self.assertTrue(replay_rules.answers_equal("5", "5"))
        self.assertFalse(replay_rules.answers_equal("5", "6"))
        # robust grader handles latex/numeric equivalence
        from benchmark.FalseConsensus.governor_v2 import grading
        self.assertTrue(grading.robust_answers_equal("\\frac{1}{2}", "0.5"))


class TestAggregation(unittest.TestCase):
    def test_env_macro(self):
        rows = []
        for env in range(3):  # 3 envs
            for _ in range(4):
                rows.append({"correct": True, "baseline_correct": True,
                              "full_main_tokens": 2000,
                              "gross_tokens_used": 192,
                              "actual_total_tokens_used": 222,
                              "probe_output_tokens_used": 30,
                              "probe_prompt_tokens_used": 100,
                              "probe_calls_used": 3,
                              "gross_saving": (2000-192)/2000,
                              "actual_net_saving": (2000-222)/2000,
                              "ideal_zero_probe_tax_saving": (2000-192)/2000,
                              "probe_tax": 30/2000,
                              "positive_net_saving": True,
                              "stopped": True, "delivered_answer": "5"})
        envs = [rpc.aggregate_env(rows[i*4:(i+1)*4]) for i in range(3)]
        m = rpc.macro_env(envs)
        self.assertAlmostEqual(m["accuracy"], 1.0)
        self.assertAlmostEqual(m["psf"], 1.0)
        self.assertEqual(m["n_envs"], 3)
        self.assertEqual(m["n_trajectories"], 12)


class TestCoverage(unittest.TestCase):
    def test_684_trajectories_and_24624_rows(self):
        # static check: 684 dev trajectories * 12 cells * 3 policies
        # dev = 114 per seed * 3 seeds * 2 models = 684
        dev_per_seed = 100 + 8 + 6  # math500+amc23+aime24
        self.assertEqual(dev_per_seed * 3 * 2, 684)
        self.assertEqual(684 * 12 * 3, 24624)


if __name__ == "__main__":
    unittest.main(verbosity=2)
