from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ctf import harness


class HarnessCommandValidationTests(unittest.TestCase):
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
