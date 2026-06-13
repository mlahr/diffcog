from __future__ import annotations

from collections.abc import Iterable

from tree_sitter import Node

from diffcog.languages.java.complexity import CallableKey, JavaSemanticContext
from diffcog.languages.java.models import JavaCallable
from diffcog.languages.java.selection import callable_key


def resolve_semantics(callables: list[JavaCallable]) -> JavaSemanticContext:
    method_keys = {
        callable_key(callable_)
        for callable_ in callables
        if callable_.kind == "method"
    }
    edges = {
        callable_key(callable_): list(_resolved_calls(callable_, method_keys))
        for callable_ in callables
        if callable_.kind == "method"
    }
    return JavaSemanticContext(recursive_call_lines=_recursive_call_lines(edges))


def _resolved_calls(
    callable_: JavaCallable, method_keys: set[CallableKey]
) -> Iterable[tuple[CallableKey, int]]:
    caller_class_path = tuple(callable_.class_path)
    current_class = callable_.class_path[-1] if callable_.class_path else None
    for invocation in _descendants(callable_.node, "method_invocation"):
        name = _node_text(invocation.child_by_field_name("name"))
        if name is None:
            continue
        if not _is_local_qualifier(invocation.child_by_field_name("object"), current_class):
            continue
        candidate = (
            caller_class_path,
            name,
            _argument_count(invocation.child_by_field_name("arguments")),
            "method",
        )
        if candidate in method_keys:
            yield candidate, invocation.start_point.row + 1


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


def _is_local_qualifier(object_node: Node | None, current_class: str | None) -> bool:
    if object_node is None:
        return True
    if object_node.type in {"this", "super"}:
        return True
    return current_class is not None and _node_text(object_node) == current_class


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
