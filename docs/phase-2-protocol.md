# OpenCLI/jelp Phase-2 Protocol (Head-to-Head)

This document defines the phase-2 evaluation pass after the phase-1 matrix.

## Objective

Run a cleaner, lower-cost confirmatory comparison between the strongest
`help-*` contender and strongest `jelp-*` contender from phase-1.

The goal is to measure practical net utility with tighter focus, then decide
whether to expand fixture coverage or iterate on prompting/schema strategy.

## Scope

- Branch: `ctf-phase-2`
- Active result directory: `ctf/results/phase2/`
- Archived phase-1 artifacts: `ctf/results/phase1/`
- Archived phase-1 decision protocol: `docs/phase1/opencli-decision-protocol.md`

## Locked comparison for phase-2 run set

Initial default candidates:

- Baseline mode (`B`): `help-only-primed`
- Candidate mode (`C`): `jelp-primed-incremental`

If phase-1 analysis later indicates a different best-in-family pair, update
this doc before generating final phase-2 evidence.

## Run configuration (initial)

- Models:
  - `gpt-4.1-mini`
  - `gpt-5-mini`
- Modes:
  - `B`
  - `C`
- Harness:
  - `--iterations 3` (start)
  - `--max-steps 12`
  - `--api-timeout-s 45`
  - `--response-max-output-tokens 1200`
  - `--adapter-retries 2`
  - `--low-memory`
  - no `--temperature` override
- Fixtures: all current fixtures in `ctf/scenarios.py`

## Staged expansion rule

1. Run initial 3-iteration pass.
2. If pooled verdict is `borderline=yes` or model verdicts disagree, add
   another 3 iterations per model.
3. Stop when verdict and cost-adjustment impact remain stable across two
   consecutive batches.

## Decision interpretation focus

Use `ctf/decision_report.py` as the decision surface and emphasize:

- evidence accounting (`observed_pairs_used`, `pair_coverage`)
- raw vs cost-adjusted verdict delta (`Cost adjustment impact`)
- CI gate (`ci_favorable`) and `borderline` state
- command-path efficiency delta and success delta

## Repro commands

Head-to-head evidence (using defaults above):

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --modes help-only-primed jelp-primed-incremental \
  --iterations 3 \
  --max-steps 12 \
  --api-timeout-s 45 \
  --response-max-output-tokens 1200 \
  --adapter-retries 2 \
  --low-memory \
  --resume \
  --out ctf/results/phase2/head2head-gpt-4.1-mini.json

PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-5-mini \
  --modes help-only-primed jelp-primed-incremental \
  --iterations 3 \
  --max-steps 12 \
  --api-timeout-s 45 \
  --response-max-output-tokens 1200 \
  --adapter-retries 2 \
  --low-memory \
  --resume \
  --out ctf/results/phase2/head2head-gpt-5-mini.json
```

Decision report:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/decision_report.py \
  --in ctf/results/phase2/head2head-gpt-4.1-mini.json \
  --in ctf/results/phase2/head2head-gpt-5-mini.json \
  --baseline help-only-primed \
  --candidate jelp-primed-incremental \
  --ci-level 0.90 \
  --bootstrap-samples 4000 \
  --seed 42 \
  --json-out ctf/results/phase2/head2head-decision.json \
  --md-out ctf/results/phase2/head2head-decision.md
```

## Next fixture expansion targets (after head-to-head)

- deeper nested subcommand trees (3+ levels)
- heavier aliasing and overlapping affordances
- more positional/option coupling with mutually-exclusive groups
- cases where full-schema introspection should avoid dead-end exploration
