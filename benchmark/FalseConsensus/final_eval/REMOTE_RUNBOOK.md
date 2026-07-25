# Remote GPU runbook

This runbook is operational. It does not authorize changing any frozen rule.

## Safety and branch

- Use the existing Vast instance. Never destroy, recycle, or recreate it.
- Check disk space before model changes.
- Work on `final-eval-multiseed`; do not commit directly on `main`.
- Pull the latest `origin/main` before starting.
- Preserve every completed trajectory; all runners resume by trajectory file.

## DeepSeek first

Serve `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` with prefix caching and enough
context for the prompt plus the 3072-token reasoning budget. Confirm `/v1/models`
and a one-request health check before starting the full run. Always pass the
verified vLLM URL explicitly to `logging_run.py`.

Before the full run, use a separate temporary output directory for 1–3
problems. Run `evaluate_run.py --allow-partial-smoke` on that directory and
check the trajectory settings, reconstructed `probes.csv`, accounting fields,
GPU summary, and smoke evaluation manifest. Never place smoke artifacts under
the formal result directory.

Run MATH500 seed 43 exactly as shown in `README.md`, including the GPU monitor.
Do not tune from the output. When all 500 trajectory files exist:

1. run `evaluate_run.py`;
2. check that the manifest says 500 problems and seed 43;
3. commit and push that seed's results to `final-eval-multiseed`;
4. repeat unchanged for seeds 44 and 45.

After the three simple@32 streams, run two explicitly labeled CertaIndex
comparisons:

- adapted/prompt-matched: a standalone `logging_run.py` run with CertaIndex
  suffix, 128-token interval, and 32-token probe cap;
- faithful `mid`: a standalone `logging_run.py` run with CertaIndex suffix,
  64-token interval, 20-token probe cap, and the same generation seed.

The faithful run changes chunk size because `dynasor/core/cot.py` defines
`effort_level("mid")` as patience 3 and chunk size 64. Never merge the two
labels.

## Qwen and remaining GPU work

Only after all DeepSeek seeds are durable:

1. switch to `Qwen/Qwen3-8B`;
2. run MATH500 seeds 43/44/45 under the identical protocol;
3. evaluate and push after each seed;
4. run the registered GSM8K untouched test;
5. run one MATH500 seed with
   `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` as the third-family model.

Delete a model cache only when disk pressure requires it and only after
confirming all result files are committed and pushed. Never delete result
directories.

## Acceptance checks

For every logging run:

- trajectory count equals dataset size;
- `probes.csv` contains only that model/dataset/seed;
- at least one trajectory contains non-null accounting fields;
- GPU monitor summary has a zero command return code and nonzero samples;
- `evaluate_run.py` completes without changing `protocol.json`;
- the remote branch is pushed before beginning a model-cache swap.
