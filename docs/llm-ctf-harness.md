# LLM CTF Harness

This harness evaluates whether machine-readable CLI introspection improves LLM tool use.

**NOTE:** the community would likely benefit from more iterations, more model variance (I've only tested two; one actually suffered in performance when made to use an open-cli schema to learn about a new tool, one saw some improvement at the cost of increased token usage, and so on.)  More tests, more comparisons, more knowledge. I find it interesting that my current results indicate that some models, under specific constraints will perform better in terms of how many tries it takes them to get a command from a cli not in their training data, but worse in how many mistakes they made in the process before getting it right vs any of the other dimensions examined. Read on, and maybe post in the Discussions if you have reports or data to contribute (presently the logs are in .gitignore, so don't try to send a PR for this. If there is interest we can work out a system for distrubuted contribution to the benchmarking effort.)

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

**Note:** A later phase will include the same trials, but using CLIs that are well-documented in the training corpora. It seems a useful control, but for now I wanted to ensure that the CLIs under test were guaranteed *not* to be in the LLM training data, so that we could confine the changes being tested to only whether the usage data is presented in human-readable help text, or schema'd json

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

Low-memory variant (recommended for long benchmark sweeps):

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py \
  --adapter openai \
  --model gpt-4.1-mini \
  --iterations 3 \
  --max-steps 12 \
  --low-memory \
  --out ctf/results/openai-run.json
```

Checkpointing behavior:

- progress is checkpointed to `--out` after each completed scenario/mode result
- if `--out` already exists, harness refuses to clobber by default
- use `--overwrite` to start fresh over an existing file
- use `--resume` to continue from an existing file and skip completed `(iteration, scenario, mode)` entries
- for lower memory usage on long runs:
  - `--summary-only` keeps only `iteration+summary` rows in `--out`
  - `--stream-details-jsonl PATH` appends full per-result records to a JSONL sidecar
  - `--low-memory` convenience mode enables `--summary-only` and defaults sidecar path to `<out>.details.jsonl`

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

Debug output includes:

- `iteration=x/y ... step=n` so long runs are trackable in real time.
- a short per-turn scope id in brackets (for example `i01.f04.ho.s03`) for grep/correlation.
- explicit console-preview truncation notices for large stdout/stderr/model text.
- explicit API-side incompletion notices when a model response reports truncation/incomplete details (for example, max output token constraints).

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

For GPT-5 family models that sometimes return empty or partial text (some sort of reasoning notice I haven't read into yet), try:

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

## Execution model and safety

- The harness executes real local subprocesses for accepted model commands.
- It is not a VM/sandbox boundary; run only in a trusted local environment.
- Command validation is strict:
  - command must parse as shell tokens
  - first token must be `python`
  - second token must be the expected fixture script (for example `fixture01_vault.py`)
- Commands that fail validation are rejected and logged, not executed.
- Potential exploit-like command patterns (shell control tokens, subshell/backtick markers, multiline command text) emit `[anomaly]` alerts and are recorded in the run log, in case the model under evaluation gets more "creative" than expected. We call it out because it would be fascinating if it occurred, but it isn't the point of the harness, so we disallow it to avoid polluting the results (and for the safety of the machine running the test harness.)

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

## Decision report (cost-adjusted)

For pre-registered decision analysis across one or more run logs:

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

See `docs/opencli-decision-protocol.md` for locked thresholds and evidence rules.

## Cost report (API spend estimate)

Estimate API spend from recorded token usage in run logs:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/cost_report.py \
  --in ctf/results/confirmatory-gpt-4.1-mini.json \
  --in ctf/results/confirmatory-gpt-5-mini.json \
  --forecast-iterations 3 \
  --json-out ctf/results/confirmatory-cost.json
```

Optional adjustments:

- `--assume-cached-input-ratio 0.25` to model partial cached-input billing.
- `--price MODEL,INPUT,OUTPUT[,CACHED_INPUT]` to override model pricing.
- `--pricing-json path/to/pricing.json` to load pricing map from a file.

Built-in defaults are a snapshot (USD / 1M tokens):

- `gpt-4.1-mini`: input `0.40`, cached input `0.10`, output `1.60`
- `gpt-5-mini`: input `0.25`, cached input `0.025`, output `2.00`
- `gpt-5`: input `1.25`, cached input `0.125`, output `10.00`

Use overrides whenever pricing changes.
