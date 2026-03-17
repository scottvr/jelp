# Task Tracker

This checklist was moved out of `README.md` so status updates stay lightweight.

## Phase 0: prove the concept inside `cling`

### Core implementation

- [x] Identify where `cling` builds its top-level `argparse.ArgumentParser`
- [x] Add a tiny local emitter module inside `cling`
- [x] Implement parser traversal over `ArgumentParser._actions`
- [x] Detect and walk subcommands via `_SubParsersAction`
- [x] Inspect `_mutually_exclusive_groups`
- [x] Normalize parser data into an internal intermediate representation
- [x] Emit OpenCLI-shaped JSON from the intermediate representation
- [x] Add `--jelp` to `cling`
- [x] Make `cling --jelp` print valid JSON and exit cleanly

### Coverage targets

- [x] Top-level options
- [x] Top-level positionals
- [x] Subcommands
- [x] Subcommand aliases
- [x] Per-subcommand options
- [x] Per-subcommand positionals
- [x] `choices`
- [x] `required`
- [x] `nargs`
- [x] `append`
- [x] `extend` if present
- [x] `count`
- [x] Mutually exclusive groups
- [x] Hidden/help-suppressed options
- [x] Defaults
- [x] Descriptions/help text

## Intermediate model

### Required normalized fields

- [x] Command name
- [x] Command description
- [x] Command aliases
- [x] Options list
- [x] Positional arguments list
- [x] Nested subcommands
- [x] Help text
- [x] Accepted values / choices
- [x] Arity / nargs
- [x] Required flag
- [x] Hidden flag

### Metadata fields for semantics not yet first-class in OpenCLI

- [x] Parser action type (`store`, `store_true`, `store_false`, `append`, `extend`, `count`, etc.)
- [x] Mutual exclusion group membership
- [x] Whether a mutual exclusion group is required
- [x] `dest`
- [x] `metavar`
- [x] `const`
- [x] `default`
- [x] Any parser-local behavior worth preserving

## OpenCLI mapping

### Straight mappings

- [x] Program / command name
- [x] Description
- [x] Version
- [x] Commands
- [x] Aliases
- [x] Options
- [x] Arguments
- [x] Accepted values
- [x] Hidden
- [ ] Examples if available

### Mappings to verify carefully

- [x] Exact `nargs` -> arity mapping
- [ ] How defaults should be represented
- [x] Whether hidden/help-suppressed elements should be emitted or omitted
- [x] Whether command aliases require any special handling
- [ ] Whether repeatable options can be represented without custom metadata

## Synthetic fixture

Create and maintain a tiny deterministic parser fixture

- [x] `-v/--verbose` with `action='count'`
- [x] `--format` with `choices`
- [x] `--tag` with `action='append'`
- [x] Mutually exclusive group: `--dry-run` vs `--execute`
- [x] `scan` subcommand
- [x] `push` subcommand
- [x] Alias for one subcommand
- [ ] Optional `BooleanOptionalAction`

## Testing

### Unit tests on the synthetic fixture

- [x] Root options emitted correctly
- [ ] Root positionals emitted correctly
- [x] Subcommands emitted correctly
- [x] Aliases preserved
- [x] Choices preserved
- [x] `count` preserved
- [x] `append` preserved
- [x] Mutual exclusion preserved
- [x] Hidden/help-suppressed behavior correct
- [x] JSON validates structurally

### Manual validation questions

- [ ] Can an LLM discover valid subcommands from the emitted JSON?
- [ ] Can an LLM tell which options belong to which subcommand?
- [ ] Can an LLM avoid mutually exclusive conflicts?
- [ ] Can an LLM tell that `-vvv` is meaningful?
- [ ] Can a simple wrapper generate a useful synopsis from the JSON alone?

### Public API

- [ ] `enable_jelp(parser, ...)`
- [x] `emit_opencli(parser, ...)`
- [x] Decide whether pretty-print mode belongs in the library or CLI
- [ ] Decide whether schema selection belongs in v0 or later

## Potential upstream OpenCLI feedback

Capture concrete examples during implementation.

- [x] Need first-class mutually exclusive groups
- [ ] Need first-class dependency / implication relationships
- [x] Need first-class repeat-count semantics
- [x] Need first-class repeatable additive option semantics
- [ ] Need provenance / confidence model for inferred data
- [x] Need parser-action semantics where operationally meaningful

## First code artifacts to draft

- [x] `NormalizedCommand` data structure
- [x] `NormalizedOption` data structure
- [x] `NormalizedArgument` data structure
- [x] `parser_to_normalized(parser)`
- [x] `normalized_to_opencli(data)`
- [ ] `handle_jelp_flag(parser, argv)` integration point

## Immediate working order

1. [x] Build the synthetic fixture
2. [x] Walk `argparse` internals into a normalized model
3. [x] Emit approximate OpenCLI JSON
4. [ ] Compare emitted JSON to real CLI behavior
5. [x] Record awkward or lossy cases
6. [x] Prepare concrete OpenCLI feedback if justified
