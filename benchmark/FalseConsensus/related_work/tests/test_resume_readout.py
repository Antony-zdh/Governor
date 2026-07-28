"""Regression tests proving BOTH invariants:
1. A fully recorded readout with readout_valid=False, finish_reason=stop/length,
   no error, no context flags — is resume-complete (skipped by resume/progress)
   but replay STILL counts it in invalid_aux_responses, delivers empty, and
   grades incorrect.
2. error/null/unknown-finish/context-flags/malformed-rows remain corrupt for
   resume (regeneration-worthy) and invalid for progress."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.related_work import common, tje, deer, certaindex_mid  # noqa


def _str_eq_group(answers):
    return len(set(answers)) <= 1


def _str_eq_target(answer, target):
    return str(answer).strip() == str(target).strip()


class ResumeReadoutValidationTests(unittest.TestCase):
    """Tests for the _readout_is_corrupt logic embedded in TJE/DEER resume."""

    def _tje_record(self, pid=1, readout=None):
        return {
            "schema_version": "related-work-tje-trigger-1",
            "problem_id": pid,
            "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
            "dataset": "math500", "base_seed": 42,
            "triggers": [{"trigger_id": 1, "trigger_type": "wait"}],
            "readout": readout,
        }

    def _write(self, td, pid, d):
        p = Path(td) / f"problem_{pid}.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    # -- Invariant 1: capped/natural invalid readout is resume-complete --
    def test_capped_invalid_readout_stop_finish_is_resume_complete(self):
        """readout_valid=False, finish_reason=stop, no error/overflow = complete."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "stop",
                         "readout_context_overflow": False,
                         "readout_context_budget_exceeded": False}))
            self.assertTrue(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_capped_invalid_readout_length_finish_is_resume_complete(self):
        """readout_valid=False, finish_reason=length, no error/overflow = complete."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "length",
                         "readout_context_overflow": False,
                         "readout_context_budget_exceeded": False}))
            self.assertTrue(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_missing_readout_is_resume_complete(self):
        """No readout = valid (no-stop/no-exit)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(readout=None))
            self.assertTrue(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    # -- Invariant 1b: replay STILL counts invalid readout in invalid_aux --
    def test_replay_counts_invalid_readout_in_invalid_aux(self):
        """Replay must still count readout_valid=False in invalid_aux_responses,
        deliver empty answer, and grade incorrect — even though resume skips it."""
        traj = {"tokens_used": 1000, "finished_naturally": True,
                "final_answer": "42", "final_correct": True, "target": "42",
                "run_settings": {"budget": 32768},
                "problem_id": 1, "dataset": "math500",
                "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "base_seed": 42}
        triggers = [{"trigger_id": 1, "trigger_type": "wait",
                      "token_position": 64, "confidence_label": "Almost certain",
                      "meets_threshold": True, "confidence_out_tokens": 5,
                      "confidence_prompt_tokens": 100,
                      "confidence_finish_reason": "stop",
                      "confidence_latency_seconds": 0.1, "retry_count": 0}]
        readout = {"readout_answer": "", "readout_valid": False,
                   "readout_truncated": True, "readout_completed_boxed": False,
                   "readout_finish_reason": "length",
                   "readout_context_overflow": False,
                   "readout_context_budget_exceeded": False,
                   "readout_out_tokens": 8192,
                   "readout_prompt_tokens": 200,
                   "readout_latency_seconds": 5.0,
                   "at_trigger_id": 1, "retry_count": 0}
        result = tje.replay(traj, triggers, readout=readout,
                           answers_equal_target_fn=_str_eq_target)
        self.assertTrue(result["stopped"])
        self.assertEqual(result["delivered_answer"], "")
        self.assertFalse(result["correct"])  # empty answer with grader = incorrect, not None
        self.assertGreater(result.get("invalid_aux_responses", 0), 0,
                           "invalid_aux_responses must be > 0 for invalid readout")

    # -- Invariant 1c: CertaIndex empty delivery with grader => False --
    def test_certaindex_empty_delivery_with_grader_is_false(self):
        """CertaIndex no-stop + no natural answer + grader => correct=False."""
        traj = {"tokens_used": 1000, "finished_naturally": False,
                "final_answer": "", "final_correct": False, "target": "42",
                "run_settings": {"budget": 32768},
                "problem_id": 1, "dataset": "math500",
                "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "base_seed": 42}
        probes = [{"probe_id": 1, "token_position": 64,
                   "probe_answer": "a", "is_certain": True},
                  {"probe_id": 2, "token_position": 128,
                   "probe_answer": "b", "is_certain": True}]
        result = certaindex_mid.replay(
            traj, probes, answers_equal_fn=_str_eq_group,
            answers_equal_target_fn=_str_eq_target)
        self.assertEqual(result["delivered_answer"], "")
        self.assertFalse(result["correct"])  # empty + grader = False, not None

    # -- Invariant 1d: DEER empty delivery with grader => False --
    def test_deer_empty_delivery_with_grader_is_false(self):
        """DEER no early exit + no natural answer + grader => correct=False."""
        traj = {"tokens_used": 1000, "finished_naturally": False,
                "final_answer": "", "final_correct": False, "target": "42",
                "run_settings": {"budget": 32768},
                "problem_id": 1, "dataset": "math500",
                "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "base_seed": 42}
        trials = [{"candidate_id": 1, "token_position": 64,
                    "confidence": 0.3, "policy": "avg1",
                    "last_token_decoded": " more", "think_close_emitted": False,
                    "meets_threshold": False, "trial_out_tokens": 10,
                    "trial_prompt_tokens": 100}]
        result = deer.replay(traj, trials, answers_equal_target_fn=_str_eq_target)
        self.assertEqual(result["delivered_answer"], "")
        self.assertFalse(result["correct"])  # empty + grader = False, not None

    # -- Invariant 1e: aggregate n_graded == n when grader supplied --
    def test_aggregate_n_graded_equals_n_with_grader(self):
        """When replay uses a grader, every row has boolean correct, so
        aggregate n_graded must equal n."""
        from benchmark.FalseConsensus.related_work import metrics
        rows = []
        for i in range(10):
            rows.append({"method": "test", "model": "m", "dataset": "d",
                         "base_seed": 42, "problem_id": i, "split": "dev",
                         "correct": (i % 2 == 0),  # all boolean
                         "baseline_correct": True,
                         "full_main_tokens": 1000, "main_tokens_through_stop": 500,
                         "all_generated_tokens": 600, "probe_out_tokens": 100,
                         "probe_prompt_tokens": 200,
                         "baseline_all_generated_tokens": 1000,
                         "delivered_answer": "x" if i % 2 == 0 else "",
                         "stopped": i % 2 == 0, "capped": False,
                         "recovery_truncated": i % 2 == 0,
                         "overthinking_avoided_tokens": 500,
                         "n_aux_calls": 1, "n_readout_calls": 0,
                         "invalid_aux_responses": 0,
                         "auxiliary_wall_seconds": 0.1})
        agg = metrics.aggregate(rows)
        self.assertEqual(agg["n"], 10)
        self.assertEqual(agg["n_graded"], 10)  # all rows have boolean correct

    # -- Invariant 2: corrupt cases remain invalid for resume/progress --
    def test_readout_with_error_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "stop",
                         "error": "timeout"}))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_readout_with_null_finish_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": None}))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_readout_with_unknown_finish_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "content_filter"}))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_readout_with_context_overflow_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "stop",
                         "readout_context_overflow": True}))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_readout_with_context_budget_exceeded_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "",
                         "readout_finish_reason": "stop",
                         "readout_context_budget_exceeded": True}))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_present_non_dict_readout_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 1, self._tje_record(readout="garbage_string"))
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_non_dict_trigger_row_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            d = self._tje_record()
            d["triggers"] = ["not_a_dict"]
            p = self._write(td, 1, d)
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_trigger_row_with_error_key_is_corrupt(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(progress)
        with tempfile.TemporaryDirectory() as td:
            d = self._tje_record()
            d["triggers"][0]["error"] = "api_error"
            p = self._write(td, 1, d)
            self.assertFalse(progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))


class CacheValidityTests(unittest.TestCase):
    """Tests for postprocess._cache_is_valid."""

    @classmethod
    def setUpClass(cls):
        from benchmark.FalseConsensus.related_work import postprocess
        cls.pp = postprocess

    def _write_rows(self, td, rows):
        p = Path(td) / "replay_rows.jsonl"
        import json
        with p.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return p

    def _valid_row(self, pid=1, correct=1, baseline_correct=1):
        return {"method": "certaindex_mid_frozen",
                "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "dataset": "math500", "base_seed": 42,
                "problem_id": pid, "split": "dev",
                "correct": correct, "baseline_correct": baseline_correct}

    def test_empty_file_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "replay_rows.jsonl"
            p.write_text("", encoding="utf-8")
            self.assertFalse(self.pp._cache_is_valid(p, 400))

    def test_truncated_file_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "replay_rows.jsonl"
            p.write_text("{bad json", encoding="utf-8")
            self.assertFalse(self.pp._cache_is_valid(p, 400))

    def test_null_correct_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._write_rows(td, [self._valid_row(correct=None)])
            self.assertFalse(self.pp._cache_is_valid(p, 1))

    def test_missing_correct_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            row = self._valid_row()
            del row["correct"]
            p = self._write_rows(td, [row])
            self.assertFalse(self.pp._cache_is_valid(p, 1))

    def test_wrong_count_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._write_rows(td, [self._valid_row(pid=i) for i in range(5)])
            self.assertFalse(self.pp._cache_is_valid(p, 400))

    def test_valid_cache_with_int_correct_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rows = [self._valid_row(pid=i, correct=i % 2, baseline_correct=1) for i in range(3)]
            p = self._write_rows(td, rows)
            self.assertTrue(self.pp._cache_is_valid(p, 3))

    def test_valid_cache_with_bool_correct_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rows = [self._valid_row(pid=i, correct=bool(i % 2), baseline_correct=True) for i in range(3)]
            p = self._write_rows(td, rows)
            self.assertTrue(self.pp._cache_is_valid(p, 3))

    def test_missing_identity_field_is_invalid(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            row = self._valid_row()
            del row["problem_id"]
            p = self._write_rows(td, [row])
            self.assertFalse(self.pp._cache_is_valid(p, 1))


if __name__ == "__main__":
    unittest.main()
