from __future__ import annotations

import pytest

from diffcog.languages.java.complexity import get_ruleset, list_ruleset_ids, score_callable
from diffcog.languages.java.parser import parse_snapshot
from diffcog.languages.java.resolver import resolve_semantics


def score_method(source: str) -> int:
    snapshot = parse_snapshot(source)
    assert len(snapshot.callables) == 1
    return score_callable(snapshot.callables[0]).score


def contribution_ids(source: str) -> list[str]:
    snapshot = parse_snapshot(source)
    assert len(snapshot.callables) == 1
    return [contribution.rule_id for contribution in score_callable(snapshot.callables[0]).contributions]


def score_methods(source: str) -> dict[str, int]:
    snapshot = parse_snapshot(source)
    semantics = resolve_semantics(snapshot.callables)
    return {
        callable_.name: score_callable(callable_, semantic_context=semantics).score
        for callable_ in snapshot.callables
    }


def test_empty_method_scores_zero() -> None:
    assert score_method("class Foo { void a() {} }\n") == 0


def test_single_if_scores_one() -> None:
    assert score_method("class Foo { void a() { if (x) { run(); } } }\n") == 1


def test_nested_if_scores_three() -> None:
    assert score_method("class Foo { void a() { if (x) { if (y) { run(); } } } }\n") == 3


def test_if_else_scores_two() -> None:
    assert score_method("class Foo { void a() { if (x) { run(); } else { stop(); } } }\n") == 2
    assert contribution_ids(
        "class Foo { void a() { if (x) { run(); } else { stop(); } } }\n"
    ).count("java.else") == 1


def test_else_if_chain_does_not_add_nested_if_penalty() -> None:
    assert (
        score_method(
            "class Foo { void a() { if (x) { run(); } else if (y) { stop(); } else { wait(); } } }\n"
        )
        == 3
    )


def test_loop_scores_one() -> None:
    assert score_method("class Foo { void a() { while (x) { run(); } } }\n") == 1


def test_if_inside_loop_scores_three() -> None:
    assert score_method("class Foo { void a() { while (x) { if (y) { run(); } } } }\n") == 3


def test_catch_scores_one() -> None:
    assert score_method(
        "class Foo { void a() { try { run(); } catch (Exception e) { recover(); } } }\n"
    ) == 1


def test_switch_scores_one() -> None:
    assert score_method("class Foo { void a(int x) { switch (x) { case 1 -> run(); } } }\n") == 1


def test_ternary_scores_one() -> None:
    assert score_method("class Foo { int a() { return x ? 1 : 2; } }\n") == 1


def test_boolean_chain_scores_one() -> None:
    assert score_method("class Foo { void a() { if (a && b && c) { run(); } } }\n") == 2
    assert contribution_ids("class Foo { void a() { if (a && b && c) { run(); } } }\n").count(
        "java.boolean_chain"
    ) == 1


def test_mixed_boolean_operator_sequences_score_each_run() -> None:
    assert score_method("class Foo { void a() { if (a && b || c && d) { run(); } } }\n") == 4


def test_labeled_jump_scores_one() -> None:
    assert score_method("class Foo { void a() { OUT: while (x) { break OUT; } } }\n") == 2
    assert "java.break" in contribution_ids(
        "class Foo { void a() { OUT: while (x) { break OUT; } } }\n"
    )


def test_unlabeled_jump_does_not_score() -> None:
    assert score_method("class Foo { void a() { while (x) { break; } } }\n") == 1


def test_lambda_increases_nesting_without_scoring_itself() -> None:
    assert score_method("class Foo { void a() { Runnable r = () -> { if (x) run(); }; } }\n") == 2


def test_direct_recursion_scores_one() -> None:
    assert score_methods("class Foo { void a() { a(); } }\n") == {"a": 1}


def test_this_qualified_recursion_scores_one() -> None:
    assert score_methods("class Foo { void a() { this.a(); } }\n") == {"a": 1}


def test_class_qualified_recursion_scores_one() -> None:
    assert score_methods("class Foo { void a() { Foo.a(); } }\n") == {"a": 1}


def test_super_qualified_call_counts_as_local_recursion() -> None:
    assert score_methods("class Foo extends Base { void a() { super.a(); } }\n") == {"a": 1}


def test_mutual_recursion_scores_each_method_once() -> None:
    assert score_methods("class Foo { void a() { b(); } void b() { a(); } }\n") == {
        "a": 1,
        "b": 1,
    }


def test_non_recursive_helper_call_does_not_score_recursion() -> None:
    assert score_methods("class Foo { void a() { b(); } void b() {} }\n") == {
        "a": 0,
        "b": 0,
    }


def test_variable_qualified_call_does_not_score_recursion() -> None:
    assert score_methods("class Foo { void a() { other.a(); } }\n") == {"a": 0}


def test_recursion_resolution_matches_arity() -> None:
    snapshot = parse_snapshot("class Foo { void a() { a(1); } void a(int x) {} }\n")
    semantics = resolve_semantics(snapshot.callables)

    scores = [
        score_callable(callable_, semantic_context=semantics).score
        for callable_ in snapshot.callables
    ]

    assert scores == [0, 0]


def test_control_flow_ruleset_includes_recursion() -> None:
    snapshot = parse_snapshot("class Foo { void a() { a(); } }\n")
    semantics = resolve_semantics(snapshot.callables)

    assert score_callable(
        snapshot.callables[0], get_ruleset("java.control-flow"), semantics
    ).score == 1


def test_control_flow_ruleset_excludes_boolean_chain() -> None:
    snapshot = parse_snapshot("class Foo { void a() { if (a && b && c) { run(); } } }\n")
    callable_ = snapshot.callables[0]

    assert score_callable(callable_, get_ruleset("java.default")).score == 2
    assert score_callable(callable_, get_ruleset("java.control-flow")).score == 1


def test_ruleset_registry_lists_known_rulesets() -> None:
    assert list_ruleset_ids() == ["java.control-flow", "java.default"]


def test_unknown_ruleset_errors_with_available_rulesets() -> None:
    with pytest.raises(ValueError, match="available: java.control-flow, java.default"):
        get_ruleset("java.missing")
