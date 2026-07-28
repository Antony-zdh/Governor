from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from benchmark.FalseConsensus.deer_inspired.common import (
    ProbeSchedule,
    branch_commit,
    branch_is_allowed,
    make_trial_record,
    split_at_terminal_wait,
    stable_seed,
    stage1_action,
    verification_cue,
    wait_matches,
)
from benchmark.FalseConsensus.deer_inspired.online_controller import (
    METHOD_PROPOSED,
    OnlineController,
)
from benchmark.FalseConsensus.deer_inspired.aggregate import audit
from benchmark.FalseConsensus.related_work.deer import calculate_confidence


class FakeTokenizer:
    def encode(self, text, add_special_tokens=False):
        return list(text)


class FakeLogprobs:
    def __init__(self, tokens, values):
        self.tokens = tokens
        self.token_logprobs = values
        self.top_logprobs = [
            {token: value} for token, value in zip(tokens, values)
        ]


def response(
    text,
    *,
    output_tokens=None,
    finish_reason="stop",
    stop_reason=None,
    probability=None,
):
    choice = SimpleNamespace(
        text=text,
        finish_reason=finish_reason,
        stop_reason=stop_reason,
    )
    if probability is not None:
        if text.endswith("</think>"):
            tokens = ["{", "12", "}", "</think>"]
        else:
            tokens = ["{", "12", "}"]
        values = [math.log(probability)] * len(tokens)
        choice.logprobs = FakeLogprobs(tokens, values)
        output_tokens = len(tokens)
    else:
        choice.logprobs = None
    return SimpleNamespace(
        choices=[choice],
        usage=SimpleNamespace(
            prompt_tokens=7,
            completion_tokens=output_tokens if output_tokens is not None else len(text),
        ),
    )


class QueueCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected completion request")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ProtocolTests(unittest.TestCase):
    def test_01_wait_is_case_insensitive(self):
        self.assertEqual(len(wait_matches("wait Wait WAIT")), 3)

    def test_02_wait_is_whole_word(self):
        self.assertEqual(wait_matches("await Waited waiter"), [])

    def test_03_clean_prefix_excludes_wait(self):
        self.assertEqual(split_at_terminal_wait("abc Wait"), ("abc ", "Wait"))

    def test_04_stop_reason_restores_wait_once(self):
        self.assertEqual(split_at_terminal_wait("abc ", "Wait"), ("abc ", "Wait"))

    def test_05_future_suffix_rejected(self):
        with self.assertRaises(ValueError):
            split_at_terminal_wait("abc Wait future")

    def test_06_before_minimum_skips_without_attempt(self):
        schedule = ProbeSchedule()
        self.assertEqual(schedule.decide(1023), (False, "before_minimum_tokens"))
        self.assertEqual(schedule.actual_attempts, 0)

    def test_07_minimum_boundary_is_dense(self):
        self.assertEqual(ProbeSchedule().decide(1024), (True, "dense"))

    def test_08_first_ten_are_dense(self):
        schedule = ProbeSchedule()
        for position in range(1024, 1034):
            should, mode = schedule.decide(position)
            self.assertTrue(should)
            self.assertEqual(mode, "dense")
            schedule.record_attempt(position)
        self.assertEqual(schedule.actual_attempts, 10)

    def test_09_eleventh_requires_512_gap(self):
        schedule = ProbeSchedule(actual_attempts=10, last_probe_position=2000)
        self.assertEqual(
            schedule.decide(2511), (False, "post_dense_gap_lt_512")
        )
        self.assertEqual(schedule.decide(2512), (True, "sparse"))

    def test_10_sparse_skip_does_not_move_last_probe(self):
        schedule = ProbeSchedule(actual_attempts=10, last_probe_position=2000)
        schedule.decide(2200)
        self.assertEqual(schedule.last_probe_position, 2000)

    def test_11_invalid_stage1_continues(self):
        self.assertEqual(stage1_action(False, 1.0), "continue")

    def test_12_branch_lower_boundary_is_strict(self):
        self.assertEqual(stage1_action(True, 0.97), "continue")

    def test_13_branch_upper_boundary_is_not_fast(self):
        self.assertEqual(stage1_action(True, 0.995), "branch")

    def test_14_fast_threshold_is_strict(self):
        self.assertEqual(stage1_action(True, 0.9950001), "fast_commit")

    def test_15_commit_threshold_is_strict(self):
        self.assertFalse(branch_commit(True, 0.99, True))
        self.assertTrue(branch_commit(True, 0.990001, True))

    def test_16_commit_requires_validity(self):
        self.assertFalse(branch_commit(False, 1.0, True))

    def test_17_commit_requires_equivalence(self):
        self.assertFalse(branch_commit(True, 1.0, False))

    def test_18_branch_cooldown_boundary(self):
        self.assertFalse(branch_is_allowed(1511, 1000))
        self.assertTrue(branch_is_allowed(1512, 1000))

    def test_19_first_branch_is_allowed(self):
        self.assertTrue(branch_is_allowed(1024, None))

    def test_20_cue_contains_only_candidate(self):
        cue = verification_cue("12")
        self.assertIn(r"\boxed{12}", cue)
        self.assertNotIn("ground truth", cue.lower())
        self.assertIn("within 64 tokens", cue)

    def test_21_seed_roles_are_isolated_and_stable(self):
        self.assertEqual(stable_seed("a", 1), stable_seed("a", 1))
        self.assertNotEqual(stable_seed("a", 1), stable_seed("b", 1))

    def test_22_avg1_skips_first_token(self):
        rows = [("x", math.log(0.1)), ("y", math.log(0.8)), ("z", math.log(0.6))]
        self.assertAlmostEqual(calculate_confidence(rows, policy="avg1"), 0.7)

    def test_23_avg2_skips_first_token(self):
        rows = [("x", math.log(0.1)), ("y", math.log(0.8)), ("z", math.log(0.2))]
        self.assertAlmostEqual(calculate_confidence(rows, policy="avg2"), 0.4)

    def test_24_qwen_gate_rejects_missing_think_close(self):
        trial = make_trial_record(
            response("{12}", probability=0.999), model="Qwen/Qwen3-8B"
        )
        self.assertFalse(trial["valid"])
        self.assertEqual(trial["confidence"], 0.0)

    def test_25_qwen_gate_accepts_exact_think_close(self):
        trial = make_trial_record(
            response("{12}</think>", probability=0.999),
            model="Qwen/Qwen3-8B",
        )
        self.assertTrue(trial["valid"])
        self.assertGreater(trial["confidence"], 0.995)

    def test_26_unbalanced_trial_is_invalid(self):
        trial = make_trial_record(
            response("{12", probability=0.999),
            model="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        )
        self.assertFalse(trial["valid"])


class ControllerTests(unittest.TestCase):
    MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    REVISION = "a" * 40

    def controller(self, root: Path, responses):
        config = {
            "protocol_version": "deer-inspired-online-dev-2026-07-28.1",
            "formal_seed": 42,
        }
        client = SimpleNamespace(completions=QueueCompletions(responses))
        controller = OnlineController(
            method=METHOD_PROPOSED,
            model=self.MODEL,
            model_revision=self.REVISION,
            benchmark="math500",
            base_seed=42,
            cap=4096,
            max_model_len=8192,
            output=root,
            config=config,
            url="http://unused",
            client=client,
            tokenizer=FakeTokenizer(),
            apply_chat_template_fn=lambda problem, model: "CHAT:" + problem,
            extract_answer_fn=lambda text, dataset: "12" if r"\boxed{12}" in text else "",
            answers_equal_fn=lambda left, right: str(left) == str(right),
            sleep_fn=lambda _: None,
        )
        return controller, client.completions

    def test_27_fast_path_stops_without_branch_or_readout(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, calls = self.controller(
                Path(directory),
                [
                    response("x" * 1024 + " Wait", finish_reason="stop", stop_reason="Wait"),
                    response("{12}", probability=0.999),
                ],
            )
            controller.collect_problem(1, "problem", "12", {})
            payload = __import__("json").loads(
                (Path(directory) / "problems/problem_1.json").read_text()
            )
            self.assertEqual(payload["terminal_state"], "fast_commit")
            self.assertEqual(payload["delivered_answer"], "12")
            self.assertEqual(payload["branches"], [])
            self.assertEqual(len(calls.calls), 2)

    def test_28_branch_failure_retains_verification_but_not_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, calls = self.controller(
                Path(directory),
                [
                    response("x" * 1024 + " Wait", finish_reason="stop", stop_reason="Wait"),
                    response("{12}", probability=0.98),
                    response(" checked", output_tokens=1),
                    response("{12}", probability=0.98),
                    response(r" final \boxed{12}", output_tokens=4),
                ],
            )
            controller.collect_problem(2, "problem", "12", {})
            payload = __import__("json").loads(
                (Path(directory) / "problems/problem_2.json").read_text()
            )
            self.assertEqual(payload["terminal_state"], "natural")
            self.assertEqual(payload["branches"][0]["outcome"], "fail_retain_verification")
            self.assertTrue(payload["branches"][0]["verification_retained"])
            self.assertNotIn("Wait", payload["native_main_text"])
            self.assertNotIn("Candidate answer", payload["native_main_text"])
            self.assertIn("Candidate answer", calls.calls[-1]["prompt"])

    def test_29_branch_success_uses_stage2_without_formal_readout(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, calls = self.controller(
                Path(directory),
                [
                    response("x" * 1024 + " Wait", finish_reason="stop", stop_reason="Wait"),
                    response("{12}", probability=0.98),
                    response(" checked", output_tokens=1),
                    response("{12}", probability=0.999),
                ],
            )
            controller.collect_problem(3, "problem", "12", {})
            payload = __import__("json").loads(
                (Path(directory) / "problems/problem_3.json").read_text()
            )
            self.assertEqual(payload["terminal_state"], "branch_commit")
            self.assertEqual(payload["delivered_answer"], "12")
            self.assertIsNone(payload["reference_readout"])
            self.assertEqual(len(calls.calls), 4)

    def test_30_resume_skips_complete_result(self):
        with tempfile.TemporaryDirectory() as directory:
            controller, calls = self.controller(
                Path(directory),
                [
                    response(r"final \boxed{12}", output_tokens=4),
                ],
            )
            controller.collect_problem(4, "problem", "12", {})
            controller.collect_problem(4, "problem", "12", {})
            self.assertEqual(len(calls.calls), 1)


class AggregateAuditTests(unittest.TestCase):
    def complete_rows(self):
        rows = []
        counts = {"math500": 100, "amc23": 8, "aime24": 6}
        for method in ("deer_inspired_online_v1", "deer_online_reference"):
            for model in (
                "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "Qwen/Qwen3-8B",
            ):
                for benchmark, count in counts.items():
                    for problem_id in range(count):
                        rows.append(
                            {
                                "method": method,
                                "model": model,
                                "benchmark": benchmark,
                                "seed": 42,
                                "problem_id": problem_id,
                                "split": "dev",
                                "config_hash": "frozen",
                                "infrastructure_error_count": 0,
                            }
                        )
        return rows

    def test_31_complete_audit_requires_exact_456(self):
        result = audit(self.complete_rows(), allow_incomplete=False)
        self.assertTrue(result["complete"])
        self.assertEqual(result["total"], 456)

    def test_32_audit_rejects_wrong_environment_coverage(self):
        rows = self.complete_rows()
        rows[0]["benchmark"] = "amc23"
        result = audit(rows, allow_incomplete=False)
        self.assertFalse(result["complete"])
        self.assertTrue(any("math500" in error for error in result["errors"]))

    def test_33_audit_rejects_infrastructure_errors(self):
        rows = self.complete_rows()
        rows[0]["infrastructure_error_count"] = 1
        self.assertFalse(audit(rows, allow_incomplete=False)["complete"])

    def test_34_audit_rejects_multiple_config_hashes(self):
        rows = self.complete_rows()
        rows[0]["config_hash"] = "changed"
        self.assertFalse(audit(rows, allow_incomplete=False)["complete"])


if __name__ == "__main__":
    unittest.main()
