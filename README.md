# jelp: machine-readable CLI introspection contract

## Summary

`jelp` is a small library and companion CLI intended to expose an existing command-line tool's interface as structured JSON.

The initial implementation will target Python `argparse` and emit JSON shaped to the OpenCLI draft specification where possible, with any currently unmapped semantics placed into a `metadata` section.

The immediate proving ground is `cling`, where `jelp` will first be integrated as a `--jelp` option. Once validated there, the functionality can be spun out into its own `jelp` repository.

## Motivation

CLI tools already contain a large amount of structured information:

- commands and subcommands
- options and flags
- positional arguments
- defaults
- accepted values / choices
- aliases
- help text
- repeatability
- exclusivity groups

Today, that information is usually exposed primarily for humans via `--help`, and secondarily for shells via completion scripts. LLMs, wrappers, automation systems, and doc generators typically do not get a single portable machine-readable contract.

`jelp` aims to expose that contract directly.

## Non-goals for v0

The first milestone is not intended to solve all CLI introspection problems.

Not in scope for v0:

- perfect inference from arbitrary uncontrolled third-party tools
- man-page / prose / folklore / requirements-document inference
- non-Python language support
- shell completion generation
- a brand-new schema independent of OpenCLI
- support for every exotic custom `argparse.Action`

## Guiding principles

1. Native parser introspection first.
   - Prefer authoritative parser metadata over scraping `--help`.

2. Emit OpenCLI when possible.
   - Reuse an emerging schema rather than inventing one prematurely.

3. Preserve semantics even if OpenCLI lacks first-class fields.
   - Use `metadata` for things like `count`, `append`, mutually exclusive groups, etc.

4. Keep v0 tiny.
   - Start with `argparse`.
   - Start with one real tool (`cling`) and one synthetic fixture.

5. Separate "native integration" from "external analysis".
   - Source-modifiable path and uncontrolled-tool path are distinct products.

## Proposed phases

### Phase 0: experiment inside `cling`

Add a minimal `--jelp` mode to `cling` using native `argparse` introspection.

Deliverables:

- `cling --jelp`
- JSON output
- basic mapping to OpenCLI draft fields
- internal notes on gaps / pain points / missing schema concepts

Success criteria:

- command tree is represented correctly
- options and positionals are represented correctly
- subcommands and aliases are represented correctly
- repeat-count flags are not lost
- repeatable options are not lost
- mutually exclusive groups are not lost
- output is stable enough to compare in tests

### Phase 1: extract into standalone `jelp` repo

Spin the implementation out into a separate project once the `cling` prototype feels real.

Deliverables:

- `jelp` Python package
- `jelp.cli:main`
- `jelp.argparse` module
- reusable install/emit API
- synthetic demo fixture for tests

### Phase 2: uncontrolled tool analysis

Add paths for tools we do not control.

Potential approaches:

1. Runtime/native path
   - if the target tool already exposes machine-readable info or framework hooks

2. `--help` parsing
   - heuristic
   - lower confidence

3. `man` page parsing
   - even more heuristic

4. Ambient document inference
   - requirements docs, READMEs, examples, etc.
   - lowest confidence
   - likely a separate subsystem

All inferred fields should carry provenance and confidence.

## v0 target feature set

The v0 prototype should support these `argparse` concepts:

- top-level options
- top-level positionals
- subcommands
- subcommand aliases
- per-subcommand options/positionals
- `choices`
- `required`
- `nargs`
- repeatable list-like options (`append`, `extend`)
- repeat-count flags (`action='count'`, e.g. `-v`, `-vv`, `-vvv`)
- mutually exclusive groups
- hidden/help-suppressed options
- defaults
- basic help text / descriptions

Nice-to-have if already present in `cling`:

- `BooleanOptionalAction`
- argument groups
- custom actions

## Expected OpenCLI mapping

Where possible, map native `argparse` concepts into OpenCLI draft fields.

Likely straightforward:

- parser / command name
- description
- version
- commands
- aliases
- options
- arguments
- arity
- accepted values
- hidden
- examples

Likely needing temporary `metadata`:

- parser action type (`count`, `append`, `extend`, etc.)
- mutually exclusive group membership
- required mutual exclusion groups
- `dest`
- `metavar`
- `const`
- parser-specific behavior not directly modeled by OpenCLI
- possibly default values, depending on exact draft expectations

## Likely OpenCLI feedback from this experiment

Areas that may merit upstream feedback if validated during implementation:

- first-class support for mutually exclusive groups
- first-class support for argument implication / dependency relationships
- first-class support for repeat-count semantics
- first-class support for repeatable additive options
- provenance / confidence for inferred vs authoritative fields
- parser action semantics where operationally meaningful to tools and LLMs

## Minimal synthetic fixture for development

In addition to testing against `cling`, maintain a tiny purpose-built fixture to validate behavior deterministically.

Suggested fixture characteristics:

- `-v/--verbose` with `action='count'`
- `--format` with `choices`
- `--tag` with `action='append'`
- one mutually exclusive group such as `--dry-run` vs `--execute`
- one `scan` subcommand with its own positional and options
- one `push` subcommand with alias and its own options
- optional `BooleanOptionalAction`

This fixture should remain small enough to inspect by eye.

## Proposed API shape

### In-tool / source-modifiable usage

```python
from jelp.argparse import enable_jelp

parser = build_parser()
enable_jelp(parser)
```

Possible future variants:

```python
enable_jelp(parser, flag="--jelp")
enable_jelp(parser, pretty_flag="--jelp-pretty")
enable_jelp(parser, schema="opencli")
```

### Library-level emission

```python
from jelp.argparse import emit_opencli

data = emit_opencli(parser)
```

### Standalone CLI

```bash
jelp inspect python_module:build_parser
jelp inspect path/to/tool.py
jelp inspect /path/to/executable --help-fallback
```

## Design choice: auto-enable vs explicit enable

Initial recommendation:

Use explicit installation via a function call rather than import-side magic.

Rationale:

- keeps behavior obvious
- avoids modifying CLI surface merely by importing a module
- still imposes near-zero friction
- leaves room for later policy/configuration

This is not a rejection of convenience. It is just the cleaner default for v0.

## Testing strategy

### Unit tests

Test direct parser -> JSON emission for the synthetic fixture.

Assertions should include:

- root options exist
- subcommands exist
- aliases are preserved
- choices are preserved
- repeat-count option is marked correctly
- append/repeatable option is marked correctly
- mutually exclusive membership is preserved
- hidden options are omitted or marked as hidden appropriately

### Integration tests

Run against `cling` and verify:

- `cling --jelp` emits valid JSON
- emitted structure matches the actual CLI
- output remains stable across revisions unless intentionally changed

### Manual review

Use emitted JSON to answer practical questions such as:

- can an LLM discover valid subcommands?
- can an LLM tell which options belong to which subcommand?
- can an LLM avoid mutually exclusive conflicts?
- can an LLM understand whether repeated `-v` is meaningful?

## Initial implementation notes

- walk `ArgumentParser._actions`
- detect subparsers via the `_SubParsersAction`
- inspect parser `_mutually_exclusive_groups`
- treat help-suppressed actions carefully
- represent parser/action internals in a normalized intermediate model first
- emit OpenCLI from the intermediate model, rather than coupling traversal directly to final JSON shape

## Immediate next steps

1. Add a tiny emitter module inside `cling`.
2. Walk the existing `argparse` parser and dump a normalized intermediate structure.
3. Map that structure into approximate OpenCLI JSON.
4. Add `--jelp` to `cling`.
5. Test against:
   - subcommands
   - repeat-count verbosity
   - repeatable options
   - any mutually exclusive groups already present
6. Note every place where semantics are awkward or lossy.
7. Prepare concrete OpenCLI feedback if gaps are confirmed.

## Longer-term roadmap

After proving the concept in `cling`:

- create `jelp` standalone repository
- package reusable Python library
- expose `jelp` CLI
- support more `argparse` edge cases
- add `click` / `Typer`
- add fallback `--help` analysis
- add provenance/confidence model
- later consider:
  - Node
  - Go
  - Rust
  - C/C++

## Core thesis

A substantial amount of tool integration work is re-describing CLI affordances that the program already knows internally.

`jelp` attempts to expose that knowledge directly in a portable, machine-readable form.

## OpenCLI feedback notes

Notes captured while implementing the `cling --jelp` PoC against the vendored OpenCLI draft:

- `Conventions` naming mismatch between prose and schema:
  - `draft.md` describes `optionArgumentSeparator`
  - `schema.json` currently defines `optionSeparator`
- OpenCLI does not currently have first-class fields for `argparse` action semantics (`count`, `append`, `extend`), so these are emitted in `metadata`.
- OpenCLI does not currently have first-class mutually exclusive group semantics, so group membership and requiredness are emitted in `metadata`.
- Arity semantics for unbounded `nargs` (`*`/`+`) require omission of `maximum` in practice; this should be explicitly documented as canonical in the spec text.

---

# TODO

## Phase 0: prove the concept inside `cling`

### Core implementation

- [ ] Identify where `cling` builds its top-level `argparse.ArgumentParser`
- [ ] Add a tiny local emitter module inside `cling`
- [ ] Implement parser traversal over `ArgumentParser._actions`
- [ ] Detect and walk subcommands via `_SubParsersAction`
- [ ] Inspect `_mutually_exclusive_groups`
- [ ] Normalize parser data into an internal intermediate representation
- [ ] Emit OpenCLI-shaped JSON from the intermediate representation
- [ ] Add `--jelp` to `cling`
- [ ] Make `cling --jelp` print valid JSON and exit cleanly

### Coverage targets

- [ ] Top-level options
- [ ] Top-level positionals
- [ ] Subcommands
- [ ] Subcommand aliases
- [ ] Per-subcommand options
- [ ] Per-subcommand positionals
- [ ] `choices`
- [ ] `required`
- [ ] `nargs`
- [ ] `append`
- [ ] `extend` if present
- [ ] `count`
- [ ] Mutually exclusive groups
- [ ] Hidden/help-suppressed options
- [ ] Defaults
- [ ] Descriptions/help text

### Nice-to-have if already present in `cling`

- [ ] `BooleanOptionalAction`
- [ ] Argument groups
- [ ] Custom `Action` subclasses

## Intermediate model

### Required normalized fields

- [ ] Command name
- [ ] Command description
- [ ] Command aliases
- [ ] Options list
- [ ] Positional arguments list
- [ ] Nested subcommands
- [ ] Help text
- [ ] Accepted values / choices
- [ ] Arity / nargs
- [ ] Required flag
- [ ] Hidden flag

### Metadata fields for semantics not yet first-class in OpenCLI

- [ ] Parser action type (`store`, `store_true`, `store_false`, `append`, `extend`, `count`, etc.)
- [ ] Mutual exclusion group membership
- [ ] Whether a mutual exclusion group is required
- [ ] `dest`
- [ ] `metavar`
- [ ] `const`
- [ ] `default`
- [ ] Any parser-local behavior worth preserving

## OpenCLI mapping

### Straight mappings

- [ ] Program / command name
- [ ] Description
- [ ] Version
- [ ] Commands
- [ ] Aliases
- [ ] Options
- [ ] Arguments
- [ ] Accepted values
- [ ] Hidden
- [ ] Examples if available

### Mappings to verify carefully

- [ ] Exact `nargs` -> arity mapping
- [ ] How defaults should be represented
- [ ] Whether hidden/help-suppressed elements should be emitted or omitted
- [ ] Whether command aliases require any special handling
- [ ] Whether repeatable options can be represented without custom metadata

## Synthetic fixture

Create and maintain a tiny deterministic parser fixture separate from `cling`.

- [ ] `-v/--verbose` with `action='count'`
- [ ] `--format` with `choices`
- [ ] `--tag` with `action='append'`
- [ ] Mutually exclusive group: `--dry-run` vs `--execute`
- [ ] `scan` subcommand
- [ ] `push` subcommand
- [ ] Alias for one subcommand
- [ ] Optional `BooleanOptionalAction`

## Testing

### Unit tests on the synthetic fixture

- [ ] Root options emitted correctly
- [ ] Root positionals emitted correctly
- [ ] Subcommands emitted correctly
- [ ] Aliases preserved
- [ ] Choices preserved
- [ ] `count` preserved
- [ ] `append` preserved
- [ ] Mutual exclusion preserved
- [ ] Hidden/help-suppressed behavior correct
- [ ] JSON validates structurally

### Integration tests against `cling`

- [ ] `cling --jelp` returns valid JSON
- [ ] Emitted structure matches actual CLI behavior
- [ ] Output is stable enough for snapshot or golden-file testing
- [ ] Repeated `-v` semantics are visible
- [ ] Any existing mutually exclusive behavior is visible

### Manual validation questions

- [ ] Can an LLM discover valid subcommands from the emitted JSON?
- [ ] Can an LLM tell which options belong to which subcommand?
- [ ] Can an LLM avoid mutually exclusive conflicts?
- [ ] Can an LLM tell that `-vvv` is meaningful?
- [ ] Can a simple wrapper generate a useful synopsis from the JSON alone?

## Extraction into standalone `jelp` repo

### Packaging

- [ ] Create standalone repository
- [ ] Add `pyproject.toml`
- [ ] Package `jelp.argparse`
- [ ] Package `jelp.cli`
- [ ] Expose `jelp.cli:main`
- [ ] Add tests and fixtures
- [ ] Add README with native integration examples
- [ ] Add README with standalone inspection examples

### Public API

- [ ] `enable_jelp(parser, ...)`
- [ ] `emit_opencli(parser, ...)`
- [ ] Decide whether pretty-print mode belongs in the library or CLI
- [ ] Decide whether schema selection belongs in v0 or later

## Uncontrolled tool analysis track

Not for immediate implementation, but worth capturing now.

### Modes

- [ ] Runtime/native introspection if target already exposes metadata
- [ ] `--help` parsing
- [ ] `man` page parsing
- [ ] README / docs / examples inference
- [ ] Provenance tracking
- [ ] Confidence scoring

### Questions to answer later

- [ ] What minimum confidence threshold is acceptable for emitted facts?
- [ ] How should contradictory sources be handled?
- [ ] Should inferred and authoritative fields live side by side in the same output?
- [ ] Should uncontrolled-tool analysis be a separate command path?

## Potential upstream OpenCLI feedback

Capture concrete examples during implementation.

- [ ] Need first-class mutually exclusive groups
- [ ] Need first-class dependency / implication relationships
- [ ] Need first-class repeat-count semantics
- [ ] Need first-class repeatable additive option semantics
- [ ] Need provenance / confidence model for inferred data
- [ ] Need parser-action semantics where operationally meaningful

## First code artifacts to draft

- [ ] `cling/jelp_emit.py` or equivalent local prototype module
- [ ] `NormalizedCommand` data structure
- [ ] `NormalizedOption` data structure
- [ ] `NormalizedArgument` data structure
- [ ] `parser_to_normalized(parser)`
- [ ] `normalized_to_opencli(data)`
- [ ] `handle_jelp_flag(parser, argv)` integration point

## Immediate working order

1. [ ] Build the synthetic fixture
2. [ ] Walk `argparse` internals into a normalized model
3. [ ] Emit approximate OpenCLI JSON
4. [ ] Add `--jelp` to `cling`
5. [ ] Compare emitted JSON to real CLI behavior
6. [ ] Record awkward or lossy cases
7. [ ] Prepare concrete OpenCLI feedback if justified
