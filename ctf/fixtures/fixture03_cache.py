from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture03-cache", description="Cache toggles"
    )
    maybe_enable_jelp(parser)

    if hasattr(argparse, "BooleanOptionalAction"):
        parser.add_argument(
            "--cache", action=argparse.BooleanOptionalAction, default=True
        )
    else:
        parser.add_argument("--cache", action="store_true", default=True)
        parser.add_argument("--no-cache", action="store_false", dest="cache")
    parser.add_argument("--retries", type=int, choices=[0, 1, 2, 3], default=3)

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch", aliases=["pull"])
    fetch.add_argument("target", choices=["artifact", "snapshot", "draft"])
    fetch.add_argument("--tier", choices=["hot", "warm", "cold"], default="warm")

    prime = subparsers.add_parser("prime")
    prime.add_argument("--seed", choices=["alpha", "beta", "rc"], required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "fetch"
        and args.target == "artifact"
        and args.tier == "cold"
        and (not args.cache)
        and args.retries == 0
    ):
        print("FLAG{cache-bool-71f0}")
        return 0

    checks = [
        (args.command == "fetch", "use fetch (or pull)"),
        (getattr(args, "target", None) == "artifact", "target should be artifact"),
        (getattr(args, "tier", None) == "cold", "tier should be cold"),
        ((not args.cache), "cache should be disabled"),
        (args.retries == 0, "retries should be 0"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
