# probe_cost_ablation — supersede notice

**Status (2026-07-30):** The following v1 artifacts are SUPERSEDED and must NOT be
used as evidence. They are preserved here for audit only.

| file | status | why superseded |
|---|---|---|
| `protocol.json` | SUPERSEDED by `protocol_v2.json` | wrong cap method (char slice), missing metrics |
| `run_ablation.py` | SUPERSEDED by `collect_capped_probes.py` + `replay_probe_cost.py` | character slicing, no replay, no grader, hard-coded repo path |
| `ablation_rows.jsonl` | SUPERSEDED by `ablation_rows_v2.jsonl` | only a probe-call inventory; cap cells identical; no accuracy/saving |
| `ablation_summary.json` | SUPERSEDED by `env_summaries_v2.jsonl` / `macro_summaries_v2.jsonl` | derived from the invalid v1 rows |

The v1 rows (8,208) were a probe-call-count inventory, not a probe-cost ablation:
`truncate_probe_text` sliced `cap*4` characters (not tokens), the stored
dense-probe records contain no `probe_text` (so truncation was a no-op), and
`total_probe_out_tokens` summed the original cap-32 counts, making cap 8/16/32
identical. No Governor rule was replayed, no stop/delivered answer, no grader,
and accuracy / accuracy-drop / gross / net / zero-tax / PSF / Pareto were absent.

**Do not reuse `ablation_rows.jsonl` as evidence.** The valid ablation is
`ablation_rows_v2.jsonl` (684 dev trajectories × 12 interval×cap × 3 policies).
