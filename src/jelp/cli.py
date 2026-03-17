from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version as package_version

from . import __version__
from .argparse import emit_opencli


def _add_shared_command_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since-last-tag", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--exclude-path", action="append", default=[])
    parser.add_argument("--exclude-kind", action="append", default=[])
    parser.add_argument("--exclude-warning", action="append", default=[])
    parser.add_argument("--group-threshold", type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jelp", description="jelp CLI")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--cache-mode")
    parser.add_argument("--jelp", action="store_true")
    parser.add_argument("--jelp-pretty", action="store_true")

    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze")
    _add_shared_command_options(analyze)
    analyze.add_argument("--json", action="store_true")
    analyze.add_argument("--markdown", action="store_true")
    analyze.add_argument("range")

    notes = subparsers.add_parser("notes")
    _add_shared_command_options(notes)
    notes.add_argument("--format")
    notes.add_argument("--input")
    notes.add_argument("--prefer-enriched", action="store_true")
    notes.add_argument("--source")
    notes.add_argument("--show-evidence", action="store_true")
    notes.add_argument("--evidence-out")
    notes.add_argument("--evidence-format")
    notes.add_argument("--out")
    notes.add_argument("--note-order")
    notes.add_argument("range")

    review = subparsers.add_parser("review")
    _add_shared_command_options(review)
    review.add_argument("--out")
    review.add_argument("range")

    enrich = subparsers.add_parser("enrich")
    _add_shared_command_options(enrich)
    enrich.add_argument("--backend")
    enrich.add_argument("--model")
    enrich.add_argument("--base-url")
    enrich.add_argument("--api-key")
    enrich.add_argument("--max-clusters", type=int)
    enrich.add_argument("--retries", type=int)
    enrich.add_argument("--retry-base-delay", type=float)
    enrich.add_argument("--retry-max-delay", type=float)
    enrich.add_argument("--rate-limit-rps", type=float)
    enrich.add_argument("--input")
    enrich.add_argument("--out")
    enrich.add_argument("range")

    return parser


def _resolved_version() -> str:
    try:
        return package_version("jelp")
    except PackageNotFoundError:
        return __version__


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.jelp or args.jelp_pretty:
        payload = emit_opencli(parser, version=_resolved_version())
        indent = 2 if args.jelp_pretty else None
        json.dump(payload, sys.stdout, indent=indent)
        sys.stdout.write("\n")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
