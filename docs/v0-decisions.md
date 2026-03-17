# v0 Decisions

## Schema Selection

Decision: schema selection stays out of v0.

Rationale:

- OpenCLI is still draft-stage.
- v0 should stay narrow and stable around one emission target.
- The library already exposes `opencli_version` for version stamping, which is enough for current usage.

Current behavior:

- `emit_opencli(..., opencli_version=...)` controls the emitted `opencli` field.
- No multi-schema switch is exposed in `jelp.cli` for v0.

## Defaults Representation

Decision: represent defaults in metadata for now.

Current behavior:

- `argparse.default` is emitted in per-option/per-argument metadata when default is not `argparse.SUPPRESS`.

Why:

- OpenCLI draft schema does not define first-class default fields on options/arguments.
- Metadata preserves semantics without inventing non-standard fields.

## Repeatable Option Semantics

Decision: keep repeat semantics in metadata for v0.

Current behavior:

- `argparse.repeat_semantics` is emitted for `append`, `extend`, and `count`.

Why:

- OpenCLI draft schema does not currently model repeat-count or additive-repeat option behavior as first-class semantics.

## Examples Mapping

Decision: emit examples when parser authors provide them.

Current behavior:

- If parser sets `parser.jelp_examples` (string or iterable of strings), it is emitted as OpenCLI `examples`.
- The same convention applies to subcommand parsers.
