# OpenCLI/jelp Cost-Adjusted Decision Protocol

This document freezes the evaluation protocol for the current decision pass.

## Objective

Determine whether OpenCLI/jelp provides a net practical benefit over standard
help traversal for current LLM behavior, using cost-adjusted criteria.

## Locked comparison

- Baseline mode (`B`): `help-only-primed`
- Primary candidate mode (`C`): `jelp-primed-useful`

Other modes are still captured for context, but verdict logic is locked to `B`
vs `C`.

## Confirmatory sweep configuration

- Models:
  - `gpt-4.1-mini`
  - `gpt-5-mini`
- Modes:
  - `help-only`
  - `help-only-primed`
  - `jelp-primed-useful`
  - `jelp-primed-incremental`
  - `jelp-primed-full`
- Harness settings:
  - `--iterations 3`
  - `--max-steps 12`
  - `--api-timeout-s 45`
  - `--response-max-output-tokens 1200`
  - `--adapter-retries 2`
  - no `--temperature` override
- Fixture set: all 8 fixtures in `ctf/scenarios.py`.

## Evidence inclusion

Only files produced by the above configuration are decision evidence. For this
pass, expected evidence paths are:

- `ctf/results/confirmatory-gpt-4.1-mini.json`
- `ctf/results/confirmatory-gpt-5-mini.json`

No prior exploratory files (temperature sweeps, subset runs, or older mode
mixes) are used for the final verdict.

## Decision metrics

For paired rows on `(model, run_file, iteration, scenario)`:

- `success_delta_pp = success(C) - success(B)` in percentage points
- `median_cmd_delta = median(commands_C - commands_B)`
- `token_ratio = mean_total_tokens(C) / mean_total_tokens(B)`

Confidence intervals use bootstrap with replacement at 90%.

## Verdict rule

`Net benefit now` when all are true:

- `success_delta_pp >= 0`
- `median_cmd_delta <= -0.5`
- `token_ratio <= 1.75`
- CI direction favorable:
  - lower bound of success delta CI is `>= 0`
  - upper bound of command delta CI is `<= -0.5`

`Promising, strategy adjustment needed` when:

- `success_delta_pp >= 0`
- `median_cmd_delta <= -0.5`
- and either:
  - `token_ratio > 1.75`, or
  - CI direction is not favorable

`No net benefit currently` when either is true:

- `success_delta_pp < 0`, or
- `median_cmd_delta >= 0`

## Generalization rule

If model-level verdicts disagree, final statement is:

- `model-sensitive / not yet general`

## Repro commands

Generate evidence files:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --modes help-only help-only-primed jelp-primed-useful jelp-primed-incremental jelp-primed-full \
  --iterations 3 \
  --max-steps 12 \
  --api-timeout-s 45 \
  --response-max-output-tokens 1200 \
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
  --out ctf/results/confirmatory-gpt-5-mini.json
```

Run the decision analyzer:

```bash
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
```

## Assumptions

- Fixture definitions remain unchanged during this decision pass.
- Harness token usage fields are treated as valid for relative comparisons.
- This protocol evaluates near-term utility, not long-horizon training effects.
