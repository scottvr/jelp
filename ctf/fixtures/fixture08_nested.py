from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture08-nested", description="Nested commands"
    )
    maybe_enable_jelp(parser)

    top = parser.add_subparsers(dest="top", required=True)
    db = top.add_parser("db")
    db_sub = db.add_subparsers(dest="dbcmd", required=True)

    migrate = db_sub.add_parser("migrate")
    migrate.add_argument("--to", choices=["v41", "v42", "v43"], required=True)
    migrate.add_argument("--online", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.top == "db"
        and args.dbcmd == "migrate"
        and args.to == "v42"
        and args.online
    ):
        print("FLAG{nested-db-b19c}")
        return 0

    hints: list[str] = []
    if args.to != "v42":
        hints.append("migrate target should be v42")
    if not args.online:
        hints.append("online mode should be enabled")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
