from __future__ import annotations

from itertools import combinations

from tree_sitter import Node

from diffcog.models import ClassMetrics, ClassSymbol, ParsedSnapshot


GO_IGNORED_TYPES = {
    "any",
    "bool",
    "byte",
    "comparable",
    "complex64",
    "complex128",
    "error",
    "float32",
    "float64",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "rune",
    "string",
    "uint",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "uintptr",
}

TYPE_NODE_TYPES = {
    "generic_type",
    "qualified_type",
    "type_identifier",
}


def score_class_metrics(snapshot: ParsedSnapshot) -> dict[tuple[str, ...], ClassMetrics]:
    methods_by_receiver = _methods_by_receiver(snapshot.callables)
    return {
        tuple(class_.namespace_path): _score_type(class_, methods_by_receiver.get(class_.name, []))
        for class_ in snapshot.classes
    }


def _score_type(class_: ClassSymbol, methods: list[Node]) -> ClassMetrics:
    if class_.kind == "interface":
        return ClassMetrics(
            cbo=len(_coupled_types(class_, _interface_body(class_.node), [])),
            lcom=0,
            wmc=len(_interface_methods(class_.node)),
        )

    field_names = _field_names(class_.node)
    method_fields = [_used_receiver_fields(method, field_names) for method in methods]
    return ClassMetrics(
        cbo=len(_coupled_types(class_, _struct_body(class_.node), methods)),
        lcom=_lcom(method_fields),
        wmc=len(methods),
    )


def _methods_by_receiver(callables: list[object]) -> dict[str, list[Node]]:
    methods: dict[str, list[Node]] = {}
    for callable_ in callables:
        if getattr(callable_, "kind", None) != "method" or not callable_.namespace_path:
            continue
        receiver = callable_.namespace_path[-1]
        methods.setdefault(receiver, []).append(callable_.node)
    return methods


def _field_names(type_declaration: Node) -> set[str]:
    body = _struct_body(type_declaration)
    if body is None:
        return set()
    names: set[str] = set()
    for field in body.children:
        if field.type != "field_declaration":
            continue
        declared = field.children_by_field_name("name")
        if declared:
            names.update(_node_text(name) for name in declared)
            continue
        type_node = field.child_by_field_name("type")
        if type_node is not None:
            names.add(_simple_type_name(type_node))
    return names


def _used_receiver_fields(method: Node, field_names: set[str]) -> set[str]:
    receiver = _receiver_name(method.child_by_field_name("receiver"))
    if receiver is None:
        return set()
    fields: set[str] = set()
    for node in _walk(method):
        if node.type != "selector_expression":
            continue
        operand = node.child_by_field_name("operand")
        field = node.child_by_field_name("field")
        if operand is not None and field is not None and _node_text(operand) == receiver:
            field_name = _node_text(field)
            if field_name in field_names:
                fields.add(field_name)
    return fields


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


def _coupled_types(class_: ClassSymbol, body: Node | None, methods: list[Node]) -> set[str]:
    own_names = {class_.name, *class_.namespace_path}
    names: set[str] = set()
    if body is not None:
        names.update(_type_names(body))
    for method in methods:
        names.update(_type_names(method))
    return {
        name
        for name in names
        if name not in own_names and name not in GO_IGNORED_TYPES
    }


def _type_names(node: Node) -> set[str]:
    names: set[str] = set()
    for child in _walk(node):
        if child.type not in TYPE_NODE_TYPES:
            continue
        names.add(_simple_type_name(child))
    return names


def _simple_type_name(node: Node) -> str:
    if node.type == "qualified_type":
        name = node.child_by_field_name("name")
        return _node_text(name) if name is not None else _node_text(node).rsplit(".", 1)[-1]
    if node.type == "generic_type":
        name = node.child_by_field_name("type")
        return _node_text(name) if name is not None else _node_text(node).split("[", 1)[0]
    return _node_text(node).lstrip("*").rsplit(".", 1)[-1]


def _interface_methods(type_declaration: Node) -> list[Node]:
    body = _interface_body(type_declaration)
    if body is None:
        return []
    return [child for child in body.children if child.type == "method_elem"]


def _struct_body(type_declaration: Node) -> Node | None:
    type_node = _declared_type(type_declaration)
    if type_node is None or type_node.type != "struct_type":
        return None
    return next((child for child in type_node.children if child.type == "field_declaration_list"), None)


def _interface_body(type_declaration: Node) -> Node | None:
    type_node = _declared_type(type_declaration)
    if type_node is None or type_node.type != "interface_type":
        return None
    return type_node


def _declared_type(type_declaration: Node) -> Node | None:
    spec = next((child for child in type_declaration.children if child.type == "type_spec"), None)
    if spec is None:
        return None
    return spec.child_by_field_name("type")


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


def _walk(node: Node) -> list[Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk(child))
    return nodes


def _node_text(node: Node) -> str:
    return node.text.decode("utf-8")
