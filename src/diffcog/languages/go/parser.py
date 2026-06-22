from __future__ import annotations

from functools import lru_cache

import tree_sitter_go
from tree_sitter import Language, Node, Parser

from diffcog.models import CallableSymbol, ClassSymbol, ParsedSnapshot


CALLABLE_DECLARATIONS = {
    "function_declaration": "function",
    "method_declaration": "method",
}

PARAMETER_NODE_TYPES = {
    "parameter_declaration",
    "variadic_parameter_declaration",
}


def parse_snapshot(source: str | None) -> ParsedSnapshot:
    if source is None:
        return ParsedSnapshot(present=False, parse_error=False, callables=[])

    parser = _parser()
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    package_name = _package_name(root)
    return ParsedSnapshot(
        present=True,
        parse_error=root.has_error,
        callables=list(_extract_callables(root, package_name)),
        classes=list(_extract_classes(root, package_name)),
    )


@lru_cache(maxsize=1)
def _parser() -> Parser:
    parser = Parser()
    parser.language = Language(tree_sitter_go.language())
    return parser


def _extract_callables(node: Node, package_name: str | None) -> list[CallableSymbol]:
    callables: list[CallableSymbol] = []
    kind = CALLABLE_DECLARATIONS.get(node.type)
    if kind is not None:
        name = _node_text(node.child_by_field_name("name"))
        namespace_path = _namespace_path(node, package_name, kind)
        if name is not None:
            callables.append(
                CallableSymbol(
                    kind=kind,
                    name=name,
                    namespace_path=namespace_path,
                    parameter_count=_parameter_count(node.child_by_field_name("parameters")),
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    node=node,
                )
            )

    for child in node.children:
        callables.extend(_extract_callables(child, package_name))

    return callables


def _extract_classes(node: Node, package_name: str | None) -> list[ClassSymbol]:
    classes: list[ClassSymbol] = []
    if node.type == "type_declaration":
        spec = next((child for child in node.children if child.type == "type_spec"), None)
        type_node = spec.child_by_field_name("type") if spec is not None else None
        name = _node_text(spec.child_by_field_name("name")) if spec is not None else None
        kind = _class_kind(type_node)
        if name is not None and kind is not None:
            namespace_path = [package_name, name] if package_name is not None else [name]
            classes.append(
                ClassSymbol(
                    name=name,
                    namespace_path=namespace_path,
                    kind=kind,
                    start_line=node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                    node=node,
                )
            )

    for child in node.children:
        classes.extend(_extract_classes(child, package_name))

    return classes


def _namespace_path(node: Node, package_name: str | None, kind: str) -> list[str]:
    namespace_path = [package_name] if package_name is not None else []
    if kind != "method":
        return namespace_path

    receiver_type = _receiver_type_name(node.child_by_field_name("receiver"))
    if receiver_type is None:
        return namespace_path
    return [*namespace_path, receiver_type]


def _package_name(root: Node) -> str | None:
    for child in root.children:
        if child.type != "package_clause":
            continue
        identifier = next((node for node in child.children if node.type == "package_identifier"), None)
        return _node_text(identifier)
    return None


def _class_kind(type_node: Node | None) -> str | None:
    if type_node is None:
        return None
    if type_node.type == "struct_type":
        return "struct"
    if type_node.type == "interface_type":
        return "interface"
    return None


def _receiver_type_name(receiver: Node | None) -> str | None:
    if receiver is None:
        return None
    for node in _walk(receiver):
        if node.type == "type_identifier":
            return _node_text(node)
    return None


def _parameter_count(parameters: Node | None) -> int:
    if parameters is None:
        return 0
    count = 0
    for child in parameters.children:
        if child.type not in PARAMETER_NODE_TYPES:
            continue
        names = child.children_by_field_name("name")
        count += len(names) if names else 1
    return count


def _walk(node: Node) -> list[Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk(child))
    return nodes


def _node_text(node: Node | None) -> str | None:
    if node is None:
        return None
    return node.text.decode("utf-8")
