from __future__ import annotations

from itertools import combinations

from tree_sitter import Node

from diffcog.models import ClassMetrics, ClassSymbol, ParsedSnapshot


JAVA_IGNORED_TYPES = {
    "boolean",
    "byte",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "void",
    "Boolean",
    "Byte",
    "Character",
    "Double",
    "Float",
    "Integer",
    "Long",
    "Short",
    "String",
    "Object",
    "Class",
    "Enum",
    "Record",
    "Exception",
    "RuntimeException",
    "Collection",
    "List",
    "Map",
    "Optional",
    "Set",
}

TYPE_NODE_TYPES = {
    "type_identifier",
    "scoped_type_identifier",
    "generic_type",
}

CALLABLE_DECLARATIONS = {
    "method_declaration",
    "constructor_declaration",
    "compact_constructor_declaration",
}

TYPE_DECLARATIONS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
}


def score_class_metrics(snapshot: ParsedSnapshot) -> dict[tuple[str, ...], ClassMetrics]:
    return {
        tuple(class_.namespace_path): _score_class(class_, snapshot.classes)
        for class_ in snapshot.classes
    }


def _score_class(class_: ClassSymbol, classes: list[ClassSymbol]) -> ClassMetrics:
    methods = _participating_methods(class_.node)
    field_names = _field_names(class_.node)
    method_fields = [_used_instance_fields(method, field_names) for method in methods]
    return ClassMetrics(
        cbo=len(_coupled_types(class_, classes)),
        lcom=_lcom(method_fields),
        wmc=len(methods),
    )


def _participating_methods(class_node: Node) -> list[Node]:
    body = class_node.child_by_field_name("body")
    if body is None:
        return []
    return [
        child
        for child in body.children
        if child.type in CALLABLE_DECLARATIONS and not _has_modifier(child, "static")
    ]


def _field_names(class_node: Node) -> set[str]:
    body = class_node.child_by_field_name("body")
    if body is None:
        return set()
    names: set[str] = set()
    for child in body.children:
        if child.type != "field_declaration":
            continue
        for declarator in _walk(child):
            if declarator.type == "variable_declarator":
                name = declarator.child_by_field_name("name")
                if name is not None:
                    names.add(_node_text(name))
    return names


def _used_instance_fields(method: Node, field_names: set[str]) -> set[str]:
    local_names = _local_names(method)
    used: set[str] = set()
    for node in _walk(method):
        if node.type == "field_access":
            object_node = node.child_by_field_name("object")
            field_node = node.child_by_field_name("field")
            if object_node is not None and object_node.type == "this" and field_node is not None:
                field_name = _node_text(field_node)
                if field_name in field_names:
                    used.add(field_name)
        elif node.type == "identifier":
            name = _node_text(node)
            if name in field_names and name not in local_names and not _is_declaration_identifier(node):
                used.add(name)
    return used


def _local_names(method: Node) -> set[str]:
    names: set[str] = set()
    parameters = method.child_by_field_name("parameters")
    if parameters is not None:
        for child in parameters.children:
            if child.type in {"formal_parameter", "spread_parameter", "receiver_parameter"}:
                name = child.child_by_field_name("name")
                if name is not None:
                    names.add(_node_text(name))
    for node in _walk(method):
        if node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            if name is not None:
                names.add(_node_text(name))
    return names


def _lcom(method_fields: list[set[str]]) -> int:
    if not method_fields or all(not fields for fields in method_fields):
        return 0
    disjoint = 0
    shared = 0
    for left, right in combinations(method_fields, 2):
        if left & right:
            shared += 1
        else:
            disjoint += 1
    return max(disjoint - shared, 0)


def _coupled_types(class_: ClassSymbol, classes: list[ClassSymbol]) -> set[str]:
    own_names = {class_.name, *class_.namespace_path}
    nested_ranges = [
        (candidate.node.start_byte, candidate.node.end_byte)
        for candidate in classes
        if candidate is not class_
        and candidate.namespace_path[: len(class_.namespace_path)] == class_.namespace_path
    ]
    names: set[str] = set()
    for node in _walk(class_.node):
        if any(start <= node.start_byte < end for start, end in nested_ranges):
            continue
        if node.type == "generic_type":
            continue
        if node.type in TYPE_NODE_TYPES:
            name = _simple_type_name(node)
            if name not in own_names and name not in JAVA_IGNORED_TYPES:
                names.add(name)
    return names


def _simple_type_name(node: Node) -> str:
    if node.type == "scoped_type_identifier":
        identifiers = [_node_text(child) for child in node.children if child.type == "identifier"]
        return identifiers[-1] if identifiers else _node_text(node).rsplit(".", 1)[-1]
    return _node_text(node).split("<", 1)[0].rsplit(".", 1)[-1]


def _has_modifier(node: Node, modifier: str) -> bool:
    modifiers = next((child for child in node.children if child.type == "modifiers"), None)
    return modifiers is not None and modifier in _node_text(modifiers).split()


def _is_declaration_identifier(node: Node) -> bool:
    parent = node.parent
    return parent is not None and parent.child_by_field_name("name") == node


def _walk(node: Node) -> list[Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk(child))
    return nodes


def _node_text(node: Node) -> str:
    return node.text.decode("utf-8")
