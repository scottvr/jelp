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
    duration_s: float
    time_to_success_s: float | None


def _policy_violation(mode: str, command: str) -> str | None:
    tokens = shlex.split(command)
    jelp_tokens = {
        "--jelp",
        "--jelp-pretty",
        "--jelp-no-meta",
        "--jelp-all",
        "--jelp-all-commands",
        "--jelp-all-no-meta",
    }

    if mode == "help-only" and any(token in jelp_tokens for token in tokens):
        return "jelp flags disallowed in help-only mode"

    if mode == "jelp-useful" and any(
        token in {"--jelp-no-meta", "--jelp-all", "--jelp-all-no-meta"}
        for token in tokens
    ):
        return (
            "only --jelp/--jelp-pretty/--jelp-all-commands allowed in jelp-useful mode"
        )

    if mode == "jelp-no-meta" and any(
        token in {"--jelp", "--jelp-pretty", "--jelp-all"} for token in tokens
    ):
        return "only --jelp-no-meta/--jelp-all-no-meta/--jelp-all-commands allowed in jelp-no-meta mode"

    return None


def _execute_command(
    command: str, *, cwd: Path, env: dict[str, str], timeout_s: float
) -> TurnRecord:
    command_to_run = command
    if command.startswith("python "):
        command_to_run = f"{shlex.quote(sys.executable)} {command[len('python ') :]}"

    proc = subprocess.run(
        command_to_run,
        cwd=str(cwd),
        env=env,
        shell=True,
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
) -> tuple[RunResult, list[TurnRecord]]:
    adapter = build_adapter(
        adapter_name,
        model=model,
        debug=debug,
        api_timeout_s=api_timeout_s,
        temperature=temperature,
        max_output_tokens=response_max_output_tokens,
        retries=adapter_retries,
    )
    turns: list[TurnRecord] = []
    invalid = 0
    parser_errors = 0
    matched_flag: str | None = None
    t0 = time.perf_counter()
    success_time: float | None = None
    seen_commands: set[str] = set()

    fixtures = fixture_dir(repo_root)
    allowed_prefix = f"python {scenario.script}"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["JELP_MODE"] = mode

    for step in range(1, max_steps + 1):
        if debug:
            print(
                f"[debug] scenario={scenario.id} mode={mode} step={step}",
                flush=True,
            )
        command = adapter.next_command(
            scenario=scenario,
            mode=mode,
            turns=turns,
            allowed_prefix=allowed_prefix,
        ).strip()

        if not command:
            if debug:
                print(
                    "[debug] adapter returned empty command; stopping scenario loop",
                    flush=True,
                )
            break
        if debug:
            print(f"[debug] command: {command}", flush=True)

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
            if debug:
                print("[debug] rejected command: duplicate", flush=True)
            continue
        seen_commands.add(command)

        if not command.startswith("python "):
            invalid += 1
            turns.append(
                TurnRecord(
                    command=command,
                    returncode=126,
                    stdout="",
                    stderr="Rejected: command must start with 'python '",
                )
            )
            if debug:
                print("[debug] rejected command: must start with python", flush=True)
            continue

        violation = _policy_violation(mode, command)
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
            if debug:
                print(f"[debug] policy violation: {violation}", flush=True)
            continue

        turn = _execute_command(command, cwd=fixtures, env=env, timeout_s=timeout_s)
        turns.append(turn)
        if debug:
            print(f"[debug] exit={turn.returncode}", flush=True)
            if turn.stdout:
                print(f"[debug] stdout:\n{turn.stdout[:1500]}", flush=True)
            if turn.stderr:
                print(f"[debug] stderr:\n{turn.stderr[:1500]}", flush=True)

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

    result = RunResult(
        scenario_id=scenario.id,
        mode=mode,
        adapter=adapter_name,
        success=success,
        matched_flag=matched_flag,
        expected_flag=scenario.expected_flag,
        command_count=len(turns),
        invalid_command_count=invalid,
        parser_error_count=parser_errors,
        duration_s=round(duration, 3),
        time_to_success_s=round(success_time, 3) if success_time is not None else None,
    )
    return result, turns


def _print_summary(results: list[RunResult]) -> None:
    header = (
        "scenario".ljust(18)
        + " mode".ljust(16)
        + " success".ljust(10)
        + " cmds".ljust(8)
        + " invalid".ljust(10)
        + " errors".ljust(9)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ctf-harness")
    parser.add_argument("--adapter", choices=["oracle", "openai"], default="oracle")
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument(
        "--modes", nargs="+", default=["help-only", "jelp-useful", "jelp-no-meta"]
    )
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--timeout-s", type=float, default=8.0)
    parser.add_argument("--api-timeout-s", type=float, default=45.0)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--response-max-output-tokens", type=int, default=500)
    parser.add_argument("--adapter-retries", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--allow-duplicates", action="store_true")
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--out", default="ctf/results/latest.json")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    selected = [s for s in SCENARIOS if not args.scenario or s.id in set(args.scenario)]

    all_results: list[RunResult] = []
    run_log: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "adapter": args.adapter,
        "model": args.model,
        "modes": args.modes,
        "results": [],
    }

    for scenario in selected:
        for mode in args.modes:
            result, turns = _run_single(
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
            )
            all_results.append(result)
            run_log["results"].append(
                {
                    "summary": asdict(result),
                    "turns": [asdict(turn) for turn in turns],
                }
            )

    _print_summary(all_results)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    print(f"\nWrote detailed run log: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
