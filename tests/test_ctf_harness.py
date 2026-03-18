from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ctf import harness


class HarnessCommandValidationTests(unittest.TestCase):
    def test_debug_scope_helpers(self) -> None:
        self.assertEqual(harness._scenario_debug_code("fixture04_bundle"), "f04")
        self.assertEqual(harness._mode_debug_code("help-only"), "ho")
        self.assertEqual(harness._mode_debug_code("unknown-mode"), "m")

    def test_extract_completed_keys(self) -> None:
        run_log = {
            "results": [
                {
                    "iteration": 2,
                    "summary": {
                        "scenario_id": "fixture03_cache",
                        "mode": "help-only",
                    },
                },
                {
                    "summary": {
                        "scenario_id": "fixture03_cache",
                        "mode": "jelp-primed-useful",
                    },
                },
            ]
        }
        self.assertEqual(
            harness._extract_completed_keys(run_log),
            {
                (2, "fixture03_cache", "help-only"),
                (1, "fixture03_cache", "jelp-primed-useful"),
            },
        )

    def test_resume_mismatch_reason(self) -> None:
        mismatch = harness._resume_mismatch_reason(
            existing={
                "adapter": "openai",
                "model": "gpt-4.1-mini",
                "modes": ["help-only"],
                "iterations": 3,
            },
            adapter="openai",
            model="gpt-5-mini",
            modes=["help-only"],
            iterations=3,
        )
        self.assertIn("model mismatch", mismatch or "")

        no_mismatch = harness._resume_mismatch_reason(
            existing={
                "adapter": "openai",
                "model": "gpt-4.1-mini",
                "modes": ["help-only"],
                "iterations": 3,
            },
            adapter="openai",
            model="gpt-4.1-mini",
            modes=["help-only"],
            iterations=3,
        )
        self.assertIsNone(no_mismatch)

    def test_summary_to_run_result_backward_compat_defaults(self) -> None:
        result = harness._summary_to_run_result(
            {
                "scenario_id": "fixture01_vault",
                "mode": "help-only",
                "adapter": "openai",
                "success": True,
                "expected_flag": "FLAG{x}",
                "command_count": 5,
                "invalid_command_count": 1,
                "parser_error_count": 0,
                "duration_s": 1.2,
                "time_to_success_s": 1.0,
            }
        )
        self.assertEqual(result.anomaly_count, 0)
        self.assertEqual(result.command_count, 5)

    def test_write_run_log_checkpoint_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "run.json"
            run_log = harness._new_run_log(
                adapter="openai",
                model="gpt-4.1-mini",
                modes=["help-only"],
                iterations=1,
                selected_scenarios=["fixture01_vault"],
            )
            harness._write_run_log_checkpoint(out, run_log)
            self.assertTrue(out.exists())
            payload = out.read_text(encoding="utf-8")
            self.assertIn("last_checkpoint_utc", payload)

    def test_main_refuses_clobber_without_resume_or_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "existing.json"
            out.write_text('{"results":[]}', encoding="utf-8")
            with self.assertRaises(SystemExit):
                harness.main(
                    [
                        "--adapter",
                        "oracle",
                        "--scenario",
                        "fixture01_vault",
                        "--modes",
                        "help-only",
                        "--iterations",
                        "1",
                        "--out",
                        str(out),
                    ]
                )

    def test_main_resume_skips_completed_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "resume.json"
            rc = harness.main(
                [
                    "--adapter",
                    "oracle",
                    "--scenario",
                    "fixture01_vault",
                    "--modes",
                    "help-only",
                    "--iterations",
                    "1",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(rc, 0)
            first = out.read_text(encoding="utf-8")

            rc2 = harness.main(
                [
                    "--adapter",
                    "oracle",
                    "--scenario",
                    "fixture01_vault",
                    "--modes",
                    "help-only",
                    "--iterations",
                    "1",
                    "--resume",
                    "--out",
                    str(out),
                ]
            )
            self.assertEqual(rc2, 0)
            second = out.read_text(encoding="utf-8")

        first_payload = json.loads(first)
        second_payload = json.loads(second)
        self.assertEqual(len(first_payload["results"]), 1)
        self.assertEqual(len(second_payload["results"]), 1)
        self.assertEqual(
            first_payload["results"][0]["summary"]["scenario_id"],
            second_payload["results"][0]["summary"]["scenario_id"],
        )

    def test_detect_command_anomalies_flags_shell_markers(self) -> None:
        reasons = harness._detect_command_anomalies(
            command="python fixture01_vault.py ; ls $(pwd) `whoami`",
            tokens=["python", "fixture01_vault.py", ";", "ls", "$(pwd)", "`whoami`"],
        )
        joined = " | ".join(reasons)
        self.assertIn("shell control tokens", joined)
        self.assertIn("subshell marker", joined)
        self.assertIn("backtick execution marker", joined)

    def test_detect_command_anomalies_flags_newline_control(self) -> None:
        reasons = harness._detect_command_anomalies(
            command="python fixture01_vault.py --help\npython fixture01_vault.py scan /",
            tokens=["python", "fixture01_vault.py", "--help"],
        )
        self.assertIn("contains newline control characters", reasons)

    def test_split_command_reports_malformed_syntax(self) -> None:
        tokens, error = harness._split_command('python "unterminated')
        self.assertIsNone(tokens)
        self.assertIsNotNone(error)

    def test_command_target_enforcement(self) -> None:
        self.assertIsNone(
            harness._command_rejection_reason(
                tokens=["python", "fixture01_vault.py", "--help"],
                expected_script="fixture01_vault.py",
            )
        )
        self.assertEqual(
            harness._command_rejection_reason(
                tokens=["python", "fixture02_release.py", "--help"],
                expected_script="fixture01_vault.py",
            ),
            "command must target 'fixture01_vault.py'",
        )
        self.assertEqual(
            harness._command_rejection_reason(
                tokens=["bash", "fixture01_vault.py", "--help"],
                expected_script="fixture01_vault.py",
            ),
            "command must start with 'python '",
        )

    @patch("ctf.harness.subprocess.run")
    def test_execute_command_uses_python_executable_without_shell(
        self, run_mock
    ) -> None:
        run_mock.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        turn = harness._execute_command(
            "python fixture01_vault.py --help",
            argv_tokens=["python", "fixture01_vault.py", "--help"],
            cwd=Path("."),
            env={},
            timeout_s=1.0,
        )

        self.assertEqual(turn.returncode, 0)
        args, kwargs = run_mock.call_args
        self.assertEqual(args[0][0], sys.executable)
        self.assertEqual(args[0][1:], ["fixture01_vault.py", "--help"])
        self.assertFalse(kwargs["shell"])

    @patch("ctf.harness.subprocess.run")
    def test_execute_command_timeout_returns_turn_record(self, run_mock) -> None:
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=[sys.executable, "fixture01_vault.py"],
            timeout=2.0,
            output="partial stdout",
            stderr="partial stderr",
        )
        turn = harness._execute_command(
            "python fixture01_vault.py --help",
            argv_tokens=["python", "fixture01_vault.py", "--help"],
            cwd=Path("."),
            env={},
            timeout_s=2.0,
        )

        self.assertEqual(turn.returncode, 124)
        self.assertIn("Timed out after 2.0s", turn.stderr)
        self.assertEqual(turn.stdout, "partial stdout")


if __name__ == "__main__":
    unittest.main()
