from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ctf import phase2_run


class Phase2RunTests(unittest.TestCase):
    @patch("ctf.phase2_run.subprocess.run")
    def test_main_runs_harness_for_models_then_decision_report(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = phase2_run.main(
                [
                    "--results-dir",
                    tmpdir,
                    "--models",
                    "model-a",
                    "model-b",
                    "--no-debug",
                ]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 3)

        first_argv = run_mock.call_args_list[0].args[0]
        second_argv = run_mock.call_args_list[1].args[0]
        third_argv = run_mock.call_args_list[2].args[0]

        self.assertEqual(first_argv[1], "ctf/harness.py")
        self.assertIn("--modes", first_argv)
        self.assertIn("help-only-primed", first_argv)
        self.assertIn("jelp-primed-incremental", first_argv)
        first_out = first_argv[first_argv.index("--out") + 1]
        self.assertIn("head2head-model-a.json", first_out)
        self.assertEqual(second_argv[1], "ctf/harness.py")
        second_out = second_argv[second_argv.index("--out") + 1]
        self.assertIn("head2head-model-b.json", second_out)

        self.assertEqual(third_argv[1], "ctf/decision_report.py")
        self.assertIn("--baseline", third_argv)
        self.assertIn("help-only-primed", third_argv)
        self.assertIn("--candidate", third_argv)
        self.assertIn("jelp-primed-incremental", third_argv)

        kwargs = run_mock.call_args_list[0].kwargs
        env = kwargs.get("env", {})
        self.assertIn("PYTHONPATH", env)
        self.assertIn("src", env["PYTHONPATH"])

    @patch("ctf.phase2_run.subprocess.run")
    def test_main_skip_decision_report(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(returncode=0)
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = phase2_run.main(
                [
                    "--results-dir",
                    tmpdir,
                    "--models",
                    "model-a",
                    "--skip-decision-report",
                    "--no-debug",
                ]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(run_mock.call_args_list[0].args[0][1], "ctf/harness.py")

    @patch("ctf.phase2_run.subprocess.run")
    def test_main_stops_when_harness_fails(self, run_mock) -> None:
        run_mock.return_value = SimpleNamespace(returncode=9)
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = phase2_run.main(
                [
                    "--results-dir",
                    tmpdir,
                    "--models",
                    "model-a",
                    "model-b",
                    "--no-debug",
                ]
            )

        self.assertEqual(rc, 9)
        self.assertEqual(run_mock.call_count, 1)
        self.assertEqual(run_mock.call_args_list[0].args[0][1], "ctf/harness.py")

    @patch("ctf.phase2_run.subprocess.run")
    def test_main_dry_run_does_not_execute_subprocesses(self, run_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = phase2_run.main(
                [
                    "--results-dir",
                    tmpdir,
                    "--models",
                    "model-a",
                    "--dry-run",
                    "--no-debug",
                ]
            )
            self.assertTrue((Path(tmpdir)).exists())
        self.assertEqual(rc, 0)
        self.assertEqual(run_mock.call_count, 0)


if __name__ == "__main__":
    unittest.main()
