from __future__ import annotations

import argparse

from common import maybe_enable_jelp


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
    parser.add_argument("target", choices=["artifact", "snapshot", "draft"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.target == "artifact" and (not args.cache) and args.retries == 0:
        print("FLAG{cache-bool-71f0}")
        return 0

    hints: list[str] = []
    if args.target != "artifact":
        hints.append("target should be artifact")
    if args.cache:
        hints.append("cache should be disabled")
    if args.retries != 0:
        hints.append("retries should be 0")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
