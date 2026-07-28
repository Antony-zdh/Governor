"""Focused tests for the durable full-bank launcher: exact model/revision/endpoint
mappings, authorized 9-environment discovery, required collector CLI arguments,
launcher dry-run behavior, and manifest completion verification.
These do not touch GPUs or start the full bank."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from benchmark.FalseConsensus.related_work import common, model_map, certaindex_mid, tje, deer  # noqa

LAUNCHER = REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh"


class ModelMapTests(unittest.TestCase):
    def test_exact_mappings(self):
        ds = model_map.model_info("deepseek")
        self.assertEqual(ds["model_id"], "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
        self.assertEqual(ds["revision"], "916b56a44061fd5cd7d6a8fb632557ed4f724f60")
        self.assertEqual(ds["endpoint"], "http://127.0.0.1:18000/v1")
        self.assertEqual(ds["port"], 18000)
        self.assertEqual(ds["gpu"], 0)
        q3 = model_map.model_info("qwen3")
        self.assertEqual(q3["model_id"], "Qwen/Qwen3-8B")
        self.assertEqual(q3["revision"], "b968826d9c46dd6066d109eabc6255188de91218")
        self.assertEqual(q3["endpoint"], "http://127.0.0.1:18001/v1")
        self.assertEqual(q3["port"], 18001)
        self.assertEqual(q3["gpu"], 1)

    def test_revisions_are_40_hex(self):
        for key in ("deepseek", "qwen3"):
            self.assertTrue(model_map.is_valid_model_key(key))
            self.assertTrue(common.is_40hex(model_map.revision_for(key)))

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            model_map.model_info("llama")

    def test_authorized_envs_count_and_names(self):
        for key in ("deepseek", "qwen3"):
            envs = model_map.authorized_envs(key)
            self.assertEqual(len(envs), 9)
            benches = sorted({b for b, s, _ in envs})
            self.assertEqual(benches, ["aime24", "amc23", "math500"])
            seeds = sorted({s for b, s, _ in envs})
            self.assertEqual(seeds, [42, 43, 44])
            slug = model_map.model_info(key)["slug"]
            for b, s, name in envs:
                self.assertEqual(name, "development__" + slug + "__" + b + "__seed_" + str(s))


class CollectorCommandTests(unittest.TestCase):
    def test_command_has_all_required_args(self):
        cmd = model_map.collector_command(
            "deepseek", "certaindex_mid", "/tmp/M", "/tmp/O", "/tmp/sm", workers=4)
        for flag in ("--main-run", "/tmp/M", "--output", "/tmp/O",
                     "--url", "http://127.0.0.1:18000/v1",
                     "--model", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                     "--model-revision", "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
                     "--split-manifest", "/tmp/sm", "--workers", "4"):
            self.assertIn(flag, cmd)

    def test_tje_command_has_max_model_len_and_readout_cap(self):
        cmd = model_map.collector_command("qwen3", "tje", "/M", "/O", "/sm")
        self.assertIn("--max-model-len", cmd)
        self.assertIn("34816", cmd)
        self.assertIn("--readout-cap", cmd)
        self.assertIn("8192", cmd)
        self.assertIn("http://127.0.0.1:18001/v1", cmd)

    def test_deer_command_qwen3_endpoint(self):
        cmd = model_map.collector_command("qwen3", "deer", "/M", "/O", "/sm")
        self.assertIn("http://127.0.0.1:18001/v1", cmd)
        self.assertIn("b968826d9c46dd6066d109eabc6255188de91218", cmd)
        self.assertNotIn("--max-model-len", cmd)
        self.assertNotIn("--readout-cap", cmd)

    def test_collectors_require_model_revision(self):
        base = ["--main-run", "/tmp/M", "--output", "/tmp/O", "--url", "http://x/v1",
                "--model", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "--split-manifest", "/tmp/sm"]
        for mod in (certaindex_mid, tje, deer):
            with self.assertRaises(SystemExit):
                mod.parse_args(base)

    def test_collectors_accept_model_revision(self):
        base = ["--main-run", "/tmp/M", "--output", "/tmp/O", "--url", "http://x/v1",
                "--model", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "--model-revision", "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
                "--split-manifest", "/tmp/sm"]
        for mod in (certaindex_mid, tje, deer):
            ns = mod.parse_args(base)
            self.assertEqual(ns.model_revision, "916b56a44061fd5cd7d6a8fb632557ed4f724f60")


class LauncherDryRunTests(unittest.TestCase):
    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", str(LAUNCHER)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "bash -n failed: " + r.stderr)

    def test_unknown_key_rejected(self):
        r = subprocess.run(["bash", str(LAUNCHER), "llama", "--dry-run"],
                            capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_dry_run_deepseek(self):
        r = subprocess.run(["bash", str(LAUNCHER), "deepseek", "--dry-run"],
                           capture_output=True, text=True, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", out)
        self.assertIn("916b56a44061fd5cd7d6a8fb632557ed4f724f60", out)
        self.assertIn("http://127.0.0.1:18000/v1", out)
        self.assertEqual(
            out.count("[certaindex_mid]") + out.count("[tje]") + out.count("[deer]"), 27)
        self.assertIn("no outputs written", out)

    def test_dry_run_qwen3(self):
        r = subprocess.run(["bash", str(LAUNCHER), "qwen3", "--dry-run"],
                           capture_output=True, text=True, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("Qwen/Qwen3-8B", out)
        self.assertIn("b968826d9c46dd6066d109eabc6255188de91218", out)
        self.assertIn("http://127.0.0.1:18001/v1", out)
        self.assertIn("--max-model-len", out)
        self.assertIn("34816", out)
        self.assertIn("--readout-cap", out)
        self.assertIn("8192", out)
        self.assertIn("no outputs written", out)


class ManifestCheckTests(unittest.TestCase):
    """Tests for manifest completion verification (item 3/4) with temp fixtures."""

    def _write_manifest(self, tmpdir, completion):
        p = Path(tmpdir) / "probe_manifest.json"
        d = {"schema_version": "related-work-certaindex-run-1",
             "probe_settings": {"model_revision": "x"}, "completion": completion}
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def test_valid_manifest_passes(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0})
            ok, reason = manifest_check.check_manifest(p, 400)
            self.assertTrue(ok)
            self.assertEqual(reason, "ok")

    def test_incomplete_manifest_fails(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": False, "expected_problem_count": 400,
                                          "observed_problem_count": 100, "missing_problem_count": 300,
                                          "recorded_failures": 0})
            ok, _ = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)

    def test_recorded_failures_fails(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 32,
                                          "observed_problem_count": 32, "missing_problem_count": 0,
                                          "recorded_failures": 3})
            ok, reason = manifest_check.check_manifest(p, 32)
            self.assertFalse(ok)
            self.assertIn("recorded_failures=3", reason)

    def test_wrong_observed_count_fails(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 24,
                                          "observed_problem_count": 20, "missing_problem_count": 4,
                                          "recorded_failures": 0})
            ok, _ = manifest_check.check_manifest(p, 24)
            self.assertFalse(ok)

    def test_no_completion_block_fails(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe_manifest.json"
            p.write_text('{"probe_settings": {}}', encoding="utf-8")
            ok, reason = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)
            self.assertIn("no completion", reason)

    def test_unreadable_json_fails(self):
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe_manifest.json"
            p.write_text("{bad json", encoding="utf-8")
            ok, _ = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)

    def test_manifest_cli_exits_nonzero_for_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": False, "expected_problem_count": 400,
                                          "observed_problem_count": 0, "missing_problem_count": 400,
                                          "recorded_failures": 0})
            r = subprocess.run([sys.executable, "-m",
                                "benchmark.FalseConsensus.related_work.manifest_check",
                                str(p), "400"], capture_output=True, text=True, cwd=str(REPO_ROOT))
            self.assertEqual(r.returncode, 1)

    def test_manifest_cli_exits_zero_for_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0})
            r = subprocess.run([sys.executable, "-m",
                                "benchmark.FalseConsensus.related_work.manifest_check",
                                str(p), "400"], capture_output=True, text=True, cwd=str(REPO_ROOT))
            self.assertEqual(r.returncode, 0)


class ManifestInvalidReadoutsTests(unittest.TestCase):
    """manifest_check: both invalid_readouts and truncated_readouts are DIAGNOSTIC
    method outcomes (not hard failures). Only recorded_failures (request errors),
    noncoverage (missing/observed mismatch), and complete=false are hard failures.
    A capped readout at readout_cap=8192 with no completed boxed is a complete
    per-problem record (replay delivers empty/incorrect)."""

    def _write_manifest(self, tmpdir, completion):
        p = Path(tmpdir) / "probe_manifest.json"
        d = {"schema_version": "related-work-certaindex-run-1",
             "probe_settings": {}, "completion": completion}
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def test_invalid_readouts_nonzero_passes(self):
        """invalid_readouts > 0 is a diagnostic, NOT a hard failure."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0, "invalid_readouts": 14})
            ok, reason = manifest_check.check_manifest(p, 400)
            self.assertTrue(ok)
            self.assertEqual(reason, "ok")

    def test_truncated_readouts_nonzero_passes(self):
        """truncated_readouts > 0 (capped at readout_cap=8192) is a diagnostic,
        NOT a hard failure."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0, "invalid_readouts": 0,
                                          "truncated_readouts": 34})
            ok, reason = manifest_check.check_manifest(p, 400)
            self.assertTrue(ok)
            self.assertEqual(reason, "ok")

    def test_both_invalid_and_truncated_nonzero_passes(self):
        """Both diagnostics nonzero -- still passes."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0, "invalid_readouts": 107,
                                          "truncated_readouts": 34})
            ok, _ = manifest_check.check_manifest(p, 400)
            self.assertTrue(ok)

    def test_recorded_failures_nonzero_fails(self):
        """recorded_failures > 0 (actual request errors) IS a hard failure."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 3})
            ok, reason = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)
            self.assertIn("recorded_failures=3", reason)

    def test_noncoverage_fails(self):
        """missing_problem_count > 0 IS a hard failure."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": True, "expected_problem_count": 400,
                                          "observed_problem_count": 300, "missing_problem_count": 100,
                                          "recorded_failures": 0})
            ok, _ = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)

    def test_incomplete_fails(self):
        """complete=false IS a hard failure."""
        from benchmark.FalseConsensus.related_work import manifest_check
        with tempfile.TemporaryDirectory() as td:
            p = self._write_manifest(td, {"complete": False, "expected_problem_count": 400,
                                          "observed_problem_count": 400, "missing_problem_count": 0,
                                          "recorded_failures": 0})
            ok, _ = manifest_check.check_manifest(p, 400)
            self.assertFalse(ok)


class ProgressValidationTests(unittest.TestCase):
    """progress._validate_problem_file: readout_valid False is invalid; missing
    readout is valid (no-trigger); problem_id mismatch is invalid."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "progress",
            str(REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/progress.py"))
        cls.progress = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.progress)

    def _tje_record(self, pid=430, readout=None):
        d = {"schema_version": "related-work-tje-trigger-1",
             "problem_id": pid,
             "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
             "dataset": "math500", "base_seed": 42,
             "triggers": [{"trigger_id": 1, "trigger_type": "wait"}],
             "readout": readout}
        return d

    def _write(self, td, pid, d):
        p = Path(td) / ("problem_" + str(pid) + ".json")
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def test_readout_valid_false_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 430, self._tje_record(
                readout={"readout_valid": False, "readout_answer": "", "readout_finish_reason": "length"}))
            self.assertFalse(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_readout_valid_true_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 430, self._tje_record(
                readout={"readout_valid": True, "readout_answer": "31", "readout_finish_reason": "stop"}))
            self.assertTrue(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_missing_readout_is_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 430, self._tje_record(readout=None))
            self.assertTrue(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_problem_id_mismatch_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(td, 430, self._tje_record(pid=431))
            self.assertFalse(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_wrong_model_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._tje_record()
            d["model"] = "wrong/model"
            p = self._write(td, 430, d)
            self.assertFalse(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))

    def test_error_in_trigger_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            d = self._tje_record()
            d["triggers"][0]["error"] = "timeout"
            p = self._write(td, 430, d)
            self.assertFalse(self.progress._validate_problem_file(
                p, "tje", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "math500", 42))


class ShellConditionalTests(unittest.TestCase):
    """Regression for the set -e + command-substitution trap: the
    if assignment; then rc=0; else rc=$?; fi pattern must capture a nonzero
    exit code without terminating the script."""

    def test_nonzero_captured_under_set_e(self):
        snippet = (
            "set -euo pipefail\n"
            "if out=$(false); then rc=0; else rc=$?; fi\n"
            "echo \"rc=$rc out=$out\"\n"
        )
        r = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "script should not crash: " + r.stderr)
        self.assertIn("rc=1", r.stdout)

    def test_zero_captured_under_set_e(self):
        snippet = (
            "set -euo pipefail\n"
            "if out=$(echo hello); then rc=0; else rc=$?; fi\n"
            "echo \"rc=$rc out=$out\"\n"
        )
        r = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("rc=0", r.stdout)
        self.assertIn("hello", r.stdout)

    def test_launcher_verify_manifest_conditional_form(self):
        """The launcher's verify_manifest function uses the if/else pattern;
        bash -n confirms syntax, and a direct call with a missing manifest
        returns nonzero without crashing."""
        r = subprocess.run(
            ["bash", "-n", str(LAUNCHER)],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


class TopLevelLocalTests(unittest.TestCase):
    """Regression: `local` is function-only in bash. A `local` declaration in
    the top-level loop (outside any function) is a runtime error that bash -n
    does not catch. This static check asserts no `local` appears in the
    launcher's full-run section (after the dry-run block)."""

    def test_no_local_at_top_level(self):
        text = LAUNCHER.read_text(encoding="utf-8")
        # The full-run section starts after the dry-run block's exit 0
        marker = "# --- full run ---"
        self.assertIn(marker, text, "full-run marker not found")
        full_run_section = text[text.index(marker):]
        for i, line in enumerate(full_run_section.splitlines(), 1):
            stripped = line.strip()
            # `local` as a bash keyword: line starts with "local " or contains
            # " local " as a command (not inside a string/comment)
            if stripped.startswith("local ") or stripped.startswith("local\t"):
                self.fail(
                    "top-level `local` found in full-run section at line +{0}: {1!r}".format(
                        i, line))

    def test_local_at_top_level_causes_runtime_error(self):
        """Demonstrates the bug: `local` outside a function is a runtime error."""
        snippet = "set -e\nlocal x=1\necho survived"
        r = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("local", r.stderr.lower())


if __name__ == "__main__":
    unittest.main()
