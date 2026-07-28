# Governor v2 related-work baselines (frozen-trajectory reproductions)

Three primary baseline families are replayed on the **frozen Governor v2
development main trajectories** (train+dev only; 18 environments; 2,736
trajectories). No main generation is regenerated or modified. The expensive GPU
work is method-specific probing/readout only.

| Family | Module | Source of truth (pinned) | Reproduction class |
|---|---|---|---|
| CertaIndex faithful `mid` | `certaindex_mid.py` | in-repo `dynasor/core/cot.py` (`effort_level('mid')`) @ `dbe76ad` | faithful prompt + stop rule; **frozen-trajectory timing** |
| Think Just Enough (TJE) | `tje.py` | https://aclanthology.org/2026.findings-eacl.263/ (Fig. 2 + §2.2) | **frozen-trajectory TJE reproduction** (confidence re-issued on frozen prefix) |
| DEER | `deer.py` | https://github.com/iie-ycx/DEER @ `c9dd19f` | **frozen-trajectory DEER reproduction** (official probes on frozen prefix) |

## Protocol summary

### CertaIndex faithful `mid` (`certaindex_mid.py`)
- Suffix (verbatim from `dynasor/core/cot.py:43`): `... Oh, I suddenly got the answer to the whole problem, **Final Answer**\n\n\[ \boxed{` — the **faithful** suffix WITH the preamble, distinct from the `SIMPLE_SUFFIX` auxiliary (no preamble).
- `effort_level('mid')` = `(patience=3, interval=64)`; probe cap 20; `temperature=0.6, top_p=0.95`; `stop=["\]"]`.
- Stop rule (verbatim from `cot.py`): the last 3 probe answers are all non-empty, all math-equivalent (`eqaul_group`), and all "certain" (no uncertainty word in `["wait","hold","but","okay","no","hmm"]`); deliver the latest probe answer.
- Zero floor; fixed positions 64,128,192,… on the decoded frozen prefix.
- **Adaptation label**: `certaindex_mid_frozen` — the prompt, suffix, cap, temperature/top_p, patience, certainty and math-equivalence stop rule are faithful; only the *timing* (frozen-prefix positions vs live-streamed chunks) is adapted. There is no off-by-one (the first probe is on prefix[:64] in both conventions).

### TJE (`tje.py`)
- Confidence instruction: the verbatim Figure-2 system prompt with all ten labels (`common.TJE_SYSTEM_PROMPT`), serialized in the tokenizer's actual **system role**; structured response `\confidence{X}`; forced prefix `\confidence{` injected at a trigger to prevent a new reasoning continuation.
- Triggers: case-insensitive whole-word `Wait` plus the final `</think>` check for the preregistered primary. `--wait-only` is an optional diagnostic.
- Threshold: `Almost certain`; decoding `temperature=0.6, top_p=0.95, top_k=20`.
- Below threshold at `</think>`: replace with continuation cue `Wait` (online); at threshold: insert `</think>` and generate the final-answer readout (readout output cost recorded).
- **Adaptation label**: `tje_frozen` — TJE can alter online generation; here the main trajectory is frozen, so confidence is re-issued on the frozen prefix. Not an end-to-end faithful run.
- Independent trigger recomputation (matches authoritative extraction): DeepSeek 30,767 `Wait` + 1,303 `</think>` = 32,070; Qwen3 32,446 `Wait` + 1,300 `</think>` = 33,746.

### DEER (`deer.py`) — pinned to upstream `c9dd19f`
- Transition point `Wait` (`--points 1`); `max_judge_steps=10`; `threshold=0.95`; `prob_check_max_tokens=20`; answer inducer `\n**Final Answer**\n\boxed`; `logprobs=1`.
- Confidence = average of per-token max prob (`exp(logprob)`) from index 1 to the last token (first generated token skipped, faithful to the released code).
- **DeepSeek (base)**: `policy=avg1` (arithmetic mean); trial `stop` = the `\boxed{}`-closing variants; early exit iff `confidence > 0.95`.
- **Qwen3**: `policy=avg2` (geometric mean); trial `stop=['</think>']`; the official additional condition — confidence is returned **only if the last generated token decodes to `</think>`**, else `0.0` (the "model must generate `</think>` after the trial answer" requirement); early exit iff `confidence > 0.95`.
- On early exit: final-answer readout from `prompt + prefix + "\n</think>\n\n"` (readout output cost recorded); on regular end (`</think>` reached naturally): the frozen natural full answer stands.
- Hard upper bound: 2,736 × 10 = 27,360 trial calls (split evenly by model before early exit).
- **Adaptation label**: `deer_frozen` — replaying official DEER probes on a frozen pre-generated path is not identical to running the entire online controller.

## Fair accounting (goal §8)

Two cost views per method:
1. **paper-style** `main_tokens_through_stop` — frozen reasoning length up to the stop (or full length if no stop);
2. **fair all-generated** `all_generated_tokens` = `main_through_stop` + every probe/trial/readout OUTPUT token. Probe/trial/readout PROMPT tokens (the re-sent prefix) are reported **separately** and never added.

Confidence intervals: deterministic **paired hierarchical bootstrap**, 10,000 samples, seed `20260727` — resample seeds, then paired problem rows within seed (`metrics.paired_hierarchical_ci`).

## Reproduction commands

Validate the frozen bank before any GPU work (CPU-only, no deps):

```bash
python -m benchmark.FalseConsensus.related_work.preflight \
  --results-root benchmark/FalseConsensus/results \
  --split-manifest benchmark/FalseConsensus/governor_v2/generated/split_manifest.json
```

### Full bank (one model)

The durable launcher derives the repository root from its own location,
validates endpoint readiness for a full run, and validates the split manifest
plus exactly 9 authorized development environments (math500/amc23/aime24 x
seeds 42/43/44) for the model. It then runs CertaIndex -> TJE -> DEER across
those 9 environments with workers=4 and the exact pinned arguments. It is
safely restartable (collectors skip complete per-problem files), fails loudly,
never selects/resets/touches GPUs or other processes, and writes
per-method/environment logs + machine-readable
status_<key>.json / progress_<key>.json under the full-results runtime area.
The portable `--dry-run` validates files, revisions, and exact commands but does
not require a live endpoint, so it remains usable after the model servers have
been intentionally stopped.
The manifest gate requires complete coverage (observed=expected, missing=0),
zero recorded request failures, and complete=true; both invalid_readouts and
truncated_readouts are diagnostic method outcomes (capped readout at
readout_cap=8192 = a complete record delivered as empty/incorrect in replay),
not infrastructure failures.

```bash
# DeepSeek (GPU 0, port 18000)
bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh deepseek
# Qwen3    (GPU 1, port 18001)
bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh qwen3
# dry run (prints the 27 planned commands, validates, writes no outputs)
bash benchmark/FalseConsensus/results/related_work/_runtime/run_full_model_pipeline.sh deepseek --dry-run
```

Progress/ETA (counts valid per-problem outputs against 400/32/24; no GPU scan):

```bash
python benchmark/FalseConsensus/results/related_work/_runtime/progress.py
```

### Individual collector commands (fully runnable)

Outputs go under
`benchmark/FalseConsensus/results/related_work/full/<model>__<bench>__seed_<s>/<method>`
(not the frozen main-run tree). DeepSeek endpoint: `http://127.0.0.1:18000/v1`;
Qwen3 endpoint: `http://127.0.0.1:18001/v1`.
Exact revisions: DeepSeek `916b56a44061fd5cd7d6a8fb632557ed4f724f60`,
Qwen3 `b968826d9c46dd6066d109eabc6255188de91218`.

```bash
SM=benchmark/FalseConsensus/governor_v2/generated/split_manifest.json
FULL=benchmark/FalseConsensus/results/related_work/full

# DeepSeek CertaIndex faithful mid (one ENV; repeat per bench/seed)
python -m benchmark.FalseConsensus.related_work.certaindex_mid \
  --main-run <ENV> --output $FULL/deepseek__<bench>__seed_<s>/certaindex_mid \
  --url http://127.0.0.1:18000/v1 --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --model-revision 916b56a44061fd5cd7d6a8fb632557ed4f724f60 \
  --split-manifest $SM --workers 4

# DeepSeek TJE primary (Wait + final think-close check); max-model-len + readout-cap required
python -m benchmark.FalseConsensus.related_work.tje \
  --main-run <ENV> --output $FULL/deepseek__<bench>__seed_<s>/tje \
  --url http://127.0.0.1:18000/v1 --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --model-revision 916b56a44061fd5cd7d6a8fb632557ed4f724f60 \
  --split-manifest $SM --workers 4 --max-model-len 34816 --readout-cap 8192

# DeepSeek DEER (auto avg1 + boxed-close stop by --model)
python -m benchmark.FalseConsensus.related_work.deer \
  --main-run <ENV> --output $FULL/deepseek__<bench>__seed_<s>/deer \
  --url http://127.0.0.1:18000/v1 --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  --model-revision 916b56a44061fd5cd7d6a8fb632557ed4f724f60 \
  --split-manifest $SM --workers 4
```

For Qwen3, use endpoint `http://127.0.0.1:18001/v1`, model `Qwen/Qwen3-8B`,
revision `b968826d9c46dd6066d109eabc6255188de91218`. DEER auto-selects `avg2`
(geometric) + the Qwen3 think-close iff gate by `--model`.

Each collector is restartable: a complete `problem_{id}.json` is skipped; a
partial/corrupt file is quarantined (`.corrupt`) and regenerated. Per-run
manifests record method, reproduction class, source commit, prompt hash,
trigger definition, output cap, sampling params, seed policy, model, protocol
version, `test_read=false`, and `main_generation_changed=false`.

After replaying all 54 method x environment outputs, build the strict pooled
views (this rejects missing/duplicate/test rows and wrong problem-ID sets):

```bash
python -m benchmark.FalseConsensus.related_work.aggregate_all \
  --inputs <all-replay-output-dirs>/replay_rows.jsonl \
  --output-dir benchmark/FalseConsensus/results/related_work/aggregate
```

The output contains per-environment split summaries, dev pooled across seeds,
train+dev diagnostics, benchmark-macro views, and paired hierarchical
bootstrap intervals.
