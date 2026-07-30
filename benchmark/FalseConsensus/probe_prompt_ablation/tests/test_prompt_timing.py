#!/usr/bin/env python3
"""Tests for the Simple@32 vs CertaIndex@32 prompt-timing ablation.

Hermetic (no GPU/server/sympy): protocol validity, environment enumeration,
the shared patience-3 stop rule, consumed-probe accounting, and the
Harm/Rescue + consensus-delay paired logic. Equivalence and grading are
injected as fakes so these run with the stdlib-only import graph.
"""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from benchmark.FalseConsensus.probe_prompt_ablation import (  # noqa: E402
    run_certaindex32 as rc, analyze_prompt_timing as apt)
from benchmark.FalseConsensus.related_work import certaindex_mid  # noqa: E402

PC = REPO / "benchmark/FalseConsensus/probe_prompt_ablation"
CI_SHA = "c3c5fe2d9ab1d28fd0be92c2316e90475142ef6ce8d23c1033764b2445401968"
SI_SHA = "1ca95d91a95141e1a735117f1efcc3440c2fc554ab510f7089da0a2b607d4895"


def probe(pos, ans, certain=True, out=10, prompt=100):
    return {"token_position": pos, "probe_id": pos // 64, "probe_answer": ans,
            "is_certain": certain, "probe_out_tokens": out,
            "probe_prompt_tokens": prompt, "probe_latency_seconds": 0.1}


def traj(tokens=2000, target="5", final="5", finished=True, budget=16384):
    return {"run_settings": {"model": "M", "dataset": "math500",
                             "base_seed": 42, "budget": budget},
            "problem_id": 0, "tokens_used": tokens,
            "finished_naturally": finished, "final_answer": final,
            "final_correct": (final == target), "target": target}


# ---- fake equivalence + grader (no sympy) ----
def fake_eqaul_group(answers):
    # all non-empty and string-equal (stripped) -> one class
    vals = [a.strip() for a in answers if a]
    return len(vals) == len(answers) and len(set(vals)) == 1


def fake_count_not_empty(answers):
    return sum(1 for a in answers if a)


def fake_grade(delivered, target):
    return bool(delivered) and delivered.strip() == str(target).strip()


class TestProtocol(unittest.TestCase):
    def test_protocol_valid_and_settings(self):
        d = json.loads((PC / "protocol.json").read_text())
        self.assertEqual(d["probe_settings"], {"cap": 32, "interval": 64,
                         "start_token": 64, "patience": 3, "temperature": 0.6,
                         "top_p": 0.95, "stop": "\\]",
                         "probe_seed_policy": "base_seed (prompt-matched to the frozen main run)"})
        self.assertEqual(d["frozen_scope"]["paired_trajectories_per_arm"], 3420)
        self.assertEqual(d["frozen_scope"]["partial_environments_per_arm"], 36)
        self.assertEqual(d["design"]["arms"]["certaindex"]["suffix_sha256"], CI_SHA)
        self.assertEqual(d["design"]["arms"]["simple"]["suffix_sha256"], SI_SHA)
        self.assertEqual(len(d["frozen_scope"]["models"]), 2)

    def test_suffix_hashes_match_common(self):
        from benchmark.FalseConsensus.related_work import common
        self.assertEqual(common.sha256_bytes(common.CERTAINDEX_SUFFIX.encode()), CI_SHA)
        self.assertEqual(common.sha256_bytes(common.SIMPLE_SUFFIX.encode()), SI_SHA)


class TestEnvEnumeration(unittest.TestCase):
    def test_18_envs_per_model_36_total(self):
        ds = rc.envs_for(rc.MODELS["deepseek"]["slug"])
        qn = rc.envs_for(rc.MODELS["qwen3"]["slug"])
        self.assertEqual(len(ds), 18)
        self.assertEqual(len(qn), 18)
        self.assertEqual(len(set(ds) | set(qn)), 36)
        # 6 seeds per (model,benchmark): 42,43,44 + 45,46,47
        seeds = {e.split("seed_")[1] for e in ds if "math500" in e}
        self.assertEqual(seeds, {"42", "43", "44", "45", "46", "47"})

    def test_revisions_pinned(self):
        self.assertEqual(rc.MODELS["deepseek"]["revision"],
                         "916b56a44061fd5cd7d6a8fb632557ed4f724f60")
        self.assertEqual(rc.MODELS["qwen3"]["revision"],
                         "b968826d9c46dd6066d109eabc6255188de91218")


class TestStopRule(unittest.TestCase):
    def test_three_consecutive_equal_certain_stops(self):
        ps = [probe(64, "5"), probe(128, "5"), probe(192, "5"), probe(256, "5")]
        d = certaindex_mid.decide_stop(ps, patience=3,
                                       answers_equal_fn=fake_eqaul_group,
                                       count_not_empty_fn=fake_count_not_empty)
        self.assertIsNotNone(d)
        self.assertEqual(d["stop_position"], 192)  # window ends at 3rd probe

    def test_uncertain_window_is_skipped_later_certain_window_stops(self):
        # first window (64,128,192) is uncertain -> skipped; second window
        # (128,192,256) all-certain -> stop at 256
        ps = [probe(64, "5", certain=False), probe(128, "5", certain=True),
              probe(192, "5", certain=True), probe(256, "5", certain=True)]
        d = certaindex_mid.decide_stop(ps, patience=3,
                                       answers_equal_fn=fake_eqaul_group,
                                       count_not_empty_fn=fake_count_not_empty)
        self.assertIsNotNone(d)
        self.assertEqual(d["stop_position"], 256)

    def test_no_consensus_no_stop(self):
        ps = [probe(64, "5"), probe(128, "6"), probe(192, "7")]
        d = certaindex_mid.decide_stop(ps, patience=3,
                                       answers_equal_fn=fake_eqaul_group,
                                       count_not_empty_fn=fake_count_not_empty)
        self.assertIsNone(d)


class TestArmReplayAccounting(unittest.TestCase):
    def _r(self, t, ps):
        return apt.arm_replay(t, ps, answers_equal_fn=fake_eqaul_group,
                              grade_fn=fake_grade)

    def test_stop_excludes_future_probes_from_consumed_tax(self):
        ps = [probe(64, "5", out=10), probe(128, "5", out=12),
              probe(192, "5", out=8), probe(256, "5", out=20)]
        r = self._r(traj(), ps)
        self.assertTrue(r["stopped"])
        self.assertEqual(r["stop_position"], 192)
        self.assertEqual(r["n_consumed_probes"], 3)  # up to stop window
        self.assertEqual(r["probe_out_tokens"], 10 + 12 + 8)
        self.assertEqual(r["all_generated_tokens"], 192 + 30)
        self.assertEqual(r["main_tokens_through_stop"], 192)
        self.assertTrue(r["correct"])

    def test_no_stop_consumes_all_probes_full_main(self):
        ps = [probe(64, "5"), probe(128, "6")]  # no 3-consensus
        r = self._r(traj(tokens=2000, final="5", target="5"), ps)
        self.assertFalse(r["stopped"])
        self.assertEqual(r["main_tokens_through_stop"], 2000)
        self.assertEqual(r["n_consumed_probes"], 2)
        self.assertEqual(r["all_generated_tokens"], 2000 + 20)


class TestPairedHarmRescue(unittest.TestCase):
    """Exercise the paired Harm/Rescue/delay definitions via _summarize."""

    def _row(self, s_stop, s_correct, c_stop, c_correct, baseline, full=2000,
             s_pos=192, c_pos=320):
        return {"model": "M", "benchmark": "math500", "seed": 42,
                "simple_stopped": s_stop, "simple_correct": s_correct,
                "simple_stop_position": s_pos if s_stop else None,
                "certaindex_stopped": c_stop, "certaindex_correct": c_correct,
                "certaindex_stop_position": c_pos if c_stop else None,
                "baseline_correct": baseline, "full_main_tokens": full,
                "both_stop": s_stop and c_stop,
                "consensus_delay": (c_pos - s_pos) if (s_stop and c_stop) else None,
                "simple_only_stop": s_stop and not c_stop,
                "certaindex_only_stop": c_stop and not s_stop,
                "neither_stop": (not s_stop) and (not c_stop),
                "simple_harm": baseline and not s_correct,
                "simple_rescue": (not baseline) and s_correct,
                "certaindex_harm": baseline and not c_correct,
                "certaindex_rescue": (not baseline) and c_correct,
                "certaindex_corrects_simple": (not s_correct) and c_correct,
                "certaindex_breaks_simple": s_correct and (not c_correct),
                "simple_harms_protected_by_certaindex": (baseline and not s_correct) and c_correct,
                "new_harms_introduced_by_certaindex": (baseline and not c_correct) and s_correct,
                "certaindex_later": (s_stop and c_stop) and (c_pos > s_pos),
                "certaindex_earlier": (s_stop and c_stop) and (c_pos < s_pos),
                "certaindex_same": (s_stop and c_stop) and (c_pos == s_pos),
                "simple_main_tokens": s_pos if s_stop else full,
                "simple_probe_out": 30, "simple_all_generated": (s_pos if s_stop else full) + 30,
                "simple_n_probes": 3,
                "certaindex_main_tokens": c_pos if c_stop else full,
                "certaindex_probe_out": 30, "certaindex_all_generated": (c_pos if c_stop else full) + 30,
                "certaindex_n_probes": 3,
                "simple_delivered": "5", "certaindex_delivered": "5"}

    def test_harm_rescue_and_delay_counts(self):
        rows = [
            # Simple harms (baseline correct, Simple wrong) but CertaIndex correct: protected
            self._row(True, False, True, True, True),
            # CertaIndex breaks Simple (Simple correct, CertaIndex wrong, baseline correct)
            self._row(True, True, True, False, True),
            # CertaIndex corrects Simple (Simple wrong, CertaIndex correct, baseline wrong)
            self._row(True, False, True, True, False, s_pos=192, c_pos=320),
            # both stop, CertaIndex later
            self._row(True, True, True, True, True, s_pos=192, c_pos=320),
        ]
        s = apt._summarize(rows, [(m, b, sd) for m, b, sd in
                                  [("M", "math500", 42)] * len(rows)])
        pr = s["pooled"]["paired"]
        self.assertEqual(pr["n_simple_harms_protected_by_certaindex"], 1)
        self.assertEqual(pr["n_new_harms_introduced_by_certaindex"], 1)
        self.assertEqual(pr["n_certaindex_corrects_simple"], 2)  # rows 1 & 3
        self.assertEqual(pr["n_certaindex_breaks_simple"], 1)  # row 2
        self.assertGreater(pr["certaindex_later"], 0.0)
        self.assertEqual(pr["mean_consensus_delay"], 128)  # 128,128,128 over 3 both-stop


if __name__ == "__main__":
    unittest.main(verbosity=2)
