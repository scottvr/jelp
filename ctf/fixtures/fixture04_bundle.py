from __future__ import annotations

import argparse

from common import maybe_enable_jelp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture04-bundle", description="Bundle packer"
    )
    maybe_enable_jelp(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack = subparsers.add_parser("pack")
    pack.add_argument(
        "files", nargs="+", choices=["a.txt", "b.txt", "c.txt", "notes.md"]
    )
    pack.add_argument("--compress", choices=["gz", "zst"], required=True)
    pack.add_argument("--level", type=int, choices=[1, 3, 6, 9], default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    needed = {"a.txt", "b.txt", "c.txt"}
    if (
        args.command == "pack"
        and needed.issubset(set(args.files))
        and args.compress == "zst"
        and args.level == 9
    ):
        print("FLAG{bundle-zst-2c4f}")
        return 0

    hints: list[str] = []
    if not needed.issubset(set(args.files)):
        hints.append("include files a.txt,b.txt,c.txt")
    if args.compress != "zst":
        hints.append("compression should be zst")
    if args.level != 9:
        hints.append("level should be 9")

    print("HINT: " + "; ".join(hints) if hints else "No flag")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
