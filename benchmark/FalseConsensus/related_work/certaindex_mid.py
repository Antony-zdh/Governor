"""CertaIndex faithful frozen-trajectory ``mid`` collector + replay.

Reproduces the CertaIndex / Dynasor ``effort_level("mid")`` early-exit rule
(``dynasor/core/cot.py``) on the frozen Governor v2 main trajectories.

Protocol (verbatim from ``dynasor/core/cot.py``):
    * probe suffix:   CERTAINDEX_SUFFIX (the *faithful* suffix WITH the
                      "Oh, I suddenly got the answer" preamble, NOT the
                      governor_v2 SIMPLE_SUFFIX which is the prompt-matched
                      auxiliary baseline without the preamble);
    * probe params:   temperature 0.6, top_p 0.95, max_tokens 20;
    * effort mid:     patience 3, chunk/interval 64;
    * stop rule:      the last ``patience`` (3) probe answers are all
                      non-empty, all math-equivalent (``eqaul_group``), and
                      all "certain" (no uncertainty word); then the latest
                      probe answer is delivered as the final boxed answer.

Frozen-trajectory adaptation (named, not concealed):
    ``dynasor/core/cot.py`` is *streaming*: it interleaves a probe every 64
    *newly generated* tokens on a live-growing prefix. Here the main trace is
    already frozen, so we re-encode ``full_text`` once and probe at fixed
    positions ``64, 128, 192, ...`` on ``decode(token_ids[:position])``. The
    prompt, the suffix, the cap, the temperature/top_p, the patience, the
    certainty test and the math-equivalence stop rule are faithful; only the
    *timing* of the probe (frozen-prefix positions vs live-streamed chunks)
    is adapted. The probe happens *after* each 64-token chunk in both
    conventions (the first probe is on prefix[:64]), so there is no off-by-one
    between the two -- this is documented rather than hidden behind the word
    "faithful". The result is labeled ``certaindex_mid_frozen``.

This module is importable without torch/transformers/sympy/openai: the live
collector constructs its client and tokenizer lazily; the decision, parsing
and accounting functions are pure and take dependency-injected equivalence.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence

from . import common
from .common import (
    CERTAINDEX_MID_INTERVAL,
    CERTAINDEX_MID_PATIENCE,
    CERTAINDEX_MID_PROBE_CAP,
    CERTAINDEX_SUFFIX,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    EXPECTED_PROTOCOL_VERSION,
    UNCERTAIN_WORDS,
    atomic_write_json,
    checkpoint_positions,
    env_metadata,
    load_main_manifest,
    load_tokenizer,
    make_openai_client,
    method_provenance,
    now_iso,
    obtain_boxed_answer,
    sha256_bytes,
    trajectory_paths,
)

METHOD = "certaindex_mid_frozen"
REPRODUCTION_CLASS = "faithful-prompt-and-stop-rule, frozen-trajectory timing"
SOURCE_COMMIT = "dbe76ad50d100f4bf237688f31942e4dc745fb07"
SOURCE_URL = "in-repo dynasor/core/cot.py (effort_level('mid'))"
PROBE_SCHEMA = "related-work-certaindex-probe-1"
RUN_SCHEMA = "related-work-certaindex-run-1"
RECORD_FIELDS = (
    "token_position",
    "probe_id",
    "probe_text",
    "probe_answer",
    "is_certain",
    "probe_out_tokens",
    "probe_prompt_tokens",
    "probe_latency_seconds",
)


# --------------------------------------------------------------------------- #
# Pure logic (no heavy deps)
# --------------------------------------------------------------------------- #
def build_probe_prompt(chat: str, prefix: str, *, suffix: str = CERTAINDEX_SUFFIX) -> str:
    """Construct the probe prompt = chat template + decoded frozen prefix + suffix."""
    return chat + prefix + suffix


def parse_probe_response(
    probe_text: str,
    *,
    obtain_answer_fn: Callable[[str], str] = obtain_boxed_answer,
    strip_fn: Optional[Callable[[str], str]] = None,
    uncertain_words: Sequence[str] = UNCERTAIN_WORDS,
) -> dict:
    """Parse a probe response into (answer, is_certain).

    Mirrors ``dynasor/core/cot.py``: ``obtain_answer`` (bracket-match to the
    first unpaired ``}``) then optional ``strip_string``; certainty is the
    absence of any uncertainty word in the raw probe text. ``strip_fn`` is
    optional so tests can run without sympy-backed ``strip_string``; the live
    collector passes ``dynasor.core.evaluator.strip_string``.
    """
    answer = obtain_answer_fn(probe_text)
    if answer and strip_fn is not None:
        try:
            answer = strip_fn(answer)
        except Exception:
            pass
    return {
        "probe_answer": answer or "",
        "is_certain": common.is_certain(probe_text, uncertain_words),
    }


def decide_stop(
    probes: Sequence[Mapping[str, Any]],
    *,
    patience: int = CERTAINDEX_MID_PATIENCE,
    answers_equal_fn: Callable[[Sequence[Any]], bool],
    count_not_empty_fn: Optional[Callable[[Sequence[Any]], int]] = None,
) -> Optional[dict]:
    """Apply the CertaIndex ``mid`` stop rule to an ordered probe list.

    Returns the stop record at the *first* probe index where the last
    ``patience`` probes are all non-empty, all math-equivalent and all
    certain; ``None`` if the rule never fires. ``answers_equal_fn`` is the
    Dynasor ``eqaul_group`` semantics (all answers fall in one
    math-equivalence class) -- injected so tests need not import sympy.
    """
    if count_not_empty_fn is None:
        def count_not_empty_fn(ans: Sequence[Any]) -> int:  # type: ignore[override]
            return sum(1 for a in ans if a != "")
    n = len(probes)
    for i in range(patience, n + 1):
        window = list(probes[i - patience : i])
        answers = [p["probe_answer"] for p in window]
        if count_not_empty_fn(answers) != patience:
            continue
        if not answers_equal_fn(answers):
            continue
        if sum(1 for p in window if p["is_certain"]) != patience:
            continue
        return {
            "stop_probe_id": window[-1].get("probe_id", i),
            "stop_position": int(window[-1]["token_position"]),
            "delivered_answer": window[-1]["probe_answer"],
            "window_probe_ids": [p.get("probe_id", idx) for idx, p in enumerate(window, 1)],
            "stop_index": i,
        }
    return None


def replay(
    trajectory: Mapping[str, Any],
    probe_records: Sequence[Mapping[str, Any]],
    *,
    patience: int = CERTAINDEX_MID_PATIENCE,
    answers_equal_fn: Callable[[Sequence[Any]], bool],
    count_not_empty_fn: Optional[Callable[[Sequence[Any]], int]] = None,
    answers_equal_target_fn: Optional[Callable[[Any, Any], bool]] = None,
    split: Optional[str] = None,
) -> dict:
    """Compute the delivered answer + token accounting for one trajectory.

    Two cost views are produced (goal §8):
      * paper-style ``main_tokens_through_stop`` (the frozen reasoning length
        up to the stop, or the full length if no stop);
      * fair ``all_generated_tokens`` = main-through-stop + every probe output
        token incurred (probe *prompt* tokens are reported separately and are
        NOT added -- they are re-sent prefix tokens, not newly generated).
    """
    full_tokens = int(trajectory.get("tokens_used", 0))
    finished_naturally = bool(trajectory.get("finished_naturally", False))
    budget = int(trajectory.get("run_settings", {}).get("budget", full_tokens or 2**31))
    full_answer = trajectory.get("final_answer", "")
    full_correct = bool(trajectory.get("final_correct", False))

    decision = decide_stop(
        probe_records,
        patience=patience,
        answers_equal_fn=answers_equal_fn,
        count_not_empty_fn=count_not_empty_fn,
    )
    probe_out_tokens = sum(int(p.get("probe_out_tokens", 0)) for p in probe_records)
    probe_prompt_tokens = sum(int(p.get("probe_prompt_tokens", 0)) for p in probe_records)
    invalid_aux = sum(
        1 for p in probe_records
        if "error" in p or not p.get("probe_answer")
    )
    auxiliary_wall = sum(float(p.get("probe_latency_seconds", 0.0)) for p in probe_records)

    if decision is not None:
        stopped = True
        main_through_stop = decision["stop_position"]
        delivered = decision["delivered_answer"]
        recovery_truncated = True
        overthinking_avoided = max(0, full_tokens - main_through_stop)
        capped = False
    else:
        stopped = False
        main_through_stop = full_tokens
        capped = not finished_naturally or full_tokens > budget
        # No early stop: deliver the frozen full answer IF it completed
        # naturally within the evaluation budget (legitimate natural answer);
        # otherwise right-censored with no deliverable answer.
        if finished_naturally and full_tokens <= budget:
            delivered = full_answer
            recovery_truncated = False
        else:
            delivered = ""
            recovery_truncated = False
        overthinking_avoided = 0

    if answers_equal_target_fn is not None:
        if delivered:
            try:
                correct = bool(answers_equal_target_fn(delivered, trajectory.get("target")))
            except Exception:
                correct = False
        else:
            correct = False  # empty delivered with grader = incorrect, not ungraded
    else:
        correct = None

    return {
        **common.trajectory_identity(trajectory),
        "split": split,
        "method": METHOD,
        "reproduction_class": REPRODUCTION_CLASS,
        "stopped": stopped,
        "capped": capped,
        "recovery_truncated": recovery_truncated,
        "overthinking_avoided_tokens": overthinking_avoided,
        "delivered_answer": delivered,
        "correct": correct,
        "baseline_correct": full_correct,
        "full_main_tokens": full_tokens,
        "main_tokens_through_stop": main_through_stop,
        "probe_out_tokens": probe_out_tokens,
        "probe_prompt_tokens": probe_prompt_tokens,
        "all_generated_tokens": main_through_stop + probe_out_tokens,
        "baseline_all_generated_tokens": full_tokens,
        "n_probes": len(probe_records),
        "n_aux_calls": len(probe_records),
        "n_readout_calls": 0,
        "invalid_aux_responses": invalid_aux,
        "auxiliary_wall_seconds": auxiliary_wall,
        "stop_position": decision["stop_position"] if decision else None,
        "stop_probe_id": decision["stop_probe_id"] if decision else None,
    }


# --------------------------------------------------------------------------- #
# Live collector (needs an endpoint; never runs in CPU-only validation)
# --------------------------------------------------------------------------- #
class CertaIndexMidCollector:
    """Restartable frozen-trajectory CertaIndex ``mid`` probe collector.

    Atomic per-problem writes + idempotent resume follow the governor_v2
    ``dense_probe.py`` convention: a complete ``problem_{id}.json`` is skipped;
    a partial/corrupt file is quarantined (renamed ``.corrupt``) and regenerated.
    """

    PROBE_SCHEMA = PROBE_SCHEMA
    RUN_SCHEMA = RUN_SCHEMA

    def __init__(self, args: argparse.Namespace, main_manifest: Mapping[str, Any]):
        self.args = args
        self.main_settings = dict(main_manifest["run_settings"])
        self.model = args.model or str(self.main_settings["model"])
        if self.model != self.main_settings["model"]:
            raise ValueError("--model disagrees with main trajectory manifest")
        if not common.is_40hex(args.model_revision):
            raise ValueError(f"--model-revision must be a 40-hex SHA, got {args.model_revision!r}")
        self.model_revision = args.model_revision
        self.dataset = str(self.main_settings["dataset"])
        self.base_seed = int(self.main_settings["base_seed"])
        self.temperature = float(self.main_settings.get("temperature", DEFAULT_TEMPERATURE))
        self.top_p = float(self.main_settings.get("top_p", DEFAULT_TOP_P))
        self.interval = int(args.interval)
        self.start_token = int(args.start_token)
        self.probe_cap = int(args.probe_tokens)
        self.patience = int(args.patience)
        self.client = make_openai_client(args.url, args.api_key, timeout=600)
        self.tokenizer = load_tokenizer(self.model, self.model_revision)
        self.output = Path(args.output)
        self.probe_dir = self.output / "probes"
        self.probe_dir.mkdir(parents=True, exist_ok=True)
        self.suffix = CERTAINDEX_SUFFIX
        main_run = Path(args.main_run)
        split_manifest = Path(args.split_manifest)
        traj_files = trajectory_paths(main_run)
        self.settings = {
            "collection_schema": self.PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "main_run": str(args.main_run),
            "model": self.model,
            "dataset": self.dataset,
            "base_seed": self.base_seed,
            "probe_suffix": self.suffix,
            "probe_suffix_sha256": sha256_bytes(self.suffix.encode("utf-8")),
            "probe_interval": self.interval,
            "start_token": self.start_token,
            "probe_tokens": self.probe_cap,
            "patience": self.patience,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "uncertain_words": list(UNCERTAIN_WORDS),
            "probe_seed_policy": "base_seed (prompt-matched to main run)",
            "model_revision": self.model_revision,
            "main_manifest_sha256": common.sha256_file(main_run / "run_manifest.json"),
            "input_trajectory_bank_sha256": common.sha256_path_set(
                traj_files, root=main_run
            ),
            "split_manifest": str(split_manifest),
            "split_manifest_sha256": common.sha256_file(split_manifest),
            "expected_problem_count": common.EXPECTED_PROBLEM_COUNTS[self.dataset],
        }
        self.provenance = method_provenance(
            METHOD,
            reproduction_class=REPRODUCTION_CLASS,
            source_commit=SOURCE_COMMIT,
            source_url=SOURCE_URL,
            prompt_text=self.suffix,
            trigger_definition=f"fixed frozen-prefix positions {self.start_token}, {self.start_token}+{self.interval}, ...",
            output_cap=self.probe_cap,
            temperature=self.temperature,
            top_p=self.top_p,
            seed_policy="base_seed (prompt-matched to main run)",
            extra={"patience": self.patience, "interval": self.interval, "faithful_suffix": True},
        )
        self._initialize_manifest()

    def _initialize_manifest(self) -> None:
        path = self.output / "probe_manifest.json"
        if path.exists():
            existing = common.load_json(path)
            if existing.get("probe_settings") != self.settings:
                raise ValueError("existing probe output has different settings")
            return
        atomic_write_json(
            path,
            {
                "schema_version": self.RUN_SCHEMA,
                "probe_settings": self.settings,
                "provenance": self.provenance,
                "protocol_version": self.main_settings.get("protocol_version"),
                "api_key_recorded": False,
                "runtime": common.runtime_versions(),
                "created_at": now_iso(),
            },
        )

    def complete(self, prompt: str):
        last_error = None
        for attempt in range(4):
            try:
                started = time.perf_counter()
                response = self.client.completions.create(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=self.probe_cap,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    seed=self.base_seed,
                    stop=["\\]"],
                    stream=False,
                )
                return response, time.perf_counter() - started, attempt
            except Exception as error:  # transient API failures: retry, do not abort
                last_error = error
                time.sleep(5 * (attempt + 1))
        raise last_error

    def collect(self, trajectory_path: Path) -> int:
        trajectory = common.load_trajectory(trajectory_path)
        if trajectory.get("run_settings", {}).get("model") != self.model:
            raise ValueError(f"model mismatch in {trajectory_path}")
        problem_id = int(trajectory["problem_id"])
        output_path = self.probe_dir / f"problem_{problem_id}.json"
        if output_path.exists():
            try:
                existing = common.load_json(output_path)
                required = {
                    "schema_version": self.PROBE_SCHEMA,
                    "method": METHOD,
                    "problem_id": problem_id,
                    "dataset": self.dataset,
                    "model": self.model,
                    "base_seed": self.base_seed,
                }
                probe_rows = existing.get("probes")
                has_errors = (
                    any("error" in row for row in probe_rows)
                    if isinstance(probe_rows, list) else True
                )
                if all(existing.get(k) == v for k, v in required.items()) and isinstance(
                    probe_rows, list
                ) and not has_errors:
                    return problem_id
                raise ValueError("incomplete or identity-mismatched CertaIndex output")
            except Exception:
                output_path.rename(output_path.with_suffix(".json.corrupt"))
        token_ids = self.tokenizer.encode(trajectory["full_text"], add_special_tokens=False)
        alignment = common.validate_token_alignment(
            trajectory["tokens_used"], len(token_ids)
        )
        positions = checkpoint_positions(
            min(len(token_ids), int(self.main_settings.get("budget", len(token_ids)))),
            start_token=self.start_token,
            interval=self.interval,
            finished_naturally=bool(trajectory["finished_naturally"]),
        )
        chat = common.apply_chat_template(str(trajectory["problem"]).strip(), self.model)
        records: List[dict] = []
        answers_equal_fn = common.real_eqaul_group
        count_not_empty_fn = common.real_count_not_empty
        strip_fn = common.real_strip_string()
        for probe_id, position in enumerate(positions, start=1):
            prefix = self.tokenizer.decode(token_ids[:position])
            try:
                response, latency, retry_count = self.complete(
                    build_probe_prompt(chat, prefix, suffix=self.suffix)
                )
            except Exception as error:  # record + continue; do not abort the problem
                records.append({
                    "token_position": position, "probe_id": probe_id,
                    "probe_text": "", "probe_answer": "", "is_certain": False,
                    "probe_out_tokens": 0, "probe_prompt_tokens": 0,
                    "probe_latency_seconds": 0.0, "error": str(error),
                    "retry_count": 3,
                })
                continue
            probe_text = str(response.choices[0].text)
            parsed = parse_probe_response(probe_text, strip_fn=strip_fn)
            records.append(
                {
                    "token_position": position,
                    "probe_id": probe_id,
                    "probe_text": probe_text,
                    "probe_answer": parsed["probe_answer"],
                    "is_certain": parsed["is_certain"],
                    "probe_out_tokens": int(response.usage.completion_tokens),
                    "probe_prompt_tokens": int(response.usage.prompt_tokens),
                    "probe_finish_reason": common.finish_reason_of(response),
                    "probe_latency_seconds": latency,
                    "retry_count": retry_count,
                }
            )
            # Online optimization (faithful to dynasor cot.py which checks
            # probe_answers[-threshold:] at each step): evaluate ONLY the latest
            # patience-length window once per new probe, not the full history.
            # Earlier windows were already checked and did not fire (or the
            # collector would have stopped). decide_stop() full-scan semantics
            # are unchanged for offline replay.
            if len(records) >= self.patience:
                window = records[-self.patience:]
                answers = [p["probe_answer"] for p in window]
                if (count_not_empty_fn(answers) == self.patience
                        and answers_equal_fn(answers)
                        and sum(1 for p in window if p["is_certain"]) == self.patience):
                    break
        payload = {
            "schema_version": self.PROBE_SCHEMA,
            "method": METHOD,
            "reproduction_class": REPRODUCTION_CLASS,
            "problem_id": problem_id,
            "dataset": self.dataset,
            "model": self.model,
            "base_seed": self.base_seed,
            "main_token_count_recorded": trajectory["tokens_used"],
            "main_token_count_reencoded": len(token_ids),
            "token_alignment": alignment,
            "chat_template_sha256": sha256_bytes(chat.encode("utf-8")),
            "probes": records,
        }
        atomic_write_json(output_path, payload)
        return problem_id


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CertaIndex faithful frozen-trajectory mid collector")
    parser.add_argument("--main-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://localhost:18000/v1")
    parser.add_argument("--api-key", default="token-abc123")
    parser.add_argument("--model", default=None)
    parser.add_argument(
        "--model-revision", required=True,
        help="exact 40-hex Hugging Face commit SHA; pinned into the tokenizer and manifest",
    )
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=common.GOVERNOR_V2 / "generated" / "split_manifest.json",
    )
    parser.add_argument("--interval", type=int, default=CERTAINDEX_MID_INTERVAL)
    parser.add_argument("--start-token", type=int, default=64)
    parser.add_argument("--probe-tokens", type=int, default=CERTAINDEX_MID_PROBE_CAP)
    parser.add_argument("--patience", type=int, default=CERTAINDEX_MID_PATIENCE)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--limit", type=int, default=0,
        help="collect only the first N trajectories (0=all; smoke use only)",
    )
    parser.add_argument(
        "--problem-id", type=int, action="append", default=[],
        help="collect only selected problem ID(s); repeat for smoke cases",
    )
    parser.add_argument("--flatten-only", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    if args.flatten_only:
        from .common import atomic_write_csv
        rows = []
        for path in sorted((args.output / "probes").glob("problem_*.json")):
            payload = common.load_json(path)
            meta = {k: payload[k] for k in ("problem_id", "dataset", "model", "base_seed")}
            for rec in payload["probes"]:
                rows.append({**meta, **rec})
        fields = ("problem_id", "dataset", "model", "base_seed", *RECORD_FIELDS)
        n = atomic_write_csv(args.output / "probes.csv", rows, fields)
        print(f"flattened {n} probes")
        return
    manifest = load_main_manifest(args.main_run)
    collector = CertaIndexMidCollector(args, manifest)
    paths = list(trajectory_paths(args.main_run))
    if args.problem_id:
        selected = set(args.problem_id)
        paths = [
            path for path in paths
            if int(path.stem.removeprefix("problem_")) in selected
        ]
    if args.limit:
        paths = paths[:args.limit]
    started = time.perf_counter()
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collector.collect, p) for p in paths]
        for index, future in enumerate(as_completed(futures), start=1):
            pid = future.result()
            print(f"[{index}/{len(paths)}] problem {pid}", flush=True)
    print(f"collected {len(paths)} trajectories")
    completion = common.finalize_collection_manifest(
        args.output / "probe_manifest.json",
        (args.output / "probes").glob("problem_*.json"),
        records_key="probes",
        expected_problem_count=common.EXPECTED_PROBLEM_COUNTS[collector.dataset],
        elapsed_seconds=time.perf_counter() - started,
    )
    print(f"completion: {completion}")


if __name__ == "__main__":
    main()
