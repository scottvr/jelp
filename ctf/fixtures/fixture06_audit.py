from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fixture06-audit", description="Audit runner")
    maybe_enable_jelp(parser)
    parser.add_argument("--profile", choices=["baseline", "strict"], default="baseline")

    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--severity", choices=["low", "med", "high"], default="low")
    run.add_argument(
        "--exclude", choices=["vendor", "tests", "docs"], action="append", default=[]
    )
    run.add_argument("--strict", action="store_true")
    run.add_argument("path", choices=["src/", "docs/", "tests/"])

    report = subparsers.add_parser("report")
    report.add_argument("--format", choices=["text", "json"], default="text")
    report.add_argument("path", choices=["src/", "docs/", "tests/"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    needed_excludes = {"vendor", "tests"}
    if (
        args.command == "run"
        and args.profile == "strict"
        and args.severity == "high"
        and args.strict
        and needed_excludes.issubset(set(args.exclude))
        and args.path == "src/"
    ):
        print("FLAG{audit-strict-53aa}")
        return 0

    checks = [
        (args.command == "run", "use the run subcommand"),
        (args.profile == "strict", "profile should be strict"),
        (getattr(args, "severity", None) == "high", "severity should be high"),
        (bool(getattr(args, "strict", False)), "strict mode should be enabled"),
        (
            needed_excludes.issubset(set(getattr(args, "exclude", []))),
            "exclude both vendor and tests",
        ),
        (getattr(args, "path", None) == "src/", "path should be src/"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
