import argparse
import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jelp.cli import build_parser, main as cli_main
from jelp import emit_opencli, enable_jelp, handle_jelp_flag, parser_to_normalized

try:
    from jsonschema import validate
except ImportError:  # pragma: no cover - dependency gate
    validate = None


class JelpTests(unittest.TestCase):
    def _fixture_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog="fixture", description="Fixture CLI")
        parser.jelp_examples = ["fixture --format json scan /tmp"]  # type: ignore[attr-defined]
        parser.add_argument(
            "-v", "--verbose", action="count", default=0, help="Increase verbosity."
        )
        parser.add_argument("--format", choices=["json", "text"], help="Output format.")
        parser.add_argument("--tag", action="append", default=[], help="Attach tags.")
        parser.add_argument("root_path", nargs="?", help="Optional root path.")
        parser.add_argument("--secret", help=argparse.SUPPRESS)
        if hasattr(argparse, "BooleanOptionalAction"):
            parser.add_argument(
                "--color",
                action=argparse.BooleanOptionalAction,
                default=True,
                help="Color output.",
            )

        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true", help="Dry run mode.")
        mode.add_argument("--execute", action="store_true", help="Execute mode.")

        subparsers = parser.add_subparsers(dest="command", required=True)
        scan = subparsers.add_parser("scan", help="Scan files.")
        scan.add_argument("path")

        push = subparsers.add_parser("push", aliases=["ship"], help="Push outputs.")
        push.add_argument("--force", action="store_true", help="Force push.")
        return parser

    def _metadata_value(self, metadata: list[dict[str, object]], name: str):
        for entry in metadata:
            if entry["name"] == name:
                return entry["value"]
        return None

    def _sanitize_snapshot(self, payload: dict[str, object]) -> dict[str, object]:
        commands = payload.get("commands", [])
        return {
            "opencli": payload["opencli"],
            "info": {
                "title": payload["info"]["title"],
                "version": payload["info"]["version"],
            },
            "root_options": [option["name"] for option in payload.get("options", [])],
            "commands": [command["name"] for command in commands],
            "command_options": {
                command["name"]: [
                    option["name"] for option in command.get("options", [])
                ]
                for command in commands
            },
            "command_arguments": {
                command["name"]: [
                    argument["name"] for argument in command.get("arguments", [])
                ]
                for command in commands
            },
        }

    def test_parser_to_normalized_preserves_key_argparse_semantics(self) -> None:
        parser = self._fixture_parser()
        normalized = parser_to_normalized(parser, version="9.9.9")

        self.assertEqual(normalized.opencli, "0.1.0")
        self.assertEqual(normalized.info["title"], "fixture")
        self.assertEqual(normalized.info["version"], "9.9.9")
        self.assertEqual(normalized.examples, ["fixture --format json scan /tmp"])

        options_by_name = {option.name: option for option in normalized.options}
        self.assertIn("--verbose", options_by_name)
        self.assertIn("--tag", options_by_name)
        self.assertIn("--format", options_by_name)
        self.assertIn("--secret", options_by_name)

        verbose = options_by_name["--verbose"].to_opencli()
        tag = options_by_name["--tag"].to_opencli()
        fmt = options_by_name["--format"].to_opencli()
        secret = options_by_name["--secret"].to_opencli()

        self.assertEqual(
            self._metadata_value(verbose["metadata"], "argparse.action"), "count"
        )
        self.assertEqual(
            self._metadata_value(verbose["metadata"], "argparse.repeat_semantics"),
            "count",
        )
        self.assertEqual(
            self._metadata_value(tag["metadata"], "argparse.action"), "append"
        )
        self.assertEqual(
            self._metadata_value(tag["metadata"], "argparse.repeat_semantics"), "append"
        )
        self.assertEqual(fmt["arguments"][0]["acceptedValues"], ["json", "text"])
        self.assertTrue(secret["hidden"])
        self.assertIn("root_path", [argument.name for argument in normalized.arguments])
        if "--color" in options_by_name:
            color = options_by_name["--color"].to_opencli()
            self.assertEqual(
                self._metadata_value(color["metadata"], "argparse.action"),
                "boolean_optional",
            )
            self.assertIn("--no-color", color["aliases"])

        root_metadata = [entry.to_opencli() for entry in normalized.metadata]
        mxg = self._metadata_value(root_metadata, "argparse.mutually_exclusive_groups")
        self.assertIsInstance(mxg, list)
        self.assertEqual(mxg[0]["required"], True)
        self.assertEqual(mxg[0]["members"], ["--dry-run", "--execute"])

        commands_by_name = {command.name: command for command in normalized.commands}
        self.assertIn("scan", commands_by_name)
        self.assertIn("push", commands_by_name)
        self.assertEqual(commands_by_name["push"].aliases, ["ship"])

    def test_emit_opencli_validates_against_vendored_schema(self) -> None:
        if validate is None:
            self.skipTest("jsonschema is not installed")

        parser = self._fixture_parser()
        payload = emit_opencli(parser, version="1.2.3")

        schema_path = (
            Path(__file__).resolve().parents[1] / "schemas" / "open-cli" / "schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validate(instance=payload, schema=schema)

    def test_cli_jelp_emits_json_and_exits_successfully(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            rc = cli_main(["--jelp"])

        self.assertEqual(rc, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["opencli"], "0.1.0")
        self.assertEqual(payload["info"]["title"], "jelp")

        command_names = [command["name"] for command in payload.get("commands", [])]
        self.assertEqual(command_names, ["analyze", "notes", "review", "enrich"])

        root_options = [option["name"] for option in payload.get("options", [])]
        self.assertEqual(
            root_options,
            [
                "--help",
                "--verbose",
                "--cache-mode",
                "--jelp",
                "--jelp-pretty",
                "--jelp-no-meta",
                "--jelp-all",
                "--jelp-all-commands",
                "--jelp-all-no-meta",
            ],
        )

    def test_cli_jelp_pretty_emits_indented_json(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            rc = cli_main(["--jelp-pretty"])

        self.assertEqual(rc, 0)
        rendered = stdout.getvalue()
        self.assertTrue(rendered.startswith("{\n"))

        payload = json.loads(rendered)
        self.assertEqual(payload["opencli"], "0.1.0")

    def test_cli_jelp_snapshot_sanitized_shape_is_stable(self) -> None:
        payload = emit_opencli(build_parser(), version="1.0.1")
        snapshot = self._sanitize_snapshot(payload)

        self.assertEqual(
            snapshot,
            {
                "opencli": "0.1.0",
                "info": {"title": "jelp", "version": "1.0.1"},
                "root_options": [
                    "--help",
                    "--verbose",
                    "--cache-mode",
                    "--jelp",
                    "--jelp-pretty",
                    "--jelp-no-meta",
                    "--jelp-all",
                    "--jelp-all-commands",
                    "--jelp-all-no-meta",
                ],
                "commands": ["analyze", "notes", "review", "enrich"],
                "command_options": {
                    "analyze": [
                        "--help",
                        "--since-last-tag",
                        "--no-cache",
                        "--exclude-path",
                        "--exclude-kind",
                        "--exclude-warning",
                        "--group-threshold",
                        "--json",
                        "--markdown",
                    ],
                    "notes": [
                        "--help",
                        "--since-last-tag",
                        "--no-cache",
                        "--exclude-path",
                        "--exclude-kind",
                        "--exclude-warning",
                        "--group-threshold",
                        "--format",
                        "--input",
                        "--prefer-enriched",
                        "--source",
                        "--show-evidence",
                        "--evidence-out",
                        "--evidence-format",
                        "--out",
                        "--note-order",
                    ],
                    "review": [
                        "--help",
                        "--since-last-tag",
                        "--no-cache",
                        "--exclude-path",
                        "--exclude-kind",
                        "--exclude-warning",
                        "--group-threshold",
                        "--out",
                    ],
                    "enrich": [
                        "--help",
                        "--since-last-tag",
                        "--no-cache",
                        "--exclude-path",
                        "--exclude-kind",
                        "--exclude-warning",
                        "--group-threshold",
                        "--backend",
                        "--model",
                        "--base-url",
                        "--api-key",
                        "--max-clusters",
                        "--retries",
                        "--retry-base-delay",
                        "--retry-max-delay",
                        "--rate-limit-rps",
                        "--input",
                        "--out",
                    ],
                },
                "command_arguments": {
                    "analyze": ["range"],
                    "notes": ["range"],
                    "review": ["range"],
                    "enrich": ["range"],
                },
            },
        )

    def test_handle_and_enable_jelp_integration_helpers(self) -> None:
        parser = argparse.ArgumentParser(prog="mini")
        parser.add_argument("--value")
        subparsers = parser.add_subparsers(dest="command")
        scan = subparsers.add_parser("scan")
        scan.add_argument("path", nargs="?")
        enable_jelp(parser, version="0.0.1")

        auto_stdout = StringIO()
        with redirect_stdout(auto_stdout):
            with self.assertRaises(SystemExit) as exit_ctx:
                parser.parse_args(["--jelp"])
        self.assertEqual(exit_ctx.exception.code, 0)
        auto_payload = json.loads(auto_stdout.getvalue())
        self.assertEqual(auto_payload["info"]["version"], "0.0.1")

        scan_order_stdout = StringIO()
        with redirect_stdout(scan_order_stdout):
            with self.assertRaises(SystemExit) as exit_ctx:
                parser.parse_args(["scan", "--jelp"])
        self.assertEqual(exit_ctx.exception.code, 0)
        scan_order_payload = json.loads(scan_order_stdout.getvalue())
        self.assertTrue(scan_order_payload["info"]["title"].endswith("scan"))

        forced_full_stdout = StringIO()
        with patch.object(
            sys,
            "argv",
            ["mini", "scan", "--jelp", "--jelp-all-commands"],
        ):
            with redirect_stdout(forced_full_stdout):
                with self.assertRaises(SystemExit) as exit_ctx:
                    parser.parse_args()
        self.assertEqual(exit_ctx.exception.code, 0)
        forced_full_payload = json.loads(forced_full_stdout.getvalue())
        self.assertEqual(forced_full_payload["info"]["title"], "mini")
        self.assertEqual(
            [command["name"] for command in forced_full_payload.get("commands", [])],
            ["scan"],
        )

        inverted_order_stdout = StringIO()
        with patch.object(sys, "argv", ["mini", "--jelp", "scan"]):
            with redirect_stdout(inverted_order_stdout):
                with self.assertRaises(SystemExit) as exit_ctx:
                    parser.parse_args()
        self.assertEqual(exit_ctx.exception.code, 0)
        inverted_order_payload = json.loads(inverted_order_stdout.getvalue())
        self.assertEqual(inverted_order_payload["info"]["title"], "mini")

        parser_inverted = argparse.ArgumentParser(prog="mini-inverted")
        sp = parser_inverted.add_subparsers(dest="command")
        sp.add_parser("scan")
        enable_jelp(parser_inverted, version="0.0.1", allow_inverted_order=True)
        inverted_enabled_stdout = StringIO()
        with patch.object(sys, "argv", ["mini-inverted", "--jelp", "scan"]):
            with redirect_stdout(inverted_enabled_stdout):
                with self.assertRaises(SystemExit) as exit_ctx:
                    parser_inverted.parse_args()
        self.assertEqual(exit_ctx.exception.code, 0)
        inverted_enabled_payload = json.loads(inverted_enabled_stdout.getvalue())
        self.assertTrue(inverted_enabled_payload["info"]["title"].endswith("scan"))

        parser_manual = argparse.ArgumentParser(prog="mini-manual")
        parser_manual.add_argument("--value")
        enable_jelp(parser_manual, auto_handle=False)

        compact = StringIO()
        handled_compact = handle_jelp_flag(
            parser_manual,
            ["--jelp"],
            version="0.0.1",
            stream=compact,
        )
        self.assertTrue(handled_compact)
        self.assertFalse(compact.getvalue().startswith("{\n"))

        pretty = StringIO()
        handled_pretty = handle_jelp_flag(
            parser_manual,
            ["--jelp-pretty"],
            version="0.0.1",
            stream=pretty,
        )
        self.assertTrue(handled_pretty)
        self.assertTrue(pretty.getvalue().startswith("{\n"))

        not_handled = handle_jelp_flag(
            parser_manual,
            ["--value", "x"],
            version="0.0.1",
        )
        self.assertFalse(not_handled)

        strict_manual = StringIO()
        handled_strict_manual = handle_jelp_flag(
            parser,
            ["--jelp", "scan"],
            version="0.0.1",
            stream=strict_manual,
        )
        self.assertTrue(handled_strict_manual)
        self.assertEqual(json.loads(strict_manual.getvalue())["info"]["title"], "mini")

        inverted_manual = StringIO()
        handled_inverted_manual = handle_jelp_flag(
            parser,
            ["--jelp", "scan"],
            version="0.0.1",
            stream=inverted_manual,
            allow_inverted_order=True,
        )
        self.assertTrue(handled_inverted_manual)
        self.assertTrue(
            json.loads(inverted_manual.getvalue())["info"]["title"].endswith("scan")
        )

        all_commands_manual = StringIO()
        handled_all_commands_manual = handle_jelp_flag(
            parser,
            ["scan", "--jelp-all-commands"],
            version="0.0.1",
            stream=all_commands_manual,
        )
        self.assertTrue(handled_all_commands_manual)
        all_commands_payload = json.loads(all_commands_manual.getvalue())
        self.assertEqual(all_commands_payload["info"]["title"], "mini")
        self.assertEqual(
            [command["name"] for command in all_commands_payload.get("commands", [])],
            ["scan"],
        )

        all_no_meta_manual = StringIO()
        handled_all_no_meta_manual = handle_jelp_flag(
            parser,
            ["scan", "--jelp-all-no-meta"],
            version="0.0.1",
            stream=all_no_meta_manual,
        )
        self.assertTrue(handled_all_no_meta_manual)
        all_no_meta_payload = json.loads(all_no_meta_manual.getvalue())
        self.assertEqual(all_no_meta_payload["info"]["title"], "mini")
        self.assertNotIn("metadata", all_no_meta_payload)
        self.assertTrue(
            all(
                "metadata" not in option
                for option in all_no_meta_payload.get("options", [])
            )
        )

    def test_metadata_levels_useful_none_all(self) -> None:
        parser = self._fixture_parser()
        useful = emit_opencli(parser, version="1.2.3", metadata_level="useful")
        none = emit_opencli(parser, version="1.2.3", metadata_level="none")
        all_data = emit_opencli(parser, version="1.2.3", metadata_level="all")

        useful_verbose = next(
            option for option in useful["options"] if option["name"] == "--verbose"
        )
        useful_metadata_names = {
            entry["name"] for entry in useful_verbose.get("metadata", [])
        }
        self.assertIn("argparse.action", useful_metadata_names)
        self.assertIn("argparse.repeat_semantics", useful_metadata_names)
        self.assertNotIn("argparse.dest", useful_metadata_names)

        all_verbose = next(
            option for option in all_data["options"] if option["name"] == "--verbose"
        )
        all_metadata_names = {
            entry["name"] for entry in all_verbose.get("metadata", [])
        }
        self.assertIn("argparse.dest", all_metadata_names)

        self.assertNotIn("metadata", none)
        self.assertTrue(
            all("metadata" not in option for option in none.get("options", []))
        )

    def test_jelp_injected_option_provenance(self) -> None:
        parser = argparse.ArgumentParser(prog="prov")
        parser.add_argument("--native")
        enable_jelp(parser, version="0.0.1")

        useful = emit_opencli(parser, version="0.0.1", metadata_level="useful")
        root_meta = useful.get("metadata", [])
        injected_list = self._metadata_value(root_meta, "jelp.injected_options")
        self.assertEqual(
            injected_list,
            [
                "--jelp",
                "--jelp-pretty",
                "--jelp-no-meta",
                "--jelp-all",
                "--jelp-all-commands",
                "--jelp-all-no-meta",
            ],
        )

        options = {option["name"]: option for option in useful.get("options", [])}
        injected_option_meta = {
            entry["name"] for entry in options["--jelp"].get("metadata", [])
        }
        self.assertIn("jelp.injected", injected_option_meta)

        native_option_meta = {
            entry["name"] for entry in options["--native"].get("metadata", [])
        }
        self.assertNotIn("jelp.injected", native_option_meta)

        none = emit_opencli(parser, version="0.0.1", metadata_level="none")
        self.assertNotIn("metadata", none)
        none_options = {option["name"]: option for option in none.get("options", [])}
        self.assertNotIn("metadata", none_options["--jelp"])

    def test_cli_no_meta_and_all_flags(self) -> None:
        no_meta_stdout = StringIO()
        with redirect_stdout(no_meta_stdout):
            rc = cli_main(["--jelp-no-meta"])
        self.assertEqual(rc, 0)
        no_meta_payload = json.loads(no_meta_stdout.getvalue())
        self.assertNotIn("metadata", no_meta_payload)

        all_stdout = StringIO()
        with redirect_stdout(all_stdout):
            rc = cli_main(["--jelp-all"])
        self.assertEqual(rc, 0)
        all_payload = json.loads(all_stdout.getvalue())
        verbose = next(
            option
            for option in all_payload.get("options", [])
            if option["name"] == "--verbose"
        )
        verbose_metadata_names = {
            entry["name"] for entry in verbose.get("metadata", [])
        }
        self.assertIn("argparse.dest", verbose_metadata_names)

        all_commands_stdout = StringIO()
        with redirect_stdout(all_commands_stdout):
            rc = cli_main(["analyze", "--jelp-all-commands"])
        self.assertEqual(rc, 0)
        all_commands_payload = json.loads(all_commands_stdout.getvalue())
        self.assertEqual(all_commands_payload["info"]["title"], "jelp")
        self.assertEqual(
            [command["name"] for command in all_commands_payload.get("commands", [])],
            ["analyze", "notes", "review", "enrich"],
        )

        all_no_meta_stdout = StringIO()
        with redirect_stdout(all_no_meta_stdout):
            rc = cli_main(["analyze", "--jelp-all-no-meta"])
        self.assertEqual(rc, 0)
        all_no_meta_payload = json.loads(all_no_meta_stdout.getvalue())
        self.assertEqual(all_no_meta_payload["info"]["title"], "jelp")
        self.assertNotIn("metadata", all_no_meta_payload)
        self.assertTrue(
            all(
                "metadata" not in option
                for option in all_no_meta_payload.get("options", [])
            )
        )

    def test_emitted_json_answers_llm_discovery_questions(self) -> None:
        payload = emit_opencli(self._fixture_parser(), version="1.2.3")
        command_names = [command["name"] for command in payload.get("commands", [])]
        self.assertEqual(command_names, ["scan", "push"])

        options_by_command = {
            command["name"]: [option["name"] for option in command.get("options", [])]
            for command in payload.get("commands", [])
        }
        self.assertEqual(options_by_command["push"], ["--help", "--force"])

        root_options = {option["name"]: option for option in payload.get("options", [])}
        verbose = root_options["--verbose"]
        verbose_metadata = verbose.get("metadata", [])
        self.assertEqual(
            self._metadata_value(verbose_metadata, "argparse.repeat_semantics"),
            "count",
        )

        root_metadata = payload.get("metadata", [])
        mxg = self._metadata_value(root_metadata, "argparse.mutually_exclusive_groups")
        self.assertEqual(mxg[0]["members"], ["--dry-run", "--execute"])

        synopsis = "commands: " + ", ".join(command_names)
        self.assertEqual(synopsis, "commands: scan, push")


if __name__ == "__main__":
    unittest.main()
