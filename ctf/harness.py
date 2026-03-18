from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from statistics import median
from pathlib import Path

from ctf.adapters import TurnRecord, build_adapter
from ctf.scenarios import SCENARIOS, Scenario, fixture_dir

FLAG_RE = re.compile(r"FLAG\{[^}]+\}")
SHELL_CONTROL_TOKENS = {";", "|", "||", "&&", ">", "<", ">>", "<<", "&"}
DEBUG_IO_PREVIEW_CHARS = 1500
MODE_DEBUG_CODES: dict[str, str] = {
    "help-only": "ho",
    "help-only-primed": "hp",
    "jelp-useful": "ju",
    "jelp-primed": "jp",
    "jelp-no-meta": "jn",
    "jelp-all": "ja",
    "jelp-primed-useful": "jpu",
    "jelp-primed-incremental": "jpi",
    "jelp-primed-full": "jpf",
}
CHECKPOINT_SCHEMA_VERSION = 1


def _usage_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _split_command(command: str) -> tuple[list[str] | None, str | None]:
    try:
        return shlex.split(command), None
    except ValueError as exc:
        return None, str(exc)


def _detect_command_anomalies(*, command: str, tokens: list[str] | None) -> list[str]:
    reasons: list[str] = []
    if "\n" in command or "\r" in command:
        reasons.append("contains newline control characters")
    if "$(" in command:
        reasons.append("contains shell-style subshell marker '$('")
    if "`" in command:
        reasons.append("contains shell-style backtick execution marker")
    if tokens is not None:
        matched = sorted({token for token in tokens if token in SHELL_CONTROL_TOKENS})
        if matched:
            reasons.append(
                "contains shell control tokens: "
                + ", ".join(f"'{token}'" for token in matched)
            )
    return reasons


def _console_preview(text: str, *, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _scenario_debug_code(scenario_id: str) -> str:
    match = re.search(r"fixture(\d+)", scenario_id)
    if match:
        return f"f{int(match.group(1)):02d}"
    safe = re.sub(r"[^a-zA-Z0-9]+", "", scenario_id)
    return (safe[:4] or "sc").lower()


def _mode_debug_code(mode: str) -> str:
    return MODE_DEBUG_CODES.get(mode, "m")


def _summary_to_run_result(summary: dict[str, object]) -> RunResult:
    return RunResult(
        scenario_id=str(summary.get("scenario_id", "")),
        mode=str(summary.get("mode", "")),
        adapter=str(summary.get("adapter", "")),
        success=bool(summary.get("success", False)),
        matched_flag=(
            None
            if summary.get("matched_flag") is None
            else str(summary["matched_flag"])
        ),
        expected_flag=str(summary.get("expected_flag", "")),
        command_count=_usage_int(summary.get("command_count")),
        invalid_command_count=_usage_int(summary.get("invalid_command_count")),
        parser_error_count=_usage_int(summary.get("parser_error_count")),
        anomaly_count=_usage_int(summary.get("anomaly_count")),
        duration_s=float(summary.get("duration_s", 0.0)),
        time_to_success_s=(
            None
            if summary.get("time_to_success_s") is None
            else float(summary["time_to_success_s"])
        ),
        api_call_count=_usage_int(summary.get("api_call_count")),
        model_input_tokens=_usage_int(summary.get("model_input_tokens")),
        model_output_tokens=_usage_int(summary.get("model_output_tokens")),
        model_total_tokens=_usage_int(summary.get("model_total_tokens")),
    )


def _result_key(iteration: int, scenario_id: str, mode: str) -> tuple[int, str, str]:
    return (iteration, scenario_id, mode)


def _extract_completed_keys(run_log: dict[str, object]) -> set[tuple[int, str, str]]:
    keys: set[tuple[int, str, str]] = set()
    rows = run_log.get("results", [])
    if not isinstance(rows, list):
        return keys
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary", {})
        if not isinstance(summary, dict):
            continue
        keys.add(
            _result_key(
                _usage_int(row.get("iteration")) or 1,
                str(summary.get("scenario_id", "")),
                str(summary.get("mode", "")),
            )
        )
    return keys


def _resume_mismatch_reason(
    *,
    existing: dict[str, object],
    adapter: str,
    model: str,
    modes: list[str],
    iterations: int,
) -> str | None:
    existing_adapter = existing.get("adapter")
    if existing_adapter is not None and str(existing_adapter) != adapter:
        return f"adapter mismatch (existing={existing_adapter}, requested={adapter})"

    existing_model = existing.get("model")
    if existing_model is not None and str(existing_model) != model:
        return f"model mismatch (existing={existing_model}, requested={model})"

    existing_modes = existing.get("modes")
    if isinstance(existing_modes, list):
        existing_modes_norm = [str(mode_name) for mode_name in existing_modes]
        if existing_modes_norm != modes:
            return f"modes mismatch (existing={existing_modes_norm}, requested={modes})"

    existing_iterations = existing.get("iterations")
    if (
        existing_iterations is not None
        and _usage_int(existing_iterations) != iterations
    ):
        return (
            "iterations mismatch "
            f"(existing={existing_iterations}, requested={iterations})"
        )

    return None


def _new_run_log(
    *,
    adapter: str,
    model: str,
    modes: list[str],
    iterations: int,
    selected_scenarios: list[str],
) -> dict[str, object]:
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "adapter": adapter,
        "model": model,
        "modes": modes,
        "iterations": iterations,
        "selected_scenarios": selected_scenarios,
        "results": [],
    }


def _write_run_log_checkpoint(path: Path, run_log: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_log["last_checkpoint_utc"] = datetime.now(UTC).isoformat()
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    temp.replace(path)


def _command_rejection_reason(*, tokens: list[str], expected_script: str) -> str | None:
    if not tokens:
        return "command must start with 'python '"
    if tokens[0] != "python":
        return "command must start with 'python '"
    if len(tokens) < 2:
        return f"command must target '{expected_script}'"
    if tokens[1] != expected_script:
        return f"command must target '{expected_script}'"
    return None


@dataclass
class RunResult:
    scenario_id: str
    mode: str
    adapter: str
    success: bool
    matched_flag: str | None
    expected_flag: str
    command_count: int
    invalid_command_count: int
    parser_error_count: int
    anomaly_count: int
    duration_s: float
    time_to_success_s: float | None
    api_call_count: int
    model_input_tokens: int
    model_output_tokens: int
    model_total_tokens: int


def _policy_violation(mode: str, tokens: list[str]) -> str | None:
    jelp_tokens = {
        "--jelp",
        "--jelp-pretty",
        "--jelp-no-meta",
        "--jelp-all",
        "--jelp-all-commands",
        "--jelp-all-no-meta",
    }
    help_tokens = {"-h", "--help"}

    if mode in {"help-only", "help-only-primed"} and any(
        token in jelp_tokens for token in tokens
    ):
        return "jelp flags disallowed in help-only mode"

    if mode in {"jelp-useful", "jelp-primed"} and any(
        token in {"--jelp-no-meta", "--jelp-all", "--jelp-all-no-meta"}
        for token in tokens
    ):
        return "only --jelp/--jelp-pretty/--jelp-all-commands allowed in jelp-useful/jelp-primed modes"

    if mode == "jelp-no-meta" and any(
        token in {"--jelp", "--jelp-pretty", "--jelp-all", "--jelp-all-commands"}
        for token in tokens
    ):
        return "only --jelp-no-meta/--jelp-all-no-meta allowed in jelp-no-meta mode"

    if mode == "jelp-primed-incremental":
        if any(token in help_tokens for token in tokens):
            return "--help is disallowed in jelp-primed-incremental mode; use --jelp traversal"
        if any(
            token
            in {
                "--jelp-no-meta",
                "--jelp-all",
                "--jelp-all-commands",
                "--jelp-all-no-meta",
            }
            for token in tokens
        ):
            return "only --jelp/--jelp-pretty allowed in jelp-primed-incremental mode"

    if mode == "jelp-primed-useful":
        if any(token in help_tokens for token in tokens):
            return "--help is disallowed in jelp-primed-useful mode; use --jelp"
        if any(
            token
            in {
                "--jelp-pretty",
                "--jelp-no-meta",
                "--jelp-all",
                "--jelp-all-commands",
                "--jelp-all-no-meta",
            }
            for token in tokens
        ):
            return "only --jelp allowed in jelp-primed-useful mode"

    if mode == "jelp-primed-full":
        if any(token in help_tokens for token in tokens):
            return (
                "--help is disallowed in jelp-primed-full mode; use --jelp-all-commands"
            )
        if any(
            token
            in {
                "--jelp",
                "--jelp-pretty",
                "--jelp-no-meta",
                "--jelp-all",
                "--jelp-all-no-meta",
            }
            for token in tokens
        ):
            return "only --jelp-all-commands allowed in jelp-primed-full mode"

    return None


def _is_non_penalized_jelp_probe(mode: str, command: str, violation: str) -> bool:
    tokens, split_error = _split_command(command)
    if split_error is not None or tokens is None:
        return False
    return _is_non_penalized_jelp_probe_tokens(
        mode=mode,
        tokens=tokens,
        violation=violation,
    )


def _is_non_penalized_jelp_probe_tokens(
    *, mode: str, tokens: list[str], violation: str
) -> bool:
    if mode != "help-only-primed":
        return False
    if "jelp flags disallowed" not in violation:
        return False
    return any(token.startswith("--jelp") for token in tokens)


def _execute_command(
    command: str,
    *,
    argv_tokens: list[str],
    cwd: Path,
    env: dict[str, str],
    timeout_s: float,
) -> TurnRecord:
    executable_argv = [sys.executable, *argv_tokens[1:]]
    try:
        proc = subprocess.run(
            executable_argv,
            cwd=str(cwd),
            env=env,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return TurnRecord(
            command=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        suffix = f"Timed out after {timeout_s}s"
        stderr = f"{stderr}\n{suffix}".strip()
        return TurnRecord(
            command=command,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )


def _run_single(
    *,
    scenario: Scenario,
    mode: str,
    adapter_name: str,
    model: str,
    max_steps: int,
    timeout_s: float,
    repo_root: Path,
    debug: bool,
    api_timeout_s: float,
    temperature: float | None,
    response_max_output_tokens: int,
    adapter_retries: int,
    reject_duplicates: bool,
    iteration_index: int,
    iteration_total: int,
) -> tuple[
    RunResult,
    list[TurnRecord],
    list[str],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    debug_events: list[str] = []
    model_usage_events: list[dict[str, object]] = []
    anomaly_events: list[dict[str, object]] = []

    def _record_debug_event(message: str) -> None:
        if debug:
            debug_events.append(message)

    def _emit_debug(message: str) -> None:
        if debug:
            print(message, flush=True)
            _record_debug_event(message)

    def _record_usage_event(event: dict[str, object]) -> None:
        model_usage_events.append(event)

    adapter = build_adapter(
        adapter_name,
        model=model,
        debug=debug,
        api_timeout_s=api_timeout_s,
        temperature=temperature,
        max_output_tokens=response_max_output_tokens,
        retries=adapter_retries,
        debug_sink=_record_debug_event if debug else None,
        usage_sink=_record_usage_event if adapter_name == "openai" else None,
    )
    turns: list[TurnRecord] = []
    invalid = 0
    parser_errors = 0
    matched_flag: str | None = None
    t0 = time.perf_counter()
    success_time: float | None = None
    seen_commands: set[str] = set()
    counted_steps = 0
    free_probe_rejections = 0

    fixtures = fixture_dir(repo_root)
    allowed_prefix = f"python {scenario.script}"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["JELP_MODE"] = mode

    def _emit_anomaly(*, step: int, command: str, reason: str) -> None:
        scope = (
            f"i{iteration_index:02d}."
            f"{_scenario_debug_code(scenario.id)}."
            f"{_mode_debug_code(mode)}."
            f"s{step:02d}"
        )
        event = {
            "scope": scope,
            "iteration": iteration_index,
            "iteration_total": iteration_total,
            "step": step,
            "scenario_id": scenario.id,
            "mode": mode,
            "command": command,
            "reason": reason,
        }
        anomaly_events.append(event)
        message = (
            f"[anomaly][{scope}] iteration={iteration_index}/{iteration_total} "
            f"scenario={scenario.id} mode={mode} step={step} "
            f"reason={reason} command={command}"
        )
        print(message, flush=True)
        if debug:
            _record_debug_event(message)

    while counted_steps < max_steps:
        step = counted_steps + 1
        scope = (
            f"i{iteration_index:02d}."
            f"{_scenario_debug_code(scenario.id)}."
            f"{_mode_debug_code(mode)}."
            f"s{step:02d}"
        )
        _emit_debug(
            f"[debug][{scope}] iteration={iteration_index}/{iteration_total} "
            f"scenario={scenario.id} mode={mode} step={step}"
        )
        command = adapter.next_command(
            scenario=scenario,
            mode=mode,
            turns=turns,
            allowed_prefix=allowed_prefix,
            debug_scope=scope,
        ).strip()

        if not command:
            _emit_debug(
                f"[debug][{scope}] adapter returned empty command; stopping scenario loop"
            )
            break
        _emit_debug(f"[debug][{scope}] command: {command}")

        if reject_duplicates and command in seen_commands:
            invalid += 1
            turns.append(
                TurnRecord(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr="Rejected: duplicate command (already attempted).",
                )
            )
            _emit_debug(f"[debug][{scope}] rejected command: duplicate")
            counted_steps += 1
            continue
        seen_commands.add(command)

        tokens, split_error = _split_command(command)
        for reason in _detect_command_anomalies(command=command, tokens=tokens):
            _emit_anomaly(step=step, command=command, reason=reason)

        if split_error is not None or tokens is None:
            invalid += 1
            turns.append(
                TurnRecord(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr=f"Rejected: malformed command syntax ({split_error})",
                )
            )
            _emit_debug(f"[debug][{scope}] rejected command: malformed syntax")
            counted_steps += 1
            continue

        target_rejection = _command_rejection_reason(
            tokens=tokens,
            expected_script=scenario.script,
        )
        if target_rejection is not None:
            invalid += 1
            turns.append(
                TurnRecord(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr=f"Rejected: {target_rejection}",
                )
            )
            _emit_debug(f"[debug][{scope}] rejected command: {target_rejection}")
            counted_steps += 1
            continue

        violation = _policy_violation(mode, tokens)
        if violation:
            invalid += 1
            turns.append(
                TurnRecord(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr=f"Rejected: {violation}",
                )
            )
            _emit_debug(f"[debug][{scope}] policy violation: {violation}")
            if _is_non_penalized_jelp_probe_tokens(
                mode=mode,
                tokens=tokens,
                violation=violation,
            ):
                free_probe_rejections += 1
                _emit_debug(
                    f"[debug][{scope}] non-penalized jelp probe rejected; step budget unchanged"
                )
                if free_probe_rejections >= max_steps:
                    _emit_debug(
                        f"[debug][{scope}] too many non-penalized probe rejections; stopping scenario loop"
                    )
                    break
                continue
            counted_steps += 1
            continue

        turn = _execute_command(
            command,
            argv_tokens=tokens,
            cwd=fixtures,
            env=env,
            timeout_s=timeout_s,
        )
        turns.append(turn)
        counted_steps += 1
        _emit_debug(f"[debug][{scope}] exit={turn.returncode}")
        if turn.stdout:
            preview, truncated = _console_preview(
                turn.stdout,
                limit=DEBUG_IO_PREVIEW_CHARS,
            )
            if truncated:
                _emit_debug(
                    f"[debug][{scope}] stdout "
                    f"(console preview {DEBUG_IO_PREVIEW_CHARS} chars; "
                    "full command output retained in run log):\n"
                    f"{preview}"
                )
            else:
                _emit_debug(f"[debug][{scope}] stdout:\n{preview}")
        if turn.stderr:
            preview, truncated = _console_preview(
                turn.stderr,
                limit=DEBUG_IO_PREVIEW_CHARS,
            )
            if truncated:
                _emit_debug(
                    f"[debug][{scope}] stderr "
                    f"(console preview {DEBUG_IO_PREVIEW_CHARS} chars; "
                    "full command output retained in run log):\n"
                    f"{preview}"
                )
            else:
                _emit_debug(f"[debug][{scope}] stderr:\n{preview}")

        if "error:" in (turn.stdout + turn.stderr):
            parser_errors += 1

        flag_match = FLAG_RE.search(turn.stdout + turn.stderr)
        if flag_match:
            matched_flag = flag_match.group(0)
            if matched_flag == scenario.expected_flag:
                success_time = time.perf_counter() - t0
                break

    duration = time.perf_counter() - t0
    success = matched_flag == scenario.expected_flag
    model_input_tokens = sum(
        _usage_int(event.get("input_tokens")) for event in model_usage_events
    )
    model_output_tokens = sum(
        _usage_int(event.get("output_tokens")) for event in model_usage_events
    )
    model_total_tokens = sum(
        _usage_int(event.get("total_tokens")) for event in model_usage_events
    )

    result = RunResult(
        scenario_id=scenario.id,
        mode=mode,
        adapter=adapter_name,
        success=success,
        matched_flag=matched_flag,
        expected_flag=scenario.expected_flag,
        command_count=counted_steps,
        invalid_command_count=invalid,
        parser_error_count=parser_errors,
        anomaly_count=len(anomaly_events),
        duration_s=round(duration, 3),
        time_to_success_s=round(success_time, 3) if success_time is not None else None,
        api_call_count=len(model_usage_events),
        model_input_tokens=model_input_tokens,
        model_output_tokens=model_output_tokens,
        model_total_tokens=model_total_tokens,
    )
    return result, turns, debug_events, model_usage_events, anomaly_events


def _print_summary(results: list[RunResult]) -> None:
    header = (
        "scenario".ljust(18)
        + " mode".ljust(16)
        + " success".ljust(10)
        + " cmds".ljust(8)
        + " invalid".ljust(10)
        + " errors".ljust(9)
        + " anomalies".ljust(11)
        + " t_success"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        print(
            result.scenario_id.ljust(18)
            + result.mode.ljust(16)
            + str(result.success).ljust(10)
            + str(result.command_count).ljust(8)
            + str(result.invalid_command_count).ljust(10)
            + str(result.parser_error_count).ljust(9)
            + str(result.anomaly_count).ljust(11)
            + str(result.time_to_success_s)
        )

    by_mode: dict[str, list[RunResult]] = {}
    for result in results:
        by_mode.setdefault(result.mode, []).append(result)

    print("\nMode aggregates")
    print(
        "mode".ljust(16)
        + " success_rate".ljust(14)
        + " med_cmds".ljust(10)
        + " med_errors".ljust(12)
        + " med_t_success"
    )
    print("-" * 66)
    for mode, rows in by_mode.items():
        success_rate = sum(1 for row in rows if row.success) / len(rows)
        med_cmds = median(row.command_count for row in rows)
        med_errors = median(row.parser_error_count for row in rows)
        success_times = [
            row.time_to_success_s for row in rows if row.time_to_success_s is not None
        ]
        med_t_success = median(success_times) if success_times else None
        print(
            mode.ljust(16)
            + f"{success_rate:.2%}".ljust(14)
            + str(med_cmds).ljust(10)
            + str(med_errors).ljust(12)
            + str(med_t_success)
        )

    if any(result.api_call_count > 0 for result in results):
        print("\nModel token totals (by mode)")
        print(
            "mode".ljust(16)
            + " api_calls".ljust(12)
            + " input_tok".ljust(12)
            + " output_tok".ljust(12)
            + " total_tok"
        )
        print("-" * 64)
        by_mode_tokens: dict[str, dict[str, int]] = {}
        for result in results:
            bucket = by_mode_tokens.setdefault(
                result.mode,
                {
                    "api_calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            )
            bucket["api_calls"] += result.api_call_count
            bucket["input_tokens"] += result.model_input_tokens
            bucket["output_tokens"] += result.model_output_tokens
            bucket["total_tokens"] += result.model_total_tokens
        for mode, bucket in by_mode_tokens.items():
            print(
                mode.ljust(16)
                + str(bucket["api_calls"]).ljust(12)
                + str(bucket["input_tokens"]).ljust(12)
                + str(bucket["output_tokens"]).ljust(12)
                + str(bucket["total_tokens"])
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctf-harness")
    parser.add_argument("--adapter", choices=["oracle", "openai"], default="oracle")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["help-only", "jelp-useful", "jelp-primed", "jelp-no-meta"],
    )
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--timeout-s", type=float, default=8.0)
    parser.add_argument("--api-timeout-s", type=float, default=45.0)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--response-max-output-tokens", type=int, default=500)
    parser.add_argument("--adapter-retries", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--allow-duplicates", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume from an existing --out log and skip completed runs",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing --out log (default is to refuse clobber)",
    )
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--out", default="ctf/results/latest.json")
    args = parser.parse_args(argv)
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.resume and args.overwrite:
        parser.error("--resume and --overwrite are mutually exclusive")

    repo_root = Path(__file__).resolve().parents[1]
    selected = [s for s in SCENARIOS if not args.scenario or s.id in set(args.scenario)]
    selected_ids = [scenario.id for scenario in selected]
    out_path = Path(args.out)

    existing = out_path.exists()
    if existing and not args.resume and not args.overwrite:
        parser.error(
            f"--out path already exists: {out_path} (use --resume or --overwrite)"
        )

    run_log: dict[str, object]
    all_results: list[RunResult]
    completed_keys: set[tuple[int, str, str]]

    if args.resume and existing:
        try:
            run_log = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parser.error(f"failed to parse existing resume log {out_path}: {exc}")
        mismatch = _resume_mismatch_reason(
            existing=run_log,
            adapter=args.adapter,
            model=args.model,
            modes=args.modes,
            iterations=args.iterations,
        )
        if mismatch is not None:
            parser.error(f"--resume is incompatible with existing log: {mismatch}")
        if "selected_scenarios" in run_log:
            existing_selected = [str(value) for value in run_log["selected_scenarios"]]
            if existing_selected != selected_ids:
                parser.error(
                    "--resume selected scenarios mismatch "
                    f"(existing={existing_selected}, requested={selected_ids})"
                )
        completed_keys = _extract_completed_keys(run_log)
        all_results = []
        for row in run_log.get("results", []):
            if not isinstance(row, dict):
                continue
            summary = row.get("summary", {})
            if isinstance(summary, dict):
                all_results.append(_summary_to_run_result(summary))
        if args.debug:
            print(
                f"[debug] resuming from {out_path} with {len(completed_keys)} completed entries",
                flush=True,
            )
    else:
        if args.resume and not existing:
            print(
                f"[debug] --resume requested but {out_path} does not exist; starting new run",
                flush=True,
            )
        run_log = _new_run_log(
            adapter=args.adapter,
            model=args.model,
            modes=args.modes,
            iterations=args.iterations,
            selected_scenarios=selected_ids,
        )
        completed_keys = set()
        all_results = []
        _write_run_log_checkpoint(out_path, run_log)

    interrupted = False
    try:
        for iteration in range(1, args.iterations + 1):
            if args.debug:
                print(
                    f"[debug] starting iteration {iteration}/{args.iterations}",
                    flush=True,
                )
            for scenario in selected:
                for mode in args.modes:
                    key = _result_key(iteration, scenario.id, mode)
                    if key in completed_keys:
                        if args.debug:
                            skip_scope = (
                                f"i{iteration:02d}."
                                f"{_scenario_debug_code(scenario.id)}."
                                f"{_mode_debug_code(mode)}."
                                "skip"
                            )
                            print(
                                f"[debug][{skip_scope}] skipping completed result from resume checkpoint",
                                flush=True,
                            )
                        continue

                    result, turns, debug_events, model_usage_events, anomaly_events = (
                        _run_single(
                            scenario=scenario,
                            mode=mode,
                            adapter_name=args.adapter,
                            model=args.model,
                            max_steps=args.max_steps,
                            timeout_s=args.timeout_s,
                            repo_root=repo_root,
                            debug=args.debug,
                            api_timeout_s=args.api_timeout_s,
                            temperature=args.temperature,
                            response_max_output_tokens=args.response_max_output_tokens,
                            adapter_retries=args.adapter_retries,
                            reject_duplicates=not args.allow_duplicates,
                            iteration_index=iteration,
                            iteration_total=args.iterations,
                        )
                    )
                    all_results.append(result)
                    run_log["results"].append(
                        {
                            "iteration": iteration,
                            "summary": asdict(result),
                            "turns": [asdict(turn) for turn in turns],
                            "debug_events": debug_events,
                            "model_usage": model_usage_events,
                            "anomalies": anomaly_events,
                        }
                    )
                    completed_keys.add(key)
                    _write_run_log_checkpoint(out_path, run_log)
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted by user; checkpoint preserved.", flush=True)

    _print_summary(all_results)

    _write_run_log_checkpoint(out_path, run_log)
    print(f"\nWrote detailed run log: {out_path}")

    if interrupted:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
