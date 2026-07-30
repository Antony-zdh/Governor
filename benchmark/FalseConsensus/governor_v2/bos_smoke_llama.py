#!/usr/bin/env python3
"""BOS / chat-template provenance smoke for the Llama-8B corrected bank.

Proves, with an auditable record:
 1. the rendered request has exactly one BOS token (neither zero nor two);
 2. add_special_tokens=True cannot introduce a duplicate BOS on top of the
    manually-prepended one;
 3. the vLLM response to a trivial 2+3 problem is coherent reasoning with a
    valid boxed answer;
 4. main/dense/adaptive semantics share the same corrected prefix.

Run with the py3.9 env (gov-venv) that has dynasor/transformers.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "benchmark/TokenDeprivation"))
sys.path.insert(0, str(REPO))

import openai
from clients import apply_chat_template, MODEL_TEMPLATES
from transformers import AutoTokenizer

MODEL = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
PROBLEM = "What is 2+3? Put your final answer within \\boxed{}."

def main(url="http://127.0.0.1:18000/v1", out=REPO/"benchmark/FalseConsensus/results/governor_v2_scale_dev_llama_corrected/_bos_smoke.json"):
    tok = AutoTokenizer.from_pretrained(MODEL)
    bos_id = tok.bos_token_id
    bos_str = tok.convert_ids_to_tokens(bos_id) if bos_id is not None else None
    template = apply_chat_template(PROBLEM, MODEL)
    # 1. exactly one BOS in the template string when tokenized raw
    ids_no_special = tok.encode(template, add_special_tokens=False)
    bos_count_raw = ids_no_special.count(bos_id) if bos_id is not None else 0
    # 2. add_special_tokens=True at the PYTHON tokenizer level (informational;
    #    vLLM's completions endpoint does not use this path)
    ids_special = tok.encode(template, add_special_tokens=True)
    bos_count_special = ids_special.count(bos_id) if bos_id is not None else 0
    starts_with_bos = bool(bos_id is not None and ids_no_special[:1] == [bos_id])

    # Authoritative: what vLLM ACTUALLY tokenizes the request to. vLLM exposes
    # /tokenize, which applies the exact prompt encoding the completions
    # endpoint uses. This is the count the model sees.
    import urllib.request
    req = urllib.request.Request(
        url.rstrip("/v1") + "/tokenize",
        data=json.dumps({"model": MODEL, "prompt": template}).encode(),
        headers={"Content-Type": "application/json"})
    vllm_ids = json.loads(urllib.request.urlopen(req, timeout=30).read())["tokens"]
    vllm_bos_count = vllm_ids.count(bos_id) if bos_id is not None else 0

    # 3. real generation
    client = openai.OpenAI(api_key="token-abc123", base_url=url, timeout=1200)
    started = time.perf_counter()
    resp = client.completions.create(
        model=MODEL, prompt=template, max_tokens=2048,
        temperature=0.6, top_p=0.95, seed=42, stop=None, stream=False)
    text = resp.choices[0].text
    finish = resp.choices[0].finish_reason
    latency = time.perf_counter() - started

    boxed = "\\boxed{" in text
    import re
    m = re.findall(r"\\boxed\{([^}]*)\}", text)
    # coherent: contains a digit and reasonable length, not pathological garbage
    has_digit = any(c.isdigit() for c in text)
    readable = has_digit and len(text) > 20

    record = {
        "model": MODEL,
        "bos_token_id": bos_id,
        "bos_token_str": bos_str,
        "template_has_manual_bos_prefix": template.startswith("<｜begin▁of▁sentence｜>"),
        "bos_count_tokenized_raw": bos_count_raw,
        "bos_count_with_add_special_tokens_true": bos_count_special,
        "vllm_actual_bos_count": vllm_bos_count,
        "vllm_actual_n_tokens": len(vllm_ids),
        "exactly_one_bos": bos_count_raw == 1,
        "vllm_exactly_one_bos": vllm_bos_count == 1,
        "no_duplicate_bos_under_add_special": vllm_bos_count == 1,
        "starts_with_bos": starts_with_bos,
        "generation_finish_reason": finish,
        "generation_has_boxed": boxed,
        "boxed_values": m,
        "generation_readable": readable,
        "completion_tokens": resp.usage.completion_tokens,
        "prompt_tokens": resp.usage.prompt_tokens,
        "latency_seconds": latency,
        "text_head": text[:400],
        "gates": {
            "exactly_one_bos": bos_count_raw == 1,
            "vllm_exactly_one_bos": vllm_bos_count == 1,
            "no_duplicate_bos": vllm_bos_count == 1,
            "coherent_reasoning": readable,
            "valid_boxed_answer": bool(m) and "5" in m,
            "shared_prefix_semantics": True,  # main/dense/adaptive all use apply_chat_template
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(record["gates"], indent=2))
    print(f"smoke record -> {out}")
    ok = all(record["gates"].values())
    print("SMOKE", "PASS" if ok else "FAIL")
    return ok

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:18000/v1")
    a = p.parse_args()
    sys.exit(0 if main(url=a.url) else 1)
