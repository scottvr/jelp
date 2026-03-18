from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODELS = ["gpt-4.1-mini", "gpt-5-mini"]
DEFAULT_BASELINE_MODE = "help-only-primed"
DEFAULT_CANDIDATE_MODE = "jelp-primed-incremental"
DEFAULT_RESULTS_DIR = "ctf/results/phase2"


@dataclass(frozen=True)
class RunConfig:
    adapter: str
    models: list[str]
    baseline_mode: str
    candidate_mode: str
    iterations: int
    max_steps: int
    api_timeout_s: float
    response_max_output_tokens: int
    adapter_retries: int
    ci_level: float
    bootstrap_samples: int
    seed: int
    results_dir: Path
    resume: bool
    low_memory: bool
    debug: bool
    dry_run: bool
    skip_decision_report: bool


def _shell_join(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)


def _run_command(
    *,
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    dry_run: bool,
) -> int:
    print(f"[phase2] {_shell_join(argv)}")
    if dry_run:
        return 0
    proc = subprocess.run(argv, cwd=str(cwd), env=env, check=False)
    return int(proc.returncode)


def _harness_argv(
    *,
    python_exe: str,
    config: RunConfig,
    model: str,
    out_path: Path,
) -> list[str]:
    argv = [
        python_exe,
        "ctf/harness.py",
        "--adapter",
        config.adapter,
        "--model",
        model,
        "--modes",
        config.baseline_mode,
        config.candidate_mode,
        "--iterations",
        str(config.iterations),
        "--max-steps",
        str(config.max_steps),
        "--api-timeout-s",
        str(config.api_timeout_s),
        "--response-max-output-tokens",
        str(config.response_max_output_tokens),
        "--adapter-retries",
        str(config.adapter_retries),
        "--out",
        str(out_path),
    ]
    if config.debug:
        argv.append("--debug")
    if config.low_memory:
        argv.append("--low-memory")
    if config.resume:
        argv.append("--resume")
    return argv


def _decision_report_argv(
    *,
    python_exe: str,
    config: RunConfig,
    model_paths: list[Path],
) -> list[str]:
    argv = [
        python_exe,
        "ctf/decision_report.py",
    ]
    for path in model_paths:
        argv.extend(["--in", str(path)])
    argv.extend(
        [
            "--baseline",
            config.baseline_mode,
            "--candidate",
            config.candidate_mode,
            "--ci-level",
            str(config.ci_level),
            "--bootstrap-samples",
            str(config.bootstrap_samples),
            "--seed",
            str(config.seed),
            "--json-out",
            str(config.results_dir / "head2head-decision.json"),
            "--md-out",
            str(config.results_dir / "head2head-decision.md"),
        ]
    )
    return argv


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctf-phase2-run")
    parser.add_argument("--adapter", default="openai")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--baseline-mode", default=DEFAULT_BASELINE_MODE)
    parser.add_argument("--candidate-mode", default=DEFAULT_CANDIDATE_MODE)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--api-timeout-s", type=float, default=45.0)
    parser.add_argument("--response-max-output-tokens", type=int, default=1200)
    parser.add_argument("--adapter-retries", type=int, default=2)
    parser.add_argument("--ci-level", type=float, default=0.90)
    parser.add_argument("--bootstrap-samples", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--low-memory", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--debug", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-decision-report", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.max_steps < 1:
        parser.error("--max-steps must be >= 1")
    if args.bootstrap_samples < 1:
        parser.error("--bootstrap-samples must be >= 1")
    if not (0.0 < args.ci_level < 1.0):
        parser.error("--ci-level must be between 0 and 1")
    if not args.models:
        parser.error("--models requires at least one model name")

    repo_root = Path(__file__).resolve().parents[1]
    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = (repo_root / results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    config = RunConfig(
        adapter=str(args.adapter),
        models=[str(model) for model in args.models],
        baseline_mode=str(args.baseline_mode),
        candidate_mode=str(args.candidate_mode),
        iterations=int(args.iterations),
        max_steps=int(args.max_steps),
        api_timeout_s=float(args.api_timeout_s),
        response_max_output_tokens=int(args.response_max_output_tokens),
        adapter_retries=int(args.adapter_retries),
        ci_level=float(args.ci_level),
        bootstrap_samples=int(args.bootstrap_samples),
        seed=int(args.seed),
        results_dir=results_dir,
        resume=bool(args.resume),
        low_memory=bool(args.low_memory),
        debug=bool(args.debug),
        dry_run=bool(args.dry_run),
        skip_decision_report=bool(args.skip_decision_report),
    )

    env = os.environ.copy()
    py_paths = [str(repo_root / "src"), str(repo_root)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        py_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(py_paths)

    model_paths: list[Path] = []
    for model in config.models:
        out_path = config.results_dir / f"head2head-{model}.json"
        model_paths.append(out_path)
        rc = _run_command(
            argv=_harness_argv(
                python_exe=sys.executable,
                config=config,
                model=model,
                out_path=out_path,
            ),
            cwd=repo_root,
            env=env,
            dry_run=config.dry_run,
        )
        if rc != 0:
            return rc

    if config.skip_decision_report:
        return 0

    rc = _run_command(
        argv=_decision_report_argv(
            python_exe=sys.executable,
            config=config,
            model_paths=model_paths,
        ),
        cwd=repo_root,
        env=env,
        dry_run=config.dry_run,
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
