from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture08-nested", description="Nested commands"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--env", choices=["dev", "stage", "prod"], default="dev")

    top = parser.add_subparsers(dest="top", required=True)

    db = top.add_parser("db")
    db_sub = db.add_subparsers(dest="dbcmd", required=True)

    migrate = db_sub.add_parser("migrate")
    migrate.add_argument("--to", choices=["v41", "v42", "v43"], required=True)
    migrate.add_argument("--online", action="store_true")
    migrate.add_argument("--lock-step", action="store_true")

    status = db_sub.add_parser("status")
    status.add_argument("--format", choices=["text", "json"], default="text")

    cache = top.add_parser("cache")
    cache_sub = cache.add_subparsers(dest="cachecmd", required=True)

    prune = cache_sub.add_parser("prune")
    prune.add_argument("--scope", choices=["all", "hot", "cold"], required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if (
        args.top == "db"
        and args.dbcmd == "migrate"
        and args.env == "prod"
        and args.to == "v42"
        and args.online
        and args.lock_step
    ):
        print("FLAG{nested-db-b19c}")
        return 0

    checks = [
        (args.top == "db", "use top-level db command"),
        (getattr(args, "dbcmd", None) == "migrate", "use db migrate"),
        (args.env == "prod", "env should be prod"),
        (getattr(args, "to", None) == "v42", "migrate target should be v42"),
        (bool(getattr(args, "online", False)), "online mode should be enabled"),
        (bool(getattr(args, "lock_step", False)), "lock-step should be enabled"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
