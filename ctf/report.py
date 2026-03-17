from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median


@dataclass(frozen=True)
class Summary:
    iteration: int
    scenario_id: str
    mode: str
    success: bool
    command_count: int
    invalid_command_count: int
    parser_error_count: int
    duration_s: float
    time_to_success_s: float | None
    api_call_count: int
    model_input_tokens: int
    model_output_tokens: int
    model_total_tokens: int


def _load_summaries(path: Path) -> list[Summary]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results", [])
    summaries: list[Summary] = []
    for row in rows:
        summary = row.get("summary", {})
        iteration = int(row.get("iteration", 1))
        summaries.append(
            Summary(
                iteration=iteration,
                scenario_id=str(summary["scenario_id"]),
                mode=str(summary["mode"]),
                success=bool(summary["success"]),
                command_count=int(summary["command_count"]),
                invalid_command_count=int(summary["invalid_command_count"]),
                parser_error_count=int(summary["parser_error_count"]),
                duration_s=float(summary["duration_s"]),
                time_to_success_s=(
                    None
                    if summary["time_to_success_s"] is None
                    else float(summary["time_to_success_s"])
                ),
                api_call_count=int(summary.get("api_call_count", 0)),
                model_input_tokens=int(summary.get("model_input_tokens", 0)),
                model_output_tokens=int(summary.get("model_output_tokens", 0)),
                model_total_tokens=int(summary.get("model_total_tokens", 0)),
            )
        )
    return summaries


def _mode_stats(rows: list[Summary]) -> dict[str, dict[str, float]]:
    by_mode: dict[str, list[Summary]] = {}
    for row in rows:
        by_mode.setdefault(row.mode, []).append(row)

    out: dict[str, dict[str, float]] = {}
    for mode, mode_rows in by_mode.items():
        success_rate = sum(1 for row in mode_rows if row.success) / len(mode_rows)
        t_success = [
            row.time_to_success_s
            for row in mode_rows
            if row.time_to_success_s is not None
        ]
        out[mode] = {
            "n": float(len(mode_rows)),
            "success_rate": success_rate,
            "mean_cmds": mean(row.command_count for row in mode_rows),
            "median_cmds": median(row.command_count for row in mode_rows),
            "mean_invalid": mean(row.invalid_command_count for row in mode_rows),
            "mean_errors": mean(row.parser_error_count for row in mode_rows),
            "median_t_success": median(t_success) if t_success else float("nan"),
            "mean_api_calls": mean(row.api_call_count for row in mode_rows),
            "mean_input_tokens": mean(row.model_input_tokens for row in mode_rows),
            "mean_output_tokens": mean(row.model_output_tokens for row in mode_rows),
            "mean_total_tokens": mean(row.model_total_tokens for row in mode_rows),
        }
    return out


def _iteration_stats(
    rows: list[Summary],
) -> dict[int, dict[str, dict[str, float]]]:
    by_iteration: dict[int, list[Summary]] = {}
    for row in rows:
        by_iteration.setdefault(row.iteration, []).append(row)
    return {
        iteration: _mode_stats(iter_rows)
        for iteration, iter_rows in sorted(by_iteration.items())
    }


def _paired_delta(
    rows: list[Summary],
    *,
    baseline: str,
    compare: str,
) -> dict[str, float]:
    by_scenario_mode: dict[tuple[int, str, str], Summary] = {}
    for row in rows:
        by_scenario_mode[(row.iteration, row.scenario_id, row.mode)] = row

    paired: list[tuple[Summary, Summary]] = []
    keys = {(row.iteration, row.scenario_id) for row in rows}
    for iteration, scenario_id in keys:
        base = by_scenario_mode.get((iteration, scenario_id, baseline))
        comp = by_scenario_mode.get((iteration, scenario_id, compare))
        if base is not None and comp is not None:
            paired.append((base, comp))

    if not paired:
        return {
            "pairs": 0.0,
            "success_delta_pp": 0.0,
            "median_cmd_delta": 0.0,
            "mean_error_delta": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "ties": 0.0,
        }

    success_delta = sum(1 for base, comp in paired if comp.success) / len(paired) - sum(
        1 for base, comp in paired if base.success
    ) / len(paired)
    cmd_deltas = [comp.command_count - base.command_count for base, comp in paired]
    error_deltas = [
        comp.parser_error_count - base.parser_error_count for base, comp in paired
    ]

    wins = sum(1 for delta in cmd_deltas if delta < 0)
    losses = sum(1 for delta in cmd_deltas if delta > 0)
    ties = len(cmd_deltas) - wins - losses

    return {
        "pairs": float(len(paired)),
        "success_delta_pp": success_delta * 100.0,
        "median_cmd_delta": float(median(cmd_deltas)),
        "mean_error_delta": float(mean(error_deltas)),
        "wins": float(wins),
        "losses": float(losses),
        "ties": float(ties),
    }


def _fmt(x: float) -> str:
    if x != x:  # nan
        return "n/a"
    if abs(x) >= 100:
        return f"{x:.1f}"
    if abs(x) >= 10:
        return f"{x:.2f}"
    return f"{x:.3f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctf-report")
    parser.add_argument("--in", dest="input_path", required=True)
    parser.add_argument("--baseline", default="help-only")
    parser.add_argument(
        "--compare",
        action="append",
        default=[
            "help-only-primed",
            "jelp-useful",
            "jelp-primed",
            "jelp-primed-useful",
            "jelp-primed-incremental",
            "jelp-primed-full",
            "jelp-no-meta",
        ],
    )
    parser.add_argument("--by-iteration", action="store_true")
    args = parser.parse_args(argv)

    rows = _load_summaries(Path(args.input_path))
    stats = _mode_stats(rows)

    print("Mode summary")
    print(
        "mode".ljust(16)
        + "n".ljust(6)
        + "success".ljust(10)
        + "mean_cmds".ljust(12)
        + "median_cmds".ljust(13)
        + "mean_errors".ljust(12)
        + "median_t_success".ljust(18)
        + "mean_total_tok"
    )
    print("-" * 96)
    for mode in sorted(stats):
        row = stats[mode]
        print(
            mode.ljust(16)
            + str(int(row["n"])).ljust(6)
            + f"{row['success_rate']:.1%}".ljust(10)
            + _fmt(row["mean_cmds"]).ljust(12)
            + _fmt(row["median_cmds"]).ljust(13)
            + _fmt(row["mean_errors"]).ljust(12)
            + _fmt(row["median_t_success"]).ljust(18)
            + _fmt(row["mean_total_tokens"])
        )

    print("\nPaired deltas vs baseline:", args.baseline)
    print(
        "compare".ljust(16)
        + "pairs".ljust(8)
        + "success_pp".ljust(12)
        + "med_cmd_delta".ljust(14)
        + "mean_err_delta".ljust(15)
        + "wins/losses/ties"
    )
    print("-" * 86)
    for compare_mode in args.compare:
        delta = _paired_delta(rows, baseline=args.baseline, compare=compare_mode)
        print(
            compare_mode.ljust(16)
            + str(int(delta["pairs"])).ljust(8)
            + _fmt(delta["success_delta_pp"]).ljust(12)
            + _fmt(delta["median_cmd_delta"]).ljust(14)
            + _fmt(delta["mean_error_delta"]).ljust(15)
            + f"{int(delta['wins'])}/{int(delta['losses'])}/{int(delta['ties'])}"
        )

    if args.by_iteration:
        print("\nPer-iteration mode summary")
        print(
            "iter".ljust(8)
            + "mode".ljust(16)
            + "n".ljust(6)
            + "success".ljust(10)
            + "mean_cmds".ljust(12)
            + "mean_errors".ljust(12)
            + "median_t_success".ljust(18)
            + "mean_total_tok"
        )
        print("-" * 94)
        iter_stats = _iteration_stats(rows)
        for iteration, mode_stats in iter_stats.items():
            for mode in sorted(mode_stats):
                row = mode_stats[mode]
                print(
                    str(iteration).ljust(8)
                    + mode.ljust(16)
                    + str(int(row["n"])).ljust(6)
                    + f"{row['success_rate']:.1%}".ljust(10)
                    + _fmt(row["mean_cmds"]).ljust(12)
                    + _fmt(row["mean_errors"]).ljust(12)
                    + _fmt(row["median_t_success"]).ljust(18)
                    + _fmt(row["mean_total_tokens"])
                )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
