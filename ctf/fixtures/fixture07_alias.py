from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fixture07-alias", description="Alias maze")
    maybe_enable_jelp(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", aliases=["peek"])
    inspect.add_argument(
        "-q", "--query", choices=["owners", "deps", "paths"], required=True
    )
    inspect.add_argument("--depth", type=int, choices=[1, 2, 3], default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect" and args.query == "deps" and args.depth == 3:
        print("FLAG{alias-maze-6b7e}")
        return 0

    hints: list[str] = []
    if args.query != "deps":
        hints.append("query should inspect dependencies")
    if args.depth != 3:
        hints.append("depth should be 3")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
