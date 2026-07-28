#!/usr/bin/env python3
"""Hardened smoke audit (corrected). Fails on any of:
  * CertaIndex suffix not the faithful (preamble) suffix, or == SIMPLE_SUFFIX;
    probe errors; material token misalignment; missing manifest; manifest
    model_revision not the pinned 40-hex; probe_finish_reason absent.
  * TJE: system_prompt_sha256 absent from manifest or != sha(TJE_SYSTEM_PROMPT);
    any collected label outside the ten official classes; the ten labels don't
    parse; confidence_finish_reason / readout_finish_reason absent; a readout
    that is present but invalid-with-stray-answer; rendered system-role has a
    duplicate BOS or mland boundary.
  * DEER: confidence recomputed from stored logprobs != stored; Qwen3 gate
    violated (conf>0 but last token != 皖think/  OR  last != 皖think/ but conf!=0);
    trial_finish_reason absent; readout validity not enforced.
  * Reproducibility: canonical projection not equal across the same-seed rerun.
  * Near-max probes: any status!=ok, prompt_tokens < 95% of trajectory, missing
    finish_reason; DEER logprobs absent / hand-check mismatch; Qwen 皖think/ gate.
  * Any endpoint error in any record; any manifest model_revision wrong.

Writes smoke_audit.json + smoke_audit.md. Run with the conda env (so tokenizers
are available for the rendered-role evidence).
"""
import json, sys, glob
from pathlib import Path

REPO = Path("/localdata/dzhaoah/Governor")
sys.path.insert(0, str(REPO))
from benchmark.FalseConsensus.related_work import common, certaindex_mid, tje, deer  # noqa
from benchmark.FalseConsensus.related_work import predicates  # noqa

RT = REPO / "benchmark/FalseConsensus/results/related_work/_runtime"
SMOKE = RT / "smoke"
SIMPLE_SHA = common.sha256_bytes(common.SIMPLE_SUFFIX.encode())
FAITHFUL_SHA = common.sha256_bytes(common.CERTAINDEX_SUFFIX.encode())
THINK = common.DEER_THINK_CLOSE
LABELS = [n for n, _l, _h in common.TJE_CONFIDENCE_LABELS]
REVISIONS = {
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
    "Qwen/Qwen3-8B": "b968826d9c46dd6066d109eabc6255188de91218",
}


def load(p):
    return json.load(open(p))


def model_of(case_dir):
    name = case_dir.name
    return "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" if name.startswith("deepseek") else "Qwen/Qwen3-8B"


def audit_certaindex(cases):
    checks = []
    ok = True
    for case_dir in sorted(SMOKE.glob("*__certaindex_mid")):
        if case_dir.name.endswith("_dup"):
            continue
        man = load(case_dir / "probe_manifest.json")
        ps = man["probe_settings"]
        mid = model_of(case_dir)
        suffix_ok = ps["probe_suffix_sha256"] == FAITHFUL_SHA and ps["probe_suffix_sha256"] != SIMPLE_SHA
        rev_ok = ps.get("model_revision") == REVISIONS[mid]
        probs = sorted((case_dir / "probes").glob("problem_*.json"))
        d = load(probs[0])
        recs = d["probes"]
        fr_ok = all("probe_finish_reason" in r for r in recs)
        errors = [r for r in recs if r.get("error")]
        mat = d.get("token_alignment", {}).get("material_mismatch", True)
        c = {"case": case_dir.name, "suffix_faithful": suffix_ok, "model_revision_pinned": rev_ok,
             "probe_finish_reason_recorded": fr_ok, "n_probes": len(recs), "probe_errors": len(errors),
             "token_alignment_material_mismatch": mat, "manifest_present": True,
             "pass": suffix_ok and rev_ok and fr_ok and not errors and not mat}
        if not c["pass"]:
            ok = False
        checks.append(c)
    return {"method": "certaindex_mid", "checks": checks, "pass": ok}


def audit_tje(cases, repro):
    checks = []
    ok = True
    readout_valid_count = 0
    readout_invalid_or_truncated = 0
    sys_prompt_sha = common.sha256_bytes(common.TJE_SYSTEM_PROMPT.encode())
    rendered_evidence = {}
    for case_dir in sorted(SMOKE.glob("*__tje")):
        man = load(case_dir / "trigger_manifest.json")
        ps = man["trigger_settings"]
        mid = model_of(case_dir)
        sha_in = ps.get("system_prompt_sha256") == sys_prompt_sha
        rev_ok = ps.get("model_revision") == REVISIONS[mid]
        trigs = sorted((case_dir / "triggers").glob("problem_*.json"))
        d = load(trigs[0]); recs = d["triggers"]
        labels = [t.get("confidence_label") for t in recs]
        labels_in_set = all(l is None or l in LABELS for l in labels)
        all_parse = all(tje.parse_confidence_response(n) == n for n in LABELS)
        fr_conf = all("confidence_finish_reason" in t for t in recs)
        ro = d.get("readout")
        # Every TRIGGERED readout must be completed and task-valid (no overflow,
        # no truncation, completed boxed, non-empty, non-null non-length finish).
        readout_ok = (ro is None) or common.readout_is_valid(ro)
        readout_overflow = bool(ro and ro.get("readout_context_overflow"))
        # per-case 0/1 flag (no cumulative leak across cases)
        case_invalid = 0
        if ro is not None and not common.readout_is_valid(ro):
            case_invalid = 1
            readout_invalid_or_truncated += 1
        if ro is not None and ro.get("readout_valid") is True and not readout_overflow:
            readout_valid_count += 1
        mat = d.get("token_alignment", {}).get("material_mismatch", True)
        is_aime_ds = (case_dir.name == "deepseek__aime24__tje")
        c = {"case": case_dir.name, "system_prompt_sha_matches": sha_in, "model_revision_pinned": rev_ok,
             "all_ten_labels_parse": all_parse, "labels_in_official_set": labels_in_set,
             "confidence_finish_reason_recorded": fr_conf, "readout_validity_enforced": readout_ok,
             "readout_context_overflow": readout_overflow,
             "n_triggers": len(recs), "labels": labels, "readout_present": bool(ro),
             "readout_valid": (ro or {}).get("readout_valid"),
             "readout_truncated": (ro or {}).get("readout_truncated"),
             "readout_completed_boxed": (ro or {}).get("readout_completed_boxed"),
             "readout_finish_reason": (ro or {}).get("readout_finish_reason"),
             "readout_invalid_or_truncated_case": case_invalid,
             "deepseek_aime24_valid_readout_asserted": (not is_aime_ds) or (bool(ro) and common.readout_is_valid(ro)),
             "token_alignment_material_mismatch": mat,
             "pass": (sha_in and rev_ok and all_parse and labels_in_set and fr_conf
                      and readout_ok and not readout_overflow and not mat
                      and (not is_aime_ds or (bool(ro) and common.readout_is_valid(ro))))}
        if not c["pass"]:
            ok = False
        checks.append(c)
    # rendered-role evidence for both tokenizers (no duplicate BOS / mland boundary)
    try:
        from benchmark.FalseConsensus.related_work import common as _c
        for mid, rev in REVISIONS.items():
            tok = _c.load_tokenizer(mid, rev)
            rendered = tje.build_system_chat(tok, "PROBLEM")
            bos = str(getattr(tok, "bos_token", "") or "")
            no_dup_bos = not (bos and rendered.count(bos) >= 2)
            no_dup_think = not rendered.endswith(THINK + "\n")
            rendered_evidence[mid] = {"no_duplicate_bos": no_dup_bos, "no_trailing_think_boundary": no_dup_think,
                                      "rendered_sha256": _c.sha256_bytes(rendered.encode()), "head": rendered[:80]}
            if not (no_dup_bos and no_dup_think):
                ok = False
    except Exception as e:
        rendered_evidence = {"error": "tokenizer unavailable: " + str(e)}
        ok = False
    return {"method": "tje", "checks": checks, "rendered_role_evidence": rendered_evidence,
            "any_readout_valid": readout_valid_count > 0, "pass": ok and readout_valid_count > 0}


def audit_deer(cases):
    checks = []
    ok = True
    for case_dir in sorted(SMOKE.glob("*__deer")):
        man = load(case_dir / "trial_manifest.json")
        ps = man["trial_settings"]
        mid = model_of(case_dir)
        rev_ok = ps.get("model_revision") == REVISIONS[mid]
        trials = sorted((case_dir / "trials").glob("problem_*.json"))
        d = load(trials[0]); recs = d["trials"]
        policy = d["policy"]; rtc = d["require_think_close"]
        hand = []
        gate_ok = True
        fr_ok = True
        for t in recs:
            lp = t.get("logprobs", [])
            if not lp:
                continue
            recomputed = deer.calculate_confidence(
                [(e["token"], e["logprob"]) for e in lp if e.get("logprob") is not None],
                policy=policy, require_think_close=rtc)
            match = abs(recomputed - t["confidence"]) < 1e-6
            if "trial_finish_reason" not in t:
                fr_ok = False
            last = t.get("last_token_decoded")
            if rtc:
                # EXACT Qwen3 gate (iff): (last==THINK and conf>0) or (last!=THINK and conf==0.0)
                gate_ok = gate_ok and (
                    (last == THINK and t["confidence"] > 0) or
                    (last != THINK and t["confidence"] == 0.0))
            hand.append({"candidate": t["candidate_id"], "match": match,
                          "stored": round(t["confidence"], 6), "recomputed": round(recomputed, 6),
                          "last_token": last})
        all_match = all(h["match"] for h in hand)
        ro = d.get("readout")
        readout_ok = True
        if ro is not None:
            stray = (ro.get("readout_valid") is False and ro.get("readout_answer") not in ("", None))
            readout_ok = "readout_finish_reason" in ro and "readout_valid" in ro and not stray
        mat = d.get("token_alignment", {}).get("material_mismatch", True)
        errors = [t for t in recs if t.get("error")]
        c = {"case": case_dir.name, "model_revision_pinned": rev_ok,
             "confidence_recomputed_matches": all_match, "qwen3_gate_ok": gate_ok if rtc else None,
             "trial_finish_reason_recorded": fr_ok, "readout_validity_enforced": readout_ok,
             "policy": policy, "n_trials": len(recs), "n_hand_checked": len(hand),
             "trial_errors": len(errors), "token_alignment_material_mismatch": mat,
             "readout_present": bool(ro), "pass": rev_ok and all_match and gate_ok and fr_ok and readout_ok and not mat and not errors}
        if not c["pass"]:
            ok = False
        checks.append(c)
    return {"method": "deer", "checks": checks, "pass": ok}


def audit_near_max(nmp):
    # Uses the shared, tested predicate so the audit cannot drift from the
    # regression-tested logic.
    checks = [predicates.near_max_probe_detail(r) for r in nmp]
    ok = all(c["pass"] for c in checks)
    return {"near_max_probes": checks, "pass": ok}


def main():
    data = json.load(open(RT / "smoke_cases.json"))
    cases = data["cases"]
    repro = data["reproducibility"]
    nmp = data["near_max_probes"]
    ac = audit_certaindex(cases)
    at = audit_tje(cases, repro)
    ad = audit_deer(cases)
    an = audit_near_max(nmp)
    # endpoint errors in any record
    any_err = False
    for case_dir in SMOKE.glob("*"):
        for f in list(case_dir.glob("*/problem_*.json")):
            d = load(f)
            for k in ("probes", "trials", "triggers"):
                for r in (d.get(k) or []):
                    if r.get("error"):
                        any_err = True
            if isinstance(d.get("readout"), dict) and "error" in d["readout"]:
                any_err = True
    rep_ok = bool(repro.get("canonical_equal"))
    overall = (ac["pass"] and at["pass"] and ad["pass"] and an["pass"] and rep_ok and not any_err)
    audit = {"certaindex": ac, "tje": at, "deer": ad, "near_max": an,
             "reproducibility": repro, "endpoint_errors_any": any_err,
             "overall_pass": overall}
    (RT / "smoke_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    lines = ["# Smoke audit (corrected)", "", f"**Overall: {'PASS' if overall else 'FAIL'}**", ""]
    for m in ("certaindex", "tje", "deer"):
        a = audit[m]
        lines.append(f"## {m} — {'PASS' if a['pass'] else 'FAIL'}")
        for c in a["checks"]:
            lines.append(f"- {c['case']}: {'pass' if c.get('pass') else 'FAIL'} { {k:v for k,v in c.items() if k not in ('hand_checks',)} }")
        if m == "tje":
            lines.append(f"- rendered_role_evidence: {a.get('rendered_role_evidence')}")
            lines.append(f"- any_readout_valid: {a.get('any_readout_valid')}")
    lines.append(f"\n## near-max probes — {'PASS' if an['pass'] else 'FAIL'}")
    for c in an["near_max_probes"]:
        lines.append(f"- {c['model']}/{c['method']}: {'pass' if c.get('pass') else 'FAIL'} { {k:v for k,v in c.items() if k!='pass'} }")
    lines.append(f"\nreproducibility canonical_equal: {rep_ok} (raw_byte_equal={repro.get('raw_byte_equal')}; {repro.get('raw_diff_reason','')})")
    lines.append(f"endpoint errors any: {any_err}")
    (RT / "smoke_audit.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"overall_pass": overall, "certaindex": ac["pass"], "tje": at["pass"],
                      "deer": ad["pass"], "near_max": an["pass"], "reproducibility": rep_ok,
                      "endpoint_errors_any": any_err}, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
