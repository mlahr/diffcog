from __future__ import annotations

from functools import lru_cache

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from diffcog.models import CallableSymbol, ClassSymbol, ParsedSnapshot


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
        classes=list(_extract_classes(root, [])),
    )


@lru_cache(maxsize=1)
def _parser() -> Parser:
    parser = Parser()
    parser.language = Language(tree_sitter_java.language())
    return parser


def _extract_callables(node: Node, namespace_path: list[str]) -> list[CallableSymbol]:
    next_namespace_path = namespace_path
    if node.type in TYPE_DECLARATIONS:
        name = _node_text(node.child_by_field_name("name"))
        if name is not None:
            next_namespace_path = [*namespace_path, name]

    callables: list[CallableSymbol] = []
    kind = CALLABLE_DECLARATIONS.get(node.type)
    if kind is not None:
        callable_name = _node_text(node.child_by_field_name("name"))
        if callable_name is not None:
            callables.append(
                CallableSymbol(
                    kind=kind,
                    name=callable_name,
                    namespace_path=next_namespace_path,
                    parameter_count=_parameter_count(node),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    node=node,
                )
            )

    for child in node.children:
        callables.extend(_extract_callables(child, next_namespace_path))

    return callables


def _extract_classes(node: Node, namespace_path: list[str]) -> list[ClassSymbol]:
    classes: list[ClassSymbol] = []
    next_namespace_path = namespace_path
    if node.type in TYPE_DECLARATIONS:
        name = _node_text(node.child_by_field_name("name"))
        if name is not None:
            next_namespace_path = [*namespace_path, name]
            classes.append(
                ClassSymbol(
                    name=name,
                    namespace_path=next_namespace_path,
                    kind=node.type.removesuffix("_declaration"),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    node=node,
                )
            )

    for child in node.children:
        classes.extend(_extract_classes(child, next_namespace_path))

    return classes


def _parameter_count(node: Node) -> int:
    parameters = node.child_by_field_name("parameters")
    if parameters is None:
        return 0
    return sum(1 for child in parameters.children if child.type in PARAMETER_NODE_TYPES)


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return node.text.decode("utf-8")
