# jelp

`jelp` exposes an `argparse` CLI as machine-readable JSON (OpenCLI-shaped), so tools and LLMs can reason about commands/options without scraping `--help` text.

This repo is an early, practical v0 focused on native parser introspection.

## Status

- Version: `0.0.1` (experimental)
- Primary target: Python `argparse`
- Output shape: OpenCLI draft-compatible JSON
- Non-OpenCLI semantics are preserved in `metadata` (for example `count`, `append`, mutually-exclusive groups)

## Install

```bash
pip install jelp
```

For local development:

```bash
pip install -e .
```

## Quick Start (Existing argparse App)

### One-line enablement (recommended)

```python
from jelp.argparse import enable_jelp

parser = build_parser()
enable_jelp(parser, version=__version__)
args = parser.parse_args(argv)
```

That is enough. `enable_jelp(...)` installs:

- `--jelp` (compact JSON)
- `--jelp-pretty` (indented JSON)

When either flag is present, `parse_args()` emits JSON and exits with code `0`.

Default ordering is argparse-like:

- `mytool subcommand --jelp` -> subcommand JSON
- `mytool --jelp subcommand` -> root JSON

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

- Schema selection is out of v0; current target is OpenCLI draft shape.
- Defaults stay in metadata (`argparse.default`) for now.
- Repeatable behavior stays in metadata (`argparse.repeat_semantics`) for now.

See:

- [docs/v0-decisions.md](docs/v0-decisions.md)
- [docs/opencli-feedback-examples.md](docs/opencli-feedback-examples.md)
- [docs/task-tracker.md](docs/task-tracker.md)
- [docs/task-tracker-roadmap.md](docs/task-tracker-roadmap.md)

## Tests

```bash
PYTHONPATH=src pytest -q
```

## Why this project exists

Many CLIs already contain high-quality structural truth in their parser definitions. `jelp` surfaces that truth directly for automation, wrappers, doc tooling, and LLM systems.
