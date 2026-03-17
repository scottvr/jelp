from __future__ import annotations

import sys
from pathlib import Path


def _ensure_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "src"
    for candidate in (repo_root, src):
        value = str(candidate)
        if value not in sys.path:
            sys.path.insert(0, value)


_ensure_import_paths()
