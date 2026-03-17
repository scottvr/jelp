from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture05-notes", description="Notes generator"
    )
    maybe_enable_jelp(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    notes = subparsers.add_parser("notes", aliases=["n"])
    notes.add_argument("--format", choices=["md", "json"], default="md")
    notes.add_argument("--out", choices=["report.md", "report.json"], required=True)
    notes.add_argument("range", choices=["HEAD~1..HEAD", "HEAD~5..HEAD"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "notes"
        and args.format == "json"
        and args.out == "report.json"
        and args.range == "HEAD~5..HEAD"
    ):
        print("FLAG{notes-range-18de}")
        return 0

    hints: list[str] = []
    if args.format != "json":
        hints.append("format should be json")
    if args.out != "report.json":
        hints.append("out should be report.json")
    if args.range != "HEAD~5..HEAD":
        hints.append("range should span last 5 commits")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
