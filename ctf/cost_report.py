from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PRICING_SNAPSHOT_DATE = "2026-03-17"
DEFAULT_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {
        "input": 0.40,
        "cached_input": 0.10,
        "output": 1.60,
    },
    "gpt-5-mini": {
        "input": 0.25,
        "cached_input": 0.025,
        "output": 2.00,
    },
    "gpt-5": {
        "input": 1.25,
        "cached_input": 0.125,
        "output": 10.00,
    },
}


@dataclass(frozen=True)
class Pricing:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None


@dataclass(frozen=True)
class UsageRow:
    source_path: str
    model: str
    mode: str
    iteration: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _normalize_model_name(model: str) -> str:
    if model in DEFAULT_PRICING_USD_PER_1M:
        return model

    if model.endswith("-latest"):
        base = model[: -len("-latest")]
        if base in DEFAULT_PRICING_USD_PER_1M:
            return base

    snapshot_match = re.match(r"^(.*)-\d{4}-\d{2}-\d{2}$", model)
    if snapshot_match:
        base = snapshot_match.group(1)
        if base in DEFAULT_PRICING_USD_PER_1M:
            return base

    return model


def _load_pricing_map(
    *,
    pricing_json: Path | None,
    price_overrides: list[str],
) -> dict[str, Pricing]:
    raw: dict[str, dict[str, float]] = {
        model: dict(prices) for model, prices in DEFAULT_PRICING_USD_PER_1M.items()
    }

    if pricing_json is not None:
        payload = json.loads(pricing_json.read_text(encoding="utf-8"))
        for model, spec in payload.items():
            if not isinstance(spec, dict):
                raise ValueError(
                    f"pricing JSON model '{model}' must map to an object, got {type(spec)}"
                )
            raw[str(model)] = {
                "input": float(spec["input"]),
                "output": float(spec["output"]),
                "cached_input": (
                    float(spec["cached_input"])
                    if "cached_input" in spec and spec["cached_input"] is not None
                    else None
                ),
            }

    for override in price_overrides:
        # Format: model,input,output[,cached_input]
        parts = [part.strip() for part in override.split(",")]
        if len(parts) not in {3, 4}:
            raise ValueError(
                f"invalid --price '{override}'; expected model,input,output[,cached_input]"
            )
        model = parts[0]
        raw[model] = {
            "input": float(parts[1]),
            "output": float(parts[2]),
            "cached_input": float(parts[3]) if len(parts) == 4 else None,
        }

    out: dict[str, Pricing] = {}
    for model, spec in raw.items():
        out[model] = Pricing(
            input_per_1m=float(spec["input"]),
            output_per_1m=float(spec["output"]),
            cached_input_per_1m=(
                None
                if spec.get("cached_input") is None
                else float(spec["cached_input"])
            ),
        )
    return out


def _extract_tokens_from_result_row(row: dict[str, object]) -> tuple[int, int, int]:
    summary = row.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    input_tokens = _as_int(summary.get("model_input_tokens"))
    output_tokens = _as_int(summary.get("model_output_tokens"))
    total_tokens = _as_int(summary.get("model_total_tokens"))

    if input_tokens > 0 or output_tokens > 0 or total_tokens > 0:
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens
        return input_tokens, output_tokens, total_tokens

    # Backfill from detailed model usage when summary aggregation is unavailable.
    usage_items = row.get("model_usage", [])
    if not isinstance(usage_items, list):
        return 0, 0, 0

    usage_input = 0
    usage_output = 0
    usage_total = 0
    for item in usage_items:
        if not isinstance(item, dict):
            continue
        usage_input += _as_int(item.get("input_tokens"))
        usage_output += _as_int(item.get("output_tokens"))
        usage_total += _as_int(item.get("total_tokens"))

    if usage_total == 0:
        usage_total = usage_input + usage_output
    return usage_input, usage_output, usage_total


def _estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    pricing: Pricing,
    cached_input_ratio: float,
) -> float:
    cached_ratio = max(0.0, min(1.0, cached_input_ratio))
    cached_input_tokens = int(round(input_tokens * cached_ratio))
    uncached_input_tokens = input_tokens - cached_input_tokens

    if pricing.cached_input_per_1m is None:
        cached_input_cost = cached_input_tokens / 1_000_000.0 * pricing.input_per_1m
    else:
        cached_input_cost = (
            cached_input_tokens / 1_000_000.0 * pricing.cached_input_per_1m
        )

    uncached_input_cost = uncached_input_tokens / 1_000_000.0 * pricing.input_per_1m
    output_cost = output_tokens / 1_000_000.0 * pricing.output_per_1m
    return uncached_input_cost + cached_input_cost + output_cost


def _load_usage_rows(
    *,
    input_paths: list[Path],
    pricing_map: dict[str, Pricing],
    cached_input_ratio: float,
) -> tuple[list[UsageRow], set[str]]:
    rows: list[UsageRow] = []
    unknown_models: set[str] = set()

    for path in input_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        run_model = str(payload.get("model", "unknown"))
        results = payload.get("results", [])
        if not isinstance(results, list):
            continue

        for item in results:
            if not isinstance(item, dict):
                continue
            summary = item.get("summary", {})
            if not isinstance(summary, dict):
                summary = {}

            mode = str(summary.get("mode", "unknown"))
            iteration = _as_int(item.get("iteration")) or 1
            input_tokens, output_tokens, total_tokens = _extract_tokens_from_result_row(
                item
            )

            raw_model = str(summary.get("model", run_model))
            model = _normalize_model_name(raw_model)
            pricing = pricing_map.get(model)
            if pricing is None:
                unknown_models.add(model)
                estimated_cost = None
            else:
                estimated_cost = _estimate_cost_usd(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    pricing=pricing,
                    cached_input_ratio=cached_input_ratio,
                )

            rows.append(
                UsageRow(
                    source_path=str(path),
                    model=model,
                    mode=mode,
                    iteration=iteration,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost,
                )
            )

    return rows, unknown_models


def _sum_tokens(rows: list[UsageRow], field: str) -> int:
    if field == "input":
        return sum(row.input_tokens for row in rows)
    if field == "output":
        return sum(row.output_tokens for row in rows)
    if field == "total":
        return sum(row.total_tokens for row in rows)
    raise ValueError(f"unsupported token field: {field}")


def _sum_cost(rows: list[UsageRow]) -> float:
    return sum(row.estimated_cost_usd or 0.0 for row in rows)


def _fmt_usd(value: float) -> str:
    return f"${value:.4f}"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def build_cost_report(
    *,
    input_paths: list[Path],
    pricing_json: Path | None,
    price_overrides: list[str],
    cached_input_ratio: float,
    forecast_iterations: int | None,
) -> tuple[dict[str, object], str]:
    pricing_map = _load_pricing_map(
        pricing_json=pricing_json,
        price_overrides=price_overrides,
    )
    rows, unknown_models = _load_usage_rows(
        input_paths=input_paths,
        pricing_map=pricing_map,
        cached_input_ratio=cached_input_ratio,
    )

    by_file: dict[str, list[UsageRow]] = {}
    by_model: dict[str, list[UsageRow]] = {}
    by_mode: dict[str, list[UsageRow]] = {}
    for row in rows:
        by_file.setdefault(row.source_path, []).append(row)
        by_model.setdefault(row.model, []).append(row)
        by_mode.setdefault(row.mode, []).append(row)

    file_summaries: dict[str, dict[str, object]] = {}
    for source_path, file_rows in sorted(by_file.items()):
        iterations = sorted({row.iteration for row in file_rows})
        total_cost = _sum_cost(file_rows)
        file_summaries[source_path] = {
            "rows": len(file_rows),
            "iterations": iterations,
            "iteration_count": len(iterations),
            "input_tokens": _sum_tokens(file_rows, "input"),
            "output_tokens": _sum_tokens(file_rows, "output"),
            "total_tokens": _sum_tokens(file_rows, "total"),
            "estimated_cost_usd": total_cost,
            "estimated_cost_per_iteration_usd": (
                total_cost / len(iterations) if iterations else None
            ),
        }

    model_summaries: dict[str, dict[str, object]] = {}
    for model, model_rows in sorted(by_model.items()):
        model_summaries[model] = {
            "rows": len(model_rows),
            "input_tokens": _sum_tokens(model_rows, "input"),
            "output_tokens": _sum_tokens(model_rows, "output"),
            "total_tokens": _sum_tokens(model_rows, "total"),
            "estimated_cost_usd": _sum_cost(model_rows),
        }

    mode_summaries: dict[str, dict[str, object]] = {}
    for mode, mode_rows in sorted(by_mode.items()):
        mode_summaries[mode] = {
            "rows": len(mode_rows),
            "input_tokens": _sum_tokens(mode_rows, "input"),
            "output_tokens": _sum_tokens(mode_rows, "output"),
            "total_tokens": _sum_tokens(mode_rows, "total"),
            "estimated_cost_usd": _sum_cost(mode_rows),
        }

    total_cost = _sum_cost(rows)
    unique_iterations: set[tuple[str, int]] = set()
    for row in rows:
        unique_iterations.add((row.source_path, row.iteration))
    iteration_count = len(unique_iterations)

    forecast = None
    if forecast_iterations is not None:
        if iteration_count == 0:
            per_iteration = None
            forecast_cost = None
        else:
            per_iteration = total_cost / iteration_count
            forecast_cost = per_iteration * forecast_iterations
        forecast = {
            "forecast_iterations": forecast_iterations,
            "estimated_cost_per_iteration_usd": per_iteration,
            "estimated_total_cost_usd": forecast_cost,
        }

    report_payload: dict[str, object] = {
        "pricing_snapshot_date": DEFAULT_PRICING_SNAPSHOT_DATE,
        "pricing_models": sorted(pricing_map.keys()),
        "cached_input_ratio_assumption": cached_input_ratio,
        "inputs": [str(path) for path in input_paths],
        "unknown_models": sorted(unknown_models),
        "totals": {
            "rows": len(rows),
            "input_tokens": _sum_tokens(rows, "input"),
            "output_tokens": _sum_tokens(rows, "output"),
            "total_tokens": _sum_tokens(rows, "total"),
            "estimated_cost_usd": total_cost,
            "iteration_count": iteration_count,
            "estimated_cost_per_iteration_usd": (
                total_cost / iteration_count if iteration_count > 0 else None
            ),
        },
        "by_file": file_summaries,
        "by_model": model_summaries,
        "by_mode": mode_summaries,
        "forecast": forecast,
    }

    lines: list[str] = [
        "CTF Cost Report",
        f"pricing snapshot date: {DEFAULT_PRICING_SNAPSHOT_DATE}",
        f"cached input ratio assumption: {cached_input_ratio:.1%}",
    ]
    if unknown_models:
        lines.append(
            "warning: unknown model pricing for: " + ", ".join(sorted(unknown_models))
        )
    lines.append("")
    lines.append("Totals")
    lines.append(
        f"- rows: {len(rows)}"
        + f", input={_fmt_int(_sum_tokens(rows, 'input'))}"
        + f", output={_fmt_int(_sum_tokens(rows, 'output'))}"
        + f", total={_fmt_int(_sum_tokens(rows, 'total'))}"
        + f", estimated_cost={_fmt_usd(total_cost)}"
    )
    if iteration_count > 0:
        lines.append(
            f"- iteration_count: {iteration_count}, estimated_cost_per_iteration={_fmt_usd(total_cost / iteration_count)}"
        )

    lines.append("")
    lines.append("By model")
    for model, summary in sorted(model_summaries.items()):
        lines.append(
            f"- {model}: rows={summary['rows']}, "
            f"input={_fmt_int(int(summary['input_tokens']))}, "
            f"output={_fmt_int(int(summary['output_tokens']))}, "
            f"estimated_cost={_fmt_usd(float(summary['estimated_cost_usd']))}"
        )

    lines.append("")
    lines.append("By mode")
    for mode, summary in sorted(mode_summaries.items()):
        lines.append(
            f"- {mode}: rows={summary['rows']}, "
            f"input={_fmt_int(int(summary['input_tokens']))}, "
            f"output={_fmt_int(int(summary['output_tokens']))}, "
            f"estimated_cost={_fmt_usd(float(summary['estimated_cost_usd']))}"
        )

    if forecast is not None:
        lines.append("")
        lines.append("Forecast")
        if forecast["estimated_total_cost_usd"] is None:
            lines.append(
                f"- cannot forecast for {forecast_iterations} iterations (no iteration data)"
            )
        else:
            lines.append(
                f"- for {forecast_iterations} iterations of same config: "
                f"estimated_total_cost={_fmt_usd(float(forecast['estimated_total_cost_usd']))}"
            )

    return report_payload, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctf-cost-report")
    parser.add_argument("--in", dest="inputs", action="append", required=True)
    parser.add_argument("--pricing-json")
    parser.add_argument(
        "--price",
        action="append",
        default=[],
        help="override pricing: model,input,output[,cached_input] (USD per 1M tokens)",
    )
    parser.add_argument(
        "--assume-cached-input-ratio",
        type=float,
        default=0.0,
        help="fraction of input tokens billed as cached input (0..1)",
    )
    parser.add_argument(
        "--forecast-iterations",
        type=int,
        help="forecast cost for N iterations of the same scenario/mode/model set",
    )
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)

    if args.assume_cached_input_ratio < 0.0 or args.assume_cached_input_ratio > 1.0:
        parser.error("--assume-cached-input-ratio must be between 0 and 1")
    if args.forecast_iterations is not None and args.forecast_iterations < 1:
        parser.error("--forecast-iterations must be >= 1")

    report_payload, text_report = build_cost_report(
        input_paths=[Path(path) for path in args.inputs],
        pricing_json=(Path(args.pricing_json) if args.pricing_json else None),
        price_overrides=list(args.price),
        cached_input_ratio=float(args.assume_cached_input_ratio),
        forecast_iterations=args.forecast_iterations,
    )

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Wrote JSON report: {out_path}")

    print(text_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
