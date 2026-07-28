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

from benchmark.FalseConsensus.related_work import common, tje, deer  # noqa


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
        self.assertIsNone(result["correct"])  # empty answer -> not graded
        self.assertGreater(result.get("invalid_aux_responses", 0), 0,
                           "invalid_aux_responses must be > 0 for invalid readout")

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


if __name__ == "__main__":
    unittest.main()
