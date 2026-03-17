from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture02-release", description="Release gate"
    )
    maybe_enable_jelp(parser)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)
    release = subparsers.add_parser("release", aliases=["push"])
    release.add_argument("--region", choices=["us", "eu"], required=True)
    release.add_argument(
        "--tag",
        action="append",
        choices=["blue", "green", "release"],
        default=[],
        help="Repeatable release labels",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    tags = set(args.tag)
    if (
        args.command == "release"
        and args.execute
        and args.region == "eu"
        and {"blue", "green"}.issubset(tags)
    ):
        print("FLAG{release-gate-9a2d}")
        return 0

    hints: list[str] = []
    if not args.execute:
        hints.append("must execute, not dry-run")
    if args.region != "eu":
        hints.append("region should be eu")
    if not {"blue", "green"}.issubset(tags):
        hints.append("need repeated --tag values blue and green")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
