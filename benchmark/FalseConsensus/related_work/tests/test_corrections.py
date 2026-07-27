"""Regression tests for the supervisor's smoke-correction requirements.

Covers: model-revision pinning (40-hex), finish_reason recording, readout
validity (no stray-number fallback; a delivered readout is valid only when an
explicit ``\\boxed{...}`` was completed before truncation), the canonical
reproducibility hash (excludes volatile timing/timestamps; includes all model
outputs/answers/certainty/tokens/positions/seeds), and TJE rendered
system-role boundary deduplication (no duplicate BOS or ``mland`` boundary).

Run from the repo root::

    python -m unittest benchmark.FalseConsensus.related_work.tests.test_corrections
"""
from __future__ import annotations

import importlib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
import sys
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.related_work import common, tje  # noqa: E402


def _have_sympy() -> bool:
    try:
        importlib.import_module("sympy")
        return True
    except Exception:
        return False


# The DeepSeek/Qwen chat template appends a forced reasoning-start boundary that
# is already present in every frozen trajectory; build_system_chat strips it.
THINK_BOUNDARY = chr(0x3c) + chr(0x74) + chr(0x68) + chr(0x69) + chr(0x6e) + chr(0x6b) + chr(0x3e)  # <think>


class RevisionPinningTests(unittest.TestCase):
    def test_is_40hex_valid_and_invalid(self):
        self.assertTrue(common.is_40hex("916b56a44061fd5cd7d6a8fb632557ed4f724f60"))
        self.assertTrue(common.is_40hex("b968826d9c46dd6066d109eabc6255188de91218"))
        self.assertFalse(common.is_40hex("notasha"))
        self.assertFalse(common.is_40hex("916b56a"))
        self.assertFalse(common.is_40hex(None))
        self.assertFalse(common.is_40hex("Z16b56a44061fd5cd7d6a8fb632557ed4f724f60"))


class ReadoutValidityTests(unittest.TestCase):
    def test_completed_boxed_detection(self):
        self.assertTrue(common.has_completed_boxed("blah \\boxed{204} end"))
        self.assertTrue(common.has_completed_boxed("\\boxed{\\frac{1}{2}}"))
        self.assertFalse(common.has_completed_boxed("\\boxed{204"))   # opened, not closed
        self.assertFalse(common.has_completed_boxed("no answer here"))
        self.assertFalse(common.has_completed_boxed("\\boxed"))       # no brace

    def test_truncated_readout_without_boxed_is_invalid_and_empty(self):
        # The DeepSeek AIME TJE smoke failure: readout length-capped mid-sentence,
        # no boxed -> must NOT accept a stray last number.
        rv = common.readout_validity("Earlier, I was thinking that 3", "length", "math500")
        self.assertFalse(rv["readout_valid"])
        self.assertEqual(rv["readout_answer"], "")
        self.assertTrue(rv["readout_truncated"])
        self.assertFalse(rv["readout_completed_boxed"])

    def test_natural_readout_without_boxed_is_invalid(self):
        rv = common.readout_validity("some reasoning without an answer", "stop", "aime24")
        self.assertFalse(rv["readout_valid"])
        self.assertEqual(rv["readout_answer"], "")

    def test_has_explicit_answer_phrase(self):
        self.assertTrue(common.has_explicit_answer_phrase("Thus, the answer is 36"))
        self.assertTrue(common.has_explicit_answer_phrase("Final answer is 12"))
        self.assertFalse(common.has_explicit_answer_phrase("no marker here"))

    @unittest.skipUnless(_have_sympy(), "extract_explicit_answer needs sympy")
    def test_truncated_readout_with_completed_boxed_is_valid(self):
        # DEER AMC: length-capped readout but a boxed answer completed first.
        rv = common.readout_validity("blah \\boxed{204} continued", "length", "math500")
        self.assertTrue(rv["readout_completed_boxed"])
        self.assertTrue(rv["readout_truncated"])
        self.assertTrue(rv["readout_valid"])
        self.assertEqual(rv["readout_answer"], "204")

    @unittest.skipUnless(_have_sympy(), "extract_explicit_answer needs sympy")
    def test_natural_readout_with_completed_boxed_is_valid(self):
        rv = common.readout_validity("Therefore \\boxed{7}", "stop", "math500")
        self.assertTrue(rv["readout_valid"])
        self.assertEqual(rv["readout_answer"], "7")


class FinishReasonTests(unittest.TestCase):
    def test_finish_reason_of_reads_choice(self):
        class Choice:
            finish_reason = "length"
        class Resp:
            choices = [Choice()]
        self.assertEqual(common.finish_reason_of(Resp()), "length")

    def test_finish_reason_of_safe_on_bad_response(self):
        self.assertIsNone(common.finish_reason_of(object()))
        self.assertIsNone(common.finish_reason_of(None))


class ReadoutAllowanceTests(unittest.TestCase):
    """Context-safe readout allowance: never exceed server context; a negative
    remaining is a context-budget error with allowance 0 (NOT max(64, neg))."""

    def test_normal_short_prompt_uses_readout_cap(self):
        a = common.compute_readout_allowance(1400, readout_cap=8192, max_model_len=34816)
        self.assertFalse(a["context_budget_exceeded"])
        self.assertEqual(a["allowance"], 8192)

    def test_near_max_prompt_caps_at_remaining(self):
        a = common.compute_readout_allowance(34000, readout_cap=8192, max_model_len=34816)
        self.assertFalse(a["context_budget_exceeded"])
        self.assertEqual(a["allowance"], 34816 - 34000 - 32)  # 784

    def test_negative_remaining_is_context_budget_error_not_max_clamped(self):
        # The false-positive bug: max(64, negative) could exceed server context.
        a = common.compute_readout_allowance(34800, readout_cap=8192, max_model_len=34816)
        self.assertTrue(a["context_budget_exceeded"])
        self.assertEqual(a["allowance"], 0)          # NOT 64
        self.assertLess(a["remaining"], 0)

    def test_large_overflow_is_context_budget_error(self):
        a = common.compute_readout_allowance(40000, readout_cap=8192, max_model_len=34816)
        self.assertTrue(a["context_budget_exceeded"])
        self.assertEqual(a["allowance"], 0)
        self.assertLess(a["remaining"], 0)

    def test_allowance_plus_prompt_never_exceeds_max_model_len(self):
        for est in (0, 1400, 30000, 34000, 34700):
            a = common.compute_readout_allowance(est, readout_cap=8192, max_model_len=34816)
            if not a["context_budget_exceeded"]:
                self.assertLessEqual(est + a["allowance"] + 32, 34816)


class CanonicalReproducibilityTests(unittest.TestCase):
    def test_hash_excludes_timing_includes_outputs(self):
        a = {"model": "m", "base_seed": 42, "problem_id": 1, "probes": [
            {"probe_text": "204}", "probe_answer": "204", "is_certain": True,
             "probe_out_tokens": 6, "probe_prompt_tokens": 100,
             "probe_finish_reason": "stop", "probe_latency_seconds": 0.12}],
             "created_at": "2026-07-27T1", "token_position": 64}
        b = {"created_at": "2026-07-27T9", "model": "m", "base_seed": 42,
             "problem_id": 1, "token_position": 64,
             "probes": [{"probe_latency_seconds": 9.9, "probe_text": "204}",
                         "probe_answer": "204", "is_certain": True,
                         "probe_out_tokens": 6, "probe_prompt_tokens": 100,
                         "probe_finish_reason": "stop"}]}
        self.assertEqual(common.canonical_hash(a), common.canonical_hash(b))

    def test_output_difference_changes_hash(self):
        a = {"probe_answer": "204", "probe_latency_seconds": 0.1}
        b = {"probe_answer": "205", "probe_latency_seconds": 0.1}
        self.assertNotEqual(common.canonical_hash(a), common.canonical_hash(b))

    def test_position_and_seed_are_included(self):
        a = {"base_seed": 42, "problem_id": 7, "probe_answer": "1"}
        b = {"base_seed": 43, "problem_id": 7, "probe_answer": "1"}
        self.assertNotEqual(common.canonical_hash(a), common.canonical_hash(b))


class TJERenderedRoleTests(unittest.TestCase):
    def _mock_tokenizer(self, bos, trailing):
        class Tok:
            pass
        tok = Tok()
        tok.bos_token = bos
        tok.apply_chat_template = lambda msgs, *, tokenize, add_generation_prompt: (
            (bos or "") + msgs[0]["content"] + "\n" + msgs[1]["content"] + "\n" + trailing
        )
        return tok

    def test_build_system_chat_strips_bos_and_think_boundary(self):
        tok = self._mock_tokenizer("<s>", THINK_BOUNDARY + "\n")
        rendered = tje.build_system_chat(tok, "the problem", system="SYS")
        self.assertFalse(rendered.startswith("<s>"))
        self.assertFalse(rendered.endswith(THINK_BOUNDARY + "\n"))
        self.assertIn("SYS", rendered)
        self.assertIn("the problem", rendered)

    def test_build_system_chat_no_bos_is_fine(self):
        tok = self._mock_tokenizer("", THINK_BOUNDARY + "\n")
        rendered = tje.build_system_chat(tok, "p", system="S")
        self.assertFalse(rendered.endswith(THINK_BOUNDARY + "\n"))

    def test_system_prompt_hash_matches_official_figure2(self):
        # pinned in configs/tje.json
        import json
        cfg = json.load(open(REPO_ROOT / "benchmark/FalseConsensus/related_work/configs/tje.json"))
        self.assertEqual(cfg["confidence_instruction_sha256"],
                         common.sha256_bytes(common.TJE_SYSTEM_PROMPT.encode("utf-8")))
        self.assertEqual(cfg["readout_cap"], 8192)
        self.assertEqual(cfg["model_revisions"]["Qwen/Qwen3-8B"],
                         "b968826d9c46dd6066d109eabc6255188de91218")


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------- #
class TJEReadoutPromptTests(unittest.TestCase):
    """Per TJE Figure 1 / Section 2.2: the final-response context retains the
    TJE system-role chat AND the triggering confidence event before the
    think-close tag. The readout must NOT use plain_chat."""

    def test_readout_prompt_equals_confidence_prompt_plus_label(self):
        # The readout must reconstruct the EXACT confidence-query context
        # (system chat + prefix + the exact space + forced \confidence{ prefix),
        # close the parsed label, then the think-close boundary.
        chat = "SYSROLECHAT"
        conf_prompt = tje.build_confidence_prompt(chat, "PREFIX")
        rp = tje.build_readout_prompt(conf_prompt, "Almost certain")
        self.assertEqual(rp, conf_prompt + "Almost certain}" + "\n" + common.DEER_THINK_CLOSE + "\n\n")
        # the triggering \confidence{Almost certain} appears before the think-close
        self.assertIn("\\confidence{Almost certain}", rp)
        self.assertLess(rp.index("\\confidence{Almost certain}"),
                         rp.index(common.DEER_THINK_CLOSE))

    def test_readout_prompt_uses_system_chat_not_plain(self):
        chat = "SYSROLECHAT"
        conf_prompt = tje.build_confidence_prompt(chat, "PREFIX")
        rp = tje.build_readout_prompt(conf_prompt, "Likely")
        # begins with the system-role chat (not plain_chat)
        self.assertTrue(rp.startswith(chat))
        # no separate plain_chat reconstruction; the readout is exactly the
        # confidence prompt + label + "}" + think-close boundary
        self.assertEqual(rp, conf_prompt + "Likely}" + "\n" + common.DEER_THINK_CLOSE + "\n\n")

    def test_readout_prompt_without_label_still_has_think_close(self):
        rp = tje.build_readout_prompt(tje.build_confidence_prompt("C", "P"))
        self.assertIn(common.DEER_THINK_CLOSE, rp)




# --------------------------------------------------------------------------- #
class ProductionPredicateTests(unittest.TestCase):
    """Regression tests against the shared production predicates (the same ones
    the smoke audit uses). These fixtures correspond to the two false-positive
    smoke runs and MUST fail the predicate."""

    def setUp(self):
        from benchmark.FalseConsensus.related_work import predicates as P
        self.P = P

    # -- readout_is_valid (common, re-exported) --
    def test_readout_valid_passes_for_completed_boxed(self):
        ro = {"readout_valid": True, "readout_truncated": False,
              "readout_completed_boxed": True, "readout_answer": "55",
              "readout_finish_reason": "stop",
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertTrue(common.readout_is_valid(ro))
        self.assertTrue(self.P.readout_is_valid(ro))

    def test_readout_null_finish_reason_is_invalid(self):
        # null finish_reason must NOT pass (old bug: None != "length" -> True)
        ro = {"readout_valid": True, "readout_truncated": False,
              "readout_completed_boxed": True, "readout_answer": "55",
              "readout_finish_reason": None,
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertFalse(common.readout_is_valid(ro))

    def test_readout_length_truncated_with_completed_marker_is_valid(self):
        # DEER AMC: length-capped readout but a boxed answer completed first.
        ro = {"readout_valid": True, "readout_truncated": True,
              "readout_completed_boxed": True, "readout_answer": "12",
              "readout_finish_reason": "length",
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertTrue(common.readout_is_valid(ro))

    def test_readout_length_truncated_no_marker_is_invalid(self):
        ro = {"readout_valid": False, "readout_truncated": True,
              "readout_completed_boxed": False, "readout_answer": "",
              "readout_finish_reason": "length",
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertFalse(common.readout_is_valid(ro))

    def test_readout_context_overflow_is_invalid(self):
        # actual_prompt + allowance > max_model_len -> hard failure
        ro = {"readout_valid": True, "readout_truncated": False,
              "readout_completed_boxed": True, "readout_answer": "55",
              "readout_finish_reason": "stop",
              "readout_context_overflow": True, "readout_context_budget_exceeded": False}
        self.assertFalse(common.readout_is_valid(ro))

    def test_readout_truncated_empty_is_invalid(self):
        # the original DeepSeek AIME TJE false positive
        ro = {"readout_valid": False, "readout_truncated": True,
              "readout_completed_boxed": False, "readout_answer": "",
              "readout_finish_reason": "length",
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertFalse(common.readout_is_valid(ro))

    def test_readout_stray_answer_is_invalid(self):
        ro = {"readout_valid": False, "readout_truncated": True,
              "readout_completed_boxed": False, "readout_answer": "3",
              "readout_finish_reason": "length",
              "readout_context_overflow": False, "readout_context_budget_exceeded": False}
        self.assertFalse(common.readout_is_valid(ro))

    # -- near_max_probe_passes --
    def _base(self, **kw):
        d = {"status": "ok", "fraction": 0.95, "latency_seconds": 1.2, "prompt_tokens": 31129}
        d.update(kw)
        return d

    def test_near_max_certa_passes_with_boxed_answer(self):
        self.assertTrue(self.P.near_max_probe_passes(
            self._base(method="certaindex_mid", finish_reason="stop", parsed_answer="204")))

    def test_near_max_certa_empty_answer_fails(self):
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="certaindex_mid", finish_reason="stop", parsed_answer="")))

    def test_near_max_tje_null_label_length_fails(self):
        # the original DeepSeek near-max TJE false positive
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="tje", finish_reason="length", parsed_label=None)))

    def test_near_max_tje_label_with_length_finish_fails(self):
        # a parsed label + length finish is STILL a failure
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="tje", finish_reason="length", parsed_label="Likely")))

    def test_near_max_tje_null_finish_fails(self):
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="tje", finish_reason=None, parsed_label="Likely")))

    def test_near_max_tje_passes_with_stop_and_label(self):
        self.assertTrue(self.P.near_max_probe_passes(
            self._base(method="tje", finish_reason="stop", parsed_label="Almost certain")))

    def test_near_max_deer_empty_answer_fails(self):
        # DEER parsed answer must be truthy, not merely not-None
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=4, logprobs=[1, 2, 3, 4], require_think_close=False)))

    def test_near_max_deer_passes_deepseek(self):
        self.assertTrue(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="12",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=4, logprobs=[1, 2, 3, 4], require_think_close=False)))

    def test_near_max_deer_qwen_gate_exact_pass(self):
        self.assertTrue(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="503",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=6, logprobs=list(range(6)),
                       require_think_close=True, last_token_decoded=common.DEER_THINK_CLOSE,
                       confidence=0.97)))

    def test_near_max_deer_qwen_gate_no_think_zero_conf_pass(self):
        self.assertTrue(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="12",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=4, logprobs=list(range(4)),
                       require_think_close=True, last_token_decoded=" more", confidence=0.0)))

    def test_near_max_deer_qwen_gate_think_zero_conf_fails(self):
        # weak 'or conf==0.0' would pass; exact gate fails
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="12",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=4, logprobs=list(range(4)),
                       require_think_close=True, last_token_decoded=common.DEER_THINK_CLOSE,
                       confidence=0.0)))

    def test_near_max_truncated_logprobs_fail(self):
        # full sequence must be stored (n_logprob_tokens == len(logprobs))
        self.assertFalse(self.P.near_max_probe_passes(
            self._base(method="deer", finish_reason="stop", parsed_answer="12",
                       confidence_finite=True, confidence_recomputed_matches=True,
                       n_logprob_tokens=6, logprobs=[1, 2, 3, 4], require_think_close=False)))



# --------------------------------------------------------------------------- #
class TJEChoiceConstraintTests(unittest.TestCase):
    """Regression for the near-max TJE false positive (parsed_label=null,
    finish_reason=length). The production confidence call pins the ten labels as
    a vLLM structured_outputs.choice constraint, forcing a valid label."""

    def test_label_names_are_exactly_the_ten_official(self):
        self.assertEqual(tje.TJE_LABEL_NAMES,
                         [n for n, _l, _h in common.TJE_CONFIDENCE_LABELS])
        self.assertEqual(len(tje.TJE_LABEL_NAMES), 10)
        self.assertIn("Almost certain", tje.TJE_LABEL_NAMES)

    def test_parse_returns_label_for_each_choice_member(self):
        for name in tje.TJE_LABEL_NAMES:
            self.assertEqual(tje.parse_confidence_response(name), name)
            self.assertEqual(tje.parse_confidence_response(name + "}"), name)


class ExactQwenGateTests(unittest.TestCase):
    """Regression for the weak Qwen-gate false positive (the unconditional
    'or confidence == 0.0' made any zero-confidence case pass). The exact gate
    is the iff: (last==THINK and conf>0) or (last!=THINK and conf==0.0)."""

    def _gate(self, last, conf):
        return ((last == common.DEER_THINK_CLOSE and conf > 0) or
                (last != common.DEER_THINK_CLOSE and conf == 0.0))

    def test_gate_passes_when_think_close_and_positive(self):
        self.assertTrue(self._gate(common.DEER_THINK_CLOSE, 0.97))

    def test_gate_passes_when_not_think_close_and_zero(self):
        self.assertTrue(self._gate(" more", 0.0))

    def test_gate_fails_when_think_close_but_zero(self):
        # The weak 'or conf==0.0' would wrongly pass this; the exact gate fails.
        self.assertFalse(self._gate(common.DEER_THINK_CLOSE, 0.0))

    def test_gate_fails_when_not_think_close_but_positive(self):
        self.assertFalse(self._gate(" more", 0.5))
