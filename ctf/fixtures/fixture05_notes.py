from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture05-notes", description="Notes generator"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--source", choices=["local", "remote"], default="local")

    subparsers = parser.add_subparsers(dest="command", required=True)

    notes = subparsers.add_parser("notes", aliases=["n"])
    notes.add_argument("--format", choices=["md", "json"], default="md")
    notes.add_argument("--out", choices=["report.md", "report.json"], required=True)
    notes.add_argument(
        "--group-by", choices=["type", "scope", "author"], default="type"
    )
    notes.add_argument(
        "range", choices=["HEAD~1..HEAD", "HEAD~5..HEAD", "v1.2.0..HEAD"]
    )

    changelog = subparsers.add_parser("changelog", aliases=["cl"])
    changelog.add_argument("--format", choices=["md", "json"], default="md")
    changelog.add_argument("range", choices=["HEAD~1..HEAD", "HEAD~10..HEAD"])

    summarize = subparsers.add_parser("summarize", aliases=["sum"])
    summarize.add_argument("--window", choices=["day", "week", "month"], default="week")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "notes"
        and args.source == "remote"
        and args.format == "json"
        and args.out == "report.json"
        and args.group_by == "scope"
        and args.range == "HEAD~5..HEAD"
    ):
        print("FLAG{notes-range-18de}")
        return 0

    checks = [
        (args.command == "notes", "use notes (or n)"),
        (args.source == "remote", "source should be remote"),
        (getattr(args, "format", None) == "json", "format should be json"),
        (getattr(args, "out", None) == "report.json", "out should be report.json"),
        (getattr(args, "group_by", None) == "scope", "group-by should be scope"),
        (
            getattr(args, "range", None) == "HEAD~5..HEAD",
            "range should span last 5 commits",
        ),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
