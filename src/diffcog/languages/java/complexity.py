from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from tree_sitter import Node

from diffcog.languages.java.models import JavaCallable

CallableKey = tuple[tuple[str, ...], str, int, str]


@dataclass(frozen=True)
class ScoringContext:
    nesting: int


@dataclass(frozen=True)
class ComplexityContribution:
    rule_id: str
    line: int
    points: int
    message: str


@dataclass(frozen=True)
class ComplexityResult:
    score: int
    contributions: list[ComplexityContribution]


@dataclass(frozen=True)
class JavaSemanticContext:
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
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
    "catch_clause",
    "switch_expression",
    "switch_statement",
    "ternary_expression",
    "lambda_expression",
}


def get_ruleset(ruleset_id: str) -> RuleSet:
    try:
        return JAVA_RULESETS[ruleset_id]
    except KeyError as exc:
        available = ", ".join(list_ruleset_ids())
        raise ValueError(f"unknown Java rule set '{ruleset_id}' (available: {available})") from exc


def list_ruleset_ids() -> list[str]:
    return sorted(JAVA_RULESETS)


def score_callable(
    callable_: JavaCallable,
    ruleset: RuleSet | None = None,
    semantic_context: JavaSemanticContext | None = None,
) -> ComplexityResult:
    active_ruleset = ruleset or DEFAULT_JAVA_RULESET
    active_semantic_context = semantic_context or JavaSemanticContext()
    contributions = [
        *_recursion_contributions(callable_, active_semantic_context),
        *_walk(callable_.node, ScoringContext(nesting=0), active_ruleset),
    ]
    return ComplexityResult(
        score=sum(contribution.points for contribution in contributions),
        contributions=contributions,
    )


def _recursion_contributions(
    callable_: JavaCallable, semantic_context: JavaSemanticContext
) -> list[ComplexityContribution]:
    line = semantic_context.recursive_call_lines.get(_callable_key(callable_))
    if line is None:
        return []
    return [
        ComplexityContribution(
            rule_id="java.recursion",
            line=line,
            points=1,
            message="recursive method call",
        )
    ]


def _callable_key(callable_: JavaCallable) -> CallableKey:
    return (
        tuple(callable_.class_path),
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
        alternative_context = ScoringContext(nesting=context.nesting + 1)
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
            rule_id="java.else",
            line=alternative.start_point.row + 1,
            points=1,
            message="else branch",
        )
    ]


def _labeled_jump_rule(rule_id: str, label: str) -> RuleScorer:
    def score(node: Node, _context: ScoringContext) -> list[ComplexityContribution]:
        jump_label = next((child for child in node.children if child.type == "identifier"), None)
        if jump_label is None:
            return []
        return [
            ComplexityContribution(
                rule_id=rule_id,
                line=node.start_point.row + 1,
                points=1,
                message=f"labeled {label}",
            )
        ]

    return score


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
            rule_id="java.boolean_chain",
            line=node.start_point.row + 1,
            points=sequence_count,
            message="boolean operator chain",
        )
    ]


def _is_boolean_binary_expression(node: Node) -> bool:
    if node.type != "binary_expression":
        return False
    return any(child.type in {"&&", "||"} for child in node.children)


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
        for child in node.children:
            if child.type in {"&&", "||"}:
                operators.append(child.type)
            elif child.is_named:
                operators.extend(_boolean_operator_sequence(child))
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


JAVA_CONTROL_FLOW_RULES = [
    ComplexityRule(
        id="java.if",
        node_types={"if_statement"},
        score=_control_flow_rule("java.if", "if statement"),
    ),
    ComplexityRule(
        id="java.else",
        node_types={"if_statement"},
        score=_else_rule,
    ),
    ComplexityRule(
        id="java.loop",
        node_types={
            "for_statement",
            "enhanced_for_statement",
            "while_statement",
            "do_statement",
        },
        score=_control_flow_rule("java.loop", "loop"),
    ),
    ComplexityRule(
        id="java.catch",
        node_types={"catch_clause"},
        score=_control_flow_rule("java.catch", "catch clause"),
    ),
    ComplexityRule(
        id="java.switch",
        node_types={"switch_expression", "switch_statement"},
        score=_control_flow_rule("java.switch", "switch"),
    ),
    ComplexityRule(
        id="java.ternary",
        node_types={"ternary_expression"},
        score=_control_flow_rule("java.ternary", "ternary expression"),
    ),
    ComplexityRule(
        id="java.break",
        node_types={"break_statement"},
        score=_labeled_jump_rule("java.break", "break"),
    ),
    ComplexityRule(
        id="java.continue",
        node_types={"continue_statement"},
        score=_labeled_jump_rule("java.continue", "continue"),
    ),
]


JAVA_BOOLEAN_CHAIN_RULE = ComplexityRule(
    id="java.boolean_chain",
    node_types={"binary_expression"},
    score=_boolean_chain_rule,
)


JAVA_CONTROL_FLOW_RULESET = RuleSet(
    id="java.control-flow",
    rules=JAVA_CONTROL_FLOW_RULES,
    nesting_node_types=CONTROL_FLOW_NODE_TYPES,
)


DEFAULT_JAVA_RULESET = RuleSet(
    id="java.default",
    rules=[
        *JAVA_CONTROL_FLOW_RULES,
        JAVA_BOOLEAN_CHAIN_RULE,
    ],
    nesting_node_types=CONTROL_FLOW_NODE_TYPES,
)


JAVA_RULESETS = {
    JAVA_CONTROL_FLOW_RULESET.id: JAVA_CONTROL_FLOW_RULESET,
    DEFAULT_JAVA_RULESET.id: DEFAULT_JAVA_RULESET,
}
