#!/usr/bin/env python3
"""Color every material claim in the current ACL draft by evidence status.

The source PDF is never modified.  The output receives:

* one audit-cover page with the red / blue / green legend;
* a colored highlight over the anchor for every material claim;
* a closed popup comment containing the status, Appendix evidence pointer,
  and either a support note, missing experiment, or contradiction;
* a hierarchical outline whose claim titles start with GREEN / BLUE / RED.

The claim inventory and physical-page anchors are shared with
``add_claim_review_bookmarks.py``.  Statuses below reflect the evidence audit
in ``FINDING_EXPERIMENT_MAP.md`` after interrogation batches 001--005.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz

from add_claim_review_bookmarks import SECTIONS


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "paper" / "acl_latex.pdf"
OUTPUT = ROOT / "output" / "pdf" / "acl_latex_claim_evidence_colored.pdf"


COLORS = {
    "GREEN": (0.10, 0.68, 0.28),
    "BLUE": (0.12, 0.36, 0.92),
    "RED": (0.92, 0.13, 0.16),
}


# RED means the wording is contradicted, factually wrong, attribution-changing,
# or materially broader than the evidence permits.
RED_CLAIMS = {
    "Held-out test and unseen models reproduce frontier (r=0.96)",
    "Boundary confidence plus verification stays within about 1 pp",
    "Finding 3: accuracy tax survives any probing scheme",
    "Finding 4: DEER stays within about 1 pp",
    "Contribution: boundary confidence with verification escapes tax",
    "Current sweep adopts the same probe mechanism as CertaIndex",
    "Naive certain 3-probe stop loses 16.4 pp",
    "Later consensus is less trustworthy",
    "Best possible rule in a large space cannot be safe and economical",
    "Dense probing every 64 tokens with simple@32",
    "Confirmation reserves seeds 45/46/47 plus two unseen models",
    "Adaptive probing does not help",
    "Same structure holds on Qwen-32B and Llama-8B",
    "No probing scheme can remove the 1.85 pp tax",
    "Accuracy floor survives any probing scheme",
    "All baselines use the same simple@32 probe bank",
    "CertaIndex is a faithful share-threshold stop",
    "DEER is the lone near-full method",
    "Section title: A Signal That Works",
    "DEER confidence is mean answer-token probability",
    "Trial/readout disagree on 14.6%; readout averages 470 tokens",
    "Verification branch commits on equivalent second answer",
    "Inspired dominates online DEER",
    "Stepping outside consensus escapes the accuracy tax",
    "No threshold on consensus escapes the accuracy tax",
    "Boundary confidence with verification saves 34% near-neutral",
    "Confirmation validates frontier on seen and unseen models alike",
    "Consensus family answer is no",
    "Boundary confidence with verification stays near full and saves 34%",
    "Held-out scope and missing Llama AIME24",
    "Non-consensus signal escapes accuracy tax",
    "Certainty is mean answer-token probability",
    "simple@32 aggregates certainty over 32 samples",
}


# BLUE means plausible or useful, but a required experiment/audit/provenance
# item is missing.  It is not currently contradicted as strongly as RED.
BLUE_CLAIMS = {
    "Safe exit needs a forward-looking signal",
    "Much computation occurs after the answer is effectively decided",
    "Finding 4: the signal is the problem, not early exit",
    "Contribution: calibrated false-consensus taxonomy",
    "Contribution: release design and sweep artifacts",
    "Self-consistency stopping criteria do not transfer",
    "Among first preregistered early-exit evaluations",
    "Error taxonomy counts over 28 AI-assisted cases",
    "About one in five false consensuses is a probe-format artifact",
    "Per-model gate is primary; per-benchmark gate diagnostic",
    "Rare gains are small and do not concentrate",
    "Accuracy result is independent of probe density",
    "Main comparison of selected Governor operating points",
    "Pure sampling noise predicts 1:1",
    "Gross/net Table 5 quantifies the probe tax",
    "TJE is a token-level early-exit stop",
    "Consensus signal is the problem, not early exit",
    "Forward-looking confidence should replace agreement",
    "Sparser probing or KV reuse could recover positive net saving",
    "Practical takeaway: use forward-looking confidence",
    "Adaptive entropy trigger means model just committed",
    "Frozen artifacts and scripts are released",
    "Grader uses robust mathematical equivalence",
    "Grader measured error rate",
    "Additional figures and tables still to add",
}


REASON_OVERRIDES = {
    "Held-out test and unseen models reproduce frontier (r=0.96)":
        "A8 supports r=0.962 and the empty joint gate only on the same two valid models. "
        "A9 shows the Llama run is degenerate and cannot support architecture generalization.",
    "Boundary confidence plus verification stays within about 1 pp":
        "A10: frozen DEER is +0.78 pp on Qwen but -4.83 pp on DeepSeek. "
        "A13: the verification branch has zero net correction, so the branch cannot receive credit.",
    "Finding 3: accuracy tax survives any probing scheme":
        "A14-A15 support the decomposition inside frozen trajectories and reachable grid positions, "
        "not a universal claim over all online probing schemes.",
    "Finding 4: DEER stays within about 1 pp":
        "A10 reports +0.78 pp on Qwen and -4.83 pp on DeepSeek; the unqualified statement is false.",
    "Contribution: boundary confidence with verification escapes tax":
        "A13 directly rejects the verification attribution: 117/117 first branches hit the 64-token cap "
        "and removing the branch leaves macro accuracy unchanged while saving more tokens.",
    "Current sweep adopts the same probe mechanism as CertaIndex":
        "A10/A14: Governor simple@32 and faithful CertaIndex use different prompts and output caps; "
        "only the general answer-probing idea is shared.",
    "Naive certain 3-probe stop loses 16.4 pp":
        "The 16.4 pp pilot result is real, but its stated certainty definition is wrong. "
        "A14: Governor is_certain is a text uncertainty-marker filter, not answer-token probability.",
    "Later consensus is less trustworthy":
        "A3: absolute-token bins decline, but relative-position bins are non-monotone; "
        "difficulty/trajectory length confounds the broad claim.",
    "Best possible rule in a large space cannot be safe and economical":
        "A5-A6 only exclude the preregistered 17,712-rule schema. 'Best possible' over all rules is unsupported.",
    "Dense probing every 64 tokens with simple@32":
        "A14: simple@32 is one completion capped at 32 output tokens, not a 32-sample probe.",
    "Confirmation reserves seeds 45/46/47 plus two unseen models":
        "A9: seeds 45/46/47 apply to the seen models; Qwen-32B and Llama use seed 45 only, "
        "and the Llama run is invalid and missing AIME24.",
    "Adaptive probing does not help":
        "A6 supports only that the preregistered adaptive-event family is dominated within the current grid.",
    "Same structure holds on Qwen-32B and Llama-8B":
        "A9: Qwen-32B is valid single-seed scale evidence; Llama outputs degenerate text and cannot be used.",
    "No probing scheme can remove the 1.85 pp tax":
        "A5/A8: 1.85 pp is a dev point estimate (same rule 0.11 pp on test). "
        "A14-A15 do not cover every possible schedule or online controller.",
    "Accuracy floor survives any probing scheme":
        "A14-A15: the reachability argument is limited to frozen trajectories and the tested grid; "
        "online probes can alter generation.",
    "All baselines use the same simple@32 probe bank":
        "A10: all three baselines ran independent method-specific GPU probes. "
        "Only frozen trajectories, grader, and accounting harness are shared.",
    "CertaIndex is a faithful share-threshold stop":
        "A10: suffix and last-three stop logic are probe-level faithful, but timing is frozen; "
        "the implemented stop is not accurately summarized as a generic share threshold.",
    "DEER is the lone near-full method":
        "A10: DEER is near-neutral on Qwen but loses 4.83 pp on DeepSeek.",
    "Section title: A Signal That Works":
        "A12-A13/A15: results are dev-only, seed-sensitive, and the verification component is negative. "
        "Use 'A Promising Alternative Signal'.",
    "DEER confidence is mean answer-token probability":
        "A14: DeepSeek uses an arithmetic mean; Qwen uses a geometric mean and requires </think>.",
    "Trial/readout disagree on 14.6%; readout averages 470 tokens":
        "A11 audited 486 pairs: disagreement is 72/486 = 14.81%, and mean readout length is 470.5 tokens. "
        "Update the stale percentage.",
    "Verification branch commits on equivalent second answer":
        "The protocol description is factual, but its implied protective role is contradicted by A13: "
        "zero net correction, 69% branch-commit accuracy versus 78% matched full, all first branches capped.",
    "Inspired dominates online DEER":
        "A12-A13: environment-macro saving is higher, but problem-pooled saving is lower "
        "(36.26% vs 37.74%) and the accuracy difference is not significant.",
    "Stepping outside consensus escapes the accuracy tax":
        "A11-A13 provide exploratory evidence only; there is no test/new-model confirmation and the branch adds no protection.",
    "No threshold on consensus escapes the accuracy tax":
        "A5-A6 exclude thresholds in the searched schema, not every possible consensus controller.",
    "Boundary confidence with verification saves 34% near-neutral":
        "A12 supports the whole controller's dev environment-macro point; A13 shows the verification branch "
        "does not cause the benefit and the saving comparison is aggregation-dependent.",
    "Confirmation validates frontier on seen and unseen models alike":
        "A8 validates same-model dev-test stability. A9 permits only single-seed Qwen-32B scale evidence; "
        "Llama architecture evidence is invalid.",
    "Consensus family answer is no":
        "A5-A8 support 'no rule in our preregistered searched space', not a universal family-level impossibility.",
    "Boundary confidence with verification stays near full and saves 34%":
        "A12 is exploratory dev evidence; A13 rejects verification attribution; no held-out test exists.",
    "Held-out scope and missing Llama AIME24":
        "A9: the problem is not merely a weaker model failing to terminate. Existing Llama outputs are "
        "degenerate from the first tokens (98/108 length-stops, 95 empty answers, 1/108 correct).",
    "Non-consensus signal escapes accuracy tax":
        "A11-A13 support a promising dev signal, not confirmed escape across split/model/architecture.",
    "Certainty is mean answer-token probability":
        "A14: Governor simple@32 certainty is based on absence of uncertainty markers in probe text.",
    "simple@32 aggregates certainty over 32 samples":
        "A14: @32 denotes a maximum of 32 output tokens from one completion.",
    "Contribution: calibrated false-consensus taxonomy":
        "A4/A15: the 134-case double-human annotation and agreement/arbiter analysis are not yet returned.",
    "Error taxonomy counts over 28 AI-assisted cases":
        "A4: AI-assisted pilot labels are useful for interface design but are not reportable human results.",
    "About one in five false consensuses is a probe-format artifact":
        "A4: this is 6/28 AI-assisted pilot labels; human validation and uncertainty are missing.",
    "Main comparison of selected Governor operating points":
        "A6: the conservative gate is empty, so three operating points were not successfully frozen; "
        "the table also contains TBD cells.",
    "Three-seed online result: -0.75 pp, 34.2% saving":
        "A12: 36/36 run directories and 1,368/1,368 rows now pass a unified audit; "
        "retain the dev-only and seed-sensitive scope.",
    "Saving advantage +12.1% CI [+0.7,+22.9]":
        "A12-A13: supported under the explicitly stated 18-environment macro bootstrap; "
        "problem-pooled saving reverses, so the weighting must stay visible.",
    "Protocol and gates were fixed before held-out evaluation":
        "A5-A6/A14: split, gates, rule registry, hashes, and manifests are retained and auditable.",
    "Probe consensus is poorly calibrated where stopping acts":
        "A2 now supports this across 18 environments and windows 3/5/8, not only the original pilot.",
}


SECTION_EVIDENCE = {
    "Abstract": "A1-A15",
    "1 Introduction and stated contributions": "A1-A15",
    "2 Related Work": "A1-A3, A10, A15",
    "3 False Consensus Phenomenon": "A1-A4",
    "4 Preregistered Test": "A5-A6, A14",
    "5 Results: Searched-Space Negative Result": "A5-A6, A8-A9",
    "6 Mechanism: Accuracy Tax and Probe Tax": "A7, A14-A15",
    "7 Prior Early-Stoppers": "A10, A14",
    "8 Boundary-Confidence Early Exit": "A11-A13, A15",
    "9 Discussion": "A5-A15",
    "10 Conclusion": "A1-A15",
    "Limitations": "A4, A8-A15",
    "Appendix and reproducibility claims": "A5-A6, A14-A15",
}


EVIDENCE_OVERRIDES = {
    "Recent unanimous window: 93.5% correct": "A1-A2",
    "Naive consensus stop loses 16.4 pp": "A1-A3",
    "Preregistered 7-D search over 17,712 rules": "A5-A6",
    "No dev rule clears safety; dev floor is 1.85 pp": "A5, A8",
    "Held-out test and unseen models reproduce frontier (r=0.96)": "A8-A9",
    "CertaIndex reproduction collapses by 56-70 pp": "A10",
    "Online controller saves about 34% at near-neutral macro accuracy": "A12-A13",
    "Finding 1: local consensus is non-terminal": "A1-A3, A7",
    "Finding 2: no safe-and-saving rule in searched space": "A5-A8",
    "Finding 2: positive net saving costs at least 4.87 pp": "A5-A6, A14",
    "Finding 2: adaptive probing is dominated": "A6",
    "Finding 4: the signal is the problem, not early exit": "A10-A13, A15",
    "Recovery is intrinsic self-correction": "A3, A7",
    "Probe consensus is poorly calibrated where stopping acts": "A2",
    "Setup: DeepSeek-7B, MATH500, seed 42, cap 3072": "A1-A3 (pilot scope)",
    "Probe observes without altering the main trajectory": "A14",
    "Cumulative unanimous consensus: 98.9% correct (87 cases)": "A1-A2 (pilot scope)",
    "Last-five unanimous window: 93.5% correct (338 cases)": "A1-A2 (pilot scope)",
    "Local consensus is not a safe online signal": "A1-A3",
    "Naive certain 3-probe stop loses 16.4 pp": "A1-A3, A14",
    "Three-probe disagreements recover: 65.5%": "A3, A7 (pilot scope)",
    "Wrong first probes recover: 76.3%": "A3 (pilot scope)",
    "Later consensus is less trustworthy": "A3",
    "Window CCE is 0.080; cumulative CCE is 0.149": "A2 (pilot scope)",
    "Share 0.8 has 47.2% accuracy (n=36)": "A2 (pilot scope)",
    "Frozen trajectories make rules probe-independent": "A14",
    "Dense probing every 64 tokens with simple@32": "A14",
    "Seven rule dimensions yield 17,712 candidates": "A5-A6, A14",
    "Confirmation reserves seeds 45/46/47 plus two unseen models": "A9",
    "Sweep covers 637,632 rule-environment-split rows": "A5",
    "No rule clears the conservative dev gate": "A5",
    "Dev Pareto frontier has 93 rules; none admissible": "A5-A6",
    "Minimum worst-case per-model drop is 1.85 pp": "A5, A8",
    "Positive net saving requires at least 4.87 pp": "A5-A6, A14",
    "Adaptive probing does not help": "A6",
    "Dev-test frontier correlation is r=0.96": "A8",
    "No rule clears the conservative gate on both splits": "A8",
    "272 test-only winners fail dev": "A8",
    "Same structure holds on Qwen-32B and Llama-8B": "A9",
    "Direction ratio is 35:1 for naive consensus": "A7",
    "Conservative variants retain 15-18:1 direction ratio": "A7",
    "Dense probing turns safe-family net saving negative": "A5-A6, A14",
    "All baselines use the same simple@32 probe bank": "A10, A14",
    "Baseline results are frozen reproductions, not original end-to-end": "A10",
    "CertaIndex loses 56-70 pp while saving 77-90%": "A10",
    "DEER: +0.8 pp Qwen, -4.8 pp DeepSeek": "A10",
    "Figure 1 uses all-generated-token saving": "A10, A14",
    "Trial/readout disagree on 14.6%; readout averages 470 tokens": "A11",
    "Readout gives no net accuracy gain": "A11",
    "Fast commit at confidence above 0.995": "A11",
    "Verification branch commits on equivalent second answer": "A13",
    "Three-seed online result: -0.75 pp, 34.2% saving": "A12",
    "Inspired dominates online DEER": "A12-A13",
    "Saving advantage +12.1% CI [+0.7,+22.9]": "A12-A13",
    "Controller is a positive signal, not a finished method": "A12-A15",
    "Held-out scope and missing Llama AIME24": "A9",
    "Exact 1.85 pp floor is not split-invariant": "A5, A8",
    "Boundary-confidence result is exploratory and approximate": "A12-A15",
    "Certainty is mean answer-token probability": "A14",
    "simple@32 aggregates certainty over 32 samples": "A14",
    "Grader measured error rate": "A15",
}


def status_for(title: str) -> str:
    if title in RED_CLAIMS:
        return "RED"
    if title in BLUE_CLAIMS:
        return "BLUE"
    return "GREEN"


def evidence_for(section: str, title: str) -> str:
    return EVIDENCE_OVERRIDES.get(title, SECTION_EVIDENCE.get(section, "A15"))


def strip_priority(comment: str | None) -> str:
    if not comment:
        return ""
    return re.sub(r"^\[CHECK-(?:HIGH|MED|LOW)\]\s*", "", comment).strip()


def message_for(
    section: str,
    title: str,
    status: str,
    original_comment: str | None,
) -> str:
    evidence = evidence_for(section, title)
    reason = REASON_OVERRIDES.get(title)
    if reason is None:
        old = strip_priority(original_comment)
        if status == "GREEN":
            reason = (
                "Supported by the current audited artifacts within the wording's stated "
                "model/benchmark/split/accounting scope."
            )
            if old:
                reason += " Scope note: " + old
        elif status == "BLUE":
            reason = old or "A required experiment, audit, or immutable provenance check is still missing."
        else:
            reason = old or "Current evidence contradicts or materially undercuts this wording."
    return f"[{status} | Evidence: {evidence}] {reason}"


def claim_inventory() -> list[tuple[str, int, str, str, str | None]]:
    rows: list[tuple[str, int, str, str, str | None]] = []
    for section, _, _, claims in SECTIONS:
        if section == "CLAIM REVIEW GUIDE":
            continue
        for title, page, anchor, comment in claims:
            rows.append((section, page, anchor, title, comment))
    return rows


def available_note_y(
    requested: float,
    used: list[float],
    page_height: float,
) -> float:
    y = min(max(requested, 28.0), page_height - 28.0)
    while any(abs(y - previous) < 15.0 for previous in used):
        y += 15.0
        if y > page_height - 28.0:
            y = max(28.0, min(used, default=43.0) - 15.0)
    used.append(y)
    return y


def add_cover(document: fitz.Document, counts: Counter[str]) -> None:
    source_page = document[1]
    page = document[0]
    page_width = source_page.rect.width
    page_height = source_page.rect.height
    if page.rect.width != page_width or page.rect.height != page_height:
        page.set_mediabox(fitz.Rect(0, 0, page_width, page_height))

    page.insert_text(
        (54, 78),
        "Governor Claim-to-Evidence Color Audit",
        fontsize=21,
        fontname="helv",
        color=(0.08, 0.12, 0.20),
    )
    page.insert_text(
        (54, 106),
        "Current ACL draft - evidence state after interrogation batches 001-005",
        fontsize=10.5,
        fontname="helv",
        color=(0.30, 0.34, 0.40),
    )
    page.draw_line((54, 124), (page_width - 54, 124), color=(0.75, 0.78, 0.82), width=1)

    legend = [
        (
            "GREEN",
            "Supported in the stated scope. The popup comment points to the supporting Appendix item.",
        ),
        (
            "BLUE",
            "Not yet verified. The popup comment states the experiment, audit, or provenance still needed.",
        ),
        (
            "RED",
            "Contradicted, factually wrong, attribution-changing, or materially broader than current evidence.",
        ),
    ]
    y = 170
    for status, description in legend:
        color = COLORS[status]
        page.draw_rect(fitz.Rect(56, y - 14, 78, y + 8), color=color, fill=color)
        page.insert_text(
            (92, y + 2),
            f"{status}  ({counts[status]} claims)",
            fontsize=12,
            fontname="hebo",
            color=color,
        )
        page.insert_textbox(
            fitz.Rect(92, y + 13, page_width - 58, y + 59),
            description,
            fontsize=10,
            fontname="helv",
            color=(0.15, 0.18, 0.23),
            lineheight=1.3,
        )
        y += 104

    page.insert_textbox(
        fitz.Rect(54, y + 4, page_width - 54, y + 112),
        (
            "How to review\n"
            "Every material claim in the 14-page draft has a colored highlight and a closed "
            "comment icon. Open a comment to see the evidence pointer and the exact support, "
            "missing experiment, or conflict. The outline lists every claim with the same "
            "status. Green is not universal truth: it means the wording is defensible only "
            "within the scope stated in the paper and comment."
        ),
        fontsize=10.5,
        fontname="helv",
        color=(0.15, 0.18, 0.23),
        lineheight=1.35,
    )
    page.insert_text(
        (54, page_height - 52),
        "Generated 2026-07-29 | Source PDF preserved unchanged",
        fontsize=8.5,
        fontname="helv",
        color=(0.42, 0.45, 0.50),
    )


def build_output() -> tuple[Counter[str], int]:
    source = fitz.open(SOURCE)
    if source.page_count != 14:
        raise RuntimeError(f"Expected 14 source pages, got {source.page_count}")

    inventory = claim_inventory()
    statuses = Counter(status_for(title) for _, _, _, title, _ in inventory)
    if len(inventory) != 130:
        raise RuntimeError(f"Expected 130 material claims, got {len(inventory)}")
    if RED_CLAIMS & BLUE_CLAIMS:
        raise RuntimeError(f"Conflicting status assignments: {RED_CLAIMS & BLUE_CLAIMS}")

    output = fitz.open()
    first = source[0]
    output.new_page(width=first.rect.width, height=first.rect.height)
    output.insert_pdf(source)
    add_cover(output, statuses)

    used_note_y: dict[int, list[float]] = {}
    toc: list[list[object]] = [
        [1, "CLAIM COLOR AUDIT GUIDE", 1, 40.0],
    ]
    annotated = 0

    for section, original_section_page, section_anchor, claims in SECTIONS:
        if section == "CLAIM REVIEW GUIDE":
            continue
        pdf_section_page = original_section_page + 1
        section_matches = output[pdf_section_page - 1].search_for(section_anchor)
        section_top = max(0.0, section_matches[0].y0 - 18.0) if section_matches else 24.0
        toc.append([1, section, pdf_section_page, section_top])

        for title, original_page, anchor, original_comment in claims:
            page_number = original_page + 1
            page = output[page_number - 1]
            matches = page.search_for(anchor)
            if not matches:
                raise RuntimeError(
                    f"Cannot match claim anchor on source page {original_page}: "
                    f"{title!r} / {anchor!r}"
                )
            target = matches[0]
            status = status_for(title)
            color = COLORS[status]
            message = message_for(section, title, status, original_comment)

            highlight = page.add_highlight_annot(target)
            highlight.set_info(
                title=f"{status}: {title}",
                subject=f"{status} claim evidence",
                content=message,
            )
            highlight.set_colors(stroke=color)
            highlight.set_opacity(0.28 if status == "GREEN" else 0.34)
            highlight.update()

            used = used_note_y.setdefault(page_number, [])
            note_y = available_note_y(target.y0, used, page.rect.height)
            note = page.add_text_annot(
                (page.rect.width - 23.0, note_y),
                message,
                icon="Comment",
            )
            note.set_info(
                title=title,
                subject=f"{status} claim evidence",
                content=message,
            )
            note.set_colors(stroke=color)
            note.set_open(False)
            note.update()

            toc.append(
                [
                    2,
                    f"{status} | {title}",
                    page_number,
                    max(0.0, float(target.y0) - 18.0),
                ]
            )
            annotated += 1

    output.set_toc(toc, collapse=1)
    metadata = dict(output.metadata)
    metadata.update(
        {
            "title": "Governor ACL Draft - Claim Evidence Color Audit",
            "subject": (
                f"130 claims: {statuses['GREEN']} green, "
                f"{statuses['BLUE']} blue, {statuses['RED']} red"
            ),
            "keywords": "Governor,false consensus,claim audit,evidence",
        }
    )
    output.set_metadata(metadata)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output.save(OUTPUT, garbage=4, deflate=True, clean=True)
    output.close()
    source.close()
    return statuses, annotated


def validate_output(expected: Counter[str], expected_annotations: int) -> None:
    document = fitz.open(OUTPUT)
    if document.page_count != 15:
        raise RuntimeError(f"Expected cover + 14 paper pages, got {document.page_count}")

    status_subjects: Counter[str] = Counter()
    highlights = notes = 0
    for page in document:
        annot = page.first_annot
        while annot:
            subject = str(annot.info.get("subject", ""))
            if subject.endswith("claim evidence"):
                status_subjects[subject.split()[0]] += 1
            if annot.type[1] == "Highlight":
                highlights += 1
            elif annot.type[1] == "Text":
                notes += 1
            annot = annot.next

    # Every claim has one highlight and one popup note.  Status subjects count
    # both annotations, hence twice the claim inventory.
    if highlights != expected_annotations or notes != expected_annotations:
        raise RuntimeError(
            f"Annotation mismatch: highlights={highlights}, notes={notes}, "
            f"expected={expected_annotations}"
        )
    for status, count in expected.items():
        if status_subjects[status] != 2 * count:
            raise RuntimeError(
                f"{status} annotation count {status_subjects[status]} != {2 * count}"
            )
    document.close()


def main() -> None:
    statuses, annotated = build_output()
    validate_output(statuses, annotated)
    print(
        f"Wrote {OUTPUT} with {annotated} claims: "
        f"GREEN={statuses['GREEN']}, BLUE={statuses['BLUE']}, RED={statuses['RED']}"
    )


if __name__ == "__main__":
    main()
