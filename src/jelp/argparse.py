from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any


_OPENCLI_VERSION = "0.1.0"


@dataclass(slots=True)
class NormalizedMetadata:
    name: str
    value: Any

    def to_opencli(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value}


@dataclass(slots=True)
class NormalizedArgument:
    name: str
    required: bool = False
    arity: dict[str, int] | None = None
    accepted_values: list[str] | None = None
    description: str | None = None
    hidden: bool = False
    metadata: list[NormalizedMetadata] = field(default_factory=list)

    def to_opencli(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "required": self.required,
            "hidden": self.hidden,
        }
        if self.arity is not None:
            payload["arity"] = self.arity
        if self.accepted_values:
            payload["acceptedValues"] = self.accepted_values
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = [entry.to_opencli() for entry in self.metadata]
        return payload


@dataclass(slots=True)
class NormalizedOption:
    name: str
    required: bool = False
    aliases: list[str] = field(default_factory=list)
    arguments: list[NormalizedArgument] = field(default_factory=list)
    description: str | None = None
    hidden: bool = False
    metadata: list[NormalizedMetadata] = field(default_factory=list)

    def to_opencli(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "required": self.required,
            "hidden": self.hidden,
        }
        if self.aliases:
            payload["aliases"] = self.aliases
        if self.arguments:
            payload["arguments"] = [argument.to_opencli() for argument in self.arguments]
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = [entry.to_opencli() for entry in self.metadata]
        return payload


@dataclass(slots=True)
class NormalizedCommand:
    name: str
    aliases: list[str] = field(default_factory=list)
    options: list[NormalizedOption] = field(default_factory=list)
    arguments: list[NormalizedArgument] = field(default_factory=list)
    commands: list[NormalizedCommand] = field(default_factory=list)
    description: str | None = None
    hidden: bool = False
    metadata: list[NormalizedMetadata] = field(default_factory=list)

    def to_opencli(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "hidden": self.hidden,
        }
        if self.aliases:
            payload["aliases"] = self.aliases
        if self.options:
            payload["options"] = [option.to_opencli() for option in self.options]
        if self.arguments:
            payload["arguments"] = [argument.to_opencli() for argument in self.arguments]
        if self.commands:
            payload["commands"] = [command.to_opencli() for command in self.commands]
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = [entry.to_opencli() for entry in self.metadata]
        return payload


@dataclass(slots=True)
class NormalizedDocument:
    opencli: str
    info: dict[str, str]
    options: list[NormalizedOption] = field(default_factory=list)
    arguments: list[NormalizedArgument] = field(default_factory=list)
    commands: list[NormalizedCommand] = field(default_factory=list)
    metadata: list[NormalizedMetadata] = field(default_factory=list)

    def to_opencli(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "opencli": self.opencli,
            "info": self.info,
        }
        if self.options:
            payload["options"] = [option.to_opencli() for option in self.options]
        if self.arguments:
            payload["arguments"] = [argument.to_opencli() for argument in self.arguments]
        if self.commands:
            payload["commands"] = [command.to_opencli() for command in self.commands]
        if self.metadata:
            payload["metadata"] = [entry.to_opencli() for entry in self.metadata]
        return payload


_ACTION_KIND_BY_CLASS_NAME = {
    "_StoreAction": "store",
    "_StoreConstAction": "store_const",
    "_StoreTrueAction": "store_true",
    "_StoreFalseAction": "store_false",
    "_AppendAction": "append",
    "_AppendConstAction": "append_const",
    "_ExtendAction": "extend",
    "_CountAction": "count",
    "BooleanOptionalAction": "boolean_optional",
    "_HelpAction": "help",
    "_VersionAction": "version",
    "_SubParsersAction": "subparsers",
}
_REPEAT_ACTIONS = {"append", "extend", "count"}


def parser_to_normalized(
    parser: argparse.ArgumentParser,
    *,
    version: str,
    opencli_version: str = _OPENCLI_VERSION,
) -> NormalizedDocument:
    root_command = _parser_to_normalized_command(
        parser,
        name=(parser.prog or "cli"),
        aliases=[],
        description_override=parser.description,
        hidden_override=False,
    )

    info: dict[str, str] = {
        "title": parser.prog or "cli",
        "version": version,
    }
    if parser.description:
        info["description"] = parser.description

    return NormalizedDocument(
        opencli=opencli_version,
        info=info,
        options=root_command.options,
        arguments=root_command.arguments,
        commands=root_command.commands,
        metadata=root_command.metadata,
    )


def normalized_to_opencli(document: NormalizedDocument) -> dict[str, Any]:
    return document.to_opencli()


def emit_opencli(
    parser: argparse.ArgumentParser,
    *,
    version: str,
    opencli_version: str = _OPENCLI_VERSION,
) -> dict[str, Any]:
    normalized = parser_to_normalized(
        parser,
        version=version,
        opencli_version=opencli_version,
    )
    return normalized_to_opencli(normalized)


def _parser_to_normalized_command(
    parser: argparse.ArgumentParser,
    *,
    name: str,
    aliases: list[str],
    description_override: str | None,
    hidden_override: bool,
) -> NormalizedCommand:
    action_identifiers = _build_action_identifiers(parser)
    action_group_membership, mutually_exclusive_groups = _build_mutually_exclusive_metadata(parser, action_identifiers)

    command = NormalizedCommand(
        name=name,
        aliases=aliases,
        description=description_override,
        hidden=hidden_override,
    )

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            command.commands.extend(_collect_subcommands(action))
            continue

        group_ids = action_group_membership.get(action, [])
        if action.option_strings:
            command.options.append(_action_to_option(action, group_ids))
        else:
            command.arguments.append(_action_to_argument(action, group_ids))

    if mutually_exclusive_groups:
        command.metadata.append(
            NormalizedMetadata(
                name="argparse.mutually_exclusive_groups",
                value=mutually_exclusive_groups,
            )
        )

    return command


def _collect_subcommands(subparsers_action: argparse._SubParsersAction) -> list[NormalizedCommand]:
    command_entries: list[NormalizedCommand] = []
    parser_to_names: dict[int, list[str]] = {}

    for command_name, command_parser in subparsers_action._name_parser_map.items():
        if command_parser is None:
            continue
        parser_id = id(command_parser)
        parser_to_names.setdefault(parser_id, []).append(command_name)

    choices_by_name = {choice.dest: choice for choice in subparsers_action._choices_actions}
    ordered_primary_names = [choice.dest for choice in subparsers_action._choices_actions]

    for primary_name in ordered_primary_names:
        command_parser = subparsers_action._name_parser_map.get(primary_name)
        if command_parser is None:
            continue

        names = parser_to_names.get(id(command_parser), [primary_name])
        aliases = [name for name in names if name != primary_name]
        choice_action = choices_by_name.get(primary_name)

        description: str | None = command_parser.description
        if description is None and choice_action and choice_action.help is not argparse.SUPPRESS:
            description = str(choice_action.help)

        hidden = bool(choice_action and choice_action.help is argparse.SUPPRESS)

        command_entries.append(
            _parser_to_normalized_command(
                command_parser,
                name=primary_name,
                aliases=aliases,
                description_override=description,
                hidden_override=hidden,
            )
        )

    return command_entries


def _build_action_identifiers(parser: argparse.ArgumentParser) -> dict[argparse.Action, str]:
    identifiers: dict[argparse.Action, str] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            continue
        if action.option_strings:
            option_name, _ = _canonical_option_strings(action.option_strings)
            identifiers[action] = option_name
        else:
            identifiers[action] = _action_argument_name(action)
    return identifiers


def _build_mutually_exclusive_metadata(
    parser: argparse.ArgumentParser,
    action_identifiers: dict[argparse.Action, str],
) -> tuple[dict[argparse.Action, list[str]], list[dict[str, Any]]]:
    action_group_membership: dict[argparse.Action, list[str]] = {}
    groups_payload: list[dict[str, Any]] = []

    for index, group in enumerate(parser._mutually_exclusive_groups, start=1):
        group_id = f"mxg_{index:03d}"
        members: list[str] = []

        for action in group._group_actions:
            identifier = action_identifiers.get(action)
            if identifier is None:
                continue
            members.append(identifier)
            action_group_membership.setdefault(action, []).append(group_id)

        if members:
            groups_payload.append(
                {
                    "name": group_id,
                    "required": bool(group.required),
                    "members": members,
                }
            )

    return action_group_membership, groups_payload


def _action_to_option(action: argparse.Action, group_ids: list[str]) -> NormalizedOption:
    option_name, aliases = _canonical_option_strings(action.option_strings)
    option = NormalizedOption(
        name=option_name,
        required=bool(action.required),
        aliases=aliases,
        description=_action_description(action),
        hidden=_action_hidden(action),
        metadata=_action_metadata(action, group_ids),
    )

    if _option_takes_argument(action):
        arity = _nargs_to_arity(action.nargs)
        minimum = arity.get("minimum", 0) if arity is not None else 0
        option.arguments.append(
            NormalizedArgument(
                name=_action_argument_name(action),
                required=minimum > 0,
                arity=arity,
                accepted_values=_action_accepted_values(action),
            )
        )

    return option


def _action_to_argument(action: argparse.Action, group_ids: list[str]) -> NormalizedArgument:
    arity = _nargs_to_arity(action.nargs)
    minimum = arity.get("minimum", 0) if arity is not None else 0
    required = bool(action.required) if hasattr(action, "required") else minimum > 0

    return NormalizedArgument(
        name=_action_argument_name(action),
        required=required,
        arity=arity,
        accepted_values=_action_accepted_values(action),
        description=_action_description(action),
        hidden=_action_hidden(action),
        metadata=_action_metadata(action, group_ids),
    )


def _action_metadata(action: argparse.Action, group_ids: list[str]) -> list[NormalizedMetadata]:
    action_kind = _action_kind(action)
    metadata: list[NormalizedMetadata] = [
        NormalizedMetadata("argparse.action", action_kind),
        NormalizedMetadata("argparse.dest", action.dest),
    ]

    metavar = action.metavar
    if metavar is not None:
        if isinstance(metavar, tuple):
            metadata.append(NormalizedMetadata("argparse.metavar", [str(item) for item in metavar]))
        else:
            metadata.append(NormalizedMetadata("argparse.metavar", str(metavar)))

    default = action.default
    if default is not argparse.SUPPRESS:
        metadata.append(NormalizedMetadata("argparse.default", default))

    const = getattr(action, "const", None)
    if const is not None:
        metadata.append(NormalizedMetadata("argparse.const", const))

    if group_ids:
        metadata.append(NormalizedMetadata("argparse.mutually_exclusive_groups", group_ids))

    if action_kind in _REPEAT_ACTIONS:
        metadata.append(NormalizedMetadata("argparse.repeat_semantics", action_kind))

    return metadata


def _action_kind(action: argparse.Action) -> str:
    class_name = action.__class__.__name__
    return _ACTION_KIND_BY_CLASS_NAME.get(class_name, class_name)


def _action_hidden(action: argparse.Action) -> bool:
    return action.help is argparse.SUPPRESS


def _action_description(action: argparse.Action) -> str | None:
    if action.help in (None, argparse.SUPPRESS):
        return None
    return str(action.help)


def _canonical_option_strings(option_strings: list[str]) -> tuple[str, list[str]]:
    canonical = next((option for option in option_strings if option.startswith("--")), option_strings[0])
    aliases = [option for option in option_strings if option != canonical]
    return canonical, aliases


def _option_takes_argument(action: argparse.Action) -> bool:
    if action.nargs == 0:
        return False

    action_kind = _action_kind(action)
    return action_kind not in {
        "count",
        "store_true",
        "store_false",
        "store_const",
        "append_const",
        "help",
        "version",
        "boolean_optional",
    }


def _action_argument_name(action: argparse.Action) -> str:
    metavar = action.metavar
    if isinstance(metavar, tuple):
        if metavar:
            return str(metavar[0])
    elif isinstance(metavar, str):
        return metavar
    return str(action.dest)


def _action_accepted_values(action: argparse.Action) -> list[str] | None:
    if action.choices is None:
        return None
    return [str(choice) for choice in action.choices]


def _nargs_to_arity(nargs: Any) -> dict[str, int] | None:
    if nargs is None:
        return {"minimum": 1, "maximum": 1}
    if nargs == "?":
        return {"minimum": 0, "maximum": 1}
    if nargs == "*":
        return {"minimum": 0}
    if nargs == "+":
        return {"minimum": 1}
    if isinstance(nargs, int):
        return {"minimum": nargs, "maximum": nargs}
    return None


__all__ = [
    "NormalizedArgument",
    "NormalizedCommand",
    "NormalizedDocument",
    "NormalizedMetadata",
    "NormalizedOption",
    "emit_opencli",
    "normalized_to_opencli",
    "parser_to_normalized",
]
