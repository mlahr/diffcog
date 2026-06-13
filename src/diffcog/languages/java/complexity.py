from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tree_sitter import Node

from diffcog.languages.java.models import JavaCallable


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
}


def score_callable(
    callable_: JavaCallable, ruleset: RuleSet | None = None
) -> ComplexityResult:
    active_ruleset = ruleset or DEFAULT_JAVA_RULESET
    contributions = _walk(callable_.node, ScoringContext(nesting=0), active_ruleset)
    return ComplexityResult(
        score=sum(contribution.points for contribution in contributions),
        contributions=contributions,
    )


def _walk(node: Node, context: ScoringContext, ruleset: RuleSet) -> list[ComplexityContribution]:
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


def _boolean_chain_rule(node: Node, _context: ScoringContext) -> list[ComplexityContribution]:
    if not _is_boolean_binary_expression(node):
        return []
    parent = node.parent
    if parent is not None and _is_boolean_binary_expression(parent):
        return []
    return [
        ComplexityContribution(
            rule_id="java.boolean_chain",
            line=node.start_point.row + 1,
            points=1,
            message="boolean operator chain",
        )
    ]


def _is_boolean_binary_expression(node: Node) -> bool:
    if node.type != "binary_expression":
        return False
    return any(child.type in {"&&", "||"} for child in node.children)


DEFAULT_JAVA_RULESET = RuleSet(
    id="java.default",
    rules=[
        ComplexityRule(
            id="java.if",
            node_types={"if_statement"},
            score=_control_flow_rule("java.if", "if statement"),
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
            id="java.boolean_chain",
            node_types={"binary_expression"},
            score=_boolean_chain_rule,
        ),
    ],
    nesting_node_types=CONTROL_FLOW_NODE_TYPES,
)
