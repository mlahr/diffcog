from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from tree_sitter import Node

from diffcog.models import CallableSymbol
from diffcog.selection import callable_key

CallableKey = tuple[tuple[str, ...], str, int, str]


@dataclass(frozen=True)
class GoSemanticContext:
    recursive_call_lines: Mapping[CallableKey, int] = field(default_factory=dict)


def resolve_semantics(callables: list[CallableSymbol]) -> GoSemanticContext:
    callable_keys = {callable_key(callable_) for callable_ in callables}
    edges = {
        callable_key(callable_): list(_resolved_calls(callable_, callable_keys))
        for callable_ in callables
    }
    return GoSemanticContext(recursive_call_lines=_recursive_call_lines(edges))


def _resolved_calls(
    callable_: CallableSymbol, callable_keys: set[CallableKey]
) -> Iterable[tuple[CallableKey, int]]:
    for call in _descendants(callable_.node, "call_expression"):
        function = call.child_by_field_name("function")
        arguments = call.child_by_field_name("arguments")
        argument_count = _argument_count(arguments)
        for candidate in _call_candidates(callable_, function, argument_count):
            if candidate in callable_keys:
                yield candidate, call.start_point.row + 1


def _call_candidates(
    callable_: CallableSymbol, function: Node | None, argument_count: int
) -> Iterable[CallableKey]:
    if function is None:
        return

    if function.type == "identifier":
        yield (
            tuple(_package_namespace(callable_)),
            _node_text(function),
            argument_count,
            "function",
        )
        return

    if function.type != "selector_expression":
        return

    name = _node_text(function.child_by_field_name("field"))
    operand = function.child_by_field_name("operand")
    if name is None or not _is_receiver_qualified_method(callable_, operand):
        return

    yield (
        tuple(callable_.namespace_path),
        name,
        argument_count,
        "method",
    )


def _is_receiver_qualified_method(callable_: CallableSymbol, operand: Node | None) -> bool:
    if callable_.kind != "method" or operand is None:
        return False
    receiver_name = _receiver_name(callable_.node.child_by_field_name("receiver"))
    return receiver_name is not None and _node_text(operand) == receiver_name


def _receiver_name(receiver: Node | None) -> str | None:
    if receiver is None:
        return None
    declaration = next(
        (child for child in receiver.children if child.type == "parameter_declaration"),
        None,
    )
    if declaration is None:
        return None
    names = declaration.children_by_field_name("name")
    if not names:
        return None
    return _node_text(names[0])


def _package_namespace(callable_: CallableSymbol) -> list[str]:
    if callable_.kind == "method":
        return callable_.namespace_path[:1]
    return callable_.namespace_path


def _recursive_call_lines(
    edges: dict[CallableKey, list[tuple[CallableKey, int]]]
) -> dict[CallableKey, int]:
    recursive_lines: dict[CallableKey, int] = {}
    for component in _strongly_connected_components(edges):
        if len(component) > 1:
            _record_cycle_lines(component, edges, recursive_lines)
            continue
        key = component[0]
        self_lines = [line for callee, line in edges.get(key, []) if callee == key]
        if self_lines:
            recursive_lines[key] = min(self_lines)
    return recursive_lines


def _record_cycle_lines(
    component: list[CallableKey],
    edges: dict[CallableKey, list[tuple[CallableKey, int]]],
    recursive_lines: dict[CallableKey, int],
) -> None:
    component_keys = set(component)
    for key in component:
        cycle_lines = [
            line
            for callee, line in edges.get(key, [])
            if callee in component_keys
        ]
        if cycle_lines:
            recursive_lines[key] = min(cycle_lines)


def _strongly_connected_components(edges: dict[CallableKey, list[tuple[CallableKey, int]]]) -> list[list[CallableKey]]:
    index = 0
    stack: list[CallableKey] = []
    on_stack: set[CallableKey] = set()
    indexes: dict[CallableKey, int] = {}
    lowlinks: dict[CallableKey, int] = {}
    components: list[list[CallableKey]] = []

    def connect(key: CallableKey) -> None:
        nonlocal index
        indexes[key] = index
        lowlinks[key] = index
        index += 1
        stack.append(key)
        on_stack.add(key)

        for callee, _line in edges.get(key, []):
            if callee not in indexes:
                connect(callee)
                lowlinks[key] = min(lowlinks[key], lowlinks[callee])
            elif callee in on_stack:
                lowlinks[key] = min(lowlinks[key], indexes[callee])

        if lowlinks[key] == indexes[key]:
            component: list[CallableKey] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == key:
                    break
            components.append(component)

    for key in edges:
        if key not in indexes:
            connect(key)

    return components


def _argument_count(arguments: Node | None) -> int:
    if arguments is None:
        return 0
    return sum(1 for child in arguments.children if child.is_named)


def _descendants(node: Node, node_type: str) -> Iterable[Node]:
    for child in node.children:
        if child.type == node_type:
            yield child
        yield from _descendants(child, node_type)


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return node.text.decode("utf-8")
