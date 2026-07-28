"""Shared frozen-trajectory utilities for the related-work baselines.

This module is the reuse seam between the existing Governor v2 / Dynasor
infrastructure and the three new related-work collectors (CertaIndex faithful
``mid``, TJE, DEER). It deliberately imports only the Python standard library
at module load time so that the pure-logic helpers (checkpoint positions,
trigger parsing, answer extraction, stop decisions, accounting) are importable
and unit-testable on a bare interpreter with no torch / transformers / sympy /
openai installed.

Heavy, dependency-bearing helpers (``AutoTokenizer``, the OpenAI client,
``dynasor.core.evaluator.eqaul_group`` / ``math_equal``, ``grading.robust_answers_equal``,
``clients.apply_chat_template``) are imported *lazily* inside the functions
that actually need them, so that importing this module never pulls in a
missing dependency. The small stdlib-only helpers below mirror the existing
governor_v2 implementations (cited inline) rather than re-import them, to
keep the import graph dependency-free.

Frozen-trajectory convention (governor_v2 ``dense_probe.py``):
    the stored main ``full_text`` is re-encoded once with
    ``tokenizer.encode(full_text, add_special_tokens=False)`` and probes are
    issued on ``tokenizer.decode(token_ids[:position])`` at fixed positions
    64, 128, 192, ... The stored ``tokens_used`` is also recorded and the
    re-encoded length is checked against it; a material mismatch is flagged.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Repository layout
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
GOVERNOR_V2 = HERE.parent / "governor_v2"
REPO_ROOT = HERE.parents[2]
TOKENDEPRIVATION = REPO_ROOT / "benchmark" / "TokenDeprivation"

# --------------------------------------------------------------------------- #
# Dynasor / Governor v2 constants (verbatim sources of truth)
# --------------------------------------------------------------------------- #
# CertaIndex probe suffix, verbatim from dynasor/core/cot.py:43 (the default
# ``probeing_suffix`` of ``openai_chat_completion_stream``). This is the
# FAITHFUL CertaIndex suffix, including the "Oh, I suddenly got the answer"
# preamble. It is deliberately distinct from the governor_v2 ``SIMPLE_SUFFIX``
# ("**Final Answer**\n\n\\[ \\boxed{") which is the prompt-matched auxiliary
# baseline suffix without the preamble.
CERTAINDEX_SUFFIX = "... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\\[ \\boxed{"

# governor_v2/dense_probe.py:26 -- the simple@32 auxiliary suffix (no preamble).
SIMPLE_SUFFIX = "**Final Answer**\n\n\\[ \\boxed{"

# dynasor/core/cot.py:5 and dynasor/core/entropy.py:99 -- verbatim.
UNCERTAIN_WORDS: Tuple[str, ...] = ("wait", "hold", "but", "okay", "no", "hmm")

# dynasor/core/cot.py:13 -- effort_level("mid") == (patience=3, chunk_size=64).
CERTAINDEX_MID_PATIENCE = 3
CERTAINDEX_MID_INTERVAL = 64
CERTAINDEX_MID_PROBE_CAP = 20

# Sampling pinned by the frozen main runs and reused (prompt-matched) by all
# three baselines' probes unless the official method mandates otherwise.
DEFAULT_TEMPERATURE = 0.6
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 20

# DEER official defaults (vllm-deer.py @ c9dd19f, argparse defaults).
DEER_THRESHOLD = 0.95
DEER_MAX_JUDGE_STEPS = 10
DEER_TRIAL_CAP = 20
# vllm-deer.py:252 -- answer inducer (verbatim).
DEER_ANSWER_INDUCER = "\n**Final Answer**\n\\boxed"
# vllm-deer.py:248/251 -- transition / end-of-think markers.
DEER_CONTINUE_STR = "Wait"
DEER_THINK_CLOSE = "</think>"
# vllm-deer.py:269 -- stop tokens that close \boxed{} in the trial answer.
DEER_PRED_PROB_STOP_TOKENS = (
    " }",
    "}\n",
    "}\n\n",
    "}.",
    "}.\n",
    "}\\",
    "}}",
    ")}",
    ")}.",
    ")}\n",
)

# TJE official system prompt (Figure 2 of https://aclanthology.org/2026.findings-eacl.263/),
# supplied verbatim from the authoritative PDF extraction. The ten confidence
# labels are preserved with their probability ranges.
TJE_SYSTEM_PROMPT = (
    "During the thinking process, you must periodically assess the confidence of your "
    "current reasoning. This assessment should not only reflect how confident you are in "
    "the current reasoning steps, but also whether you have sufficiently explored the "
    "problem, considered possible errors, and ensured there are no flaws or gaps in the "
    "logic. Assess whether you have thought deeply enough to be confident in your final "
    "answer.\n"
    "Use one of the following confidence levels:\n"
    '- “Almost no chance" (0.0–0.1)\n'
    '- "Highly unlikely" (0.1–0.2)\n'
    '- "Chances are slight" (0.2–0.3)\n'
    '- "Unlikely" (0.3–0.4)\n'
    '- "Less than even" (0.4–0.5)\n'
    '- "Better than even" (0.5–0.6)\n'
    '- "Likely" (0.6–0.7)\n'
    '- "Very good chance" (0.7–0.8)\n'
    '- "Highly likely" (0.8–0.9)\n'
    '- "Almost certain" (0.9–1.0)\n'
    "Each category reflects the overall confidence that your answer is correct, **only if** "
    "you have performed sufficient reasoning to justify your final answer. High confidence "
    "should only be reported when you have thought through the problem thoroughly and "
    "believe your reasoning supports the conclusion beyond reasonable doubt\n"
    "Always denote this using \\confidence{X}, where X is the confidence class name (only "
    "the name, without the probability range). For example, if you are 95% sure of your "
    "reasoning, you would write \\confidence{Almost certain}. If you are 12% sure, you "
    "would write \\confidence{Highly unlikely}"
)
# Ordered (label, lo, hi) -- the ten official classes, lowest to highest.
TJE_CONFIDENCE_LABELS: List[Tuple[str, float, float]] = [
    ("Almost no chance", 0.0, 0.1),
    ("Highly unlikely", 0.1, 0.2),
    ("Chances are slight", 0.2, 0.3),
    ("Unlikely", 0.3, 0.4),
    ("Less than even", 0.4, 0.5),
    ("Better than even", 0.5, 0.6),
    ("Likely", 0.6, 0.7),
    ("Very good chance", 0.7, 0.8),
    ("Highly likely", 0.8, 0.9),
    ("Almost certain", 0.9, 1.0),
]
TJE_THRESHOLD_LABEL = "Almost certain"
# The forced-prefix injected at a trigger so the model can only complete the
# structured label and cannot start a new reasoning continuation (Section 2.2).
TJE_CONFIDENCE_FORCE_PREFIX = "\\confidence{"
# Reflective marker trigger. The preregistered primary also checks final </think>.
TJE_WAIT_TRIGGER = "Wait"
# Decoding from Section 3.1.4.
TJE_TEMPERATURE = 0.6
TJE_TOP_P = 0.95
TJE_TOP_K = 20


# --------------------------------------------------------------------------- #
# Small stdlib helpers (mirror governor_v2/replay_rules.py + dense_probe.py,
# kept here so the module imports without those packages).
# --------------------------------------------------------------------------- #
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Mirror of governor_v2/replay_rules.py:sha256_file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_path_set(paths: Iterable[Path], *, root: Path) -> str:
    """Deterministic hash of relative path names and file bytes."""
    root = Path(root)
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        size = path.stat().st_size
        digest.update(size.to_bytes(8, "big"))
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    """Atomic write via ``.tmp`` + ``os.replace`` (governor_v2 convention)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Mirror of governor_v2/dense_probe.py:atomic_write_json."""
    atomic_write_text(
        path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    )


def atomic_write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    os.replace(temporary, path)
    return len(rows)


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def trajectory_paths(main_run: Path) -> List[Path]:
    """Sorted frozen main trajectory files (mirror of dense_probe.trajectory_paths)."""
    return sorted((Path(main_run) / "traj").glob("problem_*.json"))


def load_trajectory(path: Path) -> dict:
    return load_json(path)


def load_main_manifest(main_run: Path) -> dict:
    return load_json(Path(main_run) / "run_manifest.json")


def checkpoint_positions(
    token_count: int,
    *,
    start_token: int,
    interval: int,
    finished_naturally: bool,
) -> List[int]:
    """Token positions at which to probe the frozen prefix.

    Verbatim convention from ``governor_v2/dense_probe.py:checkpoint_positions``:
    positions are ``range(start_token, token_count + (0 if finished_naturally
    else 1), interval)``. The ``+1`` when the trace was *not* finished
    naturally lets the very last partial chunk be probed; a naturally-stopped
    trace already emitted its own stop token at ``token_count`` so the final
    position is inclusive of ``token_count`` only via the natural-stop branch.

    Faithful ``mid`` uses ``start_token=64, interval=64`` so positions are
    64, 128, 192, ... on the decoded frozen prefix.
    """
    if token_count <= 0:
        return []
    inclusive_stop = token_count + (0 if finished_naturally else 1)
    return list(range(start_token, inclusive_stop, interval))


def obtain_boxed_answer(s: str) -> str:
    """Return the text up to the first unpaired ``}`` in ``s``.

    Faithful mirror of ``dynasor/core/entropy.py:obtaint_answer`` /
    ``dynasor/core/cot.py:obtain_answer`` (bracket-matching on the probe
    response that follows the ``\\boxed{`` suffix). Returns ``""`` when the
    probe never closed the box.
    """
    stack: List[str] = []
    for i, c in enumerate(s):
        if c == "{":
            stack.append(c)
        elif c == "}":
            if not stack:
                return s[:i]
            stack.pop()
    return ""


def is_certain(probe_text: str, uncertain_words: Sequence[str] = UNCERTAIN_WORDS) -> bool:
    """Certainty test from ``dynasor/core/entropy.py:is_certain_answer``.

    A probe response is "certain" iff none of the uncertainty words appear as
    substrings (case-insensitively) in the raw probe text.
    """
    lowered = probe_text.lower()
    return not any(word in lowered for word in uncertain_words)


# --------------------------------------------------------------------------- #
# Frozen-bank identity / validation
# --------------------------------------------------------------------------- #
EXPECTED_PROTOCOL_VERSION = "governor-v2-preregistered-2026-07-27.10"
EXPECTED_SPLIT_SEED = "20260726"
EXPECTED_PROBLEM_COUNTS = {  # train+dev per environment (== dataset_index set)
    "math500": 400,
    "amc23": 32,
    "aime24": 24,
}
EXPECTED_SPLIT_COUNTS = {  # (train, dev, test) per benchmark
    "math500": (300, 100, 100),
    "amc23": (24, 8, 8),
    "aime24": (18, 6, 6),
}
EXPECTED_ENV_COUNT = 18
EXPECTED_TOTAL_TRAJECTORIES = 2736
EXPECTED_SOURCE_SHA256 = {
    "math500": "35dc41080a3680858b27fa7e0533d2d547825316fc5dafe5d316f4ccc5a06132",
    "amc23": "43707e1ca784602d8479de24ee8ce36609dbebc46dd152b0b12a46611aa898a4",
    "aime24": "af2b8bd2aa911b6333ad0df32f3ca05c7ae8ed10f1731f4372c8ae26990bf7ac",
}
DEVELOPMENT_MODELS = (
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "Qwen/Qwen3-8B",
)
DEVELOPMENT_SEEDS = (42, 43, 44)
DEVELOPMENT_BENCHMARKS = ("math500", "amc23", "aime24")


def load_split_map(split_manifest_path: Path) -> Dict[Tuple[str, int], str]:
    """``{(benchmark, dataset_index): split}`` (mirror of replay_rules.load_split_map).

    The trajectory ``problem_id`` field *is* the ``dataset_index`` row, so this
    map is the join key between a frozen trajectory and its split label.
    """
    payload = load_json(split_manifest_path)
    rows = payload["assignments"] if isinstance(payload, dict) else payload
    return {
        (str(row["benchmark"]), int(row["dataset_index"])): str(row["split"])
        for row in rows
    }


def split_sets(split_manifest_path: Path) -> Dict[str, Dict[str, set]]:
    """``{benchmark: {"train": set, "dev": set, "test": set}}`` keyed by dataset_index."""
    payload = load_json(split_manifest_path)
    rows = payload["assignments"] if isinstance(payload, dict) else payload
    out: Dict[str, Dict[str, set]] = {}
    for row in rows:
        b = str(row["benchmark"])
        out.setdefault(b, {"train": set(), "dev": set(), "test": set()})
        out[b][str(row["split"])].add(int(row["dataset_index"]))
    return out


def bank_summary(results_root: Path) -> dict:
    """Read-only inventory of the frozen main-run bank.

    Returns protocol versions seen, per-benchmark source SHA-256 from the
    split manifest, environment count, and total trajectory count. Pure
    inspection; raises nothing. Use :func:`validate_frozen_bank` to enforce.
    """
    results_root = Path(results_root)
    envs = sorted(
        d for d in (results_root / "governor_v2").glob("development__*")
        if d.is_dir()
    ) if (results_root / "governor_v2").exists() else sorted(
        d for d in results_root.glob("development__*") if d.is_dir()
    )
    protocol_versions = set()
    total = 0
    per_env = []
    for env in envs:
        manifest_path = env / "main" / "run_manifest.json"
        if not manifest_path.exists():
            continue
        rs = load_json(manifest_path)["run_settings"]
        protocol_versions.add(rs["protocol_version"])
        n = len(list((env / "main" / "traj").glob("problem_*.json")))
        total += n
        per_env.append(
            {
                "env": env.name,
                "model": rs["model"],
                "dataset": rs["dataset"],
                "base_seed": rs["base_seed"],
                "n_traj": n,
                "protocol_version": rs["protocol_version"],
            }
        )
    return {
        "env_count": len(per_env),
        "total_trajectories": total,
        "protocol_versions": sorted(protocol_versions),
        "environments": per_env,
    }


def validate_frozen_bank(
    results_root: Path,
    split_manifest_path: Path,
    *,
    strict_hashes: bool = True,
) -> dict:
    """Fail-fast identity / coverage / test-leakage validation of the bank.

    Enforces (per goal §5 / §11):
      * exactly EXPECTED_ENV_COUNT environments, EXPECTED_TOTAL_TRAJECTORIES rows;
      * per-benchmark expected problem counts per environment;
      * a single EXPECTED_PROTOCOL_VERSION and EXPECTED_SPLIT_SEED;
      * per-benchmark source SHA-256 matches (when ``strict_hashes``);
      * every environment's trajectory ``problem_id`` set exactly equals the
        train+dev dataset_index set (no missing, no extra);
      * zero test problem_ids leak into any trajectory;
      * zero duplicate problem_ids within an environment.

    Returns a summary dict; raises :class:`ValueError` on the first material
    violation so collectors never run against a corrupted or mismatched bank.
    """
    results_root = Path(results_root)
    split_manifest_path = Path(split_manifest_path)
    sm = load_json(split_manifest_path)
    if sm.get("protocol_version") != EXPECTED_PROTOCOL_VERSION:
        raise ValueError(
            f"split manifest protocol_version mismatch: {sm.get('protocol_version')!r}"
        )
    if str(sm.get("split_seed")) != EXPECTED_SPLIT_SEED:
        raise ValueError(f"split_seed mismatch: {sm.get('split_seed')!r}")
    for b, sha in EXPECTED_SOURCE_SHA256.items():
        recorded = sm["summaries"][b].get("source_sha256")
        if strict_hashes and recorded != sha:
            raise ValueError(f"{b} source_sha256 mismatch: {recorded!r} != {sha!r}")

    ssets = split_sets(split_manifest_path)
    for b, (tr, dv, te) in EXPECTED_SPLIT_COUNTS.items():
        if b not in ssets:
            raise ValueError(f"{b} missing from split manifest")
        got = ssets[b]
        if (len(got["train"]), len(got["dev"]), len(got["test"])) != (tr, dv, te):
            raise ValueError(
                f"{b} split counts {(len(got['train']), len(got['dev']), len(got['test']))} != {(tr, dv, te)}"
            )

    # locate the governor_v2 results root whether called with results_root or its parent
    gov_root = results_root / "governor_v2" if (results_root / "governor_v2").exists() else results_root
    envs = sorted(d for d in gov_root.glob("development__*") if d.is_dir())
    if len(envs) != EXPECTED_ENV_COUNT:
        raise ValueError(f"expected {EXPECTED_ENV_COUNT} envs, found {len(envs)}")
    protocol_versions = set()
    total = 0
    for env in envs:
        rs = load_json(env / "main" / "run_manifest.json")["run_settings"]
        protocol_versions.add(rs["protocol_version"])
        ds = rs["dataset"]
        if ds not in EXPECTED_PROBLEM_COUNTS:
            raise ValueError(f"unexpected dataset {ds!r} in {env.name}")
        ids = sorted(
            int(load_json(p)["problem_id"]) for p in trajectory_paths(env / "main")
        )
        total += len(ids)
        if len(ids) != EXPECTED_PROBLEM_COUNTS[ds]:
            raise ValueError(
                f"{env.name}: {len(ids)} trajectories != expected {EXPECTED_PROBLEM_COUNTS[ds]}"
            )
        if len(ids) != len(set(ids)):
            raise ValueError(f"{env.name}: duplicate problem_ids")
        allowed = sorted(ssets[ds]["train"] | ssets[ds]["dev"])
        if ids != allowed:
            raise ValueError(f"{env.name}: trajectory ids != train+dev set")
        leaked = [i for i in ids if i in ssets[ds]["test"]]
        if leaked:
            raise ValueError(f"{env.name}: TEST leakage {leaked[:5]}")
        if rs["model"] not in DEVELOPMENT_MODELS:
            raise ValueError(f"{env.name}: unauthorized model {rs['model']!r}")
        if rs["base_seed"] not in DEVELOPMENT_SEEDS:
            raise ValueError(f"{env.name}: unauthorized seed {rs['base_seed']}")
    if protocol_versions != {EXPECTED_PROTOCOL_VERSION}:
        raise ValueError(f"protocol versions not uniform: {protocol_versions}")
    if total != EXPECTED_TOTAL_TRAJECTORIES:
        raise ValueError(f"total {total} != expected {EXPECTED_TOTAL_TRAJECTORIES}")
    return {
        "env_count": len(envs),
        "total_trajectories": total,
        "protocol_version": EXPECTED_PROTOCOL_VERSION,
        "split_seed": EXPECTED_SPLIT_SEED,
        "source_sha256": dict(EXPECTED_SOURCE_SHA256),
        "ok": True,
    }


# --------------------------------------------------------------------------- #
# Provenance + row metadata
# --------------------------------------------------------------------------- #
def row_id(model: str, dataset: str, seed: int, problem_id: int, method: str) -> str:
    """Stable per-problem-row identifier for exact audit and dedup."""
    m = model.split("/")[-1].lower()
    return f"{method}__{m}__{dataset}__seed{seed}__p{problem_id}"


def method_provenance(
    method: str,
    *,
    reproduction_class: str,
    source_commit: str,
    source_url: str,
    prompt_text: Optional[str] = None,
    prompt_file: Optional[Path] = None,
    trigger_definition: Optional[str] = None,
    output_cap: Optional[int] = None,
    temperature: float = DEFAULT_TEMPERATURE,
    top_p: float = DEFAULT_TOP_P,
    top_k: Optional[int] = None,
    seed_policy: str = "base_seed (per the frozen main run; probes prompt-matched)",
    extra: Optional[Mapping[str, Any]] = None,
) -> dict:
    """Build a manifest provenance block with prompt hashes and source pin."""
    provenance = {
        "method": method,
        "reproduction_class": reproduction_class,
        "source_commit": source_commit,
        "source_url": source_url,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "seed_policy": seed_policy,
        "trigger_definition": trigger_definition,
        "output_cap": output_cap,
        "test_read": False,
        "main_generation_changed": False,
    }
    if prompt_text is not None:
        provenance["prompt_sha256"] = sha256_bytes(prompt_text.encode("utf-8"))
        provenance["prompt_char_count"] = len(prompt_text)
    if prompt_file is not None:
        prompt_file = Path(prompt_file)
        provenance["prompt_file"] = str(prompt_file)
        provenance["prompt_file_sha256"] = sha256_file(prompt_file)
    if extra:
        provenance.update(dict(extra))
    return provenance


def env_metadata(trajectory: Mapping[str, Any], method: str) -> dict:
    """Stable row metadata drawn from the frozen trajectory."""
    rs = trajectory.get("run_settings", {})
    return {
        "row_id": row_id(
            rs.get("model", ""), rs.get("dataset", ""), rs.get("base_seed", ""),
            int(trajectory["problem_id"]), method,
        ),
        "method": method,
        "model": rs.get("model"),
        "dataset": rs.get("dataset"),
        "base_seed": rs.get("base_seed"),
        "problem_id": int(trajectory["problem_id"]),
        "split": None,  # filled by the caller from load_split_map
        "target": trajectory.get("target"),
        "level": trajectory.get("level"),
        "subject": trajectory.get("subject"),
    }


def trajectory_identity(trajectory: Mapping[str, Any]) -> dict:
    """Minimal stable identity for a replay record (row metadata without target)."""
    rs = trajectory.get("run_settings", {})
    return {
        "model": rs.get("model"),
        "dataset": rs.get("dataset"),
        "base_seed": rs.get("base_seed"),
        "problem_id": int(trajectory.get("problem_id", -1)),
    }


# --------------------------------------------------------------------------- #
# Heavy, lazily-imported helpers (only used by the live collector / grading)
# --------------------------------------------------------------------------- #
def real_answers_equal(answer: Any, raw_target: Any) -> bool:
    """Project robust equivalence (governor_v2/grading.robust_answers_equal).

    Lazily imported so the module loads without sympy / latex2sympy2. Pure
    unit tests inject a simpler equivalence instead of calling this.
    """
    import sys
    sys.path.insert(0, str(GOVERNOR_V2))
    sys.path.insert(0, str(REPO_ROOT))
    from grading import robust_answers_equal  # type: ignore
    return robust_answers_equal(answer, raw_target)


def extract_generated_answer(text: str, dataset: str) -> str:
    """Extract an answer from a complete TJE/DEER final readout.

    ``obtain_boxed_answer`` only parses a completion that starts inside an
    already-open ``\\boxed{`` suffix. Final readouts contain their own complete
    ``\\boxed{...}``, so they require the project's task-aware extractor.
    """
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from dynasor.core.evaluator import extract_answer  # type: ignore
    try:
        return str(extract_answer(str(text), str(dataset)) or "")
    except Exception:
        return ""


def real_eqaul_group(answers: Sequence[Any]) -> bool:
    """Dynasor math-equivalence group test (dynasor.core.evaluator.eqaul_group)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from dynasor.core.evaluator import eqaul_group  # type: ignore
    return eqaul_group(list(answers))


def real_count_not_empty(answers: Sequence[Any]) -> int:
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from dynasor.core.evaluator import count_not_empty  # type: ignore
    return count_not_empty(list(answers))


def real_strip_string() -> Callable[[str], str]:
    """Return ``dynasor.core.evaluator.strip_string`` (lazy; needs sympy)."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from dynasor.core.evaluator import strip_string  # type: ignore
    return strip_string


def tokenizer_revision(tokenizer: Any) -> Optional[str]:
    """Best-effort immutable Hugging Face commit recorded by Transformers."""
    revision = getattr(tokenizer, "_commit_hash", None)
    if revision:
        return str(revision)
    init_kwargs = getattr(tokenizer, "init_kwargs", {}) or {}
    revision = init_kwargs.get("_commit_hash") or init_kwargs.get("revision")
    return str(revision) if revision else None


def runtime_versions() -> dict:
    """Recorded software environment for each live collection manifest."""
    packages = {}
    for name in (
        "vllm", "torch", "transformers", "openai", "numpy", "pandas",
        "sympy", "latex2sympy2", "word2number",
    ):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


def finalize_collection_manifest(
    manifest_path: Path,
    record_paths: Iterable[Path],
    *,
    records_key: str,
    expected_problem_count: int,
    elapsed_seconds: float,
) -> dict:
    """Attach observed coverage, retry, failure, and alignment totals."""
    paths = sorted(Path(p) for p in record_paths)
    total_calls = 0
    total_retries = 0
    errors = 0
    invalid_readouts = 0
    truncated_readouts = 0
    token_mismatches = 0
    material_token_mismatches = 0
    for path in paths:
        payload = load_json(path)
        rows = payload.get(records_key, [])
        total_calls += len(rows)
        total_retries += sum(int(row.get("retry_count", 0)) for row in rows)
        errors += sum(1 for row in rows if "error" in row)
        readout = payload.get("readout")
        if isinstance(readout, dict):
            total_calls += 1
            total_retries += int(readout.get("retry_count", 0))
            errors += int("error" in readout)
            if readout.get("readout_valid") is False:
                invalid_readouts += 1
            if readout.get("readout_truncated"):
                truncated_readouts += 1
        if payload.get("main_token_count_recorded") != payload.get(
            "main_token_count_reencoded"
        ):
            token_mismatches += 1
        if payload.get("token_alignment", {}).get("material_mismatch") is True:
            material_token_mismatches += 1
    observed = len(paths)
    completion = {
        "expected_problem_count": int(expected_problem_count),
        "observed_problem_count": observed,
        "missing_problem_count": max(0, int(expected_problem_count) - observed),
        "total_aux_calls": total_calls,
        "total_retries": total_retries,
        "recorded_failures": errors,
        "invalid_readouts": invalid_readouts,
        "truncated_readouts": truncated_readouts,
        "token_count_mismatches": token_mismatches,
        "material_token_count_mismatches": material_token_mismatches,
        "elapsed_seconds": float(elapsed_seconds),
        "finished_at": now_iso(),
        "complete": observed == int(expected_problem_count) and errors == 0,
    }
    manifest = load_json(manifest_path)
    manifest["completion"] = completion
    atomic_write_json(manifest_path, manifest)
    return completion


def make_openai_client(url: str, api_key: str = "token-abc123", timeout: float = 600.0):
    """OpenAI-compatible client (lazy; requires the openai package)."""
    import openai  # type: ignore
    return openai.OpenAI(api_key=api_key, base_url=url, timeout=timeout)


def apply_chat_template(problem: str, model: str) -> str:
    """governor_v2 chat template (benchmark/TokenDeprivation/clients.py)."""
    import sys
    sys.path.insert(0, str(TOKENDEPRIVATION))
    from clients import apply_chat_template as _act  # type: ignore
    return _act(problem, model)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


# --------------------------------------------------------------------------- #
# Trigger detection (shared text scanning for TJE / DEER)
# --------------------------------------------------------------------------- #
def find_wait_positions(text: str) -> List[int]:
    """Character offsets of case-insensitive *whole-word* ``Wait`` in ``text``.

    TJE Section 2.2 and DEER ``--points 1`` both use the reflective marker
    "Wait" as the thinking-transition trigger. "Whole-word" means the match is
    not a substring of a larger token (e.g. not "Waited" or "Await").
    """
    return [m.start() for m in re.finditer(r"(?i)\bWait\b", text)]


def find_think_close_positions(text: str) -> List[int]:
    """Character offsets of the ``</think>`` closing tag in ``text``."""
    return [m.start() for m in re.finditer(r"</think>", text)]


def char_end_to_token_position(
    tokenizer: Any,
    text: str,
    char_end: int,
) -> Tuple[List[int], int]:
    """Map a marker's exclusive character end to a prefix including it."""
    encoded = tokenizer(
        text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    token_ids = list(encoded["input_ids"])
    offsets = list(encoded["offset_mapping"])
    return token_ids, token_position_for_char_end(offsets, char_end)


def token_position_for_char_end(
    offsets: Sequence[Tuple[int, int]],
    char_end: int,
) -> int:
    """Return the token-prefix length covering ``text[:char_end]``."""
    if char_end <= 0:
        return 0
    for index, (_start, end) in enumerate(offsets, start=1):
        if int(end) >= int(char_end):
            return index
    return len(offsets)


def validate_token_alignment(recorded: int, reencoded: int) -> dict:
    """Measure and explicitly flag drift from the frozen trajectory tokenizer.

    Frozen trajectories retain generated text and the server-reported token
    count, but not the original generated token IDs.  Decode/re-encode is not
    guaranteed to be token-idempotent, so a material mismatch is an auditable
    data-quality flag rather than a reason to discard the trajectory.  The
    exact counts, delta, tolerance, and flag are persisted in every record and
    summarized in the finalized manifest.
    """
    recorded = int(recorded)
    reencoded = int(reencoded)
    delta = reencoded - recorded
    tolerance = max(2, int(round(max(recorded, 1) * 0.005)))
    result = {
        "recorded": recorded,
        "reencoded": reencoded,
        "delta": delta,
        "absolute_delta": abs(delta),
        "tolerance": tolerance,
        "material_mismatch": abs(delta) > tolerance,
    }
    return result


# --------------------------------------------------------------------------- #
# Model revision pinning + readout validity + canonical reproducibility
# --------------------------------------------------------------------------- #
_HEX_RE = re.compile(r"^[0-9a-f]{40}$")


def is_40hex(s: Any) -> bool:
    """True iff ``s`` is a 40-char lowercase hex git commit SHA."""
    return isinstance(s, str) and bool(_HEX_RE.match(s))


def load_tokenizer(model: str, revision: Optional[str] = None):
    """``AutoTokenizer.from_pretrained(model, revision=revision)`` (lazy).

    Pinning the exact cached revision makes the tokenizer bytes reproducible
    and records an immutable model revision in the manifest.
    """
    from transformers import AutoTokenizer  # type: ignore
    if revision:
        return AutoTokenizer.from_pretrained(model, revision=revision)
    return AutoTokenizer.from_pretrained(model)


def has_completed_boxed(text: str) -> bool:
    """True iff ``text`` contains a properly *closed* ``\\boxed{...}``.

    A readout is a valid delivered answer only when an explicit final-answer /
    boxed marker was **completed** before any truncation. An opened-but-unclosed
    ``\\boxed{`` (length-truncated) does NOT count, and neither does any generic
    last-number fallback from unfinished reasoning.
    """
    i = text.find("\\boxed")
    if i < 0:
        return False
    j = text.find("{", i)
    if j < 0:
        return False
    depth = 1
    k = j + 1
    while k < len(text) and depth > 0:
        ch = text[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        k += 1
    return depth == 0


_ANSWER_PHRASE_RE = re.compile(r"(?i)(final answer is|he answer is|答案是)")


def has_explicit_answer_phrase(text: str) -> bool:
    """True iff ``text`` contains an explicit final-answer phrase
    ("final answer is" / "the answer is" / "答案是") -- the same markers the
    project's task-aware ``extract_answer`` recognizes (without any last-number
    fallback)."""
    return bool(_ANSWER_PHRASE_RE.search(text or ""))


def extract_explicit_answer(text: str, dataset: str) -> str:
    """Task-aware final-answer extraction with **no last-number fallback**.

    Wraps ``dynasor.core.evaluator.extract_answer(..., use_last_number=False)``
    so unfinished/truncated reasoning never yields a stray intermediate number.
    Returns ``""`` when no ``\\boxed{}`` / "answer is" marker is present.
    """
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from dynasor.core.evaluator import extract_answer  # type: ignore
    try:
        return str(extract_answer(str(text), str(dataset), use_last_number=False) or "")
    except Exception:
        return ""


def readout_validity(readout_text: str, finish_reason: Optional[str], dataset: str) -> dict:
    """Compute a readout's delivered answer, validity, and truncation flag.

    A readout is ``valid`` iff a *completed* ``\\boxed{...}`` (closed) marker
    was found -- the explicit final-answer/boxed marker. A length-capped readout
    (``finish_reason == "length"``) is valid when such a marker was completed
    before truncation; otherwise it yields an empty answer and is invalid (no
    last-number fallback). ``has_explicit_answer_phrase`` is recorded only as a
    diagnostic and does not by itself make the readout valid.
    """
    completed = has_completed_boxed(readout_text)
    truncated = (str(finish_reason) == "length")
    answer = extract_explicit_answer(readout_text, dataset) if completed else ""
    valid = completed and bool(answer)
    return {
        "readout_answer": answer if valid else "",
        "readout_valid": valid,
        "readout_truncated": truncated,
        "readout_completed_boxed": completed,
        "readout_has_answer_phrase": has_explicit_answer_phrase(readout_text),
        "readout_finish_reason": finish_reason,
    }


def finish_reason_of(response: Any) -> Optional[str]:
    """Safely read ``choices[0].finish_reason`` from an OpenAI completion."""
    try:
        return str(response.choices[0].finish_reason)
    except Exception:
        return None


def compute_readout_allowance(
    est_prompt_tokens: int,
    *,
    readout_cap: int,
    max_model_len: int,
    safety_margin: int = 32,
    min_allowance: int = 32,
) -> dict:
    """Context-safe readout generation allowance.

    ``est_prompt_tokens`` is the actual readout-prompt token length from the
    pinned tokenizer (same ``add_special_tokens`` semantics as the completion
    endpoint). The allowance is ``min(readout_cap, max_model_len - est - margin)``
    so prompt+generation never exceeds ``max_model_len``. If the remaining
    allowance is below ``min_allowance`` (a justified minimum to produce a
    boxed answer), a context-budget error is reported and the allowance is 0 --
    never a negative value clamped up to a positive floor (which could exceed
    server context).
    """
    est = int(est_prompt_tokens)
    remaining = int(max_model_len) - est - int(safety_margin)
    if remaining < int(min_allowance):
        return {"allowance": 0, "remaining": remaining,
                "context_budget_exceeded": True}
    return {"allowance": min(int(readout_cap), remaining), "remaining": remaining,
            "context_budget_exceeded": False}


def readout_is_valid(readout: Optional[Mapping[str, Any]]) -> bool:
    """Hard predicate: a delivered readout is acceptable only when it is
    completed and task-valid.

    Requires ``readout_valid`` True, a non-empty extracted answer, a
    non-null/non-empty ``readout_finish_reason``, and NO context-budget
    overflow (``actual_prompt_tokens + allowance <= max_model_len``) and NO
    context-budget-exceeded flag. A length-truncated readout IS valid when an
    explicit final-answer/boxed marker was completed before truncation (the
    ``readout_valid`` flag already encodes the completed-marker requirement);
    an overflow, a null finish_reason, or a no-marker readout is a hard failure.
    """
    if not readout:
        return False
    fr = readout.get("readout_finish_reason")
    return bool(
        readout.get("readout_valid") is True
        and readout.get("readout_answer")
        and fr  # non-null / non-empty finish_reason
        and not readout.get("readout_context_budget_exceeded")
        and not readout.get("readout_context_overflow")
    )


# Keys whose values are timing/timestamp/volatile and are excluded from the
# canonical reproducibility projection. Everything else (model outputs, parsed
# answers, certainty, token counts, positions, seeds, configs) is included.
_VOLATILE_KEY_SUFFIXES = (
    "_latency_seconds", "latency_seconds", "_wall_seconds", "wall_seconds",
    "elapsed_seconds",
)
_VOLATILE_KEY_EXACT = {
    "created_at", "finished_at", "started_at", "timestamp", "now",
    "runtime",  # runtime version snapshot is environment-bound, not output
}


def _canonical_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _canonical_value(v)
            for k, v in value.items()
            if k not in _VOLATILE_KEY_EXACT
            and not any(k.endswith(s) for s in _VOLATILE_KEY_SUFFIXES)
        }
    if isinstance(value, list):
        return [_canonical_value(v) for v in value]
    return value


def canonical_projection(payload: Mapping[str, Any]) -> str:
    """Deterministic JSON projection excluding only volatile timing/timestamps.

    Includes all model outputs, parsed answers, certainty, token counts,
    positions, and seeds. Two same-seed runs of the same problem must produce
    identical canonical projections (raw files may differ only in latency /
    timestamps, which are documented volatile).
    """
    import copy
    projected = _canonical_value(copy.deepcopy(dict(payload)))
    return json.dumps(projected, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 of :func:`canonical_projection` (the reproducibility digest)."""
    return sha256_bytes(canonical_projection(payload).encode("utf-8"))
