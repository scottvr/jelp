from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture01-vault", description="Vault scanner"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--profile", choices=["dev", "prod"], default="dev")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", aliases=["sc"], help="Scan vault")
    scan.add_argument("path", choices=["./vault", "./tmp", "/"], help="Target path")
    scan.add_argument(
        "-v", "--verbose", action="count", default=0, help="Repeat for more detail"
    )
    scan.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.command == "scan"
        and args.profile == "prod"
        and args.path == "./vault"
        and args.format == "json"
        and args.verbose >= 2
    ):
        print("FLAG{vault-scan-e4b1}")
        return 0

    hints: list[str] = []
    if args.profile != "prod":
        hints.append("profile should be prod")
    if args.path != "./vault":
        hints.append("path should target ./vault")
    if args.format != "json":
        hints.append("json format helps")
    if args.verbose < 2:
        hints.append("repeated -v matters")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
