#!/bin/bash

set -euo pipefail

BASELINE_MODE="${BASELINE_MODE:-help-only-primed}"
CANDIDATE_MODE="${CANDIDATE_MODE:-jelp-primed-incremental}"
ITERATIONS="${ITERATIONS:-3}"
MAX_STEPS="${MAX_STEPS:-12}"
API_TIMEOUT_S="${API_TIMEOUT_S:-45}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-1200}"
ADAPTER_RETRIES="${ADAPTER_RETRIES:-2}"
RESULTS_DIR="${RESULTS_DIR:-ctf/results/phase2}"

mkdir -p "${RESULTS_DIR}"

# gather head-to-head phase-2 evidence
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
   --adapter openai \
   --model gpt-4.1-mini \
   --modes "${BASELINE_MODE}" "${CANDIDATE_MODE}" \
   --iterations "${ITERATIONS}" \
   --max-steps "${MAX_STEPS}" \
   --api-timeout-s "${API_TIMEOUT_S}" \
   --response-max-output-tokens "${MAX_OUTPUT_TOKENS}" \
   --debug \
   --low-memory \
   --resume \
   --adapter-retries "${ADAPTER_RETRIES}" \
   --out "${RESULTS_DIR}/head2head-gpt-4.1-mini.json"

PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-5-mini \
  --modes "${BASELINE_MODE}" "${CANDIDATE_MODE}" \
  --iterations "${ITERATIONS}" \
  --max-steps "${MAX_STEPS}" \
  --api-timeout-s "${API_TIMEOUT_S}" \
  --response-max-output-tokens "${MAX_OUTPUT_TOKENS}" \
  --adapter-retries "${ADAPTER_RETRIES}" \
  --debug \
  --low-memory \
  --resume \
  --out "${RESULTS_DIR}/head2head-gpt-5-mini.json"

# Run the decision analyzer
PYTHONPATH=src:. .venv/bin/python ctf/decision_report.py \
  --in "${RESULTS_DIR}/head2head-gpt-4.1-mini.json" \
  --in "${RESULTS_DIR}/head2head-gpt-5-mini.json" \
  --baseline "${BASELINE_MODE}" \
  --candidate "${CANDIDATE_MODE}" \
  --ci-level 0.90 \
  --bootstrap-samples 4000 \
  --seed 42 \
  --json-out "${RESULTS_DIR}/head2head-decision.json" \
  --md-out "${RESULTS_DIR}/head2head-decision.md"
