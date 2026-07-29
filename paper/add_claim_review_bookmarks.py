#!/usr/bin/env python3
"""Add a hierarchical claim-review outline to the ACL draft PDF.

The original PDF is never modified. Each paper section becomes a level-1
bookmark, each material claim a level-2 bookmark, and review comments become
level-3 children of the claim they qualify. The outline is collapsed at level
1 by default so PDF readers can expand it section by section.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import fitz


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "paper" / "acl_latex.pdf"
OUTPUT = ROOT / "output" / "pdf" / "acl_latex_claim_review_annotated.pdf"


# title, physical PDF page, search anchor, optional review comment
Claim = tuple[str, int, str, Optional[str]]


SECTIONS: list[tuple[str, int, str, list[Claim]]] = [
    (
        "CLAIM REVIEW GUIDE",
        1,
        "Abstract",
        [
            (
                "How to read these bookmarks",
                1,
                "Abstract",
                "[CHECK-HIGH] materially unsupported, incorrect, or attribution-changing; "
                "[CHECK-MED] scope, aggregation, statistics, or provenance needs tightening; "
                "[CHECK-LOW] documentation or presentation issue. Unmarked claims match current evidence.",
            ),
        ],
    ),
    (
        "Abstract",
        1,
        "Abstract",
        [
            (
                "Consensus tuning does not repair unsafe stopping",
                1,
                "We show this bet is unsafe",
                "[CHECK-MED] Limit to the preregistered 17,712-rule schema; the wording currently sounds universal.",
            ),
            (
                "Recent unanimous window: 93.5% correct",
                1,
                "93.5%",
                "[CHECK-MED] Exact rate is from one DeepSeek-7B, MATH500, seed-42, 3072-cap exploratory run.",
            ),
            (
                "Naive consensus stop loses 16.4 pp",
                1,
                "16.4 percentage",
                "[CHECK-MED] Same single-setting exploratory run; full answer is still capped at 3072.",
            ),
            (
                "Preregistered 7-D search over 17,712 rules",
                1,
                "17,712 rules",
                None,
            ),
            (
                "No dev rule clears safety; dev floor is 1.85 pp",
                1,
                "safest stop still",
                "[CHECK-MED] 1.85 pp is a dev point estimate; its bootstrap CI includes zero and the same rule is 0.11 pp on test.",
            ),
            (
                "Held-out test and unseen models reproduce frontier (r=0.96)",
                1,
                "r=0.96",
                "[CHECK-HIGH] r=0.96 and the joint dev-test gate are for the two seen models. Unseen models have only seed 45; Llama lacks AIME24.",
            ),
            (
                "CertaIndex reproduction collapses by 56-70 pp",
                1,
                "56",
                "[CHECK-MED] Accurate for our frozen-trajectory harness, not the original paper's end-to-end deployment.",
            ),
            (
                "Boundary confidence plus verification stays within about 1 pp",
                1,
                "retained verification branch",
                "[CHECK-HIGH] The fast path has support, but the current verification branch has zero net correction in ablation and should not receive credit.",
            ),
            (
                "Online controller saves about 34% at near-neutral macro accuracy",
                1,
                "34%",
                "[CHECK-HIGH] True only under environment-macro weighting. Problem-pooled saving is 1.48 pp lower than online DEER; no held-out test.",
            ),
            (
                "Accuracy tax is intrinsic; probe tax is reducible",
                1,
                "accuracy tax",
                "[CHECK-MED] Intrinsic claim is established inside frozen trajectories and reachable stop positions, not for every online probing scheme.",
            ),
            (
                "Safe exit needs a forward-looking signal",
                1,
                "trajectory",
                "[CHECK-MED] This is a design implication, not directly proven as a necessary condition.",
            ),
        ],
    ),
    (
        "1 Introduction and stated contributions",
        1,
        "Introduction",
        [
            (
                "Much computation occurs after the answer is effectively decided",
                1,
                "Much of this",
                "[CHECK-MED] Motivating premise is not directly quantified by the current experiments; cite evidence or soften.",
            ),
            (
                "Finding 1: local consensus is non-terminal",
                2,
                "Perfect whole",
                "[CHECK-MED] Strong within the measured math setting; exact percentages are not cross-model estimates.",
            ),
            (
                "Finding 2: no safe-and-saving rule in searched space",
                2,
                "Finding 2",
                None,
            ),
            (
                "Finding 2: positive net saving costs at least 4.87 pp",
                2,
                "4.87 pp",
                "[CHECK-MED] This floor is conditional on dense simple@32 output-token charging.",
            ),
            (
                "Finding 2: adaptive probing is dominated",
                2,
                "adaptive",
                "[CHECK-MED] Limit to the current adaptive trigger family and grid.",
            ),
            (
                "Finding 3: accuracy tax survives any probing scheme",
                2,
                "survives any probing",
                "[CHECK-HIGH] Too broad. Evidence is frozen-trajectory and grid-reachability based.",
            ),
            (
                "Finding 4: the signal is the problem, not early exit",
                2,
                "The signal is the problem",
                "[CHECK-MED] Same-harness contrast is persuasive but not a pure signal-only causal ablation.",
            ),
            (
                "Finding 4: DEER stays within about 1 pp",
                2,
                "stays within",
                "[CHECK-HIGH] Frozen DEER is +0.78 pp on Qwen but -4.83 pp on DeepSeek; the unqualified statement is inaccurate.",
            ),
            (
                "Contribution: calibrated false-consensus taxonomy",
                2,
                "error taxonomy",
                "[CHECK-HIGH] Taxonomy is AI-assisted on 28 cases; the 134-case human review is still pending.",
            ),
            (
                "Contribution: release design and sweep artifacts",
                2,
                "release the",
                "[CHECK-LOW] Verify an anonymous, accessible release and immutable hashes exist at submission time.",
            ),
            (
                "Contribution: boundary confidence with verification escapes tax",
                2,
                "escapes the accuracy tax",
                "[CHECK-HIGH] Current branch ablation does not support the verification attribution; only fast path has independent positive evidence.",
            ),
        ],
    ),
    (
        "2 Related Work",
        2,
        "Related Work",
        [
            (
                "Current sweep adopts the same probe mechanism as CertaIndex",
                3,
                "boxed-answer suffix",
                "[CHECK-MED] Governor simple@32 wording differs from faithful CertaIndex prompting; describe shared answer-probing idea, not identical mechanism.",
            ),
            (
                "Self-consistency stopping criteria do not transfer",
                3,
                "do not transfer",
                "[CHECK-MED] Mechanistic argument is plausible, but Adaptive-Consistency/ESC are not directly reproduced here.",
            ),
            (
                "Recovery is intrinsic self-correction",
                3,
                "intrinsic self-correction",
                None,
            ),
            (
                "Probe consensus is poorly calibrated where stopping acts",
                3,
                "poorly calibrated",
                "[CHECK-MED] Evidence is the single Stage-1 stream; report binning details and avoid broad calibration generalization.",
            ),
            (
                "Among first preregistered early-exit evaluations",
                3,
                "among the first",
                "[CHECK-MED] Novelty claim needs a focused literature check and a verifiable preregistration timestamp.",
            ),
        ],
    ),
    (
        "3 False Consensus Phenomenon",
        3,
        "The False Consensus Phenomenon",
        [
            (
                "Setup: DeepSeek-7B, MATH500, seed 42, cap 3072",
                3,
                "decode budget",
                "[CHECK-MED] Many trajectories are truncated; treat all exact rates as exploratory and setting-specific.",
            ),
            (
                "Probe observes without altering the main trajectory",
                3,
                "only observes",
                None,
            ),
            (
                "Cumulative unanimous consensus: 98.9% correct (87 cases)",
                4,
                "98.9%",
                None,
            ),
            (
                "Last-five unanimous window: 93.5% correct (338 cases)",
                4,
                "93.5%",
                None,
            ),
            (
                "Local consensus is not a safe online signal",
                4,
                "local consensus",
                "[CHECK-MED] Supported for this window/probe design; do not imply every possible local signal.",
            ),
            (
                "Naive certain 3-probe stop loses 16.4 pp",
                4,
                "three consecutive probes",
                "[CHECK-HIGH] Paper says 'certain' means high token-level confidence, but collection code uses absence of uncertain words.",
            ),
            (
                "Three-probe disagreements recover: 65.5%",
                4,
                "65.5%",
                None,
            ),
            (
                "Wrong first probes recover: 76.3%",
                4,
                "76.3%",
                None,
            ),
            (
                "Later consensus is less trustworthy",
                4,
                "later consensus",
                "[CHECK-MED] Single-setting observational result; difficulty is a confound, so avoid causal wording.",
            ),
            (
                "Window CCE is 0.080; cumulative CCE is 0.149",
                4,
                "0.080",
                "[CHECK-MED] Window CCE is numerically lower than cumulative CCE; explain why it is still called poorly calibrated and report bins.",
            ),
            (
                "Share 0.8 has 47.2% accuracy (n=36)",
                4,
                "47.2%",
                None,
            ),
            (
                "Error taxonomy counts over 28 AI-assisted cases",
                4,
                "28",
                "[CHECK-HIGH] Human validation is pending; do not present category proportions as settled.",
            ),
            (
                "About one in five false consensuses is a probe-format artifact",
                4,
                "roughly one in five",
                "[CHECK-HIGH] Based on 6 AI-assisted labels out of 28; too thin for a methodological frequency claim.",
            ),
            (
                "Best possible rule in a large space cannot be safe and economical",
                4,
                "searched space",
                "[CHECK-HIGH] Replace 'best possible' with 'best in our preregistered schema'.",
            ),
        ],
    ),
    (
        "4 Preregistered Test",
        4,
        "A Preregistered Test",
        [
            (
                "Frozen trajectories make rules probe-independent",
                4,
                "frozen trajectories",
                None,
            ),
            (
                "Dense probing every 64 tokens with simple@32",
                5,
                "simple@32",
                "[CHECK-HIGH] simple@32 is one probe capped at 32 output tokens, not a 32-sample probe.",
            ),
            (
                "Adaptive bank adds entropy and marker triggers",
                5,
                "adaptive bank",
                None,
            ),
            (
                "Seven rule dimensions yield 17,712 candidates",
                5,
                "17,712 candidate",
                None,
            ),
            (
                "Development: 2 models x 3 benchmarks x 3 seeds",
                5,
                "18 model",
                None,
            ),
            (
                "Problem-grouped 60/20/20 split",
                5,
                "60/20/20",
                None,
            ),
            (
                "Confirmation reserves seeds 45/46/47 plus two unseen models",
                5,
                "seeds 45/46/47",
                "[CHECK-HIGH] Seen models use seeds 45-47; both unseen models use seed 45 only. Llama AIME24 is missing.",
            ),
            (
                "Conservative, balanced, and token-efficient gates fixed",
                5,
                "three operating points",
                None,
            ),
            (
                "Per-model gate is primary; per-benchmark gate diagnostic",
                5,
                "per-model gate as primary",
                "[CHECK-MED] Clarify whether downgrading the preregistered per-benchmark gate to diagnostic was itself prespecified.",
            ),
            (
                "C1-C3 prevent held-out selection leakage",
                5,
                "Three commitments",
                "[CHECK-MED] Supply immutable commit/hash/timestamp evidence for preregistration provenance.",
            ),
        ],
    ),
    (
        "5 Results: Searched-Space Negative Result",
        6,
        "Results",
        [
            (
                "Sweep covers 637,632 rule-environment-split rows",
                6,
                "637,632",
                None,
            ),
            (
                "No rule clears the conservative dev gate",
                6,
                "No rule in",
                None,
            ),
            (
                "Dev Pareto frontier has 93 rules; none admissible",
                6,
                "93",
                None,
            ),
            (
                "Minimum worst-case per-model drop is 1.85 pp",
                6,
                "1.85 pp",
                "[CHECK-MED] Exact floor is statistically thin; CI includes zero and test value is 0.11 pp.",
            ),
            (
                "Drop percentiles: p1 3.37, p5 4.26, median 20.1 pp",
                6,
                "p1",
                None,
            ),
            (
                "Positive net saving requires at least 4.87 pp",
                6,
                "4.87 pp",
                "[CHECK-MED] Conditional on the dense 32-output-token probe accounting.",
            ),
            (
                "All 17,712 rules lose in worst-case per-model metric",
                6,
                "Every one",
                None,
            ),
            (
                "Cells fall 67.7%, rise 6.7%, unchanged 25.5%",
                6,
                "67.7%",
                None,
            ),
            (
                "Rare gains are small and do not concentrate",
                6,
                "rare gains",
                "[CHECK-MED] Add a direct artifact/table for magnitude and family concentration; current mapping lacks this analysis.",
            ),
            (
                "Accuracy result is independent of probe density",
                6,
                "independent of how densely",
                "[CHECK-MED] True only conditional on frozen trajectories and reachable stop positions.",
            ),
            (
                "Entropy family reaches 1.85 pp only with negative saving",
                6,
                "entropy_budget_fraction",
                None,
            ),
            (
                "Adaptive family needs 9.70 pp for positive saving",
                6,
                "9.70 pp",
                None,
            ),
            (
                "Adaptive probing does not help",
                6,
                "Adaptive probing does not help",
                "[CHECK-HIGH] Section title overgeneralizes; use 'Current adaptive-event family is dominated on dev'.",
            ),
            (
                "Main comparison of selected Governor operating points",
                7,
                "Main comparison",
                "[CHECK-HIGH] Tables 4 and 5 still contain TBD cells and approximate values; final numbers must be frozen before use.",
            ),
            (
                "Dev-test frontier correlation is r=0.96",
                7,
                "Pearson",
                None,
            ),
            (
                "No rule clears the conservative gate on both splits",
                7,
                "No rule clears",
                None,
            ),
            (
                "272 test-only winners fail dev",
                7,
                "272",
                None,
            ),
            (
                "Same structure holds on Qwen-32B and Llama-8B",
                7,
                "same structure holds",
                "[CHECK-HIGH] Only seed 45 for unseen models; Llama has no AIME24. Do not imply full multi-seed confirmation.",
            ),
            (
                "1.85 pp is dev-only; confirmed claims are frontier and joint gate",
                7,
                "On the floor value",
                None,
            ),
        ],
    ),
    (
        "6 Mechanism: Accuracy Tax and Probe Tax",
        7,
        "Mechanism",
        [
            (
                "Output-token accounting: T = s + p",
                7,
                "T = s + p",
                "[CHECK-MED] Excludes input/prefill cost, wall time, and memory; keep 'output-token' explicit.",
            ),
            (
                "Accuracy drop depends on stop position, not probe outputs",
                7,
                "depends only on",
                "[CHECK-MED] Deterministic inside frozen replay, not necessarily in an online controller that changes generation.",
            ),
            (
                "No probing scheme can remove the 1.85 pp tax",
                7,
                "no probing scheme",
                "[CHECK-HIGH] Overclaim: exact 1.85 pp is not stable and coverage is not every possible stop/signal.",
            ),
            (
                "Direction ratio is 35:1 for naive consensus",
                8,
                "35:1",
                None,
            ),
            (
                "Pure sampling noise predicts 1:1",
                8,
                "1:1",
                "[CHECK-MED] State the null/exchangeability assumption and preferably report a paired McNemar/binomial significance test.",
            ),
            (
                "Conservative variants retain 15-18:1 direction ratio",
                8,
                "15",
                None,
            ),
            (
                "Dense probing turns safe-family net saving negative",
                8,
                "turns the net savings",
                None,
            ),
            (
                "Probe tax is reducible by sparse probes, short probes, or KV reuse",
                8,
                "is reducible",
                "[CHECK-MED] Reducible by accounting identity, but no full density/length/KV ablation quantifies the recovered frontier.",
            ),
            (
                "Accuracy floor survives any probing scheme",
                8,
                "survives any probing",
                "[CHECK-HIGH] Reachability premise is not proven: interval-64 prefixes are not every token, and online probes may alter trajectories.",
            ),
            (
                "Gross/net Table 5 quantifies the probe tax",
                8,
                "Table 5",
                "[CHECK-HIGH] Table still contains TBD cells; it does not yet quantify the decomposition completely.",
            ),
        ],
    ),
    (
        "7 Prior Early-Stoppers",
        8,
        "Prior Early-Stoppers",
        [
            (
                "All baselines use the same simple@32 probe bank",
                8,
                "same simple@32 probe bank",
                "[CHECK-HIGH] Incorrect: faithful CertaIndex, DEER, and TJE use method-specific reprobes/prompts; only trajectories/accounting are shared.",
            ),
            (
                "Baseline results are frozen reproductions, not original end-to-end",
                8,
                "not the original",
                None,
            ),
            (
                "CertaIndex is a faithful share-threshold stop",
                8,
                "share-threshold",
                "[CHECK-MED] Prompt/stop logic is faithful, but frozen timing is still an adaptation.",
            ),
            (
                "TJE is a token-level early-exit stop",
                8,
                "TJE",
                "[CHECK-HIGH] Frozen TJE uses structured choice constraints that alter label distribution; document as adaptation, not full faithful reproduction.",
            ),
            (
                "CertaIndex loses 56-70 pp while saving 77-90%",
                9,
                "70.1",
                None,
            ),
            (
                "DEER: +0.8 pp Qwen, -4.8 pp DeepSeek",
                9,
                "DEER",
                None,
            ),
            (
                "DEER is the lone near-full method",
                9,
                "lone method",
                "[CHECK-MED] Near-full only on Qwen; DeepSeek loses 4.8 pp.",
            ),
            (
                "Consensus signal is the problem, not early exit",
                9,
                "consensus signal is the problem",
                "[CHECK-MED] Cross-method contrast includes trigger, prompt, confidence, and readout differences; not signal-only causality.",
            ),
            (
                "Figure 1 uses all-generated-token saving",
                10,
                "All-generated-token",
                None,
            ),
        ],
    ),
    (
        "8 Boundary-Confidence Early Exit",
        9,
        "A Signal That Works",
        [
            (
                "Section title: A Signal That Works",
                9,
                "A Signal That Works",
                "[CHECK-HIGH] Too definitive for exploratory dev-only, seed-sensitive results; use 'A Promising Alternative Signal'.",
            ),
            (
                "Online controller recovers savings at neutral accuracy",
                9,
                "neutral accuracy",
                "[CHECK-MED] Neutral only in environment-macro mean; seed range is -6.1 to +4.2 pp.",
            ),
            (
                "DEER confidence is mean answer-token probability",
                9,
                "answer tokens",
                "[CHECK-HIGH] Protocol differs by model: DeepSeek uses arithmetic mean; Qwen uses geometric mean plus a required </think> gate.",
            ),
            (
                "Trial/readout disagree on 14.6%; readout averages 470 tokens",
                9,
                "14.6%",
                "[CHECK-MED] Add a committed analysis artifact/script for these derived numbers.",
            ),
            (
                "Readout gives no net accuracy gain",
                9,
                "no net accuracy gain",
                "[CHECK-MED] Overall comparison hides model-specific flips; report paired counts/CIs.",
            ),
            (
                "Fast commit at confidence above 0.995",
                9,
                "fast-commits",
                "[CHECK-MED] Frozen fast-path replay supports this component; online component-only ablation is still absent.",
            ),
            (
                "Verification branch commits on equivalent second answer",
                9,
                "verification branch",
                "[CHECK-HIGH] Branch audit finds zero net correction; all accepted verification outputs hit the 64-token length cap.",
            ),
            (
                "Three-seed online result: -0.75 pp, 34.2% saving",
                9,
                "1,368",
                "[CHECK-MED] Seeds 43/44 are in nonformal outputs without the same unified audit artifact as seed 42.",
            ),
            (
                "Inspired dominates online DEER",
                9,
                "dominating",
                "[CHECK-HIGH] Only environment-macro saving dominates. Problem-pooled saving is 36.26% vs 37.74%, and accuracy difference is not significant.",
            ),
            (
                "Saving advantage +12.1% CI [+0.7,+22.9]",
                9,
                "12.1%",
                "[CHECK-HIGH] This is an 18-environment macro bootstrap; conclusion reverses under problem-pooled saving.",
            ),
            (
                "Single seed 42 sits at favorable end",
                9,
                "favorable end",
                "[CHECK-LOW] Avoid foregrounding the best seed unless clearly descriptive and non-selective.",
            ),
            (
                "Controller is a positive signal, not a finished method",
                10,
                "not a finished method",
                None,
            ),
            (
                "Stepping outside consensus escapes the accuracy tax",
                10,
                "outside the consensus",
                "[CHECK-HIGH] Evidence supports a promising signal, not confirmed escape: no test, strong seed sensitivity, and branch contributes no protection.",
            ),
        ],
    ),
    (
        "9 Discussion",
        10,
        "Discussion",
        [
            (
                "Negative result is limited to searched consensus space",
                10,
                "within a large",
                None,
            ),
            (
                "No threshold on consensus escapes the accuracy tax",
                11,
                "no threshold",
                "[CHECK-MED] Keep scope tied to the searched schema; unseen threshold/signal variants are not excluded.",
            ),
            (
                "Boundary confidence with verification saves 34% near-neutral",
                11,
                "saves",
                "[CHECK-HIGH] Do not attribute the result to verification; branch ablation is negative and saving superiority is aggregation-dependent.",
            ),
            (
                "Forward-looking confidence should replace agreement",
                11,
                "forward-looking",
                "[CHECK-MED] Present as hypothesis/design recommendation, not a necessary conclusion.",
            ),
            (
                "Confirmation validates frontier on seen and unseen models alike",
                11,
                "seen and two unseen",
                "[CHECK-HIGH] Same-model dev-test evidence is strong; unseen-model evidence is seed-45 only and incomplete for Llama.",
            ),
            (
                "Sparser probing or KV reuse could recover positive net saving",
                11,
                "could recover",
                "[CHECK-MED] Clearly label as an untested extension, not a result.",
            ),
        ],
    ),
    (
        "10 Conclusion",
        11,
        "Conclusion",
        [
            (
                "Consensus family answer is no",
                11,
                "the answer is no",
                "[CHECK-MED] Add 'within our preregistered searched space' to avoid universal wording.",
            ),
            (
                "93.5%, 16.4 pp, 17,712 rules, 1.85 pp",
                11,
                "93.5%",
                "[CHECK-MED] 93.5/16.4 are single-setting; 1.85 is dev-only and statistically thin.",
            ),
            (
                "CertaIndex collapses by 56-70 pp",
                11,
                "56",
                "[CHECK-MED] Frozen-harness reproduction only.",
            ),
            (
                "Boundary confidence with verification stays near full and saves 34%",
                11,
                "verification branch",
                "[CHECK-HIGH] Verification attribution unsupported; no held-out test and macro/pooled saving disagree.",
            ),
            (
                "Practical takeaway: use forward-looking confidence",
                11,
                "takeaway",
                "[CHECK-MED] Phrase as a promising direction pending test and model-generalization evidence.",
            ),
        ],
    ),
    (
        "Limitations",
        11,
        "Limitations",
        [
            (
                "Held-out scope and missing Llama AIME24",
                11,
                "Llama-8B",
                None,
            ),
            (
                "Exact 1.85 pp floor is not split-invariant",
                11,
                "0.11 pp",
                None,
            ),
            (
                "AMC23/AIME24 cells have coarse resolution",
                11,
                "Small held-out",
                None,
            ),
            (
                "Savings axis depends on dense probe tax",
                11,
                "Probe-tax dependence",
                None,
            ),
            (
                "Only one probe suffix and one schema are searched",
                12,
                "Single probe suffix",
                None,
            ),
            (
                "Boundary-confidence result is exploratory and approximate",
                12,
                "Boundary-confidence results",
                None,
            ),
            (
                "Non-consensus signal escapes accuracy tax",
                12,
                "It should be read",
                "[CHECK-HIGH] Even in Limitations this remains too strong; use 'provides exploratory evidence beyond consensus'.",
            ),
            (
                "Domain is competition mathematics only",
                12,
                "Domain",
                None,
            ),
        ],
    ),
    (
        "Appendix and reproducibility claims",
        13,
        "Rule Schema Details",
        [
            (
                "Rule schema enumerates 17,712 candidates",
                13,
                "17,712",
                None,
            ),
            (
                "Certainty is mean answer-token probability",
                13,
                "A probe is certain",
                "[CHECK-HIGH] Incorrect for Governor simple@32: is_certain is absence of uncertain words, not token probability.",
            ),
            (
                "simple@32 aggregates certainty over 32 samples",
                13,
                "simple@32 bank",
                "[CHECK-HIGH] Incorrect: @32 is the maximum probe output length in tokens; each checkpoint has one completion.",
            ),
            (
                "Adaptive entropy trigger means model just committed",
                13,
                "model just committed",
                "[CHECK-MED] This is an interpretation of entropy drop, not a validated semantic meaning.",
            ),
            (
                "Protocol and gates were fixed before held-out evaluation",
                13,
                "fixed before",
                "[CHECK-MED] Include the exact public/immutable timestamp, commit, and hashes.",
            ),
            (
                "Frozen artifacts and scripts are released",
                13,
                "are released",
                "[CHECK-LOW] Verify public anonymous artifact availability and remove future-tense mismatch.",
            ),
            (
                "Grader uses robust mathematical equivalence",
                13,
                "robust answer-equivalence",
                "[CHECK-MED] Human hard-case audit is pending; do not imply a measured error rate yet.",
            ),
            (
                "Grader measured error rate",
                13,
                "measured error rate",
                "[CHECK-HIGH] Explicit PENDING placeholder; complete Task B audit before submission.",
            ),
            (
                "Additional figures and tables still to add",
                13,
                "Still to add",
                "[CHECK-HIGH] Explicit PENDING material remains; final paper must remove all placeholders.",
            ),
        ],
    ),
]


def find_top(document: fitz.Document, page_number: int, anchor: str) -> float:
    """Return a bookmark destination slightly above the first anchor match."""

    page = document[page_number - 1]
    matches = page.search_for(anchor)
    if matches:
        return max(0.0, float(matches[0].y0) - 20.0)
    return 24.0


def build_toc(document: fitz.Document) -> list[list[object]]:
    toc: list[list[object]] = []
    for section_title, section_page, section_anchor, claims in SECTIONS:
        toc.append(
            [
                1,
                section_title,
                section_page,
                find_top(document, section_page, section_anchor),
            ]
        )
        for claim_title, claim_page, claim_anchor, comment in claims:
            top = find_top(document, claim_page, claim_anchor)
            toc.append([2, claim_title, claim_page, top])
            if comment:
                toc.append([3, comment, claim_page, top])
    return toc


def review_priority(comment: str) -> tuple[str, tuple[float, float, float]]:
    if comment.startswith("[CHECK-HIGH]"):
        return "CHECK-HIGH", (0.95, 0.20, 0.20)
    if comment.startswith("[CHECK-MED]"):
        return "CHECK-MED", (1.00, 0.60, 0.10)
    return "CHECK-LOW", (0.95, 0.80, 0.10)


def available_note_y(
    requested: float,
    used: list[float],
    page_height: float,
) -> float:
    y = min(max(requested, 32.0), page_height - 32.0)
    while any(abs(y - previous) < 18.0 for previous in used):
        y += 18.0
        if y > page_height - 32.0:
            y = max(32.0, min(used, default=50.0) - 18.0)
    used.append(y)
    return y


def add_review_annotations(document: fitz.Document) -> int:
    """Highlight reviewed text and add a closed popup comment in the margin."""

    note_positions: dict[int, list[float]] = {}
    comment_count = 0
    for _, _, _, claims in SECTIONS:
        for claim_title, page_number, anchor, comment in claims:
            if not comment:
                continue

            page = document[page_number - 1]
            matches = page.search_for(anchor)
            if not matches:
                raise RuntimeError(
                    f"Cannot annotate unmatched anchor on page {page_number}: {anchor}"
                )
            target = matches[0]
            priority, color = review_priority(comment)

            highlight = page.add_highlight_annot(target)
            highlight.set_info(
                title="Governor claim review",
                subject=priority,
                content=comment,
            )
            highlight.set_colors(stroke=color)
            highlight.set_opacity(0.22)
            highlight.update()

            used = note_positions.setdefault(page_number, [])
            note_y = available_note_y(target.y0, used, page.rect.height)
            note = page.add_text_annot(
                (page.rect.width - 30.0, note_y),
                comment,
                icon="Comment",
            )
            note.set_info(
                title=claim_title,
                subject=priority,
                content=comment,
            )
            note.set_colors(stroke=color)
            note.set_open(False)
            note.update()
            comment_count += 1
    return comment_count


def validate_source(document: fitz.Document) -> None:
    if document.page_count != 14:
        raise RuntimeError(
            f"Expected the reviewed draft to have 14 pages, got {document.page_count}"
        )
    text = "\n".join(page.get_text() for page in document)
    required = (
        "False Consensus",
        "17,712",
        "Boundary-Confidence",
        "PENDING",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError(f"Source PDF does not match expected draft: {missing}")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    source = fitz.open(SOURCE)
    validate_source(source)
    toc = build_toc(source)
    source.set_toc(toc, collapse=1)
    written_comments = add_review_annotations(source)
    temporary = OUTPUT.with_suffix(".tmp.pdf")
    if temporary.exists():
        temporary.unlink()
    source.save(temporary, garbage=4, deflate=True)
    source.close()
    os.replace(temporary, OUTPUT)

    reviewed = fitz.open(OUTPUT)
    actual_toc = reviewed.get_toc(simple=False)
    expected_comments = sum(
        1
        for _, _, _, claims in SECTIONS
        for _, _, _, comment in claims
        if comment
    )
    actual_comments = sum(
        1 for entry in actual_toc if str(entry[1]).startswith("[CHECK-")
    )
    if reviewed.page_count != 14:
        raise RuntimeError("Bookmarking changed the page count")
    if len(actual_toc) != len(toc):
        raise RuntimeError(
            f"TOC count mismatch: expected {len(toc)}, got {len(actual_toc)}"
        )
    if actual_comments != expected_comments:
        raise RuntimeError(
            f"Comment count mismatch: expected {expected_comments}, got {actual_comments}"
        )
    annotation_count = sum(
        sum(1 for _ in page.annots() or ())
        for page in reviewed
    )
    if written_comments != expected_comments:
        raise RuntimeError(
            f"Written comment mismatch: expected {expected_comments}, got {written_comments}"
        )
    if annotation_count != expected_comments * 2:
        raise RuntimeError(
            f"Annotation count mismatch: expected {expected_comments * 2}, "
            f"got {annotation_count}"
        )
    print(
        f"wrote={OUTPUT}\n"
        f"pages={reviewed.page_count}\n"
        f"bookmarks={len(actual_toc)}\n"
        f"review_comments={actual_comments}\n"
        f"visible_annotations={annotation_count}"
    )
    reviewed.close()


if __name__ == "__main__":
    main()
