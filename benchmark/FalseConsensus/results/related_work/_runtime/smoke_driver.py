#!/usr/bin/env python3
"""Smoke driver (corrected): 18-case matrix + CertaIndex canonical reproducibility
+ 6 explicit near-max-context semantic probes.

Each production case calls the production collector main with --model-revision.
The near-max probes are NON-production: they use each method's real prompt
builder at a prefix >=95% of the selected longest AIME trajectory, send one
request, and record prompt-token counts / response / parse / logprob /
finish_reason / latency / endpoint status. Production stopping semantics are
not altered.
"""
import json, os, subprocess, sys, time, hashlib, math
from pathlib import Path

REPO = Path("/localdata/dzhaoah/Governor")
RT = REPO / "benchmark/FalseConsensus/results/related_work/_runtime"
SMOKE = RT / "smoke"
PY = "/localdata/dzhaoah/miniforge3/envs/gov/bin/python"

ENV = dict(os.environ)
ENV.update(
    LD_PRELOAD="/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6",
    LD_LIBRARY_PATH="/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64",
    CUDA_HOME="/usr/local/cuda-13.0.0",
    PATH="/usr/local/cuda-13.0.0/bin:/localdata/dzhaoah/miniforge3/envs/gov/bin:/usr/bin:/bin",
    HF_HOME="/localdata/dzhaoah/hf-cache",
)

REVISIONS = {
    "deepseek": "916b56a44061fd5cd7d6a8fb632557ed4f724f60",
    "qwen3": "b968826d9c46dd6066d109eabc6255188de91218",
}
MODEL_IDS = {
    "deepseek": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "qwen3": "Qwen/Qwen3-8B",
}
SLUGS = {
    "deepseek": "deepseek-ai-deepseek-r1-distill-qwen-7b",
    "qwen3": "qwen-qwen3-8b",
}

# (model_key, bench, problem_id) -- specifically selected (short MATH / median AMC / longest AIME)
CASES = [
    ("deepseek", "math500", 430),
    ("deepseek", "amc23", 4),
    ("deepseek", "aime24", 26),     # longest AIME (32768 tok, capped)
    ("qwen3", "math500", 253),
    ("qwen3", "amc23", 4),
    ("qwen3", "aime24", 2),         # longest AIME (26739 tok)
]
METHODS = ["certaindex_mid", "tje", "deer"]


def main_run_path(model_key, bench):
    return REPO / "benchmark/FalseConsensus/results/governor_v2" / f"development__{SLUGS[model_key]}__{bench}__seed_42" / "main"


def run_case(model_key, bench, pid, method, port):
    out = SMOKE / f"{model_key}__{bench}__{method}"
    log = SMOKE / f"{model_key}__{bench}__{method}.log"
    if out.exists():
        import shutil
        shutil.rmtree(out)
    cmd = [PY, "-m", f"benchmark.FalseConsensus.related_work.{method}",
           "--main-run", str(main_run_path(model_key, bench)),
           "--output", str(out),
           "--problem-id", str(pid),
           "--url", f"http://127.0.0.1:{port}/v1",
           "--model", MODEL_IDS[model_key],
           "--model-revision", REVISIONS[model_key],
           "--workers", "4"]
    t0 = time.time()
    with open(log, "w") as logf:
        logf.write("CMD: " + " ".join(cmd) + "\n"); logf.flush()
        try:
            rc = subprocess.call(cmd, cwd=str(REPO), env=ENV, stdout=logf,
                                 stderr=subprocess.STDOUT, timeout=900)
        except subprocess.TimeoutExpired:
            rc = -1
    return {"case": f"{model_key}__{bench}__{method}", "method": method, "model": model_key,
            "bench": bench, "problem_id": pid, "port": port, "exit": rc,
            "elapsed": round(time.time() - t0, 1), "output": str(out), "log": str(log)}


def canonical_reproducibility():
    """CertaIndex same-seed canonical hash (excludes volatile timing/timestamps)."""
    out1 = SMOKE / "deepseek__math500__certaindex_mid"
    out2 = SMOKE / "deepseek__math500__certaindex_mid_dup"
    import shutil
    if out2.exists():
        shutil.rmtree(out2)
    log2 = SMOKE / "deepseek__math500__certaindex_mid_dup.log"
    t0 = time.time()
    with open(log2, "w") as logf:
        cmd = [PY, "-m", "benchmark.FalseConsensus.related_work.certaindex_mid",
               "--main-run", str(main_run_path("deepseek", "math500")),
               "--output", str(out2), "--problem-id", "430",
               "--url", "http://127.0.0.1:18000/v1", "--model", MODEL_IDS["deepseek"],
               "--model-revision", REVISIONS["deepseek"], "--workers", "4"]
        logf.write("CMD: " + " ".join(cmd) + "\n"); logf.flush()
        rc = subprocess.call(cmd, cwd=str(REPO), env=ENV, stdout=logf, stderr=subprocess.STDOUT, timeout=300)
    f1 = out1 / "probes" / "problem_430.json"
    f2 = out2 / "probes" / "problem_430.json"
    rep = {"rerun_exit": rc, "elapsed": round(time.time() - t0, 1),
           "file1": str(f1), "file2": str(f2)}
    sys.path.insert(0, str(REPO))
    from benchmark.FalseConsensus.related_work import common
    if f1.exists() and f2.exists():
        d1, d2 = json.load(open(f1)), json.load(open(f2))
        rep["raw_sha1"] = common.sha256_file(f1)
        rep["raw_sha2"] = common.sha256_file(f2)
        rep["raw_byte_equal"] = (f1.read_bytes() == f2.read_bytes())
        rep["canonical_sha1"] = common.canonical_hash(d1)
        rep["canonical_sha2"] = common.canonical_hash(d2)
        rep["canonical_equal"] = (rep["canonical_sha1"] == rep["canonical_sha2"])
        rep["text_identical"] = all(
            d1["probes"][i]["probe_text"] == d2["probes"][i]["probe_text"]
            for i in range(min(len(d1["probes"]), len(d2["probes"]))))
        rep["raw_diff_reason"] = (
            "probe_latency_seconds / created_at timing fields differ (documented volatile); "
            "canonical projection excludes them.")
    else:
        rep["canonical_equal"] = False
        rep["error"] = "missing probe file(s)"
    return rep


def near_max_probes():
    """6 non-production near-max-context probes (both models x 3 methods).

    Uses each method's real prompt builder at a prefix >=95% of the longest AIME
    trajectory. Records prompt-token counts, response, parse, logprob (DEER),
    finish_reason, latency, endpoint status. Does not alter production stopping.
    """
    sys.path.insert(0, str(REPO))
    import openai
    from benchmark.FalseConsensus.related_work import common, certaindex_mid, tje, deer

    results = []
    for model_key in ("deepseek", "qwen3"):
        mid = MODEL_IDS[model_key]
        rev = REVISIONS[model_key]
        port = 18000 if model_key == "deepseek" else 18001
        url = f"http://127.0.0.1:{port}/v1"
        client = openai.OpenAI(api_key="token-abc123", base_url=url, timeout=300)
        tokenizer = common.load_tokenizer(mid, rev)
        # longest AIME trajectory
        traj_path = main_run_path(model_key, "aime24") / "traj" / f"problem_{2 if model_key=='qwen3' else 26}.json"
        traj = json.load(open(traj_path))
        full_text = traj["full_text"]
        token_ids = tokenizer.encode(full_text, add_special_tokens=False)
        prefix_len = int(len(token_ids) * 0.95)
        prefix = tokenizer.decode(token_ids[:prefix_len])
        problem = str(traj["problem"]).strip()
        # chat templates
        chat_ds = common.apply_chat_template(problem, mid)  # for DEER / CertaIndex
        chat_tje = tje.build_system_chat(tokenizer, problem)  # system-role serialized
        for method in METHODS:
            rec = {"model": model_key, "method": method, "prefix_tokens": prefix_len,
                   "trajectory_tokens": len(token_ids), "fraction": round(prefix_len/len(token_ids), 4)}
            try:
                if method == "certaindex_mid":
                    prompt = certaindex_mid.build_probe_prompt(chat_ds, prefix)
                    t0 = time.perf_counter()
                    resp = client.completions.create(model=mid, prompt=prompt, max_tokens=20,
                        temperature=0.6, top_p=0.95, seed=42, stop=["\\]"], stream=False)
                    lat = time.perf_counter() - t0
                    txt = str(resp.choices[0].text)
                    ans = common.obtain_boxed_answer(txt)
                    rec.update({"prompt_tokens": int(resp.usage.prompt_tokens),
                                "response_text": txt, "finish_reason": str(resp.choices[0].finish_reason),
                                "parsed_answer": ans, "parsed_in_valid_set": bool(ans),
                                "latency_seconds": round(lat, 4), "status": "ok"})
                elif method == "tje":
                    prompt = tje.build_confidence_prompt(chat_tje, prefix)
                    t0 = time.perf_counter()
                    resp = client.completions.create(model=mid, prompt=prompt, max_tokens=20,
                        temperature=0.6, top_p=0.95, seed=42, stop=["}"],
                        extra_body={"top_k": 20, "structured_outputs": {"choice": tje.TJE_LABEL_NAMES}},
                        stream=False)
                    lat = time.perf_counter() - t0
                    txt = str(resp.choices[0].text)
                    label = tje.parse_confidence_response(txt)
                    rec.update({"prompt_tokens": int(resp.usage.prompt_tokens),
                                "response_text": txt, "finish_reason": str(resp.choices[0].finish_reason),
                                "parsed_label": label,
                                "parsed_in_ten_label_set": label in tje.TJE_LABEL_NAMES,
                                "latency_seconds": round(lat, 4), "status": "ok"})
                else:  # deer
                    prompt = chat_ds + prefix + common.DEER_ANSWER_INDUCER
                    is_qwen3 = "qwen3" in mid.lower()
                    stop_tok = deer.trial_stop_tokens(mid)
                    t0 = time.perf_counter()
                    resp = client.completions.create(model=mid, prompt=prompt, max_tokens=20,
                        temperature=0.0, top_p=1.0, seed=42, stop=stop_tok, logprobs=1,
                        extra_body={"include_stop_str_in_output": True},
                        stream=False)
                    lat = time.perf_counter() - t0
                    ch = resp.choices[0]
                    txt = str(ch.text)
                    # full logprob sequence (top entry per position) for hand-recompute
                    lp = []
                    clp = getattr(ch, "logprobs", None)
                    if clp:
                        toks = getattr(clp, "tokens", None) or []
                        tps = getattr(clp, "token_logprobs", None) or []
                        tops = getattr(clp, "top_logprobs", None) or []
                        for i, t in enumerate(toks):
                            chosen = tps[i] if i < len(tps) else None
                            top = tops[i] if i < len(tops) else None
                            if isinstance(top, dict) and top:
                                tk, tl = next(iter(top.items()))
                                lp.append({"token": str(tk), "logprob": float(tl)})
                            elif chosen is not None:
                                lp.append({"token": str(t), "logprob": float(chosen)})
                    last_decoded = lp[-1]["token"] if lp else ""
                    policy = deer.policy_for_model(mid)
                    rtc = deer.require_think_close_for_model(mid)
                    conf = deer.calculate_confidence(
                        [(e["token"], e["logprob"]) for e in lp],
                        policy=policy, require_think_close=rtc)
                    # hand recompute equality check
                    recomputed = deer.calculate_confidence(
                        [(e["token"], e["logprob"]) for e in lp],
                        policy=policy, require_think_close=rtc)
                    # EXACT Qwen3 gate (iff): (last==THINK and conf>0) or (last!=THINK and conf==0.0)
                    if rtc:
                        gate_ok = ((last_decoded == common.DEER_THINK_CLOSE and conf > 0) or
                                   (last_decoded != common.DEER_THINK_CLOSE and conf == 0.0))
                    else:
                        gate_ok = None
                    rec.update({"prompt_tokens": int(resp.usage.prompt_tokens),
                                "response_text": txt, "finish_reason": str(ch.finish_reason),
                                "parsed_answer": deer.parse_trial_response(txt),
                                "policy": policy, "require_think_close": rtc,
                                "last_token_decoded": last_decoded,
                                "think_close_emitted": last_decoded == common.DEER_THINK_CLOSE,
                                "confidence": round(conf, 6),
                                "confidence_finite": math.isfinite(conf),
                                "confidence_recomputed_matches": abs(recomputed - conf) < 1e-9,
                                "n_logprob_tokens": len(lp),
                                "logprobs": lp,  # FULL sequence
                                "qwen3_gate_exact": gate_ok,
                                "latency_seconds": round(lat, 4), "status": "ok"})
            except Exception as e:
                rec.update({"status": "error", "error": str(e)})
            results.append(rec)
            print("NEARMAX: " + json.dumps(rec), flush=True)
    return results


def main():
    SMOKE.mkdir(parents=True, exist_ok=True)
    results = []
    for model_key, bench, pid in CASES:
        port = 18000 if model_key == "deepseek" else 18001
        for method in METHODS:
            r = run_case(model_key, bench, pid, method, port)
            results.append(r)
            print(json.dumps(r), flush=True)
            if r["exit"] != 0:
                print(f"CASE FAILED: {r['case']} exit={r['exit']}, see {r['log']}", file=sys.stderr)
                (RT / "smoke_cases.json").write_text(json.dumps(results, indent=2))
                return 1
    rep = canonical_reproducibility()
    print("REPRODUCIBILITY: " + json.dumps(rep), flush=True)
    nmp = near_max_probes()
    out = {"cases": results, "reproducibility": rep, "near_max_probes": nmp}
    (RT / "smoke_cases.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
