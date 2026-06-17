from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tree_sitter import Node

from diffcog.models import CallableSymbol, ComplexityContribution, ComplexityResult
from diffcog.languages.python.resolver import PythonSemanticContext


@dataclass(frozen=True)
class ScoringContext:
    nesting: int


RuleScorer = Callable[[Node, ScoringContext], list[ComplexityContribution]]


@dataclass(frozen=True)
class ComplexityRule:
    id: str
    node_types: set[str]
    score: RuleScorer


@dataclass(frozen=True)
class RuleSet:
    id: str
    rules: list[ComplexityRule]
    nesting_node_types: set[str]


CONTROL_FLOW_NODE_TYPES = {
    "if_statement",
    "elif_clause",
    "for_statement",
    "while_statement",
    "except_clause",
    "conditional_expression",
    "match_statement",
    "lambda",
    "with_statement",
}

COMPREHENSION_NODE_TYPES = {
    "list_comprehension",
    "set_comprehension",
    "dictionary_comprehension",
    "generator_expression",
}


def score_callable(
    callable_: CallableSymbol,
    ruleset: RuleSet | None = None,
    semantic_context: PythonSemanticContext | None = None,
) -> ComplexityResult:
    active_ruleset = ruleset or DEFAULT_PYTHON_RULESET
    active_semantic_context = semantic_context or PythonSemanticContext()
    contributions = [
        *_recursion_contributions(callable_, active_semantic_context),
        *_walk(callable_.node, ScoringContext(nesting=0), active_ruleset),
    ]
    return ComplexityResult(
        score=sum(contribution.points for contribution in contributions),
        contributions=contributions,
    )


def _recursion_contributions(
    callable_: CallableSymbol, semantic_context: PythonSemanticContext
) -> list[ComplexityContribution]:
    line = semantic_context.recursive_call_lines.get(_callable_key(callable_))
    if line is None:
        return []
    return [
        ComplexityContribution(
            rule_id="python.recursion",
            line=line,
            points=1,
            message="recursive function call",
        )
    ]


def _callable_key(callable_: CallableSymbol) -> tuple[tuple[str, ...], str, int, str]:
    return (
        tuple(callable_.namespace_path),
        callable_.name,
        callable_.parameter_count,
        callable_.kind,
    )


def _walk(node: Node, context: ScoringContext, ruleset: RuleSet) -> list[ComplexityContribution]:
    if node.type == "if_statement":
        return _walk_if_statement(node, context, ruleset)
    if node.type == "elif_clause":
        return _walk_elif_clause(node, context, ruleset)

    contributions: list[ComplexityContribution] = []
    for rule in ruleset.rules:
        if node.type in rule.node_types:
            contributions.extend(rule.score(node, context))

    child_context = context
    if node.type in ruleset.nesting_node_types:
        child_context = ScoringContext(nesting=context.nesting + 1)

    for child in node.children:
        contributions.extend(_walk(child, child_context, ruleset))

    return contributions


def _walk_if_statement(
    node: Node, context: ScoringContext, ruleset: RuleSet
) -> list[ComplexityContribution]:
    contributions: list[ComplexityContribution] = []
    for rule in ruleset.rules:
        if node.type in rule.node_types:
            contributions.extend(rule.score(node, context))

    condition = node.child_by_field_name("condition")
    if condition is not None:
        contributions.extend(_walk(condition, context, ruleset))

    consequence = node.child_by_field_name("consequence")
    if consequence is not None:
        contributions.extend(_walk(consequence, ScoringContext(nesting=context.nesting + 1), ruleset))

    for alternative in node.children_by_field_name("alternative"):
        if alternative.type == "elif_clause":
            contributions.extend(_walk(alternative, context, ruleset))
        else:
            contributions.extend(_walk(alternative, ScoringContext(nesting=context.nesting + 1), ruleset))

    return contributions


def _walk_elif_clause(
    node: Node, context: ScoringContext, ruleset: RuleSet
) -> list[ComplexityContribution]:
    contributions: list[ComplexityContribution] = []
    for rule in ruleset.rules:
        if node.type in rule.node_types:
            contributions.extend(rule.score(node, context))

    condition = node.child_by_field_name("condition")
    if condition is not None:
        contributions.extend(_walk(condition, context, ruleset))

    consequence = node.child_by_field_name("consequence")
    if consequence is not None:
        contributions.extend(_walk(consequence, ScoringContext(nesting=context.nesting + 1), ruleset))

    return contributions


def _control_flow_rule(rule_id: str, label: str) -> RuleScorer:
    def score(node: Node, context: ScoringContext) -> list[ComplexityContribution]:
        points = 1 + context.nesting
        return [
            ComplexityContribution(
                rule_id=rule_id,
                line=node.start_point.row + 1,
                points=points,
                message=f"{label} at nesting depth {context.nesting}",
            )
        ]

    return score


def _else_rule(node: Node, _context: ScoringContext) -> list[ComplexityContribution]:
    alternatives = [child for child in node.children_by_field_name("alternative") if child.type == "else_clause"]
    return [
        ComplexityContribution(
            rule_id="python.else",
            line=alternative.start_point.row + 1,
            points=1,
            message="else branch",
        )
        for alternative in alternatives
    ]


def _boolean_chain_rule(node: Node, _context: ScoringContext) -> list[ComplexityContribution]:
    if _has_boolean_operator_ancestor(node):
        return []
    sequence_count = _boolean_sequence_count(node)
    if sequence_count == 0:
        return []
    return [
        ComplexityContribution(
            rule_id="python.boolean_chain",
            line=node.start_point.row + 1,
            points=sequence_count,
            message="boolean operator chain",
        )
    ]


def _has_boolean_operator_ancestor(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "boolean_operator":
            return True
        parent = parent.parent
    return False


def _boolean_sequence_count(node: Node) -> int:
    count = 0
    current_operator: str | None = None
    for operator in _boolean_operator_sequence(node):
        if operator is None:
            current_operator = None
        elif operator != current_operator:
            count += 1
            current_operator = operator
    return count


def _boolean_operator_sequence(node: Node) -> list[str | None]:
    if node.type == "boolean_operator":
        operators: list[str | None] = []
        left = node.child_by_field_name("left")
        if left is not None:
            operators.extend(_boolean_operator_sequence(left))
        operator = node.child_by_field_name("operator")
        if operator is not None:
            operators.append(operator.type)
        right = node.child_by_field_name("right")
        if right is not None:
            operators.extend(_boolean_operator_sequence(right))
        return operators
    if node.type == "not_operator":
        argument = node.child_by_field_name("argument")
        return [None, *_boolean_operator_sequence(argument)] if argument is not None else [None]
    if node.type == "parenthesized_expression":
        operators: list[str | None] = []
        for child in node.children:
            if child.is_named:
                operators.extend(_boolean_operator_sequence(child))
        return operators
    return []


PYTHON_CONTROL_FLOW_RULES = [
    ComplexityRule(
        id="python.if",
        node_types={"if_statement"},
        score=_control_flow_rule("python.if", "if statement"),
    ),
    ComplexityRule(
        id="python.elif",
        node_types={"elif_clause"},
        score=_control_flow_rule("python.elif", "elif clause"),
    ),
    ComplexityRule(
        id="python.else",
        node_types={"if_statement"},
        score=_else_rule,
    ),
    ComplexityRule(
        id="python.loop",
        node_types={"for_statement", "while_statement"},
        score=_control_flow_rule("python.loop", "loop"),
    ),
    ComplexityRule(
        id="python.except",
        node_types={"except_clause"},
        score=_control_flow_rule("python.except", "except clause"),
    ),
    ComplexityRule(
        id="python.ternary",
        node_types={"conditional_expression"},
        score=_control_flow_rule("python.ternary", "ternary expression"),
    ),
    ComplexityRule(
        id="python.match",
        node_types={"match_statement"},
        score=_control_flow_rule("python.match", "match statement"),
    ),
]


PYTHON_BOOLEAN_CHAIN_RULE = ComplexityRule(
    id="python.boolean_chain",
    node_types={"boolean_operator"},
    score=_boolean_chain_rule,
)


PYTHON_CONTROL_FLOW_RULESET = RuleSet(
    id="python.control-flow",
    rules=PYTHON_CONTROL_FLOW_RULES,
    nesting_node_types=CONTROL_FLOW_NODE_TYPES | COMPREHENSION_NODE_TYPES,
)


DEFAULT_PYTHON_RULESET = RuleSet(
    id="python.default",
    rules=[
        *PYTHON_CONTROL_FLOW_RULES,
        PYTHON_BOOLEAN_CHAIN_RULE,
    ],
    nesting_node_types=CONTROL_FLOW_NODE_TYPES | COMPREHENSION_NODE_TYPES,
)


PYTHON_RULESETS = {
    PYTHON_CONTROL_FLOW_RULESET.id: PYTHON_CONTROL_FLOW_RULESET,
    DEFAULT_PYTHON_RULESET.id: DEFAULT_PYTHON_RULESET,
}
