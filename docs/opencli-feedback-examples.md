# OpenCLI Feedback Examples

Concrete feedback from `jelp` v0 implementation and tests.

## Dependency / Implication Relationships

Observed need:

- CLIs often require relationships like "if `--json` is set, `--out` is required" or "this option implies that mode".

Current gap:

- OpenCLI draft has no first-class field for implication/dependency constraints.

Current `jelp` posture:

- Preserve what `argparse` exposes in metadata when available.
- Recommend first-class relationship fields upstream so tooling/LLMs do not infer behavior heuristically.

## Provenance / Confidence for Inferred Data

Observed need:

- Native parser introspection is authoritative.
- Future uncontrolled-tool modes (`--help`, `man`, docs inference) are heuristic.

Current gap:

- OpenCLI draft has no standardized provenance/confidence shape for inferred vs authoritative fields.

Current `jelp` posture:

- v0 remains native-introspection only.
- Propose upstream model for source/provenance/confidence once heuristic modes are added.
