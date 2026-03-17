from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fixture07-alias", description="Alias maze")
    maybe_enable_jelp(parser)
    parser.add_argument("--workspace", choices=["poly", "mono"], default="poly")

    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", aliases=["peek"])
    inspect.add_argument(
        "-q", "--query", choices=["owners", "deps", "paths"], required=True
    )
    inspect.add_argument("--depth", type=int, choices=[1, 2, 3], default=1)
    inspect.add_argument("--mode", choices=["shallow", "full"], default="shallow")

    graph = subparsers.add_parser("graph", aliases=["g"])
    graph.add_argument("--focus", choices=["services", "libraries"], required=True)
    graph.add_argument("--depth", type=int, choices=[1, 2, 3], default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "inspect"
        and args.workspace == "mono"
        and args.query == "deps"
        and args.depth == 3
        and args.mode == "full"
    ):
        print("FLAG{alias-maze-6b7e}")
        return 0

    checks = [
        (args.command == "inspect", "use inspect (or peek)"),
        (args.workspace == "mono", "workspace should be mono"),
        (getattr(args, "query", None) == "deps", "query should inspect dependencies"),
        (getattr(args, "depth", None) == 3, "depth should be 3"),
        (getattr(args, "mode", None) == "full", "mode should be full"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
