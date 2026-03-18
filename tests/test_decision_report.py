from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ctf import decision_report as dr


def _summary(
    *,
    scenario_id: str,
    mode: str,
    success: bool,
    command_count: int,
    model_total_tokens: int,
    parser_error_count: int = 0,
) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "mode": mode,
        "success": success,
        "command_count": command_count,
        "parser_error_count": parser_error_count,
        "model_total_tokens": model_total_tokens,
    }


def _result(iteration: int, summary: dict[str, object]) -> dict[str, object]:
    return {"iteration": iteration, "summary": summary}


def _write_run(path: Path, *, model: str, results: list[dict[str, object]]) -> None:
    payload = {"model": model, "results": results}
    path.write_text(json.dumps(payload), encoding="utf-8")


class DecisionVerdictTests(unittest.TestCase):
    def test_classify_verdict_branches_and_edges(self) -> None:
        cases = [
            (
                {
                    "success_delta_pp": 1.0,
                    "median_cmd_delta": -1.0,
                    "token_ratio": 1.2,
                    "ci_favorable": True,
                },
                dr.VERDICT_NET_BENEFIT,
            ),
            (
                {
                    "success_delta_pp": 1.0,
                    "median_cmd_delta": -1.0,
                    "token_ratio": 2.0,
                    "ci_favorable": True,
                },
                dr.VERDICT_PROMISING,
            ),
            (
                {
                    "success_delta_pp": 1.0,
                    "median_cmd_delta": -1.0,
                    "token_ratio": 1.2,
                    "ci_favorable": False,
                },
                dr.VERDICT_PROMISING,
            ),
            (
                {
                    "success_delta_pp": -0.1,
                    "median_cmd_delta": -1.0,
                    "token_ratio": 1.2,
                    "ci_favorable": True,
                },
                dr.VERDICT_NO_NET,
            ),
            (
                {
                    "success_delta_pp": 1.0,
                    "median_cmd_delta": 0.0,
                    "token_ratio": 1.2,
                    "ci_favorable": True,
                },
                dr.VERDICT_NO_NET,
            ),
            (
                {
                    "success_delta_pp": 0.0,
                    "median_cmd_delta": -0.5,
                    "token_ratio": 1.75,
                    "ci_favorable": True,
                },
                dr.VERDICT_NET_BENEFIT,
            ),
            (
                {
                    "success_delta_pp": 0.0,
                    "median_cmd_delta": -0.49,
                    "token_ratio": 1.75,
                    "ci_favorable": True,
                },
                dr.VERDICT_NO_NET,
            ),
        ]
        for kwargs, expected in cases:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(dr.classify_verdict(**kwargs), expected)


class DecisionReportPipelineTests(unittest.TestCase):
    def test_build_decision_report_respects_iteration_in_pairing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir) / "run.json"
            _write_run(
                run_path,
                model="test-model",
                results=[
                    _result(
                        1,
                        _summary(
                            scenario_id="fixture-a",
                            mode="help-only-primed",
                            success=False,
                            command_count=7,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="fixture-a",
                            mode="jelp-primed-useful",
                            success=True,
                            command_count=5,
                            model_total_tokens=120,
                        ),
                    ),
                    _result(
                        2,
                        _summary(
                            scenario_id="fixture-a",
                            mode="help-only-primed",
                            success=False,
                            command_count=6,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        2,
                        _summary(
                            scenario_id="fixture-a",
                            mode="jelp-primed-useful",
                            success=True,
                            command_count=4,
                            model_total_tokens=120,
                        ),
                    ),
                ],
            )
            report, _ = dr.build_decision_report(input_paths=[run_path], seed=7)

        decision = report["models"]["test-model"]["decision"]
        evidence = report["models"]["test-model"]["evidence"]
        drivers = report["models"]["test-model"]["decision_drivers"]
        self.assertEqual(decision["pair_count"], 2)
        self.assertEqual(decision["success_delta_pp"], 100.0)
        self.assertEqual(decision["median_cmd_delta"], -2.0)
        self.assertEqual(decision["success_delta_pp_obs"], 100.0)
        self.assertEqual(decision["raw_verdict_no_cost"], dr.VERDICT_NET_BENEFIT)
        self.assertFalse(decision["cost_adjustment_changed"])
        self.assertEqual(evidence["observed_pairs_used"], 2)
        self.assertEqual(evidence["expected_pairs"], 2)
        self.assertEqual(evidence["pair_coverage"], 1.0)
        self.assertTrue(any("Derived verdict" in line for line in drivers))

    def test_regression_existing_result_file_parses_tokens_and_pairs(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[1]
            / "ctf"
            / "results"
            / "openai-gpt-4.1-mini-temp-0.2-primed-modes--steps-12_3runs.json"
        )
        if not fixture.exists():
            self.skipTest(f"missing fixture file: {fixture}")

        report, _ = dr.build_decision_report(
            input_paths=[fixture],
            baseline="help-only-primed",
            candidate="jelp-primed-useful",
            bootstrap_samples=800,
            seed=42,
        )

        model_block = report["models"]["gpt-4.1-mini"]
        decision = model_block["decision"]
        evidence = model_block["evidence"]
        mode_summary = model_block["mode_summary"]
        self.assertEqual(decision["pair_count"], 24)
        self.assertEqual(evidence["observed_pairs_used"], 24)
        self.assertEqual(evidence["expected_pairs"], 24)
        self.assertGreater(mode_summary["help-only-primed"]["mean_total_tokens"], 3000)
        self.assertGreater(
            mode_summary["jelp-primed-useful"]["mean_total_tokens"], 8000
        )
        self.assertGreater(decision["token_ratio"], 2.0)

    def test_markdown_contains_required_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "model-a.json"
            path_b = Path(tmpdir) / "model-b.json"

            _write_run(
                path_a,
                model="model-a",
                results=[
                    _result(
                        1,
                        _summary(
                            scenario_id="s1",
                            mode="help-only-primed",
                            success=False,
                            command_count=8,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="s1",
                            mode="jelp-primed-useful",
                            success=True,
                            command_count=5,
                            model_total_tokens=130,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="s2",
                            mode="help-only-primed",
                            success=False,
                            command_count=7,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="s2",
                            mode="jelp-primed-useful",
                            success=True,
                            command_count=5,
                            model_total_tokens=130,
                        ),
                    ),
                ],
            )

            _write_run(
                path_b,
                model="model-b",
                results=[
                    _result(
                        1,
                        _summary(
                            scenario_id="s1",
                            mode="help-only-primed",
                            success=True,
                            command_count=4,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="s1",
                            mode="jelp-primed-useful",
                            success=False,
                            command_count=6,
                            model_total_tokens=140,
                        ),
                    ),
                ],
            )

            _, markdown = dr.build_decision_report(
                input_paths=[path_a, path_b],
                bootstrap_samples=500,
                seed=11,
            )

        for marker in [
            "## Evidence accounting",
            "## Per-model decision metrics",
            "## Pooled decision metrics",
            "## Cost adjustment impact",
            "## Final verdict",
            "## Decision drivers",
            "## Caveats",
            "borderline=yes",
            "(B) help-only-primed",
            "(C) jelp-primed-useful",
            "model-a",
            "model-b",
            "**model-a**",
            "**model-b**",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, markdown)

    def test_cli_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_path = Path(tmpdir) / "run.json"
            json_out = Path(tmpdir) / "decision.json"
            md_out = Path(tmpdir) / "decision.md"

            _write_run(
                run_path,
                model="cli-model",
                results=[
                    _result(
                        1,
                        _summary(
                            scenario_id="fixture-a",
                            mode="help-only-primed",
                            success=False,
                            command_count=8,
                            model_total_tokens=100,
                        ),
                    ),
                    _result(
                        1,
                        _summary(
                            scenario_id="fixture-a",
                            mode="jelp-primed-useful",
                            success=True,
                            command_count=6,
                            model_total_tokens=150,
                        ),
                    ),
                ],
            )

            buffer = StringIO()
            with redirect_stdout(buffer):
                rc = dr.main(
                    [
                        "--in",
                        str(run_path),
                        "--json-out",
                        str(json_out),
                        "--md-out",
                        str(md_out),
                        "--bootstrap-samples",
                        "200",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(json_out.exists())
            self.assertTrue(md_out.exists())

            payload = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertIn("final_statement", payload)
            self.assertIn("cost_adjustment_summary", payload)
            markdown = md_out.read_text(encoding="utf-8")
            self.assertIn("# OpenCLI/jelp Decision Memo", markdown)


if __name__ == "__main__":
    unittest.main()
