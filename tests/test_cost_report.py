from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ctf import cost_report as cr


def _result(
    *,
    iteration: int,
    mode: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    model_usage: list[dict[str, int]] | None = None,
) -> dict[str, object]:
    return {
        "iteration": iteration,
        "summary": {
            "mode": mode,
            "model_input_tokens": input_tokens,
            "model_output_tokens": output_tokens,
            "model_total_tokens": total_tokens,
        },
        "model_usage": model_usage or [],
    }


def _write_run(path: Path, *, model: str, results: list[dict[str, object]]) -> None:
    payload = {"model": model, "results": results}
    path.write_text(json.dumps(payload), encoding="utf-8")


class CostReportTests(unittest.TestCase):
    def test_build_cost_report_known_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir) / "run.json"
            _write_run(
                run,
                model="gpt-4.1-mini",
                results=[
                    _result(
                        iteration=1,
                        mode="help-only",
                        input_tokens=1_000_000,
                        output_tokens=1_000_000,
                        total_tokens=2_000_000,
                    )
                ],
            )

            payload, text = cr.build_cost_report(
                input_paths=[run],
                pricing_json=None,
                price_overrides=[],
                cached_input_ratio=0.0,
                forecast_iterations=3,
            )

        self.assertEqual(payload["unknown_models"], [])
        # gpt-4.1-mini default: input=0.40, output=1.60 per 1M
        self.assertAlmostEqual(payload["totals"]["estimated_cost_usd"], 2.0, places=6)
        self.assertIn("estimated_cost=$2.0000", text)
        self.assertIn("for 3 iterations of same config: estimated_total_cost=$6.0000", text)

    def test_summary_zero_backfills_from_model_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir) / "run.json"
            _write_run(
                run,
                model="gpt-5-mini",
                results=[
                    _result(
                        iteration=1,
                        mode="jelp-primed-useful",
                        input_tokens=0,
                        output_tokens=0,
                        total_tokens=0,
                        model_usage=[
                            {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
                            {"input_tokens": 300, "output_tokens": 25, "total_tokens": 325},
                        ],
                    )
                ],
            )

            payload, _ = cr.build_cost_report(
                input_paths=[run],
                pricing_json=None,
                price_overrides=[],
                cached_input_ratio=0.0,
                forecast_iterations=None,
            )

        self.assertEqual(payload["totals"]["input_tokens"], 400)
        self.assertEqual(payload["totals"]["output_tokens"], 75)
        self.assertEqual(payload["totals"]["total_tokens"], 475)
        self.assertGreater(payload["totals"]["estimated_cost_usd"], 0)

    def test_model_alias_normalization_snapshot(self) -> None:
        self.assertEqual(cr._normalize_model_name("gpt-5-mini-2025-08-07"), "gpt-5-mini")
        self.assertEqual(cr._normalize_model_name("gpt-5-2025-08-07"), "gpt-5")
        self.assertEqual(cr._normalize_model_name("unknown-2025-08-07"), "unknown-2025-08-07")

    def test_unknown_model_is_reported_and_cost_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir) / "run.json"
            _write_run(
                run,
                model="mystery-model",
                results=[
                    _result(
                        iteration=1,
                        mode="help-only",
                        input_tokens=100,
                        output_tokens=50,
                        total_tokens=150,
                    )
                ],
            )

            payload, text = cr.build_cost_report(
                input_paths=[run],
                pricing_json=None,
                price_overrides=[],
                cached_input_ratio=0.0,
                forecast_iterations=None,
            )

        self.assertEqual(payload["unknown_models"], ["mystery-model"])
        self.assertIn("warning: unknown model pricing for: mystery-model", text)
        self.assertEqual(payload["totals"]["estimated_cost_usd"], 0.0)

    def test_cli_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run = Path(tmpdir) / "run.json"
            out = Path(tmpdir) / "out.json"
            _write_run(
                run,
                model="gpt-4.1-mini",
                results=[
                    _result(
                        iteration=1,
                        mode="help-only",
                        input_tokens=250_000,
                        output_tokens=100_000,
                        total_tokens=350_000,
                    )
                ],
            )

            buf = StringIO()
            with redirect_stdout(buf):
                rc = cr.main(
                    [
                        "--in",
                        str(run),
                        "--json-out",
                        str(out),
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("totals", payload)


if __name__ == "__main__":
    unittest.main()
