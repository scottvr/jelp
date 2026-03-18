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

SUCCESS_DELTA_THRESHOLD = 0.0
MEDIAN_CMD_DELTA_THRESHOLD = -0.5
TOKEN_RATIO_THRESHOLD = 1.75


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


@dataclass(frozen=True)
class PairAccounting:
    observed_pairs: int
    expected_pairs: int
    pair_coverage: float
    baseline_only: int
    candidate_only: int


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
        pair_key = _pair_key(row)
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


def _pair_key(row: SummaryRow) -> tuple[str, str, int, str]:
    return (row.model, row.run_id, row.iteration, row.scenario_id)


def _pair_accounting(
    rows: list[SummaryRow], *, baseline: str, candidate: str
) -> PairAccounting:
    baseline_keys = {_pair_key(row) for row in rows if row.mode == baseline}
    candidate_keys = {_pair_key(row) for row in rows if row.mode == candidate}
    observed_pairs = len(baseline_keys & candidate_keys)
    expected_pairs = len(baseline_keys | candidate_keys)
    pair_coverage = (
        float("nan") if expected_pairs == 0 else observed_pairs / expected_pairs
    )
    return PairAccounting(
        observed_pairs=observed_pairs,
        expected_pairs=expected_pairs,
        pair_coverage=pair_coverage,
        baseline_only=len(baseline_keys - candidate_keys),
        candidate_only=len(candidate_keys - baseline_keys),
    )


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

    if success_delta_pp < SUCCESS_DELTA_THRESHOLD or median_cmd_delta >= 0:
        return VERDICT_NO_NET

    if (
        success_delta_pp >= SUCCESS_DELTA_THRESHOLD
        and median_cmd_delta <= MEDIAN_CMD_DELTA_THRESHOLD
    ):
        if token_ratio <= TOKEN_RATIO_THRESHOLD and ci_favorable:
            return VERDICT_NET_BENEFIT
        return VERDICT_PROMISING

    return VERDICT_NO_NET


def classify_raw_verdict(
    *,
    success_delta_pp: float,
    median_cmd_delta: float,
    ci_favorable: bool,
) -> str:
    if math.isnan(success_delta_pp) or math.isnan(median_cmd_delta):
        return VERDICT_INSUFFICIENT

    if success_delta_pp < SUCCESS_DELTA_THRESHOLD or median_cmd_delta >= 0:
        return VERDICT_NO_NET

    if (
        success_delta_pp >= SUCCESS_DELTA_THRESHOLD
        and median_cmd_delta <= MEDIAN_CMD_DELTA_THRESHOLD
    ):
        if ci_favorable:
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
    ci_favorable = (
        success_ci_low >= SUCCESS_DELTA_THRESHOLD
        and cmd_ci_high <= MEDIAN_CMD_DELTA_THRESHOLD
    )

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


def _raw_verdict_from_metrics(metrics: DecisionMetrics) -> str:
    return classify_raw_verdict(
        success_delta_pp=metrics.success_delta_pp,
        median_cmd_delta=metrics.median_cmd_delta,
        ci_favorable=metrics.ci_favorable,
    )


def _cost_adjustment_impact(
    metrics: DecisionMetrics,
) -> tuple[str, bool, str | None]:
    raw_verdict = _raw_verdict_from_metrics(metrics)
    changed = raw_verdict != metrics.verdict
    if not changed:
        return raw_verdict, False, None
    if (
        raw_verdict == VERDICT_NET_BENEFIT
        and metrics.verdict == VERDICT_PROMISING
        and metrics.token_ratio > TOKEN_RATIO_THRESHOLD
    ):
        return (
            raw_verdict,
            True,
            f"token_ratio_obs > {TOKEN_RATIO_THRESHOLD:.2f}",
        )
    return raw_verdict, True, "cost-adjusted thresholds changed classification"


def _safe_number(value: float) -> float | None:
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _ci_width(low: float, high: float) -> float:
    if math.isnan(low) or math.isnan(high) or math.isinf(low) or math.isinf(high):
        return float("nan")
    return high - low


def _contains_threshold(low: float, high: float, threshold: float) -> bool:
    if math.isnan(low) or math.isnan(high) or math.isinf(low) or math.isinf(high):
        return False
    lower = min(low, high)
    upper = max(low, high)
    return lower <= threshold <= upper


def _is_borderline(metrics: DecisionMetrics) -> bool:
    return (
        _contains_threshold(
            metrics.success_ci_low,
            metrics.success_ci_high,
            SUCCESS_DELTA_THRESHOLD,
        )
        or _contains_threshold(
            metrics.cmd_ci_low,
            metrics.cmd_ci_high,
            MEDIAN_CMD_DELTA_THRESHOLD,
        )
        or _contains_threshold(
            metrics.token_ratio_ci_low,
            metrics.token_ratio_ci_high,
            TOKEN_RATIO_THRESHOLD,
        )
    )


def _borderline_reasons(metrics: DecisionMetrics) -> list[str]:
    reasons: list[str] = []
    if _contains_threshold(
        metrics.success_ci_low,
        metrics.success_ci_high,
        SUCCESS_DELTA_THRESHOLD,
    ):
        reasons.append(f"success_ci includes threshold {SUCCESS_DELTA_THRESHOLD:.1f}pp")
    if _contains_threshold(
        metrics.cmd_ci_low,
        metrics.cmd_ci_high,
        MEDIAN_CMD_DELTA_THRESHOLD,
    ):
        reasons.append(
            f"median_cmd_ci includes threshold {MEDIAN_CMD_DELTA_THRESHOLD:.1f}"
        )
    if _contains_threshold(
        metrics.token_ratio_ci_low,
        metrics.token_ratio_ci_high,
        TOKEN_RATIO_THRESHOLD,
    ):
        reasons.append(f"token_ratio_ci includes threshold {TOKEN_RATIO_THRESHOLD:.2f}")
    return reasons


def _pass_fail(condition: bool) -> str:
    return "pass" if condition else "fail"


def _decision_driver_lines(
    *,
    label: str,
    metrics: DecisionMetrics,
    accounting: PairAccounting,
    include_label_line: bool = True,
) -> list[str]:
    observed_success_ok = metrics.success_delta_pp >= SUCCESS_DELTA_THRESHOLD
    observed_cmd_ok = metrics.median_cmd_delta <= MEDIAN_CMD_DELTA_THRESHOLD
    observed_token_ok = metrics.token_ratio <= TOKEN_RATIO_THRESHOLD
    ci_success_ok = metrics.success_ci_low >= SUCCESS_DELTA_THRESHOLD
    ci_cmd_ok = metrics.cmd_ci_high <= MEDIAN_CMD_DELTA_THRESHOLD
    borderline = _is_borderline(metrics)
    borderline_reasons = _borderline_reasons(metrics)
    reason_suffix = f" ({'; '.join(borderline_reasons)})" if borderline_reasons else ""
    lines: list[str] = []
    if include_label_line:
        lines.append(
            f"- `{label}`: observed pairs `{accounting.observed_pairs}/{accounting.expected_pairs}` (coverage `{_fmt_pct(accounting.pair_coverage)}`)"
        )
    else:
        lines.append(
            f"- observed pairs `{accounting.observed_pairs}/{accounting.expected_pairs}` (coverage `{_fmt_pct(accounting.pair_coverage)}`)"
        )
    lines.extend(
        [
            (
                f"- `success_delta_pp_obs={_fmt(metrics.success_delta_pp)}` vs threshold `>= {SUCCESS_DELTA_THRESHOLD:.1f}`: "
                f"`{_pass_fail(observed_success_ok)}`; `success_ci_boot=[{_fmt(metrics.success_ci_low)}, {_fmt(metrics.success_ci_high)}]`"
            ),
            (
                f"- `median_cmd_delta_obs={_fmt(metrics.median_cmd_delta)}` vs threshold `<= {MEDIAN_CMD_DELTA_THRESHOLD:.1f}`: "
                f"`{_pass_fail(observed_cmd_ok)}`; `median_cmd_ci_boot=[{_fmt(metrics.cmd_ci_low)}, {_fmt(metrics.cmd_ci_high)}]`"
            ),
            (
                f"- `token_ratio_obs={_fmt(metrics.token_ratio)}` vs threshold `<= {TOKEN_RATIO_THRESHOLD:.2f}`: "
                f"`{_pass_fail(observed_token_ok)}`; `token_ratio_ci_boot=[{_fmt(metrics.token_ratio_ci_low)}, {_fmt(metrics.token_ratio_ci_high)}]`"
            ),
            (
                f"- `ci_favorable` gate (`success_ci_low >= {SUCCESS_DELTA_THRESHOLD:.1f}` and "
                f"`cmd_ci_high <= {MEDIAN_CMD_DELTA_THRESHOLD:.1f}`): "
                f"`{_pass_fail(ci_success_ok and ci_cmd_ok)}` "
                f"(success part: `{_pass_fail(ci_success_ok)}`, command part: `{_pass_fail(ci_cmd_ok)}`)"
            ),
            f"- `borderline`: `{'yes' if borderline else 'no'}`{reason_suffix}",
            f"- Derived verdict: `{metrics.verdict}`",
        ]
    )
    return lines


def _cost_impact_row(label: str, *, metrics: DecisionMetrics) -> str:
    raw_verdict, changed, reason = _cost_adjustment_impact(metrics)
    return (
        "| "
        + " | ".join(
            [
                label,
                raw_verdict,
                metrics.verdict,
                "yes" if changed else "no",
                _fmt(metrics.token_ratio),
                f"{TOKEN_RATIO_THRESHOLD:.2f}",
                reason or "-",
            ]
        )
        + " |"
    )


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
    success_ci_width = _ci_width(metrics.success_ci_low, metrics.success_ci_high)
    cmd_ci_width = _ci_width(metrics.cmd_ci_low, metrics.cmd_ci_high)
    token_ratio_ci_width = _ci_width(
        metrics.token_ratio_ci_low, metrics.token_ratio_ci_high
    )
    borderline = _is_borderline(metrics)
    raw_verdict, cost_adjustment_changed, cost_adjustment_reason = (
        _cost_adjustment_impact(metrics)
    )
    return {
        # Back-compat keys:
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
        # Provenance-explicit keys:
        "success_delta_pp_obs": _safe_number(metrics.success_delta_pp),
        "median_cmd_delta_obs": _safe_number(metrics.median_cmd_delta),
        "token_ratio_obs": _safe_number(metrics.token_ratio),
        "success_ci_boot": [
            _safe_number(metrics.success_ci_low),
            _safe_number(metrics.success_ci_high),
        ],
        "median_cmd_ci_boot": [
            _safe_number(metrics.cmd_ci_low),
            _safe_number(metrics.cmd_ci_high),
        ],
        "token_ratio_ci_boot": [
            _safe_number(metrics.token_ratio_ci_low),
            _safe_number(metrics.token_ratio_ci_high),
        ],
        "success_ci_width_pp": _safe_number(success_ci_width),
        "median_cmd_ci_width": _safe_number(cmd_ci_width),
        "token_ratio_ci_width": _safe_number(token_ratio_ci_width),
        "borderline": borderline,
        "raw_verdict_no_cost": raw_verdict,
        "cost_adjusted_verdict": metrics.verdict,
        "cost_adjustment_changed": cost_adjustment_changed,
        "cost_adjustment_reason": cost_adjustment_reason,
        "ci_favorable": metrics.ci_favorable,
        "verdict": metrics.verdict,
    }


def _pair_accounting_to_dict(accounting: PairAccounting) -> dict[str, object]:
    return {
        "observed_pairs_used": accounting.observed_pairs,
        "expected_pairs": accounting.expected_pairs,
        "pair_coverage": _safe_number(accounting.pair_coverage),
        "baseline_only": accounting.baseline_only,
        "candidate_only": accounting.candidate_only,
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


def _annotated_mode_label(*, mode: str, baseline: str, candidate: str) -> str:
    if mode == baseline and mode == candidate:
        return f"(B/C) {mode}"
    if mode == baseline:
        return f"(B) {mode}"
    if mode == candidate:
        return f"(C) {mode}"
    return mode


def _mode_table(
    mode_stats: dict[str, ModeSummary], *, baseline: str, candidate: str
) -> list[str]:
    lines = [
        "| mode | n | success | mean_cmds | median_cmds | mean_errors | mean_total_tok |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode in sorted(mode_stats):
        row = mode_stats[mode]
        mode_label = _annotated_mode_label(
            mode=mode, baseline=baseline, candidate=candidate
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    mode_label,
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


def _decision_row(
    label: str,
    *,
    metrics: DecisionMetrics,
    accounting: PairAccounting,
) -> str:
    success_ci = f"[{_fmt(metrics.success_ci_low)}, {_fmt(metrics.success_ci_high)}]"
    cmd_ci = f"[{_fmt(metrics.cmd_ci_low)}, {_fmt(metrics.cmd_ci_high)}]"
    token_ci = (
        f"[{_fmt(metrics.token_ratio_ci_low)}, {_fmt(metrics.token_ratio_ci_high)}]"
    )
    borderline = _is_borderline(metrics)
    return (
        "| "
        + " | ".join(
            [
                label,
                str(accounting.observed_pairs),
                str(accounting.expected_pairs),
                _fmt_pct(accounting.pair_coverage),
                _fmt(metrics.success_delta_pp),
                _fmt(metrics.median_cmd_delta),
                _fmt(metrics.token_ratio),
                success_ci,
                cmd_ci,
                token_ci,
                _fmt(_ci_width(metrics.success_ci_low, metrics.success_ci_high)),
                _fmt(_ci_width(metrics.cmd_ci_low, metrics.cmd_ci_high)),
                _fmt(
                    _ci_width(metrics.token_ratio_ci_low, metrics.token_ratio_ci_high)
                ),
                "yes" if borderline else "no",
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
    bootstrap_samples: int,
    base_seed: int,
    model_seeds: dict[str, int],
    pooled_seed: int,
    model_mode_stats: dict[str, dict[str, ModeSummary]],
    model_accounting: dict[str, PairAccounting],
    pooled_mode_stats: dict[str, ModeSummary],
    pooled_accounting: PairAccounting,
    model_metrics: dict[str, DecisionMetrics],
    pooled_metrics: DecisionMetrics,
    model_driver_lines: dict[str, list[str]],
    pooled_driver_lines: list[str],
    final_statement: str,
) -> str:
    ci_percent = int(round(ci_level * 100))
    lines: list[str] = [
        "# OpenCLI/jelp Decision Memo",
        "",
        f"- Baseline: `{baseline}`",
        f"- Candidate: `{candidate}`",
        f"- Confidence interval: `{ci_percent}%` bootstrap",
        f"- Bootstrap samples: `{bootstrap_samples}`",
        f"- Base seed: `{base_seed}`",
        "",
        "Interpretation note:",
        "- Columns ending in `_obs` come directly from observed paired runs.",
        "- Columns ending in `_ci_boot` are bootstrap uncertainty estimates.",
        (
            "- `borderline=yes` means at least one bootstrap CI interval crosses a "
            "decision threshold, so classification may be sensitive to modest variation."
        ),
        "",
        "## Per-model mode summary",
        "",
    ]

    for model in sorted(model_mode_stats):
        lines.append(f"### {model}")
        lines.extend(
            _mode_table(
                model_mode_stats[model],
                baseline=baseline,
                candidate=candidate,
            )
        )
        lines.append("")

    lines.extend(
        [
            "## Pooled mode summary",
            "",
        ]
    )
    lines.extend(
        _mode_table(
            pooled_mode_stats,
            baseline=baseline,
            candidate=candidate,
        )
    )
    lines.extend(
        [
            "",
            "## Evidence accounting",
            "",
            "| scope | observed_pairs_used | expected_pairs | pair_coverage | baseline_only | candidate_only | bootstrap_samples | seed |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for model in sorted(model_metrics):
        accounting = model_accounting[model]
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    str(accounting.observed_pairs),
                    str(accounting.expected_pairs),
                    _fmt_pct(accounting.pair_coverage),
                    str(accounting.baseline_only),
                    str(accounting.candidate_only),
                    str(bootstrap_samples),
                    str(model_seeds[model]),
                ]
            )
            + " |"
        )
    lines.append(
        "| "
        + " | ".join(
            [
                "all-models",
                str(pooled_accounting.observed_pairs),
                str(pooled_accounting.expected_pairs),
                _fmt_pct(pooled_accounting.pair_coverage),
                str(pooled_accounting.baseline_only),
                str(pooled_accounting.candidate_only),
                str(bootstrap_samples),
                str(pooled_seed),
            ]
        )
        + " |"
    )

    lines.extend(
        [
            "",
            "## Per-model decision metrics",
            "",
            "| model | observed_pairs_used | expected_pairs | pair_coverage | success_delta_pp_obs | median_cmd_delta_obs | token_ratio_obs | success_ci_boot | median_cmd_ci_boot | token_ratio_ci_boot | success_ci_width | median_cmd_ci_width | token_ratio_ci_width | borderline | ci_favorable | verdict |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for model in sorted(model_metrics):
        lines.append(
            _decision_row(
                model,
                metrics=model_metrics[model],
                accounting=model_accounting[model],
            )
        )

    lines.extend(
        [
            "",
            "## Pooled decision metrics",
            "",
            "| scope | observed_pairs_used | expected_pairs | pair_coverage | success_delta_pp_obs | median_cmd_delta_obs | token_ratio_obs | success_ci_boot | median_cmd_ci_boot | token_ratio_ci_boot | success_ci_width | median_cmd_ci_width | token_ratio_ci_width | borderline | ci_favorable | verdict |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
            _decision_row(
                "all-models",
                metrics=pooled_metrics,
                accounting=pooled_accounting,
            ),
            "",
            "## Cost adjustment impact",
            "",
            "| scope | raw_verdict_no_cost | cost_adjusted_verdict | changed_by_cost | token_ratio_obs | token_ratio_threshold | reason |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for model in sorted(model_metrics):
        lines.append(_cost_impact_row(model, metrics=model_metrics[model]))
    lines.append(_cost_impact_row("all-models", metrics=pooled_metrics))

    lines.extend(
        [
            "",
            "## Final verdict",
            "",
            f"- `{final_statement}`",
            "",
            "## Decision drivers",
            "",
        ]
    )
    lines.extend(pooled_driver_lines)
    if model_driver_lines:
        lines.extend(["", "### Per-model drivers", ""])
        for model in sorted(model_driver_lines):
            lines.append(f"**{model}**")
            lines.extend(model_driver_lines[model])
            lines.append("")

    lines.extend(
        [
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
    model_accounting: dict[str, PairAccounting] = {}
    model_metrics: dict[str, DecisionMetrics] = {}
    model_driver_lines: dict[str, list[str]] = {}
    model_seeds: dict[str, int] = {}
    for index, model in enumerate(model_names):
        model_rows = [row for row in rows if row.model == model]
        model_mode_stats[model] = _mode_stats(model_rows)
        model_accounting[model] = _pair_accounting(
            model_rows, baseline=baseline, candidate=candidate
        )
        model_pairs = _paired_rows(model_rows, baseline=baseline, candidate=candidate)
        model_seed = seed + index
        model_seeds[model] = model_seed
        model_metrics[model] = _decision_metrics(
            model_pairs,
            ci_level=ci_level,
            bootstrap_samples=bootstrap_samples,
            seed=model_seed,
        )
        model_driver_lines[model] = _decision_driver_lines(
            label=model,
            metrics=model_metrics[model],
            accounting=model_accounting[model],
            include_label_line=False,
        )

    pooled_accounting = _pair_accounting(rows, baseline=baseline, candidate=candidate)
    pooled_pairs = _paired_rows(rows, baseline=baseline, candidate=candidate)
    pooled_seed = seed + 10_000
    pooled_metrics = _decision_metrics(
        pooled_pairs,
        ci_level=ci_level,
        bootstrap_samples=bootstrap_samples,
        seed=pooled_seed,
    )
    pooled_driver_lines = _decision_driver_lines(
        label="all-models",
        metrics=pooled_metrics,
        accounting=pooled_accounting,
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
                "success_delta_pp_min": SUCCESS_DELTA_THRESHOLD,
                "median_cmd_delta_max_for_net_benefit": MEDIAN_CMD_DELTA_THRESHOLD,
                "token_ratio_max_for_net_benefit": TOKEN_RATIO_THRESHOLD,
                "ci_direction_rule": "success_ci_low >= 0 and cmd_ci_high <= -0.5",
            },
            "metric_provenance": {
                "obs_suffix": "observed paired-run estimates from real data",
                "ci_boot_suffix": "bootstrap confidence interval estimates",
                "borderline": (
                    "true when any bootstrap CI overlaps a decision threshold"
                ),
            },
        },
        "inputs": [str(path) for path in input_paths],
        "models": {
            model: {
                "evidence": _pair_accounting_to_dict(model_accounting[model]),
                "mode_summary": {
                    mode: _mode_summary_to_dict(summary)
                    for mode, summary in sorted(model_mode_stats[model].items())
                },
                "decision": _decision_to_dict(model_metrics[model]),
                "decision_drivers": model_driver_lines[model],
            }
            for model in sorted(model_metrics)
        },
        "pooled": {
            "evidence": _pair_accounting_to_dict(pooled_accounting),
            "mode_summary": {
                mode: _mode_summary_to_dict(summary)
                for mode, summary in sorted(pooled_mode_stats.items())
            },
            "decision": _decision_to_dict(pooled_metrics),
            "decision_drivers": pooled_driver_lines,
        },
        "final_statement": final_statement,
        "cost_adjustment_summary": {
            "models_with_changed_verdict": sorted(
                [
                    model
                    for model, metrics in model_metrics.items()
                    if _cost_adjustment_impact(metrics)[1]
                ]
            ),
            "pooled_changed": _cost_adjustment_impact(pooled_metrics)[1],
        },
    }

    markdown = _render_markdown(
        baseline=baseline,
        candidate=candidate,
        ci_level=ci_level,
        bootstrap_samples=bootstrap_samples,
        base_seed=seed,
        model_seeds=model_seeds,
        pooled_seed=pooled_seed,
        model_mode_stats=model_mode_stats,
        model_accounting=model_accounting,
        pooled_mode_stats=pooled_mode_stats,
        pooled_accounting=pooled_accounting,
        model_metrics=model_metrics,
        pooled_metrics=pooled_metrics,
        model_driver_lines=model_driver_lines,
        pooled_driver_lines=pooled_driver_lines,
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
