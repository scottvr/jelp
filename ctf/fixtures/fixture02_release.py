from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture02-release", description="Release gate"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--channel", choices=["stable", "canary"], default="stable")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    release = subparsers.add_parser("release", aliases=["push"])
    release.add_argument("--region", choices=["us", "eu", "ap"], required=True)
    release.add_argument("--window", choices=["am", "pm"], default="pm")
    release.add_argument(
        "--tag",
        action="append",
        choices=["blue", "green", "release", "hotfix"],
        default=[],
        help="Repeatable release labels",
    )

    promote = subparsers.add_parser("promote", help="Promote staged candidate")
    promote.add_argument("--stage", choices=["qa", "preprod", "prod"], required=True)
    promote.add_argument(
        "--ticket", choices=["CHG-100", "CHG-200", "CHG-300"], required=True
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    tags = set(getattr(args, "tag", []))
    if (
        args.command == "release"
        and args.execute
        and args.channel == "canary"
        and args.region == "eu"
        and args.window == "am"
        and {"blue", "green"}.issubset(tags)
    ):
        print("FLAG{release-gate-9a2d}")
        return 0

    checks = [
        (args.command == "release", "use the release subcommand"),
        (args.execute, "must execute, not dry-run"),
        (args.channel == "canary", "channel should be canary"),
        (getattr(args, "region", None) == "eu", "region should be eu"),
        (getattr(args, "window", None) == "am", "window should be am"),
        ({"blue", "green"}.issubset(tags), "repeat --tag with blue and green"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
