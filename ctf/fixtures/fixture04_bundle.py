from __future__ import annotations

import argparse

from common import maybe_enable_jelp, render_hint


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fixture04-bundle", description="Bundle packer"
    )
    maybe_enable_jelp(parser)
    parser.add_argument("--profile", choices=["dev", "ci"], default="dev")

    subparsers = parser.add_subparsers(dest="command", required=True)

    pack = subparsers.add_parser("pack")
    pack.add_argument(
        "files",
        nargs="+",
        choices=["a.txt", "b.txt", "c.txt", "notes.md", "manifest.json"],
    )
    pack.add_argument("--compress", choices=["gz", "zst"], required=True)
    pack.add_argument("--level", type=int, choices=[1, 3, 6, 9], default=1)
    pack.add_argument("--sign", action="store_true")

    unpack = subparsers.add_parser("unpack")
    unpack.add_argument("bundle", choices=["bundle.tar.gz", "bundle.tar.zst"])
    unpack.add_argument("--verify", action="store_true")

    verify = subparsers.add_parser("verify")
    verify.add_argument("artifact", choices=["bundle-a", "bundle-b"])
    verify.add_argument("--strict", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    needed = {"a.txt", "b.txt", "c.txt"}
    if (
        args.command == "pack"
        and args.profile == "ci"
        and needed.issubset(set(args.files))
        and args.compress == "zst"
        and args.level == 9
        and args.sign
    ):
        print("FLAG{bundle-zst-2c4f}")
        return 0

    checks = [
        (args.command == "pack", "use the pack subcommand"),
        (args.profile == "ci", "profile should be ci"),
        (
            needed.issubset(set(getattr(args, "files", []))),
            "include files a.txt,b.txt,c.txt",
        ),
        (getattr(args, "compress", None) == "zst", "compression should be zst"),
        (getattr(args, "level", None) == 9, "level should be 9"),
        (bool(getattr(args, "sign", False)), "signing should be enabled"),
    ]
    print(render_hint(checks))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
