# jelp spin-out handoff (from changeling)

This document captures exactly what to move into a standalone `jelp` repository and how `cling` is already prepared to consume it.

## Current integration behavior in `cling`

`cling` now routes OpenCLI emission through a bridge module:

- `src/changeling/jelp_bridge.py`

Behavior:

1. Try import: `from jelp.argparse import emit_opencli`
2. If unavailable, fall back to local: `from changeling.jelp import emit_opencli`

This means once `jelp` is packaged and installed in the same environment, `cling --jelp` and `cling --jelp-pretty` can use the external package without changing CLI call sites.

## API contract to preserve in standalone `jelp`

Target import path:

```python
from jelp.argparse import emit_opencli
```

Recommended callable shape (fully compatible with current bridge invocation):

```python
def emit_opencli(
    parser: argparse.ArgumentParser,
    *,
    version: str,
    opencli_version: str = "0.1.0",
) -> dict[str, Any]:
    ...
```

The bridge is tolerant if `opencli_version` is omitted in the standalone API.

## Files to copy as initial seed for the new `jelp` repo

- `src/changeling/jelp.py` (core parser traversal + OpenCLI projection)
- `tests/test_jelp.py` (adapt imports to `jelp.argparse` as needed)
- `docs/architecture/open-cli/schema.json` (vendored schema reference for tests)

## Minimal package layout suggestion for new repo

```text
jelp/
  pyproject.toml
  src/jelp/__init__.py
  src/jelp/argparse.py
  tests/test_argparse_emit.py
  schemas/opencli-0.1/schema.json
```

## Migration steps (safe order)

1. Copy `changeling` local emitter logic into `src/jelp/argparse.py`.
2. Port tests and make them pass in standalone repo.
3. Publish/install `jelp` into the same venv as `cling`.
4. Run `cling --jelp` and verify output unchanged (or intentionally changed with snapshots updated).
5. Remove local fallback emitter from `changeling` only after confidence window.

## Recommended cleanup in `changeling` after external package is stable

- Keep `jelp_bridge.py`, but drop fallback import path to `changeling.jelp`.
- Remove local emitter module and local emitter tests if external dependency is mandatory.
- Keep CLI integration tests that validate `--jelp` and `--jelp-pretty` behavior.
