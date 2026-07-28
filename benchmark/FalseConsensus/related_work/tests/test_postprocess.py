"""CPU-only tests for the postprocess orchestrator, report generator, and PDF
rendering script. These do not touch GPUs, frozen trajectories, collector
semantics, or active full output files."""
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

from benchmark.FalseConsensus.related_work import postprocess, report_gen, common, metrics  # noqa

RENDER_PDF = REPO_ROOT / "benchmark/FalseConsensus/results/related_work/_runtime/render_pdf.sh"


class PostprocessDryRunTests(unittest.TestCase):
    def test_dry_run_prints_plan(self):
        r = subprocess.run(
            [sys.executable, "-m", "benchmark.FalseConsensus.related_work.postprocess", "--dry-run"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
            env={**os.environ,
                 "LD_PRELOAD": "/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6",
                 "LD_LIBRARY_PATH": "/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64",
                 "HF_HOME": "/localdata/dzhaoah/hf-cache"})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        self.assertIn("DRY RUN", out)
        self.assertIn("replay_commands=54", out)
        self.assertIn("expected_rows=8208", out)
        self.assertIn(str(metrics.BOOTSTRAP_SAMPLES), out)
        self.assertIn("replay_jobs=8", out)
        self.assertIn("no outputs written", out)

    def test_dry_run_non_mutating(self):
        """Dry run should not create any output files."""
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(
                [sys.executable, "-m", "benchmark.FalseConsensus.related_work.postprocess",
                 "--dry-run", "--full-root", td, "--replay-root", str(Path(td) / "replay"),
                 "--aggregate-dir", str(Path(td) / "agg")],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
                env={**os.environ,
                     "LD_PRELOAD": "/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6",
                     "LD_LIBRARY_PATH": "/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64",
                     "HF_HOME": "/localdata/dzhaoah/hf-cache"})
            self.assertEqual(r.returncode, 0, r.stderr)
            # no files created in the temp dir
            created = list(Path(td).rglob("*"))
            self.assertEqual(len(created), 0, f"dry-run created files: {created}")


class ReportGenTests(unittest.TestCase):
    def _fixture_aggregate(self):
        return {
            "schema_version": "related-work-aggregate-1",
            "bootstrap_samples": metrics.BOOTSTRAP_SAMPLES,
            "bootstrap_seed": metrics.BOOTSTRAP_SEED,
            "row_count": 8208,
            "methods": ["certaindex_mid_frozen", "deer_frozen", "tje_frozen"],
            "coverage": {"ok": True, "method_count": 3, "environment_count": 54,
                         "rows_per_method": {"certaindex_mid_frozen": 2736, "tje_frozen": 2736, "deer_frozen": 2736},
                         "test_rows": 0},
            "dev_pooled": [
                {"method": "certaindex_mid_frozen", "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                 "dataset": "math500", "n": 300, "accuracy": 0.85, "baseline_accuracy": 0.90,
                 "accuracy_diff_pp": -5.0, "all_generated_token_saving_fraction": 0.30,
                 "main_only_token_saving_fraction": 0.40, "stop_rate": 0.75, "avg_probe_out_tokens": 12.5,
                 "ci": {"accuracy_diff": -0.05, "accuracy_diff_ci_lo": -0.08, "accuracy_diff_ci_hi": -0.02,
                        "all_generated_token_saving": 0.30, "token_saving_ci_lo": 0.25, "token_saving_ci_hi": 0.35}},
            ],
            "dev_macro": [
                {"method": "certaindex_mid_frozen", "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                 "benchmark_count": 3, "accuracy": 0.83, "accuracy_diff_pp": -4.5,
                 "all_generated_token_saving_fraction": 0.28, "main_only_token_saving_fraction": 0.38,
                 "stop_rate": 0.70},
            ],
        }

    def test_report_with_data(self):
        with tempfile.TemporaryDirectory() as td:
            agg_path = Path(td) / "aggregate.json"
            out_path = Path(td) / "report.md"
            agg_path.write_text(json.dumps(self._fixture_aggregate(), ensure_ascii=False), encoding="utf-8")
            text = report_gen.generate_report(agg_path, out_path)
            self.assertTrue(out_path.exists())
            self.assertIn("Governor v2 相关工作基线实验报告", text)
            self.assertIn("CertaIndex faithful mid", text)
            self.assertIn("85.00%", text)  # fixture accuracy
            self.assertIn("[-8.00, -2.00]", text)
            self.assertIn("[25.00, 35.00]", text)
            self.assertIn("数据已就绪", text)
            self.assertIn("Accuracy-compute Pareto", text)
            self.assertIn("Matched-accuracy / matched-token", text)
            self.assertIn("Artifact inventory", text)
            self.assertIn("复现命令", text)

    def test_report_skeleton_no_data(self):
        with tempfile.TemporaryDirectory() as td:
            agg_path = Path(td) / "nonexistent.json"
            out_path = Path(td) / "report.md"
            text = report_gen.generate_report(agg_path, out_path)
            self.assertTrue(out_path.exists())
            self.assertIn("数据尚不完整", text)
            self.assertIn("数据待补", text)
            # must NOT contain fabricated fixture values
            self.assertNotIn("0.85", text)

    def test_report_cli(self):
        with tempfile.TemporaryDirectory() as td:
            agg_path = Path(td) / "aggregate.json"
            out_path = Path(td) / "report.md"
            agg_path.write_text(json.dumps(self._fixture_aggregate(), ensure_ascii=False), encoding="utf-8")
            r = subprocess.run(
                [sys.executable, "-m", "benchmark.FalseConsensus.related_work.report_gen",
                 "--aggregate", str(agg_path), "--output", str(out_path)],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
                env={**os.environ,
                     "LD_PRELOAD": "/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6",
                     "LD_LIBRARY_PATH": "/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64",
                     "HF_HOME": "/localdata/dzhaoah/hf-cache"})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out_path.exists())


class RenderPdfSyntaxTests(unittest.TestCase):
    def test_bash_n(self):
        r = subprocess.run(["bash", "-n", str(RENDER_PDF)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"bash -n failed: {r.stderr}")


class ManifestCheckAllTests(unittest.TestCase):
    """Test the postprocess.check_all_manifests logic with temp fixtures."""

    def _make_manifest(self, dir_path, method, complete, expected=400, observed=None,
                      missing=0, failures=0, invalid_readouts=0):
        name = {"certaindex_mid": "probe_manifest.json",
                "tje": "trigger_manifest.json", "deer": "trial_manifest.json"}[method]
        d = {"completion": {
            "complete": complete,
            "expected_problem_count": expected,
            "observed_problem_count": observed if observed is not None else expected,
            "missing_problem_count": missing,
            "recorded_failures": failures,
            "invalid_readouts": invalid_readouts,
        }}
        p = Path(dir_path) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d), encoding="utf-8")
        return p

    def test_all_manifests_ok(self):
        with tempfile.TemporaryDirectory() as td:
            for method in ("certaindex_mid", "tje", "deer"):
                for key in ("deepseek", "qwen3"):
                    for bench in ("math500", "amc23", "aime24"):
                        for seed in (42, 43, 44):
                            exp = {"math500": 400, "amc23": 32, "aime24": 24}[bench]
                            d = Path(td) / f"{key}__{bench}__seed_{seed}" / method
                            self._make_manifest(d, method, True, expected=exp)
            ok, failures = postprocess.check_all_manifests(Path(td))
            self.assertTrue(ok)
            self.assertEqual(len(failures), 0)

    def test_one_incomplete_manifest_detected(self):
        with tempfile.TemporaryDirectory() as td:
            for method in ("certaindex_mid", "tje", "deer"):
                for key in ("deepseek", "qwen3"):
                    for bench in ("math500", "amc23", "aime24"):
                        for seed in (42, 43, 44):
                            exp = {"math500": 400, "amc23": 32, "aime24": 24}[bench]
                            d = Path(td) / f"{key}__{bench}__seed_{seed}" / method
                            complete = not (method == "tje" and key == "deepseek" and bench == "math500" and seed == 42)
                            self._make_manifest(d, method, complete, expected=exp,
                                               observed=exp if complete else 0,
                                               missing=0 if complete else exp)
            ok, failures = postprocess.check_all_manifests(Path(td))
            self.assertFalse(ok)
            self.assertEqual(len(failures), 1)


if __name__ == "__main__":
    unittest.main()
