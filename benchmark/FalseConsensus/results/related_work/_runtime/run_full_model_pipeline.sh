#!/usr/bin/env bash
# run_full_model_pipeline.sh -- durable full-bank launcher for one model.
#
# Usage: run_full_model_pipeline.sh <deepseek|qwen3> [--dry-run]
#
# Hard-maps the model key to its exact model id, 40-hex revision, endpoint, and
# GPU (informational only). Validates endpoint readiness, the split manifest, and
# the exactly-9 authorized development environments (math500/amc23/aime24 x seeds
# 42/43/44) for that model, then runs CertaIndex (9 envs) -> TJE (9 envs) -> DEER
# (9 envs) with workers=4 and the exact collector arguments.
#
# Properties: location-independent (cd to REPO); safely restartable (collectors
# skip complete per-problem files); fails loudly (set -euo pipefail); captures
# the real collector exit code; verifies the manifest completion block after each
# run (complete=true, observed=expected, missing=0, failures=0); uses absolute
# /localdata/dzhaoah/Governor paths; never selects/resets/touches GPUs or other
# processes; writes per-method/environment logs + atomic machine-readable
# status_<key>.json / progress_<key>.json under the full-results runtime area.
# --dry-run is genuinely non-mutating (validates and prints only; no mkdir/status).
set -euo pipefail

REPO=/localdata/dzhaoah/Governor
PY=/localdata/dzhaoah/miniforge3/envs/gov/bin/python
SPLIT_MANIFEST="$REPO/benchmark/FalseConsensus/governor_v2/generated/split_manifest.json"
BANK_ROOT="$REPO/benchmark/FalseConsensus/results/governor_v2"
RESULTS_ROOT="$REPO/benchmark/FalseConsensus/results/related_work/full"
RUNTIME_DIR="$RESULTS_ROOT/_runtime"
WORKERS=4
TJE_MAX_MODEL_LEN=34816
TJE_READOUT_CAP=8192

# --- hard model map (mirrors related_work/model_map.py) ---
declare -A MODEL_ID REVISION ENDPOINT PORT GPU SLUG
MODEL_ID[deepseek]="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
REVISION[deepseek]="916b56a44061fd5cd7d6a8fb632557ed4f724f60"
ENDPOINT[deepseek]="http://127.0.0.1:18000/v1"
PORT[deepseek]=18000
GPU[deepseek]=0
SLUG[deepseek]="deepseek-ai-deepseek-r1-distill-qwen-7b"

MODEL_ID[qwen3]="Qwen/Qwen3-8B"
REVISION[qwen3]="b968826d9c46dd6066d109eabc6255188de91218"
ENDPOINT[qwen3]="http://127.0.0.1:18001/v1"
PORT[qwen3]=18001
GPU[qwen3]=1
SLUG[qwen3]="qwen-qwen3-8b"

BENCHMARKS=(math500 amc23 aime24)
SEEDS=(42 43 44)
METHODS=(certaindex_mid tje deer)
declare -A EXPECTED_COUNT
EXPECTED_COUNT[math500]=400
EXPECTED_COUNT[amc23]=32
EXPECTED_COUNT[aime24]=24

KEY="${1:-}"
DRY_RUN=0
[[ "${2:-}" == "--dry-run" ]] && DRY_RUN=1

if [[ -z "$KEY" ]] || [[ "$KEY" != "deepseek" && "$KEY" != "qwen3" ]]; then
    echo "Usage: $0 <deepseek|qwen3> [--dry-run]" >&2
    exit 2
fi

# --- location-independent: cd to repo root (so python -m ... works) ---
cd "$REPO"

MID="${MODEL_ID[$KEY]}"
REV="${REVISION[$KEY]}"
URL="${ENDPOINT[$KEY]}"
SLUG_VAL="${SLUG[$KEY]}"
GPU_VAL="${GPU[$KEY]}"
START_TS=$(date +%s)
START_ISO=$(date +%Y-%m-%dT%H:%M:%S)

# --- atomic JSON writer (tmp file + rename) ---
write_json_atomic() {
    local file="$1" content="$2"
    local tmp="${file}.tmp.$$"
    printf '%s\n' "$content" > "$tmp"
    mv "$tmp" "$file"
}

# --- manifest completion verification (captures stdout+stderr + exit code) ---
verify_manifest() {
    local out_dir="$1" method="$2" bench="$3"
    local manifest
    case "$method" in
        certaindex_mid) manifest="$out_dir/probe_manifest.json" ;;
        tje) manifest="$out_dir/trigger_manifest.json" ;;
        deer) manifest="$out_dir/trial_manifest.json" ;;
    esac
    if [[ ! -f "$manifest" ]]; then
        echo "manifest_missing:$manifest"
        return 1
    fi
    # capture stdout+stderr; decide from the verifier exit code; retain the reason.
    # Wrapped in if/else so set -e does not terminate the script on a nonzero
    # verifier exit (the exact reason is retained in $out).
    local out vrc
    if out=$("$PY" -m benchmark.FalseConsensus.related_work.manifest_check \
        "$manifest" "${EXPECTED_COUNT[$bench]}" 2>&1); then
        vrc=0
    else
        vrc=$?
    fi
    if [[ $vrc -eq 0 ]]; then
        echo "ok"
    else
        echo "$out"
    fi
    return $vrc
}

# --- validation (read-only; safe in dry-run) ---
validate() {
    local errors=0
    if ! curl -sS --max-time 8 "$URL/models" -H "Authorization: Bearer token-abc123" >/dev/null 2>&1; then
        echo "FAIL: endpoint $URL not ready (model server for $KEY not up on GPU $GPU_VAL)" >&2
        errors=$((errors+1))
    fi
    if [[ ! -f "$SPLIT_MANIFEST" ]]; then
        echo "FAIL: split manifest not found: $SPLIT_MANIFEST" >&2
        errors=$((errors+1))
    fi
    local found=0
    for b in "${BENCHMARKS[@]}"; do
        for s in "${SEEDS[@]}"; do
            local env="$BANK_ROOT/development__${SLUG_VAL}__${b}__seed_${s}/main"
            if [[ ! -d "$env" ]]; then
                echo "FAIL: missing dev environment main-run: $env" >&2
                errors=$((errors+1))
            else
                found=$((found+1))
            fi
        done
    done
    if [[ $found -ne 9 ]]; then
        echo "FAIL: expected 9 dev environments for $KEY, found $found" >&2
        errors=$((errors+1))
    fi
    if [[ ! "$REV" =~ ^[0-9a-f]{40}$ ]]; then
        echo "FAIL: revision not 40-hex: $REV" >&2
        errors=$((errors+1))
    fi
    return $errors
}

# --- build the exact collector command ---
collector_cmd() {
    local method="$1" main_run="$2" out_dir="$3"
    local cmd=("$PY" -m "benchmark.FalseConsensus.related_work.${method}"
        --main-run "$main_run" --output "$out_dir" --url "$URL"
        --model "$MID" --model-revision "$REV" --split-manifest "$SPLIT_MANIFEST"
        --workers "$WORKERS")
    if [[ "$method" == "tje" ]]; then
        cmd+=(--max-model-len "$TJE_MAX_MODEL_LEN" --readout-cap "$TJE_READOUT_CAP")
    fi
    printf '%s\0' "${cmd[@]}"
}

if ! validate; then
    echo "Validation failed; aborting." >&2
    exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
    # genuinely non-mutating: validate and print only; no mkdir, no status writes
    echo "=== DRY RUN: $KEY (model=$MID rev=$REV endpoint=$URL gpu=$GPU_VAL workers=$WORKERS) ==="
    echo "split_manifest=$SPLIT_MANIFEST"
    echo "results_root=$RESULTS_ROOT"
    echo "authorized_envs=9 (math500/amc23/aime24 x seeds 42/43/44)"
    echo "repo_root=$REPO (cwd)"
    for method in "${METHODS[@]}"; do
        for b in "${BENCHMARKS[@]}"; do
            for s in "${SEEDS[@]}"; do
                main_run="$BANK_ROOT/development__${SLUG_VAL}__${b}__seed_${s}/main"
                out_dir="$RESULTS_ROOT/${KEY}__${b}__seed_${s}/${method}"
                mapfile -d '' -t cmd < <(collector_cmd "$method" "$main_run" "$out_dir")
                echo "[$method] ${b}/seed_${s}"
                printf '  %s\n' "${cmd[@]}"
            done
        done
    done
    echo "=== DRY RUN complete: 27 commands planned, no outputs written ==="
    exit 0
fi

# --- full run ---
mkdir -p "$RUNTIME_DIR" "$RESULTS_ROOT"
LOG_DIR="$RUNTIME_DIR/logs_${KEY}"
mkdir -p "$LOG_DIR"
STATUS_FILE="$RUNTIME_DIR/status_${KEY}.json"
PROGRESS_FILE="$RUNTIME_DIR/progress_${KEY}.json"

write_json_atomic "$STATUS_FILE" \
    "{\"model_key\":\"$KEY\",\"model_id\":\"$MID\",\"revision\":\"$REV\",\"endpoint\":\"$URL\",\"gpu\":$GPU_VAL,\"state\":\"running\",\"started_at\":\"$START_ISO\",\"detail\":\"CertaIndex -> TJE -> DEER across 9 envs\"}"

total=0; done=0; failed=0
for method in "${METHODS[@]}"; do
    for b in "${BENCHMARKS[@]}"; do
        for s in "${SEEDS[@]}"; do
            total=$((total+1))
            main_run="$BANK_ROOT/development__${SLUG_VAL}__${b}__seed_${s}/main"
            out_dir="$RESULTS_ROOT/${KEY}__${b}__seed_${s}/${method}"
            log_file="$LOG_DIR/${method}__${b}__seed_${s}.log"
            mkdir -p "$out_dir"
            mapfile -d '' -t cmd < <(collector_cmd "$method" "$main_run" "$out_dir")
            echo "[$total/27] $method $b seed_$s -> $out_dir"
            NOW_ISO=$(date +%Y-%m-%dT%H:%M:%S)
            write_json_atomic "$PROGRESS_FILE" \
                "{\"model_key\":\"$KEY\",\"method\":\"$method\",\"bench\":\"$b\",\"seed\":$s,\"total_jobs\":$total,\"done\":$done,\"failed\":$failed,\"state\":\"running\",\"updated_at\":\"$NOW_ISO\"}"
            if env LD_PRELOAD=/localdata/dzhaoah/miniforge3/envs/gov/lib/libstdc++.so.6 \
                LD_LIBRARY_PATH=/localdata/dzhaoah/miniforge3/envs/gov/lib:/usr/local/cuda-13.0.0/lib64 \
                CUDA_HOME=/usr/local/cuda-13.0.0 \
                PATH=/usr/local/cuda-13.0.0/bin:/localdata/dzhaoah/miniforge3/envs/gov/bin:$PATH \
                HF_HOME=/localdata/dzhaoah/hf-cache \
                "${cmd[@]}" > "$log_file" 2>&1; then
                rc=0
            else
                rc=$?  # capture the real collector exit code BEFORE any other command
            fi
            # verify the manifest completion block regardless of collector rc.
            # Wrapped in if/else so set -e does not terminate the script when
            # verify_manifest returns nonzero (the exact reason is retained).
            # NOTE: no `local` here — this is the top-level loop, not a function;
            # `local` at top level is a runtime error in bash.
            if verify_reason=$(verify_manifest "$out_dir" "$method" "$b"); then
                verify_rc=0
            else
                verify_rc=$?
            fi
            if [[ $rc -eq 0 && $verify_rc -eq 0 ]]; then
                done=$((done+1))
            else
                failed=$((failed+1))
                echo "FAIL: $method $b seed_$s collector_rc=$rc manifest_rc=$verify_rc reason='$verify_reason' -> $log_file" >&2
            fi
            NOW_ISO=$(date +%Y-%m-%dT%H:%M:%S)
            write_json_atomic "$PROGRESS_FILE" \
                "{\"model_key\":\"$KEY\",\"method\":\"$method\",\"bench\":\"$b\",\"seed\":$s,\"total_jobs\":$total,\"done\":$done,\"failed\":$failed,\"state\":\"step_done\",\"updated_at\":\"$NOW_ISO\"}"
        done
    done
done

END_ISO=$(date +%Y-%m-%dT%H:%M:%S)
state="complete"; [[ $failed -gt 0 ]] && state="completed_with_failures"
write_json_atomic "$STATUS_FILE" \
    "{\"model_key\":\"$KEY\",\"model_id\":\"$MID\",\"revision\":\"$REV\",\"endpoint\":\"$URL\",\"gpu\":$GPU_VAL,\"state\":\"$state\",\"started_at\":\"$START_ISO\",\"ended_at\":\"$END_ISO\",\"detail\":\"done=$done failed=$failed total=$total\"}"
echo "=== $KEY done: $done/$total ok, $failed failed ==="
[[ $failed -eq 0 ]]
