# G1 probe-wording report (v5, 18 environments, dev split)

## 1. Coverage

- development trajectories scanned: 684
- trajectories excluded (hit budget, position-as-fraction undefined): 32
- paired probe positions analysed: 46360
- NO length-based (3,072-token) exclusion applied -- the v3 cap is removed. Only budget-hitters are dropped, as before, because their position fraction is undefined.

| model | benchmark | seed | trajectories | positions |
|---|---|---:|---:|---:|
| deepseek7b | aime24 | 42 | 6 | 883 |
| deepseek7b | aime24 | 43 | 6 | 1135 |
| deepseek7b | aime24 | 44 | 6 | 554 |
| deepseek7b | amc23 | 42 | 8 | 843 |
| deepseek7b | amc23 | 43 | 8 | 558 |
| deepseek7b | amc23 | 44 | 8 | 644 |
| deepseek7b | math500 | 42 | 100 | 4989 |
| deepseek7b | math500 | 43 | 100 | 4820 |
| deepseek7b | math500 | 44 | 100 | 4990 |
| qwen3_8b | aime24 | 42 | 6 | 1228 |
| qwen3_8b | aime24 | 43 | 6 | 1056 |
| qwen3_8b | aime24 | 44 | 6 | 900 |
| qwen3_8b | amc23 | 42 | 8 | 709 |
| qwen3_8b | amc23 | 43 | 8 | 906 |
| qwen3_8b | amc23 | 44 | 8 | 1117 |
| qwen3_8b | math500 | 42 | 100 | 7311 |
| qwen3_8b | math500 | 43 | 100 | 6886 |
| qwen3_8b | math500 | 44 | 100 | 6831 |

## 2. Two-wording agreement by relative-position bin

Bins are position as a fraction of each trajectory's own length. `agree` = the two suffixes return the same answer (robust grader). Reported pooled, macro over 18 envs, and per model.


### pooled

| position | n | agree% | disagree% | corr simple% | corr certaindex% |
|---|---:|---:|---:|---:|---:|
| 0-5% | 2015 | 53.7 | 46.3 | 13.5 | 12.7 |
| 5-10% | 2345 | 54.5 | 45.5 | 19.0 | 18.8 |
| 10-15% | 2319 | 57.4 | 42.6 | 21.7 | 23.5 |
| 15-20% | 2312 | 58.8 | 41.2 | 29.6 | 31.7 |
| 20-30% | 4629 | 65.8 | 34.2 | 39.3 | 40.7 |
| 30-40% | 4643 | 72.9 | 27.1 | 47.7 | 50.0 |
| 40-50% | 4675 | 77.3 | 22.7 | 55.2 | 56.9 |
| 50-60% | 4701 | 80.7 | 19.3 | 60.4 | 62.3 |
| 60-70% | 4671 | 82.5 | 17.5 | 64.3 | 65.9 |
| 70-85% | 7035 | 86.0 | 14.0 | 68.8 | 70.5 |
| 85-101% | 7015 | 88.0 | 12.0 | 75.9 | 77.6 |

### DeepSeek-7B

| position | n | agree% | disagree% | corr simple% | corr certaindex% |
|---|---:|---:|---:|---:|---:|
| 0-5% | 823 | 37.3 | 62.7 | 12.8 | 12.3 |
| 5-10% | 980 | 43.2 | 56.8 | 19.2 | 18.2 |
| 10-15% | 973 | 46.8 | 53.2 | 20.0 | 21.3 |
| 15-20% | 978 | 49.6 | 50.4 | 24.6 | 26.8 |
| 20-30% | 1955 | 55.4 | 44.6 | 31.8 | 32.4 |
| 30-40% | 1958 | 62.6 | 37.4 | 37.9 | 39.5 |
| 40-50% | 1959 | 67.2 | 32.8 | 45.7 | 46.5 |
| 50-60% | 1960 | 71.4 | 28.6 | 51.2 | 52.6 |
| 60-70% | 1960 | 72.5 | 27.5 | 54.7 | 55.9 |
| 70-85% | 2939 | 79.7 | 20.3 | 62.2 | 62.2 |
| 85-101% | 2931 | 83.9 | 16.1 | 70.6 | 67.9 |

### Qwen3-8B

| position | n | agree% | disagree% | corr simple% | corr certaindex% |
|---|---:|---:|---:|---:|---:|
| 0-5% | 1192 | 65.0 | 35.0 | 14.0 | 13.0 |
| 5-10% | 1365 | 62.6 | 37.4 | 18.8 | 19.3 |
| 10-15% | 1346 | 65.0 | 35.0 | 23.0 | 25.0 |
| 15-20% | 1334 | 65.5 | 34.5 | 33.3 | 35.2 |
| 20-30% | 2674 | 73.4 | 26.6 | 44.7 | 46.7 |
| 30-40% | 2685 | 80.4 | 19.6 | 54.9 | 57.6 |
| 40-50% | 2716 | 84.5 | 15.5 | 62.0 | 64.5 |
| 50-60% | 2741 | 87.4 | 12.6 | 67.0 | 69.2 |
| 60-70% | 2711 | 89.7 | 10.3 | 71.2 | 73.1 |
| 70-85% | 4096 | 90.5 | 9.5 | 73.6 | 76.4 |
| 85-101% | 4084 | 90.9 | 9.1 | 79.8 | 84.6 |

### macro over 18 environments

| position | n_envs | n_pooled | agree% | disagree% | corr simple% | corr certaindex% |
|---|---:|---:|---:|---:|---:|---:|
| 0-5% | 18 | 2015 | 45.2 | 54.8 | 7.6 | 6.6 |
| 5-10% | 18 | 2345 | 45.8 | 54.2 | 9.7 | 8.8 |
| 10-15% | 18 | 2319 | 47.7 | 52.3 | 11.6 | 11.7 |
| 15-20% | 18 | 2312 | 47.1 | 52.9 | 17.1 | 18.0 |
| 20-30% | 18 | 4629 | 53.0 | 47.0 | 24.2 | 25.3 |
| 30-40% | 18 | 4643 | 60.2 | 39.8 | 30.5 | 32.3 |
| 40-50% | 18 | 4675 | 63.7 | 36.3 | 36.4 | 37.6 |
| 50-60% | 18 | 4701 | 67.5 | 32.5 | 44.6 | 45.9 |
| 60-70% | 18 | 4671 | 71.5 | 28.5 | 51.3 | 52.0 |
| 70-85% | 18 | 7035 | 80.1 | 19.9 | 59.4 | 60.2 |
| 85-101% | 18 | 7015 | 87.1 | 12.9 | 71.7 | 72.9 |

## 3. Probe-correctness by bin

See the `corr simple%` / `corr certaindex%` columns above: probe-answer correctness (probe answer == gold target) by bin, per suffix. The two suffixes track each other closely, supporting the readout-vs-timing decomposition below.


## 4. Headline numbers (the two the paper quotes)

Disagreement = 1 - agreement. First tenth = bins 0-10%; final third = bins 70-100% (the v3 definition, so the two are directly comparable).

### pooled
- first tenth (0-10%): disagree 45.87% / agree 54.13% (n=4360)
- final third (70-100%): disagree 13.01% / agree 86.99% (n=14050)
- overall: agree 75.41% (n=46360)

### DeepSeek-7B
- first tenth (0-10%): disagree 59.51% / agree 40.49% (n=1803)
- final third (70-100%): disagree 18.21% / agree 81.79% (n=5870)
- overall: agree 66.53% (n=19416)

### Qwen3-8B
- first tenth (0-10%): disagree 36.25% / agree 63.75% (n=2557)
- final third (70-100%): disagree 9.28% / agree 90.72% (n=8180)
- overall: agree 81.82% (n=26944)

### macro (18 envs)
- first tenth: disagree 54.45% (n=4360)
- final third: disagree 16.40% (n=14050)
- overall: agree 66.08%

### macro DeepSeek-7B (9 envs)
- first tenth: disagree 68.61% (n=1803)
- final third: disagree 22.80% (n=5870)
- overall: agree 54.80%

### macro Qwen3-8B (9 envs)
- first tenth: disagree 40.29% (n=2557)
- final third: disagree 9.99% (n=8180)
- overall: agree 77.36%


## 5. Readout-vs-timing decomposition

The paper (§4.2) reports a ~0.65pp *readout* effect (which suffix) against a ~9.15pp *timing* effect (when one probes). Those were measured on stop-accuracy at a specific operating point; here we measure the analogous decomposition on raw probe-answer correctness over the paired positions, so the magnitudes are not directly the paper's numbers but the qualitative point -- suffix barely moves correctness, position moves it a great deal -- is directly comparable. Definitions:

- readout effect = |correct_simple - correct_certaindex| (how much the suffix changes the read answer's correctness);
- timing effect = correct(last bin) - correct(first bin), averaged over the two suffixes (how much position changes correctness).

| view | correct simple% | correct certaindex% |
|---|---:|---:|
| first bin (0-5%) | 13.50 | 12.70 |
| last bin (85-100%) | 75.92 | 77.63 |
| overall | 52.91 | 54.46 |

- readout effect (overall |simple - certaindex|): 1.55pp
- timing effect (last - first bin, avg suffix): 63.68pp

The sensitivity to wording is early-specific: the two suffixes agree far less early (53.7% in the first bin) than late (88.0% in the last bin), while their correctness is nearly identical -- so the early disagreement is about *which answer is elicited*, not a defect of one suffix.


## 6. Direct comparison against committed v3 numbers

| metric | v3 (1 env, 241 traj, 3072-cap) | v5 (18 envs, 684 traj, no cap) | change |
|---|---:|---:|---|
| first-tenth disagreement | 53.5% (n=213) | 45.9% (n=4360) | shrank |
| last-bin disagreement | 11.4% | 12.0% | grew |
| overall disagreement | 24.0% | 24.6% | grew |

**Verdict.** The v5 numbers remove the 3,072-token cap and the single-environment scope. Once length selection is removed, the early disagreement in the first tenth shrinks (v3 53.5% -> v5 45.9%) and the final-third disagreement grows (v3 11.4% -> v5 13.0%); overall agreement is essentially unchanged (76.0% -> 75.4% agree). The qualitative shape -- early answers are substantially a property of the question asked (46% disagree early) and become properties of the state only as the trajectory finishes (13% disagree late) -- **survives on the full 18-environment, un-truncated set, so the §4.2 conclusion is unchanged**. The per-model split shows the effect is larger on DeepSeek-7B (first-tenth 60% disagree) than on Qwen3-8B (36%), but present in both.
