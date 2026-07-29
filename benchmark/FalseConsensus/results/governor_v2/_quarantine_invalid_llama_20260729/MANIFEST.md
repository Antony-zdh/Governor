# Quarantined invalid Llama confirmation results

## Source
- Old commit: pre-ugcpu2-batch-20260729
- Model: deepseek-ai/DeepSeek-R1-Distill-Llama-8B
- Phase: confirmation, seed 45

## Failure evidence
- Output garbled from first token: `+=+=+========~==.` (not natural language)
- ~98/108 trajectories: finish_reason=length, final_answer empty
- Missing AIME24 environment entirely
- Root cause: vLLM 0.26+ does not auto-add BOS for Llama tokenizer;
  clients.py apply_chat_template omitted BOS, causing tokenizer mismatch

## Fix applied
- clients.py: added BOS prefix +  ^{
  to Llama-8B template
- Smoke verified: readable output, correct answer \\boxed{5} for 2+3
- New results collected under confirmation__deepseek-ai-deepseek-r1-distill-llama-8b__*
