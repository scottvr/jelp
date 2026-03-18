#!/bin/bash

# gather evidence
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
   --adapter openai \
   --model gpt-4.1-mini \
   --modes help-only help-only-primed jelp-primed-useful jelp-primed-incremental jelp-primed-full \
   --iterations 3 \
   --max-steps 12 \
   --api-timeout-s 45 \
   --response-max-output-tokens 1200 \
   --debug \
   --resume \
   --adapter-retries 2 \
   --out ctf/results/confirmatory-gpt-4.1-mini.json

PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-5-mini \
  --modes help-only help-only-primed jelp-primed-useful jelp-primed-incremental jelp-primed-full \
  --iterations 3 \
  --max-steps 12 \
  --api-timeout-s 45 \
  --response-max-output-tokens 1200 \
  --adapter-retries 2 \
  --debug \
  --resume \
  --out ctf/results/confirmatory-gpt-5-mini.json

# Run the decision analyzer
PYTHONPATH=src:. .venv/bin/python ctf/decision_report.py \
  --in ctf/results/confirmatory-gpt-4.1-mini.json \
  --in ctf/results/confirmatory-gpt-5-mini.json \
  --baseline help-only-primed \
  --candidate jelp-primed-useful \
  --ci-level 0.90 \
  --bootstrap-samples 4000 \
  --seed 42 \
  --json-out ctf/results/confirmatory-decision.json \
  --md-out ctf/results/confirmatory-decision.md
