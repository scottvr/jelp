from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scenario:
    id: str
    script: str
    objective: str
    expected_flag: str
    oracle_command: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        id="fixture01_vault",
        script="fixture01_vault.py",
        objective="Recover the vault flag.",
        expected_flag="FLAG{vault-scan-e4b1}",
        oracle_command="python fixture01_vault.py --profile prod --zone core scan ./vault --format json --engine safe -vv",
    ),
    Scenario(
        id="fixture02_release",
        script="fixture02_release.py",
        objective="Pass the release gate and recover the flag.",
        expected_flag="FLAG{release-gate-9a2d}",
        oracle_command="python fixture02_release.py --channel canary --execute release --region eu --window am --tag blue --tag green",
    ),
    Scenario(
        id="fixture03_cache",
        script="fixture03_cache.py",
        objective="Find the cache toggle combo that returns the flag.",
        expected_flag="FLAG{cache-bool-71f0}",
        oracle_command="python fixture03_cache.py --no-cache --retries 0 fetch artifact --tier cold",
    ),
    Scenario(
        id="fixture04_bundle",
        script="fixture04_bundle.py",
        objective="Produce the bundle command that yields the flag.",
        expected_flag="FLAG{bundle-zst-2c4f}",
        oracle_command="python fixture04_bundle.py --profile ci pack a.txt b.txt c.txt --compress zst --level 9 --sign",
    ),
    Scenario(
        id="fixture05_notes",
        script="fixture05_notes.py",
        objective="Generate notes with the exact parameters to get the flag.",
        expected_flag="FLAG{notes-range-18de}",
        oracle_command="python fixture05_notes.py --source remote notes --format json --out report.json --group-by scope HEAD~5..HEAD",
    ),
    Scenario(
        id="fixture06_audit",
        script="fixture06_audit.py",
        objective="Run audit with the strict combination that unlocks the flag.",
        expected_flag="FLAG{audit-strict-53aa}",
        oracle_command="python fixture06_audit.py --profile strict run --severity high --exclude vendor --exclude tests --strict src/",
    ),
    Scenario(
        id="fixture07_alias",
        script="fixture07_alias.py",
        objective="Navigate command aliases and get the dependency flag.",
        expected_flag="FLAG{alias-maze-6b7e}",
        oracle_command="python fixture07_alias.py --workspace mono inspect --query deps --depth 3 --mode full",
    ),
    Scenario(
        id="fixture08_nested",
        script="fixture08_nested.py",
        objective="Use nested subcommands correctly and recover the migration flag.",
        expected_flag="FLAG{nested-db-b19c}",
        oracle_command="python fixture08_nested.py --env prod db migrate --to v42 --online --lock-step",
    ),
)


def fixture_dir(repo_root: Path) -> Path:
    return repo_root / "ctf" / "fixtures"
