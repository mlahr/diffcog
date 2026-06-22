from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from tree_sitter import Node

from diffcog.models import CallableSymbol, ComplexityContribution, ComplexityResult

CallableKey = tuple[tuple[str, ...], str, int, str]


@dataclass(frozen=True)
class ScoringContext:
    nesting: int


@dataclass(frozen=True)
class GoSemanticContext:
    recursive_call_lines: Mapping[CallableKey, int] = field(default_factory=dict)


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
    "for_statement",
    "expression_switch_statement",
    "type_switch_statement",
    "select_statement",
    "func_literal",
}


def get_ruleset(ruleset_id: str) -> RuleSet:
    try:
        return GO_RULESETS[ruleset_id]
    except KeyError as exc:
        available = ", ".join(list_ruleset_ids())
        raise ValueError(f"unknown Go rule set '{ruleset_id}' (available: {available})") from exc


def list_ruleset_ids() -> list[str]:
    return sorted(GO_RULESETS)


def score_callable(
    callable_: CallableSymbol,
    ruleset: RuleSet | None = None,
    semantic_context: GoSemanticContext | None = None,
) -> ComplexityResult:
    active_ruleset = ruleset or DEFAULT_GO_RULESET
    active_semantic_context = semantic_context or GoSemanticContext()
    contributions = [
        *_recursion_contributions(callable_, active_semantic_context),
        *_walk(callable_.node, ScoringContext(nesting=0), active_ruleset),
    ]
    return ComplexityResult(
        score=sum(contribution.points for contribution in contributions),
        contributions=contributions,
    )


def _recursion_contributions(
    callable_: CallableSymbol, semantic_context: GoSemanticContext
) -> list[ComplexityContribution]:
    line = semantic_context.recursive_call_lines.get(_callable_key(callable_))
    if line is None:
        return []
    return [
        ComplexityContribution(
            rule_id="go.recursion",
            line=line,
            points=1,
            message="recursive function call",
        )
    ]


def _callable_key(callable_: CallableSymbol) -> CallableKey:
    return (
        tuple(callable_.namespace_path),
        callable_.name,
        callable_.parameter_count,
        callable_.kind,
    )


def _walk(node: Node, context: ScoringContext, ruleset: RuleSet) -> list[ComplexityContribution]:
    if node.type == "if_statement":
        return _walk_if_statement(node, context, ruleset)

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
    consequence_context = context
    if not _is_else_if(node):
        consequence_context = ScoringContext(nesting=context.nesting + 1)
    if consequence is not None:
        contributions.extend(_walk(consequence, consequence_context, ruleset))

    alternative = node.child_by_field_name("alternative")
    if alternative is not None:
        alternative_context = context if alternative.type == "if_statement" else ScoringContext(nesting=context.nesting + 1)
        contributions.extend(_walk(alternative, alternative_context, ruleset))

    return contributions


def _control_flow_rule(rule_id: str, label: str) -> RuleScorer:
    def score(node: Node, context: ScoringContext) -> list[ComplexityContribution]:
        if node.type == "if_statement" and _is_else_if(node):
            return []
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
    alternative = node.child_by_field_name("alternative")
    if alternative is None:
        return []
    return [
        ComplexityContribution(
            rule_id="go.else",
            line=alternative.start_point.row + 1,
            points=1,
            message="else branch",
        )
    ]


def _boolean_chain_rule(node: Node, _context: ScoringContext) -> list[ComplexityContribution]:
    if not _is_boolean_binary_expression(node):
        return []
    parent = node.parent
    if parent is not None and _is_boolean_binary_expression(parent):
        return []
    sequence_count = _boolean_sequence_count(node)
    if sequence_count == 0:
        return []
    return [
        ComplexityContribution(
            rule_id="go.boolean_chain",
            line=node.start_point.row + 1,
            points=sequence_count,
            message="boolean operator chain",
        )
    ]


def _is_boolean_binary_expression(node: Node) -> bool:
    if node.type != "binary_expression":
        return False
    operator = node.child_by_field_name("operator")
    return operator is not None and operator.type in {"&&", "||"}


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
    if node.type == "binary_expression":
        operators: list[str | None] = []
        left = node.child_by_field_name("left")
        if left is not None:
            operators.extend(_boolean_operator_sequence(left))
        operator = node.child_by_field_name("operator")
        if operator is not None and operator.type in {"&&", "||"}:
            operators.append(operator.type)
        right = node.child_by_field_name("right")
        if right is not None:
            operators.extend(_boolean_operator_sequence(right))
        return operators
    if node.type == "unary_expression" and any(child.type == "!" for child in node.children):
        operators = [None]
        for child in node.children:
            if child.is_named:
                operators.extend(_boolean_operator_sequence(child))
        return operators
    return []


def _is_else_if(node: Node) -> bool:
    parent = node.parent
    return (
        parent is not None
        and parent.type == "if_statement"
        and _field_name(parent, node) == "alternative"
    )


def _field_name(parent: Node, child: Node) -> str | None:
    for index, candidate in enumerate(parent.children):
        if candidate == child:
            return parent.field_name_for_child(index)
    return None


GO_CONTROL_FLOW_RULES = [
    ComplexityRule(
        id="go.if",
        node_types={"if_statement"},
        score=_control_flow_rule("go.if", "if statement"),
    ),
    ComplexityRule(
        id="go.else",
        node_types={"if_statement"},
        score=_else_rule,
    ),
    ComplexityRule(
        id="go.loop",
        node_types={"for_statement"},
        score=_control_flow_rule("go.loop", "loop"),
    ),
    ComplexityRule(
        id="go.switch",
        node_types={"expression_switch_statement", "type_switch_statement"},
        score=_control_flow_rule("go.switch", "switch"),
    ),
    ComplexityRule(
        id="go.select",
        node_types={"select_statement"},
        score=_control_flow_rule("go.select", "select"),
    ),
]


GO_BOOLEAN_CHAIN_RULE = ComplexityRule(
    id="go.boolean_chain",
    node_types={"binary_expression"},
    score=_boolean_chain_rule,
)


GO_CONTROL_FLOW_RULESET = RuleSet(
    id="go.control-flow",
    rules=GO_CONTROL_FLOW_RULES,
    nesting_node_types=CONTROL_FLOW_NODE_TYPES,
)


DEFAULT_GO_RULESET = RuleSet(
    id="go.default",
    rules=[
        *GO_CONTROL_FLOW_RULES,
        GO_BOOLEAN_CHAIN_RULE,
    ],
    nesting_node_types=CONTROL_FLOW_NODE_TYPES,
)


GO_RULESETS = {
    GO_CONTROL_FLOW_RULESET.id: GO_CONTROL_FLOW_RULESET,
    DEFAULT_GO_RULESET.id: DEFAULT_GO_RULESET,
}
