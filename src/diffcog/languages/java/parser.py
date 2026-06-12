from __future__ import annotations

from functools import lru_cache

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from diffcog.languages.java.models import JavaCallable, ParsedSnapshot


TYPE_DECLARATIONS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
}

CALLABLE_DECLARATIONS = {
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "compact_constructor_declaration": "constructor",
}

PARAMETER_NODE_TYPES = {
    "formal_parameter",
    "spread_parameter",
    "receiver_parameter",
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
    parser.language = Language(tree_sitter_java.language())
    return parser


def _extract_callables(node: Node, class_path: list[str]) -> list[JavaCallable]:
    next_class_path = class_path
    if node.type in TYPE_DECLARATIONS:
        name = _node_text(node.child_by_field_name("name"))
        if name is not None:
            next_class_path = [*class_path, name]

    callables: list[JavaCallable] = []
    kind = CALLABLE_DECLARATIONS.get(node.type)
    if kind is not None:
        callable_name = _node_text(node.child_by_field_name("name"))
        if callable_name is not None:
            callables.append(
                JavaCallable(
                    kind=kind,
                    name=callable_name,
                    class_path=next_class_path,
                    parameter_count=_parameter_count(node),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                )
            )

    for child in node.children:
        callables.extend(_extract_callables(child, next_class_path))

    return callables


def _parameter_count(node: Node) -> int:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return 0
    return sum(1 for child in parameters.children if child.type in PARAMETER_NODE_TYPES)


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return node.text.decode("utf-8")
