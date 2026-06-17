from __future__ import annotations

from itertools import combinations

from tree_sitter import Node

from diffcog.models import ClassMetrics, ClassSymbol, ParsedSnapshot


PYTHON_IGNORED_TYPES = {
    "Any",
    "None",
    "bool",
    "bytes",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "object",
    "set",
    "str",
    "tuple",
}


def score_class_metrics(snapshot: ParsedSnapshot) -> dict[tuple[str, ...], ClassMetrics]:
    imports = _imported_names(snapshot.classes)
    return {
        tuple(class_.namespace_path): _score_class(class_, imports)
        for class_ in snapshot.classes
    }


def _score_class(class_: ClassSymbol, imports: set[str]) -> ClassMetrics:
    methods = _participating_methods(class_.node)
    method_fields = [_used_instance_fields(method) for method in methods]
    return ClassMetrics(
        cbo=len(_coupled_types(class_, imports)),
        lcom=_lcom(method_fields),
        wmc=len(methods),
    )


def _participating_methods(class_node: Node) -> list[Node]:
    body = class_node.child_by_field_name("body")
    if body is None:
        return []
    methods: list[Node] = []
    for child in body.children:
        definition = _definition_node(child)
        if definition.type != "function_definition":
            continue
        if _has_decorator(child, "staticmethod"):
            continue
        if _first_parameter_name(definition) == "self":
            methods.append(definition)
    return methods


def _used_instance_fields(method: Node) -> set[str]:
    receiver = _first_parameter_name(method)
    if receiver is None:
        return set()
    fields: set[str] = set()
    for node in _walk(method):
        if node.type != "attribute":
            continue
        object_node = node.child_by_field_name("object")
        attribute_node = node.child_by_field_name("attribute")
        if object_node is not None and _node_text(object_node) == receiver and attribute_node is not None:
            fields.add(_node_text(attribute_node))
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


def _coupled_types(class_: ClassSymbol, imports: set[str]) -> set[str]:
    own_names = {class_.name, *class_.namespace_path}
    field_types = _field_type_map(class_.node)
    names: set[str] = set()
    for node in _walk(class_.node):
        if node.type == "type":
            names.update(_type_names(node))
        elif node.type == "class_definition":
            superclasses = node.child_by_field_name("superclasses")
            if superclasses is not None:
                names.update(_reference_names(superclasses))
        elif node.type == "call":
            call_name = _call_name(node)
            if call_name is not None and call_name in imports:
                names.add(call_name)
            field_type = _self_field_call_type(node, field_types)
            if field_type is not None:
                names.add(field_type)
    return {
        name
        for name in names
        if name not in own_names and name not in PYTHON_IGNORED_TYPES
    }


def _field_type_map(class_node: Node) -> dict[str, str]:
    fields: dict[str, str] = {}
    receiver_names = {"self"}
    for node in _walk(class_node):
        if node.type != "assignment":
            continue
        left = node.child_by_field_name("left")
        type_node = node.child_by_field_name("type")
        right = node.child_by_field_name("right")
        if type_node is not None and left is not None:
            if left.type == "identifier":
                first_name = next(iter(_type_names(type_node)), None)
                if first_name is not None:
                    fields[_node_text(left)] = first_name
            elif left.type == "attribute":
                field = _self_field_name(left, receiver_names)
                first_name = next(iter(_type_names(type_node)), None)
                if field is not None and first_name is not None:
                    fields[field] = first_name
        elif left is not None and right is not None and left.type == "attribute":
            field = _self_field_name(left, receiver_names)
            if field is None or right.type != "identifier":
                continue
            parameter_type = _parameter_type_for_assignment(node, _node_text(right))
            if parameter_type is not None:
                fields[field] = parameter_type
    return fields


def _parameter_type_for_assignment(assignment: Node, name: str) -> str | None:
    function = _ancestor(assignment, "function_definition")
    if function is None:
        return None
    parameters = function.child_by_field_name("parameters")
    if parameters is None:
        return None
    for parameter in parameters.children:
        if parameter.type != "typed_parameter":
            continue
        parameter_name = next((child for child in parameter.children if child.type == "identifier"), None)
        type_node = parameter.child_by_field_name("type")
        if parameter_name is not None and _node_text(parameter_name) == name and type_node is not None:
            return next(iter(_type_names(type_node)), None)
    return None


def _self_field_call_type(node: Node, field_types: dict[str, str]) -> str | None:
    function = node.child_by_field_name("function")
    if function is None or function.type != "attribute":
        return None
    object_node = function.child_by_field_name("object")
    if object_node is None or object_node.type != "attribute":
        return None
    field = _self_field_name(object_node, {"self"})
    if field is None:
        return None
    return field_types.get(field)


def _type_names(node: Node) -> set[str]:
    return {
        _node_text(child)
        for child in _walk(node)
        if child.type == "identifier" and _node_text(child) not in PYTHON_IGNORED_TYPES
    }


def _reference_names(node: Node) -> set[str]:
    return {
        _node_text(child)
        for child in _walk(node)
        if child.type == "identifier" and _node_text(child) not in PYTHON_IGNORED_TYPES
    }


def _imported_names(classes: list[ClassSymbol]) -> set[str]:
    root = _root(classes[0].node) if classes else None
    if root is None:
        return set()
    names: set[str] = set()
    for node in _walk(root):
        if node.type not in {"import_statement", "import_from_statement"}:
            continue
        for child in _walk(node):
            if child.type == "identifier":
                names.add(_node_text(child))
    return names


def _call_name(node: Node) -> str | None:
    function = node.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "identifier":
        return _node_text(function)
    if function.type == "attribute":
        attribute = function.child_by_field_name("attribute")
        if attribute is not None:
            return _node_text(attribute)
    return None


def _self_field_name(attribute: Node, receiver_names: set[str]) -> str | None:
    object_node = attribute.child_by_field_name("object")
    attribute_node = attribute.child_by_field_name("attribute")
    if object_node is None or attribute_node is None:
        return None
    if object_node.type == "identifier" and _node_text(object_node) in receiver_names:
        return _node_text(attribute_node)
    return None


def _first_parameter_name(function: Node) -> str | None:
    parameters = function.child_by_field_name("parameters")
    if parameters is None:
        return None
    for child in parameters.children:
        if child.type == "identifier":
            return _node_text(child)
        if child.type in {"typed_parameter", "default_parameter", "typed_default_parameter"}:
            identifier = next((grandchild for grandchild in child.children if grandchild.type == "identifier"), None)
            return _node_text(identifier) if identifier is not None else None
    return None


def _definition_node(node: Node) -> Node:
    if node.type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        if definition is not None:
            return definition
    return node


def _has_decorator(node: Node, decorator_name: str) -> bool:
    if node.type != "decorated_definition":
        return False
    return any(child.type == "decorator" and decorator_name in _node_text(child) for child in node.children)


def _ancestor(node: Node, node_type: str) -> Node | None:
    parent = node.parent
    while parent is not None:
        if parent.type == node_type:
            return parent
        parent = parent.parent
    return None


def _root(node: Node) -> Node:
    current = node
    while current.parent is not None:
        current = current.parent
    return current


def _walk(node: Node) -> list[Node]:
    nodes = [node]
    for child in node.children:
        nodes.extend(_walk(child))
    return nodes


def _node_text(node: Node) -> str:
    return node.text.decode("utf-8")
