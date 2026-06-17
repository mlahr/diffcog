from __future__ import annotations

from functools import lru_cache

import tree_sitter_python
from tree_sitter import Language, Node, Parser

from diffcog.models import CallableSymbol, ParsedSnapshot


PARAMETER_NODE_TYPES = {
    "identifier",
    "typed_parameter",
    "default_parameter",
    "typed_default_parameter",
    "list_splat_pattern",
    "dictionary_splat_pattern",
}


def parse_snapshot(source: str | None) -> ParsedSnapshot:
    if source is None:
        return ParsedSnapshot(present=False, parse_error=False, callables=[])

    parser = _parser()
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    return ParsedSnapshot(
        present=True,
        parse_error=root.has_error,
        callables=list(_extract_callables(root, [])),
    )


@lru_cache(maxsize=1)
def _parser() -> Parser:
    parser = Parser()
    parser.language = Language(tree_sitter_python.language())
    return parser


def _extract_callables(node: Node, containers: list[tuple[str, str]]) -> list[CallableSymbol]:
    node = _definition_node(node)

    if node.type == "class_definition":
        class_name = _node_text(node.child_by_field_name("name"))
        next_containers = containers
        if class_name is not None:
            next_containers = [*containers, ("class", class_name)]
        return _extract_child_callables(node, next_containers)

    if node.type == "function_definition":
        function_name = _node_text(node.child_by_field_name("name"))
        if function_name is None:
            return _extract_child_callables(node, containers)

        callable_ = CallableSymbol(
            kind=_callable_kind(containers),
            name=function_name,
            namespace_path=[name for _kind, name in containers],
            parameter_count=_parameter_count(node),
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            node=node,
        )
        return [
            callable_,
            *_extract_child_callables(node, [*containers, ("function", function_name)]),
        ]

    return _extract_child_callables(node, containers)


def _extract_child_callables(node: Node, containers: list[tuple[str, str]]) -> list[CallableSymbol]:
    callables: list[CallableSymbol] = []
    for child in node.children:
        callables.extend(_extract_callables(child, containers))
    return callables


def _definition_node(node: Node) -> Node:
    if node.type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        if definition is not None:
            return definition
    return node


def _callable_kind(containers: list[tuple[str, str]]) -> str:
    if containers and containers[-1][0] == "class":
        return "method"
    return "function"


def _parameter_count(node: Node) -> int:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return 0
    return sum(1 for child in parameters.children if child.type in PARAMETER_NODE_TYPES)


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return node.text.decode("utf-8")
