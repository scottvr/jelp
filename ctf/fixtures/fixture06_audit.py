from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fixture06-audit", description="Audit runner")
    maybe_enable_jelp(parser)
    parser.add_argument("--severity", choices=["low", "med", "high"], default="low")
    parser.add_argument(
        "--exclude", choices=["vendor", "tests", "docs"], action="append", default=[]
    )
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("path", choices=["src/", "docs/", "tests/"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    needed_excludes = {"vendor", "tests"}
    if (
        args.severity == "high"
        and args.strict
        and needed_excludes.issubset(set(args.exclude))
        and args.path == "src/"
    ):
        print("FLAG{audit-strict-53aa}")
        return 0

    hints: list[str] = []
    if args.severity != "high":
        hints.append("severity should be high")
    if not args.strict:
        hints.append("strict mode should be enabled")
    if not needed_excludes.issubset(set(args.exclude)):
        hints.append("exclude both vendor and tests")
    if args.path != "src/":
        hints.append("path should be src/")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
