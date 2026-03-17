from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

DEFAULT_BASELINE = "help-only-primed"
DEFAULT_CANDIDATE = "jelp-primed-useful"
DEFAULT_CI_LEVEL = 0.90
DEFAULT_BOOTSTRAP_SAMPLES = 4000
DEFAULT_SEED = 42

VERDICT_NET_BENEFIT = "Net benefit now"
VERDICT_PROMISING = "Promising, strategy adjustment needed"
VERDICT_NO_NET = "No net benefit currently"
VERDICT_INSUFFICIENT = "Insufficient evidence"
VERDICT_MODEL_SENSITIVE = "model-sensitive / not yet general"


@dataclass(frozen=True)
class SummaryRow:
    run_id: str
    source_path: str
    model: str
    iteration: int
    scenario_id: str
    mode: str
    success: bool
    command_count: int
    parser_error_count: int
    model_total_tokens: int


@dataclass(frozen=True)
class ModeSummary:
    n: int
    success_rate: float
    mean_cmds: float
    median_cmds: float
    mean_errors: float
    mean_total_tokens: float


@dataclass(frozen=True)
class DecisionMetrics:
    pair_count: int
    success_delta_pp: float
    median_cmd_delta: float
    token_ratio: float
    success_ci_low: float
    success_ci_high: float
    cmd_ci_low: float
    cmd_ci_high: float
    token_ratio_ci_low: float
    token_ratio_ci_high: float
    ci_favorable: bool
    verdict: str


def _as_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _as_bool(value: object) -> bool:
    return bool(value)


def _load_summary_rows(paths: list[Path]) -> list[SummaryRow]:
    rows: list[SummaryRow] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        model = str(payload.get("model", "unknown"))
        run_id = str(path.resolve())
        for item in payload.get("results", []):
            summary = item.get("summary", {})
            rows.append(
                SummaryRow(
                    run_id=run_id,
                    source_path=str(path),
                    model=model,
                    iteration=_as_int(item.get("iteration", 1), default=1),
                    scenario_id=str(summary.get("scenario_id", "")),
                    mode=str(summary.get("mode", "")),
                    success=_as_bool(summary.get("success", False)),
                    command_count=_as_int(summary.get("command_count", 0)),
                    parser_error_count=_as_int(summary.get("parser_error_count", 0)),
                    model_total_tokens=_as_int(summary.get("model_total_tokens", 0)),
                )
            )
    return rows


def _mode_stats(rows: list[SummaryRow]) -> dict[str, ModeSummary]:
    by_mode: dict[str, list[SummaryRow]] = {}
    for row in rows:
        by_mode.setdefault(row.mode, []).append(row)

    out: dict[str, ModeSummary] = {}
    for mode, mode_rows in by_mode.items():
        out[mode] = ModeSummary(
            n=len(mode_rows),
            success_rate=sum(1 for row in mode_rows if row.success) / len(mode_rows),
            mean_cmds=mean(row.command_count for row in mode_rows),
            median_cmds=float(median(row.command_count for row in mode_rows)),
            mean_errors=mean(row.parser_error_count for row in mode_rows),
            mean_total_tokens=mean(row.model_total_tokens for row in mode_rows),
        )
    return out


def _paired_rows(
    rows: list[SummaryRow], *, baseline: str, candidate: str
) -> list[tuple[SummaryRow, SummaryRow]]:
    by_pair_mode: dict[tuple[str, str, int, str, str], SummaryRow] = {}
    pair_keys: set[tuple[str, str, int, str]] = set()

    for row in rows:
        pair_key = (row.model, row.run_id, row.iteration, row.scenario_id)
        pair_keys.add(pair_key)
        by_pair_mode[
            (row.model, row.run_id, row.iteration, row.scenario_id, row.mode)
        ] = row

    paired: list[tuple[SummaryRow, SummaryRow]] = []
    for model, run_id, iteration, scenario_id in sorted(pair_keys):
        base = by_pair_mode.get((model, run_id, iteration, scenario_id, baseline))
        comp = by_pair_mode.get((model, run_id, iteration, scenario_id, candidate))
        if base is not None and comp is not None:
            paired.append((base, comp))
    return paired


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _token_ratio_from_pairs(pairs: list[tuple[SummaryRow, SummaryRow]]) -> float:
    if not pairs:
        return float("nan")
    base_mean = mean(base.model_total_tokens for base, _ in pairs)
    cand_mean = mean(comp.model_total_tokens for _, comp in pairs)
    if base_mean <= 0:
        if cand_mean <= 0:
            return 1.0
        return float("inf")
    return cand_mean / base_mean


def _point_metrics(
    pairs: list[tuple[SummaryRow, SummaryRow]],
) -> tuple[float, float, float]:
    if not pairs:
        return float("nan"), float("nan"), float("nan")

    success_delta_pp = (
        (
            sum(1 for base, comp in pairs if comp.success)
            - sum(1 for base, comp in pairs if base.success)
        )
        / len(pairs)
        * 100.0
    )
    cmd_deltas = [comp.command_count - base.command_count for base, comp in pairs]
    return success_delta_pp, float(median(cmd_deltas)), _token_ratio_from_pairs(pairs)


def _bootstrap_cis(
    pairs: list[tuple[SummaryRow, SummaryRow]],
    *,
    ci_level: float,
    samples: int,
    seed: int,
) -> tuple[float, float, float, float, float, float]:
    if not pairs:
        nan = float("nan")
        return nan, nan, nan, nan, nan, nan

    rng = random.Random(seed)
    n = len(pairs)
    success_samples: list[float] = []
    cmd_samples: list[float] = []
    token_ratio_samples: list[float] = []

    for _ in range(samples):
        draw = [pairs[rng.randrange(n)] for _ in range(n)]
        success_delta_pp, median_cmd_delta, token_ratio = _point_metrics(draw)
        success_samples.append(success_delta_pp)
        cmd_samples.append(median_cmd_delta)
        token_ratio_samples.append(token_ratio)

    alpha = (1.0 - ci_level) / 2.0
    low_q = alpha
    high_q = 1.0 - alpha
    return (
        _quantile(success_samples, low_q),
        _quantile(success_samples, high_q),
        _quantile(cmd_samples, low_q),
        _quantile(cmd_samples, high_q),
        _quantile(token_ratio_samples, low_q),
        _quantile(token_ratio_samples, high_q),
    )


def classify_verdict(
    *,
    success_delta_pp: float,
    median_cmd_delta: float,
    token_ratio: float,
    ci_favorable: bool,
) -> str:
    if (
        math.isnan(success_delta_pp)
        or math.isnan(median_cmd_delta)
        or math.isnan(token_ratio)
    ):
        return VERDICT_INSUFFICIENT

    if success_delta_pp < 0 or median_cmd_delta >= 0:
        return VERDICT_NO_NET

    if success_delta_pp >= 0 and median_cmd_delta <= -0.5:
        if token_ratio <= 1.75 and ci_favorable:
            return VERDICT_NET_BENEFIT
        return VERDICT_PROMISING

    return VERDICT_NO_NET


def _decision_metrics(
    pairs: list[tuple[SummaryRow, SummaryRow]],
    *,
    ci_level: float,
    bootstrap_samples: int,
    seed: int,
) -> DecisionMetrics:
    if not pairs:
        return DecisionMetrics(
            pair_count=0,
            success_delta_pp=float("nan"),
            median_cmd_delta=float("nan"),
            token_ratio=float("nan"),
            success_ci_low=float("nan"),
            success_ci_high=float("nan"),
            cmd_ci_low=float("nan"),
            cmd_ci_high=float("nan"),
            token_ratio_ci_low=float("nan"),
            token_ratio_ci_high=float("nan"),
            ci_favorable=False,
            verdict=VERDICT_INSUFFICIENT,
        )

    success_delta_pp, median_cmd_delta, token_ratio = _point_metrics(pairs)
    (
        success_ci_low,
        success_ci_high,
        cmd_ci_low,
        cmd_ci_high,
        token_ratio_ci_low,
        token_ratio_ci_high,
    ) = _bootstrap_cis(
        pairs,
        ci_level=ci_level,
        samples=bootstrap_samples,
        seed=seed,
    )
    ci_favorable = success_ci_low >= 0.0 and cmd_ci_high <= -0.5

    return DecisionMetrics(
        pair_count=len(pairs),
        success_delta_pp=success_delta_pp,
        median_cmd_delta=median_cmd_delta,
        token_ratio=token_ratio,
        success_ci_low=success_ci_low,
        success_ci_high=success_ci_high,
        cmd_ci_low=cmd_ci_low,
        cmd_ci_high=cmd_ci_high,
        token_ratio_ci_low=token_ratio_ci_low,
        token_ratio_ci_high=token_ratio_ci_high,
        ci_favorable=ci_favorable,
        verdict=classify_verdict(
            success_delta_pp=success_delta_pp,
            median_cmd_delta=median_cmd_delta,
            token_ratio=token_ratio,
            ci_favorable=ci_favorable,
        ),
    )


def _safe_number(value: float) -> float | None:
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _mode_summary_to_dict(summary: ModeSummary) -> dict[str, float | int | None]:
    return {
        "n": summary.n,
        "success_rate": summary.success_rate,
        "mean_cmds": summary.mean_cmds,
        "median_cmds": summary.median_cmds,
        "mean_errors": summary.mean_errors,
        "mean_total_tokens": summary.mean_total_tokens,
    }


def _decision_to_dict(metrics: DecisionMetrics) -> dict[str, object]:
    return {
        "pair_count": metrics.pair_count,
        "success_delta_pp": _safe_number(metrics.success_delta_pp),
        "median_cmd_delta": _safe_number(metrics.median_cmd_delta),
        "token_ratio": _safe_number(metrics.token_ratio),
        "success_ci": [
            _safe_number(metrics.success_ci_low),
            _safe_number(metrics.success_ci_high),
        ],
        "median_cmd_ci": [
            _safe_number(metrics.cmd_ci_low),
            _safe_number(metrics.cmd_ci_high),
        ],
        "token_ratio_ci": [
            _safe_number(metrics.token_ratio_ci_low),
            _safe_number(metrics.token_ratio_ci_high),
        ],
        "ci_favorable": metrics.ci_favorable,
        "verdict": metrics.verdict,
    }


def _fmt(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    if math.isinf(value):
        return "inf"
    if abs(value) >= 100:
        return f"{value:.1f}"
    if abs(value) >= 10:
        return f"{value:.2f}"
    return f"{value:.3f}"


def _fmt_pct(value: float) -> str:
    if math.isnan(value):
        return "n/a"
    return f"{value:.1%}"


def _mode_table(mode_stats: dict[str, ModeSummary]) -> list[str]:
    lines = [
        "| mode | n | success | mean_cmds | median_cmds | mean_errors | mean_total_tok |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in sorted(mode_stats):
        row = mode_stats[mode]
        lines.append(
            "| "
            + " | ".join(
                [
                    mode,
                    str(row.n),
                    _fmt_pct(row.success_rate),
                    _fmt(row.mean_cmds),
                    _fmt(row.median_cmds),
                    _fmt(row.mean_errors),
                    _fmt(row.mean_total_tokens),
                ]
            )
            + " |"
        )
    return lines


def _decision_row(label: str, metrics: DecisionMetrics) -> str:
    success_ci = f"[{_fmt(metrics.success_ci_low)}, {_fmt(metrics.success_ci_high)}]"
    cmd_ci = f"[{_fmt(metrics.cmd_ci_low)}, {_fmt(metrics.cmd_ci_high)}]"
    return (
        "| "
        + " | ".join(
            [
                label,
                str(metrics.pair_count),
                _fmt(metrics.success_delta_pp),
                _fmt(metrics.median_cmd_delta),
                _fmt(metrics.token_ratio),
                success_ci,
                cmd_ci,
                "yes" if metrics.ci_favorable else "no",
                metrics.verdict,
            ]
        )
        + " |"
    )


def _render_markdown(
    *,
    baseline: str,
    candidate: str,
    ci_level: float,
    model_mode_stats: dict[str, dict[str, ModeSummary]],
    pooled_mode_stats: dict[str, ModeSummary],
    model_metrics: dict[str, DecisionMetrics],
    pooled_metrics: DecisionMetrics,
    final_statement: str,
) -> str:
    ci_percent = int(round(ci_level * 100))
    lines: list[str] = [
        "# OpenCLI/jelp Decision Memo",
        "",
        f"- Baseline: `{baseline}`",
        f"- Candidate: `{candidate}`",
        f"- Confidence interval: `{ci_percent}%` bootstrap",
        "",
        "## Per-model mode summary",
        "",
    ]

    for model in sorted(model_mode_stats):
        lines.append(f"### {model}")
        lines.extend(_mode_table(model_mode_stats[model]))
        lines.append("")

    lines.extend(
        [
            "## Pooled mode summary",
            "",
        ]
    )
    lines.extend(_mode_table(pooled_mode_stats))
    lines.extend(
        [
            "",
            "## Per-model decision metrics",
            "",
            "| model | pairs | success_delta_pp | median_cmd_delta | token_ratio | success_ci | median_cmd_ci | ci_favorable | verdict |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for model in sorted(model_metrics):
        lines.append(_decision_row(model, model_metrics[model]))

    lines.extend(
        [
            "",
            "## Pooled decision metrics",
            "",
            "| scope | pairs | success_delta_pp | median_cmd_delta | token_ratio | success_ci | median_cmd_ci | ci_favorable | verdict |",
            "| --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
            _decision_row("all-models", pooled_metrics),
            "",
            "## Final verdict",
            "",
            f"- `{final_statement}`",
            "",
            "## Caveats",
            "",
            "- Verdict is cost-adjusted for current model behavior and prompting strategy.",
            "- Token ratio is point-estimated from mean total tokens in paired runs.",
            "- CIs are bootstrap estimates; low pair counts widen uncertainty.",
        ]
    )
    return "\n".join(lines)


def build_decision_report(
    *,
    input_paths: list[Path],
    baseline: str = DEFAULT_BASELINE,
    candidate: str = DEFAULT_CANDIDATE,
    ci_level: float = DEFAULT_CI_LEVEL,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> tuple[dict[str, object], str]:
    rows = _load_summary_rows(input_paths)
    pooled_mode_stats = _mode_stats(rows)

    model_names = sorted({row.model for row in rows})
    model_mode_stats: dict[str, dict[str, ModeSummary]] = {}
    model_metrics: dict[str, DecisionMetrics] = {}
    for index, model in enumerate(model_names):
        model_rows = [row for row in rows if row.model == model]
        model_mode_stats[model] = _mode_stats(model_rows)
        model_pairs = _paired_rows(model_rows, baseline=baseline, candidate=candidate)
        model_metrics[model] = _decision_metrics(
            model_pairs,
            ci_level=ci_level,
            bootstrap_samples=bootstrap_samples,
            seed=seed + index,
        )

    pooled_pairs = _paired_rows(rows, baseline=baseline, candidate=candidate)
    pooled_metrics = _decision_metrics(
        pooled_pairs,
        ci_level=ci_level,
        bootstrap_samples=bootstrap_samples,
        seed=seed + 10_000,
    )

    model_verdicts = {
        metrics.verdict for metrics in model_metrics.values() if metrics.pair_count > 0
    }
    if not model_verdicts:
        final_statement = VERDICT_INSUFFICIENT
    elif len(model_verdicts) > 1:
        final_statement = VERDICT_MODEL_SENSITIVE
    else:
        final_statement = next(iter(model_verdicts))

    report_payload = {
        "protocol": {
            "baseline": baseline,
            "candidate": candidate,
            "ci_level": ci_level,
            "bootstrap_samples": bootstrap_samples,
            "seed": seed,
            "decision_thresholds": {
                "success_delta_pp_min": 0.0,
                "median_cmd_delta_max_for_net_benefit": -0.5,
                "token_ratio_max_for_net_benefit": 1.75,
                "ci_direction_rule": "success_ci_low >= 0 and cmd_ci_high <= -0.5",
            },
        },
        "inputs": [str(path) for path in input_paths],
        "models": {
            model: {
                "mode_summary": {
                    mode: _mode_summary_to_dict(summary)
                    for mode, summary in sorted(model_mode_stats[model].items())
                },
                "decision": _decision_to_dict(model_metrics[model]),
            }
            for model in sorted(model_metrics)
        },
        "pooled": {
            "mode_summary": {
                mode: _mode_summary_to_dict(summary)
                for mode, summary in sorted(pooled_mode_stats.items())
            },
            "decision": _decision_to_dict(pooled_metrics),
        },
        "final_statement": final_statement,
    }

    markdown = _render_markdown(
        baseline=baseline,
        candidate=candidate,
        ci_level=ci_level,
        model_mode_stats=model_mode_stats,
        pooled_mode_stats=pooled_mode_stats,
        model_metrics=model_metrics,
        pooled_metrics=pooled_metrics,
        final_statement=final_statement,
    )
    return report_payload, markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctf-decision-report")
    parser.add_argument("--in", dest="inputs", action="append", required=True)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE)
    parser.add_argument("--candidate", default=DEFAULT_CANDIDATE)
    parser.add_argument("--ci-level", type=float, default=DEFAULT_CI_LEVEL)
    parser.add_argument(
        "--bootstrap-samples", type=int, default=DEFAULT_BOOTSTRAP_SAMPLES
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json-out")
    parser.add_argument("--md-out")
    parser.add_argument("--print-json", action="store_true")
    args = parser.parse_args(argv)

    if not (0.0 < args.ci_level < 1.0):
        parser.error("--ci-level must be between 0 and 1")
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be >= 1")

    input_paths = [Path(path) for path in args.inputs]
    report_payload, markdown = build_decision_report(
        input_paths=input_paths,
        baseline=args.baseline,
        candidate=args.candidate,
        ci_level=args.ci_level,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )

    if args.md_out:
        md_path = Path(args.md_out)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")
        print(f"Wrote markdown memo: {md_path}")

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Wrote machine-readable verdict: {json_path}")

    print(markdown)
    if args.print_json:
        print()
        print(json.dumps(report_payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
