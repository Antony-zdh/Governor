"""Authoritative model/revision/endpoint map for the related-work baselines.

Single tested source of truth for the model key -> (model id, 40-hex revision,
endpoint URL, port, GPU id, slug, expected dev environments). The bash launcher
``_runtime/run_full_model_pipeline.sh`` mirrors this map; the regression tests
verify both agree.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# Hard map. GPU ids are informational only -- the launcher never selects, resets,
# or touches GPUs/processes; it talks only to the already-running vLLM endpoint.
MODELS: Dict[str, Dict[str, object]] = {
    "deepseek": {
        "model_id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "revision": "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
        "endpoint": "http://127.0.0.1:18000/v1",
        "port": 18000,
        "gpu": 0,
        "slug": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    },
    "qwen3": {
        "model_id": "Qwen/Qwen3-8B",
        "revision": "b968826d9c46dd6066d109eabc6255188de91218",
        "endpoint": "http://127.0.0.1:18001/v1",
        "port": 18001,
        "gpu": 1,
        "slug": "qwen-qwen3-8b",
    },
}

BENCHMARKS = ("math500", "amc23", "aime24")
SEEDS = (42, 43, 44)
EXPECTED_PROBLEM_COUNTS = {"math500": 400, "amc23": 32, "aime24": 24}
METHODS = ("certaindex_mid", "tje", "deer")

# TJE-specific pinned runtime params.
TJE_MAX_MODEL_LEN = 34816
TJE_READOUT_CAP = 8192


def is_valid_model_key(key: str) -> bool:
    return key in MODELS


def model_info(key: str) -> Dict[str, object]:
    if key not in MODELS:
        raise ValueError(f"unknown model key {key!r}; expected one of {sorted(MODELS)}")
    return dict(MODELS[key])


def revision_for(key: str) -> str:
    return str(MODELS[key]["revision"])


def endpoint_for(key: str) -> str:
    return str(MODELS[key]["endpoint"])


def env_dir_name(key: str, bench: str, seed: int) -> str:
    """Frozen main-run environment directory name (under governor_v2/)."""
    return f"development__{MODELS[key]['slug']}__{bench}__seed_{seed}"


def authorized_envs(key: str) -> List[Tuple[str, int, str]]:
    """The exactly-9 authorized development environments for a model key:
    (benchmark, seed, env_dir_name) for math500/amc23/aime24 x seeds 42/43/44."""
    if key not in MODELS:
        raise ValueError(f"unknown model key {key!r}")
    return [(b, s, env_dir_name(key, b, s)) for b in BENCHMARKS for s in SEEDS]


def collector_command(key: str, method: str, main_run: str, output: str,
                      split_manifest: str, workers: int = 4) -> List[str]:
    """Build the exact, fully-runnable collector command for a method/env."""
    info = model_info(key)
    cmd = [
        "python", "-m", f"benchmark.FalseConsensus.related_work.{method}",
        "--main-run", main_run,
        "--output", output,
        "--url", str(info["endpoint"]),
        "--model", str(info["model_id"]),
        "--model-revision", str(info["revision"]),
        "--split-manifest", split_manifest,
        "--workers", str(workers),
    ]
    if method == "tje":
        cmd += ["--max-model-len", str(TJE_MAX_MODEL_LEN),
                "--readout-cap", str(TJE_READOUT_CAP)]
    return cmd
