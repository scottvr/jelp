# jelp

`jelp` exposes an `argparse` CLI as machine-readable JSON (OpenCLI-shaped), so tools and LLMs can reason about commands/options without scraping `--help` text.

This repo is an early, practical v.0 focused on native parser introspection.

## Why?
The original motivation was to create a way to modify existing CLI apps that use argparse, with a simple one-line modification that would expose all of the argparsing behavior just as would be exposed with `--help`, but as a JSON object. After learning about OpenCLI, the implementation was modified to try adhere to the schema, in hopes that it would be useful for both `jelp` and the OpenCLI schema by exposing any shortcomings in the draft, and validating the assumption that describing a CLI in this sort of manner is generally more effective than letting an LLM just discover usage via `--help` as a human user would.

## What?
Also included in this repo is an evaluation harness designed to perform a cost-benefit analysis on LLM tool-use via naive cli `--help` queries vs the same usage, with the LLM given information about the CLI in a JSON object conforming to an OpenCLI schema. It takes the shape of a [CTF challenge](docs/llm-ctf-harness.md) with deterministic flags and meaningfully measurable outcomes. If you're only here for the current results, here's the general gist of it:

| scope        | raw_verdict_no_cost                   | cost_adjusted_verdict                 | changed_by_cost | token_ratio_obs | token_ratio_threshold | reason |
| ------------ | ------------------------------------- | ------------------------------------- | --------------- | --------------: | --------------------: | ------ |
| gpt-4.1-mini | No net benefit currently              | No net benefit currently              | no              |           2.361 |                  1.75 | -      |
| gpt-5-mini   | Net benefit now                       | Net benefit now                       | no              |           1.150 |                  1.75 | -      |
| all-models   | Promising, strategy adjustment needed | Promising, strategy adjustment needed | no              |           1.608 |                  1.75 | -      |

This table comes from the [generated CTF harness phase-1 report](https://github.com/scottvr/jelp/blob/ctf-phase-1/ctf/results/confirmatory-decision.md#cost-adjustment-impact).

----

## Status

- Version: `0.0.1` (experimental)
- Primary target: Python `argparse`
- Output shape: OpenCLI draft-compatible JSON
- Non-OpenCLI semantics are preserved in `metadata` (for example `count`, `append`, mutually-exclusive groups)

## Installation

clone the repo, then:

```bash
cd jelp
pip install -e .'[all]'
```

### Install CTF harness

Then, if you're interested in the CTF harness:

```bash
pip install -e .'[ctf]'
```

Most of what you'll want for this is in the ctf/ directory, but to replay exactly what I did to generate the current results, you'll find that in the file `llm-ctf-bench.sh`.


## Development Quick Start (Existing argparse App)

### One-line enablement (recommended)

```python
from jelp.argparse import enable_jelp

parser = build_parser()
enable_jelp(parser, version=__version__)
args = parser.parse_args(argv)
```

That is enough. `enable_jelp(...)` installs:

- `--jelp` (compact JSON, useful metadata)
- `--jelp-pretty` (indented JSON, useful metadata)
- `--jelp-no-meta` (compact JSON, no metadata)
- `--jelp-all` (compact JSON, full metadata)
- `--jelp-all-commands` (compact JSON, useful metadata, full CLI tree)
- `--jelp-all-no-meta` (compact JSON, no metadata, full CLI tree)

When any `--jelp*` flag is present, `parse_args()` emits JSON and exits with code `0`.

Default ordering is argparse-like:

- `mytool subcommand --jelp` -> subcommand JSON
- `mytool --jelp subcommand` -> root JSON

For a guaranteed full-tree dump (regardless where the flag appears), use:

- `mytool subcommand --jelp-all-commands`
- `mytool subcommand --jelp-all-no-meta`

If you want inverted-order compatibility, opt in:

```python
enable_jelp(parser, version=__version__, allow_inverted_order=True)
```

### Explicit/manual handling (optional)

Use this only if you need to control emission flow yourself.

```python
from jelp.argparse import enable_jelp, handle_jelp_flag

parser = build_parser()
enable_jelp(parser, auto_handle=False)

if handle_jelp_flag(parser, argv, version=__version__):
    return 0

args = parser.parse_args(argv)
```

## Library API

### Emit OpenCLI-shaped JSON directly

```python
from jelp.argparse import emit_opencli

data = emit_opencli(parser, version="1.2.3")
```

Metadata profile can be selected:

```python
emit_opencli(parser, version="1.2.3", metadata_level="useful")  # default
emit_opencli(parser, version="1.2.3", metadata_level="none")
emit_opencli(parser, version="1.2.3", metadata_level="all")
```

### Add examples to output

If your parser (or subparser) defines `jelp_examples`, they are emitted into OpenCLI `examples`.

```python
parser.jelp_examples = [
    "mytool --format json scan src",
    "mytool --verbose push --force",
]
```

### Version stamping

- `version=` is required for emission APIs.
- `opencli_version=` defaults to `"0.1.0"` and controls the emitted `opencli` field.

## What jelp captures (v0)

- root options and positionals
- subcommands and aliases
- command-local options and positionals
- `choices`, `required`, and `nargs` -> arity mapping
- hidden/help-suppressed elements
- mutually-exclusive groups
- defaults / action semantics / repeat semantics in metadata
- `BooleanOptionalAction` behavior (including `--foo` / `--no-foo` aliases)

## Current decisions

- Schema selection is not in v0; current target is OpenCLI draft shape.
- Defaults stay in metadata (`argparse.default`) for now.
- Repeatable behavior stays in metadata (`argparse.repeat_semantics`) for now.

Metadata levels:

- `useful` (default): keeps caller-relevant metadata
- `none`: strips all metadata
- `all`: includes full internal metadata (debug/audit)

When jelp injects flags via `enable_jelp(...)`, provenance is tagged in metadata:

- option-level: `jelp.injected: true`
- parser-level: `jelp.injected_options: [...]`

See:

- [docs/v0-decisions.md](docs/v0-decisions.md)
- [docs/opencli-feedback-examples.md](docs/opencli-feedback-examples.md)
- [docs/llm-ctf-harness.md](docs/llm-ctf-harness.md)
- [docs/phase-2-protocol.md](docs/phase-2-protocol.md)
- [docs/phase1/opencli-decision-protocol.md](docs/phase1/opencli-decision-protocol.md) (archived phase-1 protocol)
- [docs/task-tracker.md](docs/task-tracker.md)
- [docs/task-tracker-roadmap.md](docs/task-tracker-roadmap.md)

Quick harness smoke test:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter oracle --out ctf/results/phase2/oracle.json
```

Phase-2 preset runner:

```bash
PYTHONPATH=src:. .venv/bin/python ctf/phase2_run.py
```

## Why this project exists

Many CLIs already contain high-quality structural truth in their parser definitions.
`jelp` surfaces that truth directly for automation, wrappers, doc tooling, and LLM systems.
