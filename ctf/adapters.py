from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Protocol

from ctf.scenarios import Scenario


@dataclass(frozen=True)
class TurnRecord:
    command: str
    returncode: int
    stdout: str
    stderr: str


class CommandAdapter(Protocol):
    def next_command(
        self,
        *,
        scenario: Scenario,
        mode: str,
        turns: list[TurnRecord],
        allowed_prefix: str,
    ) -> str: ...


class OracleAdapter:
    def next_command(
        self,
        *,
        scenario: Scenario,
        mode: str,
        turns: list[TurnRecord],
        allowed_prefix: str,
    ) -> str:
        del mode, allowed_prefix
        if turns:
            return ""
        return scenario.oracle_command


class OpenAIAdapter:
    def __init__(
        self,
        model: str,
        *,
        debug: bool = False,
        api_timeout_s: float = 45.0,
        temperature: float | None = None,
        max_output_tokens: int = 500,
        retries: int = 1,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "openai package is required for --adapter openai"
            ) from exc
        self._client = OpenAI()
        self._model = model
        self._debug = debug
        self._api_timeout_s = api_timeout_s
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._retries = retries

    def next_command(
        self,
        *,
        scenario: Scenario,
        mode: str,
        turns: list[TurnRecord],
        allowed_prefix: str,
    ) -> str:
        history_lines: list[str] = []
        for idx, turn in enumerate(turns, start=1):
            history_lines.append(
                f"Step {idx}\\n"
                f"command: {turn.command}\\n"
                f"exit: {turn.returncode}\\n"
                f"stdout:\\n{turn.stdout[:1400]}\\n"
                f"stderr:\\n{turn.stderr[:1400]}"
            )

        content = (
            "You are solving a CLI CTF challenge. "
            "Return ONLY JSON with keys: command, note.\\n"
            f"Goal: {scenario.objective}\\n"
            f"Expected flag pattern: {scenario.expected_flag[:12]}...\\n"
            f"Mode: {mode}\\n"
            f"Allowed command prefix: {allowed_prefix}\\n"
            "Use shell commands to discover and execute the correct invocation.\\n"
            "Strategy requirements:\\n"
            "- Start by inspecting interface shape (`--help`, and `--jelp` when available in this mode).\\n"
            "- Do NOT repeat an identical command that already failed.\\n"
            "- If argparse reports unrecognized arguments, adjust option placement based on usage.\\n"
            "- Change one parameter at a time after a near miss.\\n"
            "If finished or blocked, return command as empty string.\\n\\n"
            "History:\\n"
            + ("\\n\\n".join(history_lines) if history_lines else "(none)")
        )

        prompt = content
        for attempt in range(self._retries + 1):
            request_kwargs = {
                "model": self._model,
                "input": prompt,
                "max_output_tokens": self._max_output_tokens,
                "timeout": self._api_timeout_s,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "ctf_command",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "command": {"type": "string"},
                                "note": {"type": "string"},
                            },
                            "required": ["command", "note"],
                            "additionalProperties": False,
                        },
                    }
                },
            }
            if self._temperature is not None:
                request_kwargs["temperature"] = self._temperature

            if self._debug:
                print(
                    f"[debug][openai] requesting model={self._model} timeout={self._api_timeout_s}s attempt={attempt + 1}",
                    flush=True,
                )
            t0 = time.perf_counter()
            try:
                response = self._client.responses.create(**request_kwargs)
            except Exception as exc:  # pragma: no cover - network runtime behavior
                if self._debug:
                    print(f"[debug][openai] request failed: {exc}", flush=True)
                return ""
            elapsed = time.perf_counter() - t0
            text = (response.output_text or "").strip()
            if not text:
                text = _extract_text_from_response_output(response)
            if self._debug:
                print(f"[debug][openai] response in {elapsed:.2f}s", flush=True)
                if text:
                    print(f"[debug][openai] raw response:\n{text}", flush=True)
                else:
                    print("[debug][openai] empty response text", flush=True)
                    output = getattr(response, "output", None)
                    if output is not None:
                        print(f"[debug][openai] raw output items: {output}", flush=True)
            command = _extract_command_from_model_text(text)
            if self._debug:
                print(f"[debug][openai] parsed command: {command}", flush=True)
            if command:
                return command
            prompt = (
                content + "\n\nYour previous answer did not include a usable command. "
                "Return valid JSON with a non-empty `command` string."
            )

        return ""


def build_adapter(
    name: str,
    *,
    model: str,
    debug: bool = False,
    api_timeout_s: float = 45.0,
    temperature: float | None = None,
    max_output_tokens: int = 500,
    retries: int = 1,
) -> CommandAdapter:
    if name == "oracle":
        return OracleAdapter()
    if name == "openai":
        return OpenAIAdapter(
            model=model,
            debug=debug,
            api_timeout_s=api_timeout_s,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            retries=retries,
        )
    raise ValueError(f"Unknown adapter: {name}")


def _extract_command_from_model_text(text: str) -> str:
    raw = text.strip()
    if not raw:
        return ""

    # Strip common markdown code fences.
    if raw.startswith("```"):
        fence_lines = raw.splitlines()
        if len(fence_lines) >= 3 and fence_lines[-1].strip() == "```":
            raw = "\n".join(fence_lines[1:-1]).strip()
        if raw.lower().startswith("json\n"):
            raw = raw[5:].strip()

    # Try direct JSON parse first.
    payload = _try_load_json_object(raw)
    if payload is not None:
        command = payload.get("command")
        return str(command).strip() if isinstance(command, str) else ""

    # Try to locate a JSON object embedded in extra text.
    for candidate in re.findall(r"\{[\s\S]*?\}", raw):
        payload = _try_load_json_object(candidate)
        if payload is None:
            continue
        command = payload.get("command")
        if isinstance(command, str):
            return command.strip()

    # Last-resort regex extraction of the command field.
    match = re.search(r'"command"\s*:\s*"([^"]*)"', raw)
    if match:
        return match.group(1).strip()

    # Fallback: first non-empty line.
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _try_load_json_object(raw: str) -> dict[str, object] | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_text_from_response_output(response: object) -> str:
    chunks: list[str] = []
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return ""

    for item in output:
        content = getattr(item, "content", None)
        if not isinstance(content, list):
            continue
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())

    return "\n".join(chunks).strip()
