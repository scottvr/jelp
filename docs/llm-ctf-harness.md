# LLM CTF Harness

This harness evaluates whether machine-readable CLI introspection improves LLM tool use.

## Goal

Measure task success and efficiency across core modes:

1. `help-only`: no jelp flags available
2. `jelp-useful`: `--jelp` / `--jelp-pretty` / `--jelp-all-commands` available
3. `jelp-primed`: same flags as `jelp-useful`, plus a prompt primer describing OpenCLI/jelp capability
4. `jelp-no-meta`: `--jelp-no-meta` (and full-tree `--jelp-all-no-meta`) available

Optional debug mode: `jelp-all`.

Additional experimental modes:

- `jelp-primed-useful`:
  - prompt primer enabled
  - `--help` disabled
  - only compact `--jelp` allowed (useful metadata, parser-local scope)
- `jelp-primed-incremental`:
  - prompt primer enabled
  - `--help` disabled
  - only `--jelp` / `--jelp-pretty` allowed for schema discovery
- `jelp-primed-full`:
  - prompt primer enabled
  - `--help` disabled
  - only `--jelp-all-commands` allowed for schema discovery

Optional control mode: `help-only-primed`:

- same tool constraints as `help-only` (no jelp flags allowed)
- adds the same OpenCLI/jelp primer text used in primed runs
- denied `--jelp*` probes are non-penalized for step budget in this mode

## Scenario set

Fixtures live in `ctf/fixtures/` and are intentionally unfamiliar CLIs. Each has a hidden success condition that prints one deterministic `FLAG{...}`.
Fixtures include realistic decoy commands and root/subcommand coupling so interface exploration is rewarded over blind guessing.

Current fixture count: 8.

## Metrics captured

Per scenario/mode run:

- `success` (expected flag returned)
- `command_count`
- `invalid_command_count`
- `parser_error_count`
- `duration_s`
- `time_to_success_s`
- `api_call_count` (LLM request count)
- `model_input_tokens`, `model_output_tokens`, `model_total_tokens`

Detailed command/stdio traces are written to a JSON log.

## Run

### Oracle smoke test (deterministic)

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter oracle --out ctf/results/oracle.json
```

### OpenAI-based naive LLM run

Requires `OPENAI_API_KEY` and `openai` package.

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --max-steps 12 \
  --api-timeout-s 45 \
  --response-max-output-tokens 500 \
  --adapter-retries 1 \
  --out ctf/results/openai-run.json
```

### Subset run

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --modes help-only help-only-primed jelp-useful jelp-primed jelp-no-meta \
  --scenario fixture01_vault \
  --scenario fixture08_nested
```

### Primed jelp-only experiment

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --modes jelp-primed-useful jelp-primed-incremental jelp-primed-full \
  --iterations 3 \
  --max-steps 12 \
  --out ctf/results/openai-primed-jelp-only.json
```

### Live debug mode

Shows step-by-step harness activity and raw model text responses.
When `--debug` is enabled, these debug lines are also persisted in the output JSON under each result as `debug_events`.

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --debug \
  --api-timeout-s 45 \
  --response-max-output-tokens 500 \
  --adapter-retries 1 \
  --max-steps 12
```

If your chosen model supports temperature, you can pass it:

```bash
... --temperature 0.2
```

If omitted, no temperature is sent (avoids model-compatibility issues).

For GPT-5 family models that sometimes return empty or partial text, try:

```bash
--model gpt-5-mini --adapter-retries 2 --response-max-output-tokens 700
```

## Suggested evaluation protocol

1. Run each mode with the same model and step budget.
2. Compare:
   - success uplift: `help-only` -> `jelp-useful`
   - awareness uplift: `jelp-useful` -> `jelp-primed`
   - priming-only control: `help-only` -> `help-only-primed`
   - compact useful-only test: `jelp-primed-useful` vs `jelp-primed-full`
   - schema ingestion style: `jelp-primed-incremental` -> `jelp-primed-full`
   - efficiency uplift: command_count/time/error reductions
3. Check metadata value by comparing `jelp-useful`/`jelp-primed` vs `jelp-no-meta`.
4. Use `jelp-all` only as a diagnostic control for ambiguity or provenance debugging.

## Notes on fairness

- Harness policy disallows jelp flags in `help-only` mode.
- In `jelp-no-meta` mode, metadata-bearing flags are rejected.
- Commands must invoke fixture CLIs via `python ...`; non-CLI shell exploration is rejected for consistency.

## Files

- Runner: `ctf/harness.py`
- Adapters: `ctf/adapters.py`
- Scenarios: `ctf/scenarios.py`
- Fixtures: `ctf/fixtures/*.py`
- Results: `ctf/results/*.json`

## Reporting

After a harness run, compute mode-level and paired baseline deltas:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/report.py --in ctf/results/openai-run.json
```

Defaults:

- baseline: `help-only`
- comparisons: `jelp-useful`, `jelp-primed`, `jelp-no-meta`

Override comparisons:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/report.py \
  --in ctf/results/openai-run.json \
  --baseline help-only \
  --compare jelp-useful \
  --compare jelp-primed \
  --compare jelp-no-meta \
  --compare jelp-all
```
