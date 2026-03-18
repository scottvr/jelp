from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ctf.scenarios import Scenario

_DEFAULT_HISTORY_CHARS = 1400
_JELP_HISTORY_CHARS = 20000
_DEBUG_MODEL_TEXT_PREVIEW_CHARS = 2000


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
        debug_scope: str = "",
    ) -> str: ...


class OracleAdapter:
    def next_command(
        self,
        *,
        scenario: Scenario,
        mode: str,
        turns: list[TurnRecord],
        allowed_prefix: str,
        debug_scope: str = "",
    ) -> str:
        del mode, allowed_prefix, debug_scope
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
        debug_sink: Callable[[str], None] | None = None,
        usage_sink: Callable[[dict[str, object]], None] | None = None,
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
        self._debug_sink = debug_sink
        self._usage_sink = usage_sink

    def next_command(
        self,
        *,
        scenario: Scenario,
        mode: str,
        turns: list[TurnRecord],
        allowed_prefix: str,
        debug_scope: str = "",
    ) -> str:
        scope_prefix = f"[{debug_scope}]" if debug_scope else ""
        history_lines: list[str] = []
        history_truncations: list[str] = []
        for idx, turn in enumerate(turns, start=1):
            history_chars = (
                _JELP_HISTORY_CHARS
                if "--jelp" in turn.command
                else _DEFAULT_HISTORY_CHARS
            )
            if len(turn.stdout) > history_chars:
                history_truncations.append(
                    f"step {idx} stdout {len(turn.stdout)}->{history_chars}"
                )
            if len(turn.stderr) > history_chars:
                history_truncations.append(
                    f"step {idx} stderr {len(turn.stderr)}->{history_chars}"
                )
            history_lines.append(
                f"Step {idx}\\n"
                f"command: {turn.command}\\n"
                f"exit: {turn.returncode}\\n"
                f"stdout:\\n{turn.stdout[:history_chars]}\\n"
                f"stderr:\\n{turn.stderr[:history_chars]}"
            )

        primer = ""
        if mode in {
            "jelp-primed",
            "jelp-primed-useful",
            "jelp-primed-incremental",
            "jelp-primed-full",
        }:
            primer = (
                "OpenCLI primer:\\n"
                "- OpenCLI JSON is a machine-readable schema of commands, options, arguments, arity, and accepted values.\\n"
                "- In this benchmark, every fixture app uses argparse and `--jelp*` emits OpenCLI schema from argparse objects.\\n"
                "- Simple argparse heuristic: metadata keys that start with `argparse.` indicate parser-derived fields.\\n"
                "- Executable CLI tokens come from commands/options/arguments fields, not metadata keys.\\n"
                "- Prefer reading that schema over trial-and-error command guessing when available.\\n"
            )
        elif mode == "help-only-primed":
            primer = (
                "OpenCLI primer:\\n"
                "- Many CLIs expose machine-readable OpenCLI-like schema via `--jelp*`, emitted from argparse.\\n"
                "- In this mode, `--jelp*` is intentionally disabled as an experimental control.\\n"
                "- Use standard `--help` and subcommand help traversal to discover the interface.\\n"
            )

        content = (
            "You are solving a CLI CTF challenge. "
            "Return ONLY JSON with keys: command, note.\\n"
            f"Goal: {scenario.objective}\\n"
            f"Expected flag pattern: {scenario.expected_flag[:12]}...\\n"
            f"Mode: {mode}\\n"
            f"Allowed command prefix: {allowed_prefix}\\n"
            "Use shell commands to discover and execute the correct invocation.\\n"
            + primer
            + "Strategy requirements:\\n"
            + "- Start by inspecting interface shape (`--help`, and `--jelp` when available in this mode).\\n"
            + "- Prefer compact `--jelp` output over `--jelp-pretty` unless readability is absolutely necessary.\\n"
            + "- In `jelp-useful`, prefer `--jelp-all-commands` early to inspect the full command tree in one step.\\n"
            + "- In `jelp-no-meta`, prefer `--jelp-all-no-meta` early for full-tree output without metadata.\\n"
            + "- In `jelp-primed`, explicitly prioritize `--jelp-all-commands` first unless denied by parser output.\\n"
            + "- In `jelp-primed-useful`, use compact `--jelp` only (no pretty/all variants).\\n"
            + "- In `jelp-primed-incremental`, use `--jelp` traversal only (`--help` is disabled).\\n"
            + "- In `jelp-primed-full`, use a single `--jelp-all-commands` read first, then execute.\\n"
            + "- In `help-only-primed`, do not rely on `--jelp*`; use `--help` traversal only.\\n"
            + "- Do NOT repeat an identical command that already failed.\\n"
            + "- If argparse reports unrecognized arguments, adjust option placement based on usage.\\n"
            + "- Change one parameter at a time after a near miss.\\n"
            + "If finished or blocked, return command as empty string.\\n\\n"
            + "History:\\n"
            + ("\\n\\n".join(history_lines) if history_lines else "(none)")
        )

        prompt = content
        if history_truncations:
            listed = "; ".join(history_truncations[:6])
            more = (
                f" (+{len(history_truncations) - 6} more)"
                if len(history_truncations) > 6
                else ""
            )
            self._emit_debug(
                "[debug]"
                + scope_prefix
                + "[openai] model-input history truncation applied before request: "
                f"{listed}{more}"
            )
        total_attempts = self._retries + 1
        for attempt_index in range(total_attempts):
            attempt = attempt_index + 1
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

            self._emit_debug(
                "[debug]"
                + scope_prefix
                + "[openai] "
                + f"requesting model={self._model} timeout={self._api_timeout_s}s attempt={attempt}/{total_attempts}"
            )
            t0 = time.perf_counter()
            try:
                response = self._client.responses.create(**request_kwargs)
            except Exception as exc:  # pragma: no cover - network runtime behavior
                self._emit_debug(f"[debug]{scope_prefix}[openai] request failed: {exc}")
                return ""
            elapsed = time.perf_counter() - t0
            self._emit_usage(
                {
                    "attempt": attempt,
                    "attempt_total": total_attempts,
                    "elapsed_s": round(elapsed, 3),
                    "model": self._model,
                    **_extract_response_usage(response),
                }
            )
            text = (response.output_text or "").strip()
            if not text:
                text = _extract_text_from_response_output(response)
            truncation_reason = _response_incomplete_reason(response)
            if truncation_reason is not None:
                self._emit_debug(
                    "[debug]"
                    + scope_prefix
                    + "[openai] model output may be constraint-truncated "
                    f"(api side): {truncation_reason}"
                )
            self._emit_debug(
                f"[debug]{scope_prefix}[openai] response in {elapsed:.2f}s"
            )
            if text:
                preview, truncated = _console_preview(
                    text,
                    limit=_DEBUG_MODEL_TEXT_PREVIEW_CHARS,
                )
                if truncated:
                    self._emit_debug(
                        "[debug]" + scope_prefix + "[openai] raw response "
                        f"(console preview {_DEBUG_MODEL_TEXT_PREVIEW_CHARS} chars; "
                        "command parsing used the full response text):\n"
                        f"{preview}"
                    )
                else:
                    self._emit_debug(
                        f"[debug]{scope_prefix}[openai] raw response:\n{preview}"
                    )
            else:
                output_class = _classify_response_output_items(response)
                self._emit_debug(
                    "[debug]"
                    + scope_prefix
                    + "[openai] no command-bearing response text "
                    f"({output_class})"
                )
                output = getattr(response, "output", None)
                if output is not None:
                    self._emit_debug(
                        f"[debug]{scope_prefix}[openai] raw output items: {output}"
                    )
            command = _extract_command_from_model_text(text)
            self._emit_debug(f"[debug]{scope_prefix}[openai] parsed command: {command}")
            if command:
                return command
            prompt = (
                content + "\n\nYour previous answer did not include a usable command. "
                "Return valid JSON with a non-empty `command` string."
            )

        return ""

    def _emit_debug(self, message: str) -> None:
        if not self._debug and self._debug_sink is None:
            return
        if self._debug:
            print(message, flush=True)
        if self._debug_sink is not None:
            self._debug_sink(message)

    def _emit_usage(self, usage: dict[str, object]) -> None:
        if self._usage_sink is not None:
            self._usage_sink(usage)


def build_adapter(
    name: str,
    *,
    model: str,
    debug: bool = False,
    api_timeout_s: float = 45.0,
    temperature: float | None = None,
    max_output_tokens: int = 500,
    retries: int = 1,
    debug_sink: Callable[[str], None] | None = None,
    usage_sink: Callable[[dict[str, object]], None] | None = None,
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
            debug_sink=debug_sink,
            usage_sink=usage_sink,
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
            arguments = getattr(item, "arguments", None)
            if isinstance(arguments, str) and arguments.strip():
                chunks.append(arguments.strip())
            continue
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
            parsed = getattr(part, "parsed", None)
            if parsed is not None:
                if isinstance(parsed, (dict, list)):
                    chunks.append(json.dumps(parsed, separators=(",", ":")))
                else:
                    chunks.append(str(parsed))

    return "\n".join(chunks).strip()


def _extract_response_usage(response: object) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    input_tokens = _as_int(getattr(usage, "input_tokens", None))
    output_tokens = _as_int(getattr(usage, "output_tokens", None))
    total_tokens = _as_int(getattr(usage, "total_tokens", None))
    if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _response_incomplete_reason(response: object) -> str | None:
    details = getattr(response, "incomplete_details", None)
    if details is not None:
        if isinstance(details, dict):
            reason = details.get("reason")
            if reason is not None:
                return str(reason)
            return str(details)
        reason = getattr(details, "reason", None)
        if reason is not None:
            return str(reason)
        return str(details)

    status = getattr(response, "status", None)
    if isinstance(status, str) and status.lower() == "incomplete":
        return "response status is incomplete"
    return None


def _classify_response_output_items(response: object) -> str:
    output = getattr(response, "output", None)
    if not isinstance(output, list):
        return "output list unavailable"
    if not output:
        return "output list empty"

    item_types: list[str] = []
    for item in output:
        item_type = getattr(item, "type", None)
        if isinstance(item_type, str):
            item_types.append(item_type)
        else:
            item_types.append(type(item).__name__)

    unique = sorted(set(item_types))
    if unique == ["reasoning"]:
        return "reasoning-only output items"
    return "output item types: " + ",".join(unique)


def _console_preview(text: str, *, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _as_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
