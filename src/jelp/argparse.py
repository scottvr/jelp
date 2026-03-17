from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Any, Literal


_OPENCLI_VERSION = "0.1.0"
MetadataLevel = Literal["useful", "none", "all"]
_VALID_METADATA_LEVELS: set[str] = {"useful", "none", "all"}


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
            payload["arguments"] = [
                argument.to_opencli() for argument in self.arguments
            ]
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
    examples: list[str] | None = None
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
            payload["arguments"] = [
                argument.to_opencli() for argument in self.arguments
            ]
        if self.commands:
            payload["commands"] = [command.to_opencli() for command in self.commands]
        if self.description:
            payload["description"] = self.description
        if self.examples:
            payload["examples"] = self.examples
        if self.metadata:
            payload["metadata"] = [entry.to_opencli() for entry in self.metadata]
        return payload


@dataclass(slots=True)
class NormalizedDocument:
    opencli: str
    info: dict[str, str]
    examples: list[str] | None = None
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
            payload["arguments"] = [
                argument.to_opencli() for argument in self.arguments
            ]
        if self.commands:
            payload["commands"] = [command.to_opencli() for command in self.commands]
        if self.examples:
            payload["examples"] = self.examples
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
        examples=_parser_examples(parser),
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
    metadata_level: MetadataLevel = "useful",
) -> dict[str, Any]:
    _validate_metadata_level(metadata_level)
    normalized = parser_to_normalized(
        parser,
        version=version,
        opencli_version=opencli_version,
    )
    payload = normalized_to_opencli(normalized)
    _apply_metadata_level(payload, metadata_level)
    return payload


def enable_jelp(
    parser: argparse.ArgumentParser,
    *,
    version: str | None = None,
    opencli_version: str = _OPENCLI_VERSION,
    flag: str = "--jelp",
    pretty_flag: str = "--jelp-pretty",
    no_meta_flag: str = "--jelp-no-meta",
    all_flag: str = "--jelp-all",
    auto_handle: bool = True,
    allow_inverted_order: bool = False,
    help_text: str = "Emit OpenCLI JSON and exit.",
    pretty_help_text: str = "Emit pretty OpenCLI JSON and exit.",
    no_meta_help_text: str = "Emit OpenCLI JSON without metadata and exit.",
    all_help_text: str = "Emit OpenCLI JSON with all metadata and exit.",
) -> argparse.ArgumentParser:
    emit_version = (
        str(getattr(parser, "jelp_version", "0.0.0")) if version is None else version
    )

    for target_parser in _walk_parser_tree(parser):
        if auto_handle:
            action = _make_jelp_emit_action(
                owner_parser=target_parser,
                root_parser=parser,
                version=emit_version,
                opencli_version=opencli_version,
                pretty=False,
                flag=flag,
                pretty_flag=pretty_flag,
                no_meta_flag=no_meta_flag,
                all_flag=all_flag,
                metadata_level="useful",
                allow_inverted_order=allow_inverted_order,
            )
            pretty_action = _make_jelp_emit_action(
                owner_parser=target_parser,
                root_parser=parser,
                version=emit_version,
                opencli_version=opencli_version,
                pretty=True,
                flag=flag,
                pretty_flag=pretty_flag,
                no_meta_flag=no_meta_flag,
                all_flag=all_flag,
                metadata_level="useful",
                allow_inverted_order=allow_inverted_order,
            )
            no_meta_action = _make_jelp_emit_action(
                owner_parser=target_parser,
                root_parser=parser,
                version=emit_version,
                opencli_version=opencli_version,
                pretty=False,
                flag=flag,
                pretty_flag=pretty_flag,
                no_meta_flag=no_meta_flag,
                all_flag=all_flag,
                metadata_level="none",
                allow_inverted_order=allow_inverted_order,
            )
            all_action = _make_jelp_emit_action(
                owner_parser=target_parser,
                root_parser=parser,
                version=emit_version,
                opencli_version=opencli_version,
                pretty=False,
                flag=flag,
                pretty_flag=pretty_flag,
                no_meta_flag=no_meta_flag,
                all_flag=all_flag,
                metadata_level="all",
                allow_inverted_order=allow_inverted_order,
            )
        else:
            action = "store_true"
            pretty_action = "store_true"
            no_meta_action = "store_true"
            all_action = "store_true"

        if flag not in target_parser._option_string_actions:
            added = target_parser.add_argument(flag, action=action, help=help_text)
            _mark_jelp_injected_option(target_parser, added)
        if pretty_flag not in target_parser._option_string_actions:
            added = target_parser.add_argument(
                pretty_flag, action=pretty_action, help=pretty_help_text
            )
            _mark_jelp_injected_option(target_parser, added)
        if no_meta_flag not in target_parser._option_string_actions:
            added = target_parser.add_argument(
                no_meta_flag,
                action=no_meta_action,
                help=no_meta_help_text,
            )
            _mark_jelp_injected_option(target_parser, added)
        if all_flag not in target_parser._option_string_actions:
            added = target_parser.add_argument(
                all_flag,
                action=all_action,
                help=all_help_text,
            )
            _mark_jelp_injected_option(target_parser, added)
    return parser


def handle_jelp_flag(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None = None,
    *,
    version: str,
    opencli_version: str = _OPENCLI_VERSION,
    flag: str = "--jelp",
    pretty_flag: str = "--jelp-pretty",
    no_meta_flag: str = "--jelp-no-meta",
    all_flag: str = "--jelp-all",
    allow_inverted_order: bool = False,
    stream: Any = None,
) -> bool:
    args = list(sys.argv[1:] if argv is None else argv)
    wants_compact = flag in args
    wants_pretty = pretty_flag in args
    wants_no_meta = no_meta_flag in args
    wants_all = all_flag in args
    if not wants_compact and not wants_pretty and not wants_no_meta and not wants_all:
        return False
    jelp_flags = {flag, pretty_flag, no_meta_flag, all_flag}
    if allow_inverted_order:
        target_parser = _resolve_target_parser_from_argv(
            parser,
            args,
            jelp_flags=jelp_flags,
        )
    else:
        target_parser = _resolve_target_parser_strict(
            parser,
            args,
            jelp_flags=jelp_flags,
        )
    metadata_level: MetadataLevel = "useful"
    pretty = wants_pretty
    if wants_all:
        metadata_level = "all"
        pretty = False
    elif wants_no_meta:
        metadata_level = "none"
        pretty = False

    _emit_opencli_payload(
        target_parser,
        version=version,
        opencli_version=opencli_version,
        metadata_level=metadata_level,
        pretty=pretty,
        stream=stream,
    )
    return True


def _make_jelp_emit_action(
    *,
    owner_parser: argparse.ArgumentParser,
    root_parser: argparse.ArgumentParser,
    version: str,
    opencli_version: str,
    pretty: bool,
    flag: str,
    pretty_flag: str,
    no_meta_flag: str,
    all_flag: str,
    metadata_level: MetadataLevel,
    allow_inverted_order: bool,
) -> type[argparse.Action]:
    class _JelpEmitAction(argparse.Action):
        def __init__(self, option_strings: list[str], dest: str, **kwargs: Any) -> None:
            kwargs.setdefault("nargs", 0)
            super().__init__(option_strings, dest, **kwargs)

        def __call__(
            self,
            _: argparse.ArgumentParser,
            namespace: argparse.Namespace,
            values: Any,
            option_string: str | None = None,
        ) -> None:
            del namespace, values, option_string
            target_parser = owner_parser
            if owner_parser is root_parser:
                argv = list(sys.argv[1:])
                jelp_flags = {flag, pretty_flag, no_meta_flag, all_flag}
                if allow_inverted_order:
                    target_parser = _resolve_target_parser_from_argv(
                        root_parser,
                        argv,
                        jelp_flags=jelp_flags,
                    )
                else:
                    target_parser = _resolve_target_parser_strict(
                        root_parser,
                        argv,
                        jelp_flags=jelp_flags,
                    )
            _emit_opencli_payload(
                target_parser,
                version=version,
                opencli_version=opencli_version,
                metadata_level=metadata_level,
                pretty=pretty,
                stream=None,
            )
            owner_parser.exit(0)

    return _JelpEmitAction


def _emit_opencli_payload(
    parser: argparse.ArgumentParser,
    *,
    version: str,
    opencli_version: str,
    metadata_level: MetadataLevel,
    pretty: bool,
    stream: Any = None,
) -> None:
    payload = emit_opencli(
        parser,
        version=version,
        opencli_version=opencli_version,
        metadata_level=metadata_level,
    )
    target = sys.stdout if stream is None else stream
    json.dump(payload, target, indent=2 if pretty else None)
    target.write("\n")


def _walk_parser_tree(
    parser: argparse.ArgumentParser,
) -> list[argparse.ArgumentParser]:
    output: list[argparse.ArgumentParser] = []
    stack = [parser]
    seen: set[int] = set()

    while stack:
        current = stack.pop()
        current_id = id(current)
        if current_id in seen:
            continue
        seen.add(current_id)
        output.append(current)
        for action in current._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for child in action._name_parser_map.values():
                if child is not None:
                    stack.append(child)

    return output


def _mark_jelp_injected_option(
    parser: argparse.ArgumentParser,
    action: argparse.Action,
) -> None:
    setattr(action, "jelp_injected", True)
    injected = list(getattr(parser, "jelp_injected_option_strings", []))
    injected.append(action.option_strings[0] if action.option_strings else action.dest)
    setattr(parser, "jelp_injected_option_strings", injected)


def _resolve_target_parser_from_argv(
    root_parser: argparse.ArgumentParser,
    argv: list[str],
    *,
    jelp_flags: set[str],
) -> argparse.ArgumentParser:
    flag_positions = [index for index, token in enumerate(argv) if token in jelp_flags]
    if not flag_positions:
        return _resolve_target_parser_from_tokens(root_parser, argv)

    first_flag = flag_positions[0]
    after_flag = _resolve_target_parser_from_tokens(root_parser, argv[first_flag + 1 :])
    if after_flag is not root_parser:
        return after_flag

    before_flag = _resolve_target_parser_from_tokens(root_parser, argv[:first_flag])
    if before_flag is not root_parser:
        return before_flag

    return _resolve_target_parser_from_tokens(root_parser, argv)


def _resolve_target_parser_strict(
    root_parser: argparse.ArgumentParser,
    argv: list[str],
    *,
    jelp_flags: set[str],
) -> argparse.ArgumentParser:
    for index, token in enumerate(argv):
        if token in jelp_flags:
            return _resolve_target_parser_from_tokens(root_parser, argv[:index])
    return _resolve_target_parser_from_tokens(root_parser, argv)


def _validate_metadata_level(metadata_level: str) -> None:
    if metadata_level not in _VALID_METADATA_LEVELS:
        raise ValueError(
            f"Invalid metadata_level: {metadata_level!r}. "
            "Expected one of: 'useful', 'none', 'all'."
        )


def _apply_metadata_level(
    payload: dict[str, Any], metadata_level: MetadataLevel
) -> None:
    if metadata_level == "all":
        return
    _prune_metadata(payload, metadata_level)


def _prune_metadata(node: Any, metadata_level: MetadataLevel) -> None:
    if isinstance(node, dict):
        if "metadata" in node:
            if metadata_level == "none":
                del node["metadata"]
            else:
                filtered = [
                    entry
                    for entry in node["metadata"]
                    if _is_useful_metadata_entry(entry)
                ]
                if filtered:
                    node["metadata"] = filtered
                else:
                    del node["metadata"]
        for value in node.values():
            _prune_metadata(value, metadata_level)
    elif isinstance(node, list):
        for item in node:
            _prune_metadata(item, metadata_level)


def _is_useful_metadata_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    name = entry.get("name")
    if not isinstance(name, str):
        return False
    if not name.startswith("argparse."):
        return True
    if name in {
        "argparse.default",
        "argparse.const",
        "argparse.repeat_semantics",
        "argparse.mutually_exclusive_groups",
    }:
        return True
    if name == "argparse.action":
        action_value = entry.get("value")
        return action_value not in {
            "store",
            "store_true",
            "store_false",
            "store_const",
            "help",
            "version",
            "subparsers",
        }
    return False


def _resolve_target_parser_from_tokens(
    root_parser: argparse.ArgumentParser,
    tokens: list[str],
) -> argparse.ArgumentParser:
    current = root_parser
    remaining = tokens

    while True:
        subparsers_action = _first_subparsers_action(current)
        if subparsers_action is None:
            return current

        matched_parser: argparse.ArgumentParser | None = None
        matched_index = -1
        for index, token in enumerate(remaining):
            candidate = subparsers_action._name_parser_map.get(token)
            if candidate is not None:
                matched_parser = candidate
                matched_index = index
                break

        if matched_parser is None:
            return current

        current = matched_parser
        remaining = remaining[matched_index + 1 :]


def _first_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _parser_to_normalized_command(
    parser: argparse.ArgumentParser,
    *,
    name: str,
    aliases: list[str],
    description_override: str | None,
    hidden_override: bool,
) -> NormalizedCommand:
    action_identifiers = _build_action_identifiers(parser)
    action_group_membership, mutually_exclusive_groups = (
        _build_mutually_exclusive_metadata(parser, action_identifiers)
    )

    command = NormalizedCommand(
        name=name,
        aliases=aliases,
        description=description_override,
        examples=_parser_examples(parser),
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
    injected_options = list(getattr(parser, "jelp_injected_option_strings", []))
    if injected_options:
        command.metadata.append(
            NormalizedMetadata(
                name="jelp.injected_options",
                value=injected_options,
            )
        )

    return command


def _collect_subcommands(
    subparsers_action: argparse._SubParsersAction,
) -> list[NormalizedCommand]:
    command_entries: list[NormalizedCommand] = []
    parser_to_names: dict[int, list[str]] = {}
    parser_by_id: dict[int, argparse.ArgumentParser] = {}
    parser_order: list[int] = []

    for command_name, command_parser in subparsers_action._name_parser_map.items():
        if command_parser is None:
            continue
        parser_id = id(command_parser)
        if parser_id not in parser_by_id:
            parser_by_id[parser_id] = command_parser
            parser_order.append(parser_id)
        parser_to_names.setdefault(parser_id, []).append(command_name)

    choices_by_name = {
        choice.dest: choice for choice in subparsers_action._choices_actions
    }
    for parser_id in parser_order:
        command_parser = parser_by_id[parser_id]
        names = parser_to_names.get(parser_id, [])
        if not names:
            continue

        primary_name = next(
            (name for name in names if name in choices_by_name), names[0]
        )
        aliases = [name for name in names if name != primary_name]
        choice_action = choices_by_name.get(primary_name)

        description: str | None = command_parser.description
        if (
            description is None
            and choice_action
            and choice_action.help is not argparse.SUPPRESS
        ):
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


def _build_action_identifiers(
    parser: argparse.ArgumentParser,
) -> dict[argparse.Action, str]:
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


def _action_to_option(
    action: argparse.Action, group_ids: list[str]
) -> NormalizedOption:
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


def _action_to_argument(
    action: argparse.Action, group_ids: list[str]
) -> NormalizedArgument:
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


def _action_metadata(
    action: argparse.Action, group_ids: list[str]
) -> list[NormalizedMetadata]:
    action_kind = _action_kind(action)
    metadata: list[NormalizedMetadata] = [
        NormalizedMetadata("argparse.action", action_kind),
        NormalizedMetadata("argparse.dest", action.dest),
    ]

    metavar = action.metavar
    if metavar is not None:
        if isinstance(metavar, tuple):
            metadata.append(
                NormalizedMetadata("argparse.metavar", [str(item) for item in metavar])
            )
        else:
            metadata.append(NormalizedMetadata("argparse.metavar", str(metavar)))

    default = action.default
    if default is not argparse.SUPPRESS:
        metadata.append(NormalizedMetadata("argparse.default", default))

    const = getattr(action, "const", None)
    if const is not None:
        metadata.append(NormalizedMetadata("argparse.const", const))

    if group_ids:
        metadata.append(
            NormalizedMetadata("argparse.mutually_exclusive_groups", group_ids)
        )

    if action_kind in _REPEAT_ACTIONS:
        metadata.append(NormalizedMetadata("argparse.repeat_semantics", action_kind))
    if bool(getattr(action, "jelp_injected", False)):
        metadata.append(NormalizedMetadata("jelp.injected", True))

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
    canonical = next(
        (option for option in option_strings if option.startswith("--")),
        option_strings[0],
    )
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


def _parser_examples(parser: argparse.ArgumentParser) -> list[str] | None:
    examples = getattr(parser, "jelp_examples", None)
    if examples is None:
        return None
    if isinstance(examples, str):
        return [examples]
    return [str(example) for example in examples]


__all__ = [
    "NormalizedArgument",
    "NormalizedCommand",
    "NormalizedDocument",
    "NormalizedMetadata",
    "NormalizedOption",
    "enable_jelp",
    "emit_opencli",
    "handle_jelp_flag",
    "normalized_to_opencli",
    "parser_to_normalized",
]
