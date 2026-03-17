from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture01-vault", description="Vault scanner"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--profile", choices=["dev", "prod"], default="dev")
    parser.add_argument("--zone", choices=["edge", "core"], default="edge")

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", aliases=["sc"], help="Scan vault")
    scan.add_argument("path", choices=["./vault", "./tmp", "/"], help="Target path")
    scan.add_argument(
        "-v", "--verbose", action="count", default=0, help="Repeat for more detail"
    )
    scan.add_argument("--format", choices=["text", "json"], default="text")
    scan.add_argument("--engine", choices=["fast", "safe"], default="fast")

    index = subparsers.add_parser("index", aliases=["ix"], help="Index metadata")
    index.add_argument("scope", choices=["local", "global"], default="local")
    index.add_argument("--rebuild", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "scan"
        and args.profile == "prod"
        and args.zone == "core"
        and args.path == "./vault"
        and args.format == "json"
        and args.engine == "safe"
        and args.verbose >= 2
    ):
        print("FLAG{vault-scan-e4b1}")
        return 0

    checks = [
        (args.command == "scan", "use the scan subcommand"),
        (args.profile == "prod", "profile should be prod"),
        (args.zone == "core", "zone should be core"),
        (getattr(args, "path", None) == "./vault", "path should target ./vault"),
        (getattr(args, "format", None) == "json", "json output helps"),
        (getattr(args, "engine", None) == "safe", "engine should be safe"),
        (getattr(args, "verbose", 0) >= 2, "repeat -v twice"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
