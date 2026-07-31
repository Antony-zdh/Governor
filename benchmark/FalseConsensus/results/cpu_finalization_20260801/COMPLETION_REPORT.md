# FalseConsensus CPU evidence closure - 2026-08-01

All locally executable CPU tasks A-F passed row-count, scope, leakage and artifact
checks. No GPU inference or model download was performed.

| Task | Result |
|---|---|
| A matched signal | 3,420 trajectories; 30,606 exact DEER/TJE-position matches; unified frontier emitted |
| B Governor freeze/Test | 33,264 Train/Dev candidates; 3 rules frozen before Test; 2,052 rule-problem Test rows |
| C related-work Test | 3 methods x 684 = 2,052 rows; scope bug fixed; per-axis and macro tables emitted |
| D human adjudication | Task A 134/134 and Task B 89/89 resolved; raw annotations unchanged |
| E simple@32 Oracle | 3,420 trajectories; 80.56% strict upper-bound accuracy; 46.70% micro saving |
| F evidence closure | A24-A28, figures, artifact pointers and PDF updated |

Key limitations remain explicit: all core data are competition mathematics; matched
signal retains only exact-position overlap; long persistence is post-hoc sensitivity;
Oracle uses reference labels and is non-deployable; human Task B is risk-enriched.
The independent remote unseen-model seed 46/47 increment is not a blocker and is not
represented as complete here.

## Verification commands

```bash
python -m py_compile benchmark/FalseConsensus/related_work/aggregate_all.py benchmark/FalseConsensus/related_work/report_gen.py benchmark/FalseConsensus/report/analyze_matched_signal_frontier.py benchmark/FalseConsensus/governor_v2/analysis/freeze_extended_candidates.py benchmark/FalseConsensus/governor_v2/analysis/oracle_simple32.py benchmark/FalseConsensus/human_eval/adjudicate_reviews.py benchmark/FalseConsensus/finalize_cpu_evidence.py
python -m unittest benchmark.FalseConsensus.related_work.tests.test_postprocess.ReportGenTests -v
python benchmark/FalseConsensus/finalize_cpu_evidence.py
bash paper/render_finding_map_pdf.sh
```

Machine-readable inventory: `artifact_manifest.json` in this directory.
