# DEER-inspired deployment-style online Dev experiment

This package implements two live controllers:

- `deer_inspired_online_v1`: fast path plus retained verification
  branch-and-commit;
- `deer_online_reference`: official DEER-style online Wait probing and formal
  readout.

It does not read frozen main text during generation. Formal mode is hard-locked
to the Governor v2 Dev split and seed 42.

## CPU validation

```bash
python -m compileall benchmark/FalseConsensus/deer_inspired
python -m unittest discover \
  -s benchmark/FalseConsensus/deer_inspired/tests -v
```

If `pytest` is installed, the same tests can be run with:

```bash
pytest -q benchmark/FalseConsensus/deer_inspired/tests
pytest -q benchmark/FalseConsensus/related_work/tests
```

## Formal collection

Start a BF16 vLLM completion server with the exact model revision and
`--enable-prefix-caching`. Record the full launch command:

```bash
export VLLM_SERVER_COMMAND='python -m vllm.entrypoints.openai.api_server ...'
bash benchmark/FalseConsensus/deer_inspired/run_online_dev.sh \
  deepseek-ai/DeepSeek-R1-Distill-Qwen-7B \
  916b56a44061fd5cd7d6a8fb632557ed4f724f60 \
  http://127.0.0.1:18000/v1 \
  benchmark/FalseConsensus/results/deer_inspired/online_dev \
  2
```

Run the Qwen3 model analogously after replacing the model, revision and
endpoint. Use separate output directories for GPU smoke by adding `--smoke`
and one or more `--problem-id` arguments directly to `online_controller`.

## Aggregate and render

```bash
python -m benchmark.FalseConsensus.deer_inspired.aggregate \
  --results-root benchmark/FalseConsensus/results/deer_inspired/online_dev \
  --output benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate

python -m benchmark.FalseConsensus.deer_inspired.report \
  --markdown benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/report.md \
  --pdf benchmark/FalseConsensus/results/deer_inspired/online_dev/aggregate/report.pdf
```

The default aggregate is fail-closed: each method must contain exactly 228
results, all at seed 42, with no recorded infrastructure error. Use
`--allow-incomplete` only for explicitly labeled progress diagnostics.
