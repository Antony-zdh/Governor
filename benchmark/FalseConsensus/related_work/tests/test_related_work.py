"""Unit tests for the related-work baselines (GPU/endpoint-free).

These tests exercise the pure decision / parsing / accounting logic only; they
never start a model server, never import torch/transformers/sympy/openai at
module load, and never read test-split data. The frozen-bank identity tests
read the committed development bank (train+dev only) under
``benchmark/FalseConsensus/results/governor_v2``.

Run from the repository root::

    python -m unittest discover -s benchmark/FalseConsensus/related_work/tests
    # or:
    python -m pytest benchmark/FalseConsensus/related_work/tests
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
for p in (str(REPO_ROOT), str(HERE.parents[1].parent / "governor_v2")):
    if p not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.related_work import aggregate_all, common, certaindex_mid, deer, metrics, replay as replay_driver, tje  # noqa: E402

RESULTS_ROOT = REPO_ROOT / "benchmark" / "FalseConsensus" / "results" / "governor_v2"
SPLIT_MANIFEST = REPO_ROOT / "benchmark" / "FalseConsensus" / "governor_v2" / "generated" / "split_manifest.json"


def _str_eq_group(answers):
    """Injected equivalence for CertaIndex tests (no sympy): exact string eq."""
    answers = [a for a in answers]
    return len(set(answers)) <= 1


def _str_eq_target(answer, target):
    return str(answer).strip() == str(target).strip()


# --------------------------------------------------------------------------- #
class TriggerParsingTests(unittest.TestCase):
    def test_whole_word_wait_not_substring(self):
        text = "Wait here. Awaited the bus. Waiting. Wait, no."
        pos = common.find_wait_positions(text)
        # "Awaited" and "Waiting" must NOT match; only standalone "Wait" tokens.
        self.assertEqual(pos, [0, len("Wait here. Awaited the bus. Waiting. ")])
        # the second match is the final "Wait, no." -> offset of that Wait
        self.assertEqual(text[pos[1]:pos[1] + 4], "Wait")

    def test_case_insensitive_wait(self):
        self.assertEqual(len(common.find_wait_positions("wait and Wait and WAIT")), 3)

    def test_think_close_offsets(self):
        tc = common.DEER_THINK_CLOSE
        text = tc + " some text " + tc + " end"
        self.assertEqual(len(common.find_think_close_positions(text)), 2)

    def test_tje_wait_only_vs_end_think_inclusive(self):
        tc = common.DEER_THINK_CLOSE
        text = "Wait " + tc + " Wait " + tc
        primary = tje.find_triggers(text, include_think_close=False)
        self.assertEqual([t["trigger_type"] for t in primary], ["wait", "wait"])
        full = tje.find_triggers(text, include_think_close=True)
        self.assertEqual(sorted(t["trigger_type"] for t in full), ["think_close", "think_close", "wait", "wait"])
        # ordered by char offset
        self.assertEqual(full[0]["trigger_type"], "wait")
        self.assertEqual(full[0]["trigger_char_end"], len("Wait"))
        self.assertEqual(tje.find_triggers(text), full)


# --------------------------------------------------------------------------- #
class TJEConfidenceTests(unittest.TestCase):
    def test_parse_forced_prefix_completion(self):
        self.assertEqual(tje.parse_confidence_response("Almost certain}"), "Almost certain")
        self.assertEqual(tje.parse_confidence_response("Likely}"), "Likely")

    def test_parse_full_token(self):
        self.assertEqual(tje.parse_confidence_response("\\confidence{Almost certain}"), "Almost certain")
        self.assertEqual(tje.parse_confidence_response("\\confidence{Highly unlikely}"), "Highly unlikely")

    def test_parse_unknown_returns_none(self):
        self.assertIsNone(tje.parse_confidence_response("garbage"))
        self.assertIsNone(tje.parse_confidence_response(""))

    def test_ten_labels_preserved(self):
        self.assertEqual(len(common.TJE_CONFIDENCE_LABELS), 10)
        names = [n for n, _l, _h in common.TJE_CONFIDENCE_LABELS]
        self.assertEqual(names[0], "Almost no chance")
        self.assertEqual(names[-1], "Almost certain")
        self.assertEqual(common.TJE_THRESHOLD_LABEL, "Almost certain")

    def test_threshold_is_almost_certain_only(self):
        # only "Almost certain" meets the primary threshold
        for name, _l, _h in common.TJE_CONFIDENCE_LABELS:
            if name == "Almost certain":
                self.assertTrue(tje.label_meets_threshold(name))
            else:
                self.assertFalse(tje.label_meets_threshold(name))

    def test_label_ordinal_monotonic(self):
        idx = [tje.label_index(n) for n, _l, _h in common.TJE_CONFIDENCE_LABELS]
        self.assertEqual(idx, list(range(10)))

    def test_system_prompt_has_force_token_and_all_labels(self):
        self.assertIn("\\confidence{X}", common.TJE_SYSTEM_PROMPT)
        for name, _l, _h in common.TJE_CONFIDENCE_LABELS:
            self.assertIn(name, common.TJE_SYSTEM_PROMPT)
        self.assertEqual(common.TJE_CONFIDENCE_FORCE_PREFIX, "\\confidence{")

    def test_official_prompt_hash_and_readout_marker(self):
        self.assertEqual(
            hashlib.sha256(common.TJE_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
            "201ab025fa608098782ebb6b42ba7643800d75377bfd752315486c2f491eab80",
        )
        self.assertIn('- “Almost no chance" (0.0–0.1)', common.TJE_SYSTEM_PROMPT)
        conf = tje.build_confidence_prompt("CHAT", "PREFIX", system="SYSTEM")
        readout = tje.build_readout_prompt(conf, "Almost certain")
        self.assertEqual(readout, conf + "Almost certain}" + chr(10) + common.DEER_THINK_CLOSE + chr(10) + chr(10))
        self.assertIn("\\confidence{Almost certain}", readout)
        self.assertLess(readout.index("\\confidence{Almost certain}"), readout.index(common.DEER_THINK_CLOSE))

    def test_system_prompt_is_in_system_role_without_duplicate_boundaries(self):
        class FakeTokenizer:
            bos_token = "<BOS>"

            def apply_chat_template(self, messages, **_kwargs):
                self.messages = messages
                return "<BOS><SYS>" + messages[0]["content"] + "</SYS><USER>" + \
                    messages[1]["content"] + "</USER><ASSIST><think>\n"

        tokenizer = FakeTokenizer()
        rendered = tje.build_system_chat(tokenizer, "PROBLEM", system="SYSTEM")
        self.assertEqual(
            rendered, "<SYS>SYSTEM</SYS><USER>PROBLEM</USER><ASSIST>"
        )
        self.assertEqual(tokenizer.messages[0]["role"], "system")
        prompt = tje.build_confidence_prompt(rendered, "<think>\nWait")
        self.assertEqual(
            prompt,
            "<SYS>SYSTEM</SYS><USER>PROBLEM</USER><ASSIST><think>\nWait \\confidence{",
        )


# --------------------------------------------------------------------------- #
class CertaIndexStopTests(unittest.TestCase):
    def _probe(self, pid, pos, answer, certain):
        return {"probe_id": pid, "token_position": pos, "probe_answer": answer, "is_certain": certain}

    def test_suffix_is_faithful_not_simple(self):
        # faithful CertaIndex suffix carries the preamble; SIMPLE_SUFFIX does not
        self.assertIn("Oh, I suddenly got the answer", common.CERTAINDEX_SUFFIX)
        self.assertNotIn("Oh, I suddenly got the answer", common.SIMPLE_SUFFIX)
        self.assertNotEqual(common.CERTAINDEX_SUFFIX, common.SIMPLE_SUFFIX)
        # build_probe_prompt uses the faithful suffix by default
        self.assertEqual(certaindex_mid.build_probe_prompt("C", "P")[-len(common.CERTAINDEX_SUFFIX):], common.CERTAINDEX_SUFFIX)

    def test_stop_requires_three_nonempty_equal_certain(self):
        probes = [
            self._probe(1, 64, "204", True),
            self._probe(2, 128, "204", True),
            self._probe(3, 192, "204", True),
        ]
        d = certaindex_mid.decide_stop(probes, answers_equal_fn=_str_eq_group)
        self.assertIsNotNone(d)
        self.assertEqual(d["stop_position"], 192)
        self.assertEqual(d["delivered_answer"], "204")

    def test_no_stop_when_patience_window_not_full(self):
        probes = [self._probe(1, 64, "204", True), self._probe(2, 128, "204", True)]
        self.assertIsNone(certaindex_mid.decide_stop(probes, answers_equal_fn=_str_eq_group))

    def test_no_stop_when_uncertain(self):
        probes = [
            self._probe(1, 64, "204", True),
            self._probe(2, 128, "204", False),  # uncertainty word -> not certain
            self._probe(3, 192, "204", True),
        ]
        self.assertIsNone(certaindex_mid.decide_stop(probes, answers_equal_fn=_str_eq_group))

    def test_no_stop_when_disagree(self):
        probes = [
            self._probe(1, 64, "204", True),
            self._probe(2, 128, "100", True),
            self._probe(3, 192, "204", True),
        ]
        self.assertIsNone(certaindex_mid.decide_stop(probes, answers_equal_fn=_str_eq_group))

    def test_no_stop_when_empty(self):
        probes = [
            self._probe(1, 64, "", True),
            self._probe(2, 128, "", True),
            self._probe(3, 192, "", True),
        ]
        self.assertIsNone(certaindex_mid.decide_stop(probes, answers_equal_fn=_str_eq_group))

    def test_replay_stop_accounting(self):
        traj = {"tokens_used": 1000, "finished_naturally": True, "final_answer": "204",
                "final_correct": True, "target": "204",
                "run_settings": {"budget": 32768}}
        probes = [self._probe(i, 64 * i, "204", True) for i in range(1, 4)]
        out = certaindex_mid.replay(traj, probes, answers_equal_fn=_str_eq_group,
                                    answers_equal_target_fn=_str_eq_target)
        self.assertTrue(out["stopped"])
        self.assertEqual(out["main_tokens_through_stop"], 192)
        self.assertEqual(out["delivered_answer"], "204")
        self.assertTrue(out["correct"])
        # all-generated = main-through-stop + probe outputs; probe prompts separate
        self.assertEqual(out["all_generated_tokens"], 192 + out["probe_out_tokens"])
        self.assertGreater(out["baseline_all_generated_tokens"], out["all_generated_tokens"])

    def test_replay_no_stop_delivers_frozen(self):
        traj = {"tokens_used": 500, "finished_naturally": True, "final_answer": "7",
                "final_correct": True, "target": "7", "run_settings": {"budget": 32768}}
        probes = [self._probe(1, 64, "7", True), self._probe(2, 128, "8", True)]
        out = certaindex_mid.replay(traj, probes, answers_equal_fn=_str_eq_group,
                                    answers_equal_target_fn=_str_eq_target)
        self.assertFalse(out["stopped"])
        self.assertEqual(out["main_tokens_through_stop"], 500)
        self.assertEqual(out["delivered_answer"], "7")
        self.assertTrue(out["correct"])

    def test_replay_capped_trace_has_no_deliverable_future_answer(self):
        traj = {"tokens_used": 500, "finished_naturally": False, "final_answer": "7",
                "final_correct": False, "target": "7", "run_settings": {"budget": 500}}
        out = certaindex_mid.replay(
            traj, [], answers_equal_fn=_str_eq_group,
            answers_equal_target_fn=_str_eq_target,
        )
        self.assertTrue(out["capped"])
        self.assertEqual(out["delivered_answer"], "")

    def test_collector_source_breaks_at_first_stop(self):
        # Regression guard: the live collector must not continue issuing all
        # frozen-prefix probes after the stop rule fires.  Match Dynasor's
        # online behavior by checking only the latest patience-sized window;
        # earlier windows were already checked on prior iterations.
        source = Path(certaindex_mid.__file__).read_text(encoding="utf-8")
        self.assertIn("window = records[-self.patience:]", source)
        self.assertIn("answers_equal_fn(answers)", source)
        self.assertIn("count_not_empty_fn(answers) == self.patience", source)


# --------------------------------------------------------------------------- #
class DEERConfidenceTests(unittest.TestCase):
    import math as _m

    def _lp(self, probs):
        # build (token, logprob) list; tokens named t0..tn-1
        return [(f"t{i}", self._m.log(p)) for i, p in enumerate(probs)]

    def test_avg1_arithmetic(self):
        # skip index 0 -> mean of 0.8, 0.8 = 0.8
        lp = self._lp([0.5, 0.8, 0.8])
        self.assertAlmostEqual(deer.calculate_confidence(lp, policy="avg1", require_think_close=False), 0.8, places=6)

    def test_avg2_geometric(self):
        lp = self._lp([0.5, 0.8, 0.8])
        # geom of 0.8,0.8 = 0.8
        self.assertAlmostEqual(deer.calculate_confidence(lp, policy="avg2", require_think_close=False), 0.8, places=6)
        lp2 = self._lp([0.5, 0.9, 0.4])
        # geom of 0.9,0.4 = sqrt(0.36)=0.6
        self.assertAlmostEqual(deer.calculate_confidence(lp2, policy="avg2", require_think_close=False), 0.6, places=6)

    def test_first_token_skipped(self):
        # index 0 excluded; confidence over indices 1..n-1
        lp = self._lp([1e-9, 0.99, 0.99])
        self.assertAlmostEqual(deer.calculate_confidence(lp, policy="avg1", require_think_close=False), 0.99, places=6)

    def test_qwen3_condition_blocks_exit_without_think_close(self):
        lp = self._lp([0.5, 0.99, 0.99])  # last token not </think>
        self.assertAlmostEqual(deer.calculate_confidence(lp, policy="avg2", require_think_close=True), 0.0, places=12)

    def test_qwen3_condition_passes_with_think_close(self):
        lp = [("a", self._m.log(0.5)), ("b", self._m.log(0.99)), (common.DEER_THINK_CLOSE, self._m.log(0.99))]
        self.assertAlmostEqual(deer.calculate_confidence(lp, policy="avg2", require_think_close=True), 0.99, places=6)

    def test_model_specific_branches(self):
        ds = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        q3 = "Qwen/Qwen3-8B"
        self.assertEqual(deer.policy_for_model(ds), "avg1")
        self.assertEqual(deer.policy_for_model(q3), "avg2")
        self.assertFalse(deer.require_think_close_for_model(ds))
        self.assertTrue(deer.require_think_close_for_model(q3))
        self.assertEqual(deer.trial_stop_tokens(q3), [common.DEER_THINK_CLOSE])
        self.assertIn("}", deer.trial_stop_tokens(ds)[0])

    def test_inducer_and_constants(self):
        self.assertEqual(common.DEER_ANSWER_INDUCER, "\n**Final Answer**\n\\boxed")
        self.assertEqual(common.DEER_THRESHOLD, 0.95)
        self.assertEqual(common.DEER_MAX_JUDGE_STEPS, 10)
        self.assertEqual(common.DEER_TRIAL_CAP, 20)
        self.assertEqual(deer.parse_trial_response("{\\frac{1}{2}} trailing"), "\\frac{1}{2}")

    def test_decide_stop_threshold(self):
        trials = [
            {"candidate_id": 1, "token_position": 64, "confidence": 0.80, "policy": "avg1"},
            {"candidate_id": 2, "token_position": 128, "confidence": 0.97, "policy": "avg1"},
        ]
        d = deer.decide_stop(trials)
        self.assertEqual(d["stop_candidate_id"], 2)
        self.assertEqual(d["stop_position"], 128)

    def test_replay_exit_and_no_exit(self):
        traj = {"tokens_used": 800, "finished_naturally": True, "final_answer": "5",
                "final_correct": True, "target": "5", "run_settings": {"budget": 32768}}
        trials = [{"candidate_id": 1, "token_position": 200, "confidence": 0.97,
                   "policy": "avg1", "trial_out_tokens": 18, "trial_prompt_tokens": 500}]
        readout = {"readout_answer": "5", "readout_out_tokens": 40, "readout_prompt_tokens": 250}
        out = deer.replay(traj, trials, readout=readout, answers_equal_target_fn=_str_eq_target)
        self.assertTrue(out["stopped"])
        self.assertEqual(out["main_tokens_through_stop"], 200)
        self.assertEqual(out["delivered_answer"], "5")
        self.assertEqual(out["all_generated_tokens"], 200 + 18 + 40)
        # no exit: regular end at </think>, frozen full answer
        out2 = deer.replay(traj, [{"candidate_id": 1, "token_position": 200, "confidence": 0.5,
                                    "policy": "avg1", "trial_out_tokens": 18, "trial_prompt_tokens": 500}],
                            answers_equal_target_fn=_str_eq_target)
        self.assertFalse(out2["stopped"])
        self.assertEqual(out2["main_tokens_through_stop"], 800)
        self.assertEqual(out2["delivered_answer"], "5")


# --------------------------------------------------------------------------- #
class ResumabilityDedupTests(unittest.TestCase):
    def test_atomic_write_json_is_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out.json"
            common.atomic_write_json(p, {"a": 1})
            self.assertEqual(json.loads(p.read_text())["a"], 1)
            common.atomic_write_json(p, {"a": 2})
            self.assertEqual(json.loads(p.read_text())["a"], 2)
            # no leftover .tmp
            self.assertFalse((p.with_suffix(".json.tmp")).exists())

    def test_checkpoint_positions_inclusive_natural(self):
        # naturally-stopped trace of 200 tokens, start 64, interval 64
        self.assertEqual(common.checkpoint_positions(200, start_token=64, interval=64, finished_naturally=True),
                         [64, 128, 192])
        # not-finished-naturally adds +1 so the last partial chunk is probed
        self.assertEqual(common.checkpoint_positions(192, start_token=64, interval=64, finished_naturally=False),
                         [64, 128, 192])

    def test_obtain_boxed_answer(self):
        self.assertEqual(common.obtain_boxed_answer("204}\n\n stuff"), "204")
        self.assertEqual(common.obtain_boxed_answer("no close"), "")
        self.assertEqual(common.obtain_boxed_answer("\\frac{1}{2}}"), "\\frac{1}{2}")

    def test_is_certain(self):
        self.assertTrue(common.is_certain("204"))
        self.assertFalse(common.is_certain("wait, maybe 204"))
        self.assertFalse(common.is_certain("Hmm, not sure"))

    def test_trigger_mapping_includes_complete_marker(self):
        class FakeTokenizer:
            def __call__(self, text, **_kwargs):
                return {
                    "input_ids": list(range(len(text))),
                    "offset_mapping": [(i, i + 1) for i in range(len(text))],
                }
        ids, position = common.char_end_to_token_position(FakeTokenizer(), "xWaity", 5)
        self.assertEqual(position, 5)
        self.assertEqual(ids[:position], [0, 1, 2, 3, 4])


class ReplayDriverTests(unittest.TestCase):
    def test_load_collected_rejects_missing(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                replay_driver._load_collected(certaindex_mid, Path(td), 7)

    def test_certaindex_replay_call_has_no_readout_keyword(self):
        source = Path(replay_driver.__file__).read_text(encoding="utf-8")
        self.assertIn("rec = method_mod.replay(traj, seq, **kw)", source)

    def test_replay_environment_runs_each_method(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main = root / "main"
            (main / "traj").mkdir(parents=True)
            run_settings = {
                "model": "Qwen/Qwen3-8B", "dataset": "aime24",
                "base_seed": 42, "budget": 100,
            }
            common.atomic_write_json(main / "run_manifest.json", {"run_settings": run_settings})
            common.atomic_write_json(main / "traj" / "problem_1.json", {
                "problem_id": 1, "tokens_used": 20, "finished_naturally": True,
                "final_answer": "5", "final_correct": True, "target": "5",
                "run_settings": run_settings,
            })
            fixtures = (
                (certaindex_mid, "probes", {"probes": []}),
                (tje, "triggers", {
                    "triggers": [], "readout": None, "include_think_close": True,
                }),
                (deer, "trials", {"trials": [], "readout": None}),
            )
            with mock.patch.object(
                replay_driver, "_real_fns",
                return_value=(_str_eq_group, lambda x: len([v for v in x if v]), _str_eq_target),
            ):
                for module, subdir, payload in fixtures:
                    collected = root / module.METHOD
                    (collected / subdir).mkdir(parents=True)
                    common.atomic_write_json(
                        collected / subdir / "problem_1.json",
                        {
                            "method": module.METHOD,
                            "problem_id": 1,
                            **payload,
                        },
                    )
                    rows = replay_driver.replay_environment(
                        module, main, collected, {("aime24", 1): "dev"}
                    )
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["delivered_answer"], "5")


# --------------------------------------------------------------------------- #
class FrozenBankTests(unittest.TestCase):
    def test_constants_match_real_bank(self):
        self.assertEqual(common.EXPECTED_ENV_COUNT, 18)
        self.assertEqual(common.EXPECTED_TOTAL_TRAJECTORIES, 2736)
        self.assertEqual(common.EXPECTED_PROBLEM_COUNTS, {"math500": 400, "amc23": 32, "aime24": 24})

    @unittest.skipUnless(RESULTS_ROOT.exists() and SPLIT_MANIFEST.exists(),
                         "frozen bank not present in this checkout")
    def test_validate_real_frozen_bank(self):
        # must pass against the committed development bank
        summary = common.validate_frozen_bank(
            REPO_ROOT / "benchmark" / "FalseConsensus" / "results",
            SPLIT_MANIFEST,
        )
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["env_count"], 18)
        self.assertEqual(summary["total_trajectories"], 2736)
        self.assertEqual(summary["protocol_version"], common.EXPECTED_PROTOCOL_VERSION)

    @unittest.skipUnless(RESULTS_ROOT.exists() and SPLIT_MANIFEST.exists(),
                         "frozen bank not present in this checkout")
    def test_bank_summary_counts(self):
        s = common.bank_summary(REPO_ROOT / "benchmark" / "FalseConsensus" / "results")
        self.assertEqual(s["env_count"], 18)
        self.assertEqual(s["total_trajectories"], 2736)

    def test_validate_rejects_test_leakage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # complete split manifest: all three benchmarks with correct
            # train/dev/test counts; aime24 id 0 is placed in the TEST split.
            assignments = []
            # aime24: 18 train (1..18), 6 dev (19..24), 6 test (0, 25..29)
            aime_test = [0] + list(range(25, 30))
            aime_train = list(range(1, 19))
            aime_dev = list(range(19, 25))
            for i in aime_train:
                assignments.append({"benchmark": "aime24", "dataset_index": i, "split": "train"})
            for i in aime_dev:
                assignments.append({"benchmark": "aime24", "dataset_index": i, "split": "dev"})
            for i in aime_test:
                assignments.append({"benchmark": "aime24", "dataset_index": i, "split": "test"})
            # math500 / amc23: just satisfy the count check with synthetic ids
            for b, (tr, dv, te) in common.EXPECTED_SPLIT_COUNTS.items():
                if b == "aime24":
                    continue
                k = 0
                for _ in range(tr):
                    assignments.append({"benchmark": b, "dataset_index": k, "split": "train"}); k += 1
                for _ in range(dv):
                    assignments.append({"benchmark": b, "dataset_index": k, "split": "dev"}); k += 1
                for _ in range(te):
                    assignments.append({"benchmark": b, "dataset_index": k, "split": "test"}); k += 1
            sm = {
                "protocol_version": common.EXPECTED_PROTOCOL_VERSION,
                "split_seed": common.EXPECTED_SPLIT_SEED,
                "summaries": {b: {"source_sha256": common.EXPECTED_SOURCE_SHA256[b]} for b in common.EXPECTED_SOURCE_SHA256},
                "assignments": assignments,
            }
            smp = root / "split_manifest.json"
            common.atomic_write_json(smp, sm)
            env = root / "governor_v2" / "development__deepseek-ai-deepseek-r1-distill-qwen-7b__aime24__seed_42"
            (env / "main" / "traj").mkdir(parents=True)
            # trajectory whose problem_id is the aime24 TEST id 0 -> leakage
            common.atomic_write_json(env / "main" / "traj" / "problem_0.json",
                                     {"problem_id": 0, "full_text": "", "tokens_used": 0,
                                      "finished_naturally": True, "run_settings": {
                                          "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                                          "dataset": "aime24", "base_seed": 42,
                                          "protocol_version": common.EXPECTED_PROTOCOL_VERSION}})
            common.atomic_write_json(env / "main" / "run_manifest.json",
                                     {"run_settings": {"model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                                                       "dataset": "aime24", "base_seed": 42,
                                                       "protocol_version": common.EXPECTED_PROTOCOL_VERSION}})
            with self.assertRaises(ValueError):
                common.validate_frozen_bank(root, smp)


# --------------------------------------------------------------------------- #
class TriggerRecomputationTests(unittest.TestCase):
    """Cross-check Wait/</think> trigger counts on the real frozen bank against
    the authoritative independent recomputation (DeepSeek 30,767 Wait + 1,303
    </think> = 32,070; Qwen3 32,446 Wait + 1,300 </think> = 33,746)."""

    @unittest.skipUnless(RESULTS_ROOT.exists(), "frozen bank not present")
    def test_trigger_counts_match_authoritative(self):
        counts = {"deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": {"wait": 0, "think": 0},
                  "Qwen/Qwen3-8B": {"wait": 0, "think": 0}}
        for env in sorted(RESULTS_ROOT.glob("development__*")):
            manifest = json.loads((env / "main" / "run_manifest.json").read_text())
            model = manifest["run_settings"]["model"]
            if model not in counts:
                continue
            for tp in sorted((env / "main" / "traj").glob("problem_*.json")):
                text = json.loads(tp.read_text())["full_text"]
                counts[model]["wait"] += len(common.find_wait_positions(text))
                counts[model]["think"] += len(common.find_think_close_positions(text))
        ds = counts["deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"]
        q3 = counts["Qwen/Qwen3-8B"]
        self.assertEqual(ds["wait"], 30767, f"DeepSeek Wait count {ds['wait']}")
        self.assertEqual(ds["think"], 1303, f"DeepSeek </think> count {ds['think']}")
        self.assertEqual(ds["wait"] + ds["think"], 32070)
        self.assertEqual(q3["wait"], 32446, f"Qwen3 Wait count {q3['wait']}")
        self.assertEqual(q3["think"], 1300, f"Qwen3 </think> count {q3['think']}")
        self.assertEqual(q3["wait"] + q3["think"], 33746)


# --------------------------------------------------------------------------- #
class MetricsTests(unittest.TestCase):
    def test_per_problem_metric_two_views(self):
        rec = {"method": "x", "model": "m", "dataset": "d", "base_seed": 42, "problem_id": 1,
               "split": "dev", "correct": 1, "baseline_correct": 1, "delivered_answer": "5",
               "stopped": True, "capped": False, "recovery_truncated": True,
               "full_main_tokens": 1000, "main_tokens_through_stop": 200,
               "all_generated_tokens": 260, "probe_out_tokens": 60, "probe_prompt_tokens": 800,
               "baseline_all_generated_tokens": 1000, "overthinking_avoided_tokens": 800}
        m = metrics.per_problem_metric(rec)
        self.assertAlmostEqual(m["main_only_saving_fraction"], 0.8)
        self.assertAlmostEqual(m["all_generated_saving_fraction"], 0.74)
        self.assertEqual(m["probe_prompt_tokens"], 800)  # reported separately, not in all_generated

    def test_aggregate_and_bootstrap(self):
        rows_m = [{"base_seed": 42, "problem_id": i, "correct": int(i % 2 == 0),
                   "all_generated_tokens": 100, "baseline_all_generated_tokens": 200} for i in range(8)] + \
                 [{"base_seed": 43, "problem_id": i, "correct": int(i % 3 == 0),
                   "all_generated_tokens": 120, "baseline_all_generated_tokens": 200} for i in range(8)]
        rows_b = [{"base_seed": r["base_seed"], "problem_id": r["problem_id"], "correct": 1,
                   "all_generated_tokens": 200, "baseline_all_generated_tokens": 200} for r in rows_m]
        agg = metrics.aggregate([metrics.per_problem_metric({**r, "method": "m", "model": "mo", "dataset": "d",
                                                              "baseline_correct": 1, "stopped": 1, "capped": 0,
                                                              "recovery_truncated": 0, "main_tokens_through_stop": 100,
                                                              "full_main_tokens": 200, "probe_out_tokens": 0,
                                                              "probe_prompt_tokens": 0, "delivered_answer": "x",
                                                              "overthinking_avoided_tokens": 0})
                                 for r in rows_m])
        self.assertEqual(agg["n"], 16)
        ci = metrics.paired_hierarchical_ci(rows_m, rows_b, n_samples=500, seed=20260727)
        self.assertEqual(ci["n_rows"], 16)
        self.assertLess(ci["accuracy_diff_ci_lo"], ci["accuracy_diff_ci_hi"])
        self.assertLess(ci["token_saving_ci_lo"], ci["token_saving_ci_hi"])
        self.assertEqual(ci["seed"], 20260727)

    def test_cross_environment_views(self):
        rows = []
        for seed in (42, 43, 44):
            for problem_id, split in ((1, "train"), (2, "dev")):
                rows.append(metrics.per_problem_metric({
                    "method": "m", "model": "model", "dataset": "math500",
                    "base_seed": seed, "problem_id": problem_id, "split": split,
                    "correct": 1, "baseline_correct": 1, "delivered_answer": "1",
                    "stopped": True, "capped": False, "recovery_truncated": True,
                    "full_main_tokens": 100, "main_tokens_through_stop": 50,
                    "all_generated_tokens": 60, "probe_out_tokens": 10,
                    "probe_prompt_tokens": 100,
                    "baseline_all_generated_tokens": 100,
                    "overthinking_avoided_tokens": 50,
                }))
        views = aggregate_all.build_views(rows, n_samples=50, seed=20260727)
        self.assertEqual(len(views["environment_split"]), 6)
        self.assertEqual(len(views["dev_pooled"]), 1)
        self.assertEqual(views["dev_pooled"][0]["ci"]["n_rows"], 3)
        self.assertAlmostEqual(
            views["dev_pooled"][0]["all_generated_token_saving_fraction"], 0.4
        )


if __name__ == "__main__":
    unittest.main()
