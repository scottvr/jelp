from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from jelp.argparse import enable_jelp


@dataclass(frozen=True)
class JelpRuntimeMode:
    name: str
    allow_jelp: bool


_ALLOWED_MODES: dict[str, JelpRuntimeMode] = {
    "help-only": JelpRuntimeMode(name="help-only", allow_jelp=False),
    "jelp-useful": JelpRuntimeMode(name="jelp-useful", allow_jelp=True),
    "jelp-no-meta": JelpRuntimeMode(name="jelp-no-meta", allow_jelp=True),
    "jelp-all": JelpRuntimeMode(name="jelp-all", allow_jelp=True),
}


def runtime_mode() -> JelpRuntimeMode:
    raw = os.getenv("JELP_MODE", "help-only")
    return _ALLOWED_MODES.get(raw, _ALLOWED_MODES["help-only"])


def maybe_enable_jelp(parser: argparse.ArgumentParser) -> None:
    mode = runtime_mode()
    if not mode.allow_jelp:
        return
    enable_jelp(parser, version="ctf-0.1.0")
