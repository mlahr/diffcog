from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from tree_sitter import Node

from diffcog.models import CallableSymbol
from diffcog.selection import callable_key

CallableKey = tuple[tuple[str, ...], str, int, str]


@dataclass(frozen=True)
class PythonSemanticContext:
    recursive_call_lines: Mapping[CallableKey, int] = field(default_factory=dict)


def resolve_semantics(callables: list[CallableSymbol]) -> PythonSemanticContext:
    callable_keys = {callable_key(callable_) for callable_ in callables}
    edges = {
        callable_key(callable_): list(_resolved_calls(callable_, callable_keys))
        for callable_ in callables
    }
    return PythonSemanticContext(recursive_call_lines=_recursive_call_lines(edges))


def _resolved_calls(
    callable_: CallableSymbol, callable_keys: set[CallableKey]
) -> Iterable[tuple[CallableKey, int]]:
    for call in _descendants(callable_.node, "call"):
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
            tuple(callable_.namespace_path),
            _node_text(function),
            argument_count,
            "function",
        )
        yield (
            tuple(callable_.namespace_path),
            _node_text(function),
            argument_count,
            "method",
        )
        return

    if function.type != "attribute":
        return

    name = _node_text(function.child_by_field_name("attribute"))
    object_node = function.child_by_field_name("object")
    if name is None or not _is_local_method_qualifier(callable_, object_node):
        return

    yield (
        tuple(callable_.namespace_path),
        name,
        argument_count + 1,
        "method",
    )


def _is_local_method_qualifier(callable_: CallableSymbol, object_node: Node | None) -> bool:
    if object_node is None:
        return False
    qualifier = _node_text(object_node)
    if qualifier in {"self", "cls"}:
        return callable_.kind == "method"
    current_class = _current_class_name(callable_)
    return current_class is not None and qualifier == current_class


def _current_class_name(callable_: CallableSymbol) -> str | None:
    if callable_.kind != "method" or not callable_.namespace_path:
        return None
    return callable_.namespace_path[-1]


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
