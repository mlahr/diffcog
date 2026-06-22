from __future__ import annotations

import pytest

from diffcog.languages.go.complexity import get_ruleset, list_ruleset_ids, score_callable
from diffcog.languages.go.parser import parse_snapshot
from diffcog.languages.go.resolver import resolve_semantics


def score_function(source: str) -> int:
    snapshot = parse_snapshot(source)
    assert len(snapshot.callables) == 1
    return score_callable(snapshot.callables[0]).score


def contribution_ids(source: str) -> list[str]:
    snapshot = parse_snapshot(source)
    assert len(snapshot.callables) == 1
    return [contribution.rule_id for contribution in score_callable(snapshot.callables[0]).contributions]


def score_function_control_flow(source: str) -> int:
    snapshot = parse_snapshot(source)
    assert len(snapshot.callables) == 1
    return score_callable(snapshot.callables[0], get_ruleset("go.control-flow")).score


def score_functions(source: str) -> dict[str, int]:
    snapshot = parse_snapshot(source)
    semantics = resolve_semantics(snapshot.callables)
    return {
        callable_.name: score_callable(callable_, semantic_context=semantics).score
        for callable_ in snapshot.callables
    }


def test_empty_function_scores_zero() -> None:
    assert score_function("package app\n\nfunc Run() {}\n") == 0


def test_single_if_scores_one() -> None:
    assert score_function("package app\n\nfunc Run(x bool) { if x { work() } }\n") == 1


def test_nested_if_scores_three() -> None:
    assert score_function("package app\n\nfunc Run(x, y bool) { if x { if y { work() } } }\n") == 3


def test_if_else_scores_two() -> None:
    source = "package app\n\nfunc Run(x bool) { if x { work() } else { stop() } }\n"

    assert score_function(source) == 2
    assert contribution_ids(source).count("go.else") == 1


def test_else_if_chain_does_not_add_nested_if_penalty() -> None:
    source = "package app\n\nfunc Run(x, y bool) { if x { work() } else if y { stop() } else { wait() } }\n"

    assert score_function(source) == 3


def test_loop_scores_one() -> None:
    assert score_function("package app\n\nfunc Run(items []int) { for _, item := range items { _ = item } }\n") == 1
    assert score_function("package app\n\nfunc Run(x bool) { for x { work() } }\n") == 1


def test_if_inside_loop_scores_three() -> None:
    source = "package app\n\nfunc Run(items []int) { for _, item := range items { if item > 0 { work() } } }\n"

    assert score_function(source) == 3


def test_switch_scores_once() -> None:
    source = "package app\n\nfunc Run(x int) { switch x { case 1: work(); default: stop() } }\n"

    assert score_function(source) == 1
    assert contribution_ids(source).count("go.switch") == 1


def test_type_switch_scores_once() -> None:
    source = "package app\n\nfunc Run(x any) { switch x.(type) { case int: work(); default: stop() } }\n"

    assert score_function(source) == 1
    assert contribution_ids(source).count("go.switch") == 1


def test_select_scores_once() -> None:
    source = "package app\n\nfunc Run(ch <-chan int) { select { case <-ch: work(); default: stop() } }\n"

    assert score_function(source) == 1
    assert contribution_ids(source).count("go.select") == 1


def test_boolean_chain_scores_one() -> None:
    source = "package app\n\nfunc Run(a, b, c bool) { if a && b && c { work() } }\n"

    assert score_function(source) == 2
    assert contribution_ids(source).count("go.boolean_chain") == 1


def test_mixed_boolean_operator_sequences_score_each_run() -> None:
    source = "package app\n\nfunc Run(a, b, c, d bool) { if a && b || c && d { work() } }\n"

    assert score_function(source) == 4


def test_control_flow_ruleset_excludes_boolean_chain() -> None:
    source = "package app\n\nfunc Run(a, b, c bool) { if a && b && c { work() } }\n"

    assert score_function(source) == 2
    assert score_function_control_flow(source) == 1


def test_func_literal_increases_nesting_without_scoring_itself() -> None:
    source = "package app\n\nfunc Run() { fn := func(x bool) { if x { work() } }; fn(true) }\n"

    assert score_function(source) == 2


def test_direct_function_recursion_scores_one() -> None:
    assert score_functions("package app\n\nfunc Run() { Run() }\n") == {"Run": 1}


def test_mutual_function_recursion_scores_each_function_once() -> None:
    assert score_functions("package app\n\nfunc First() { Second() }\nfunc Second() { First() }\n") == {
        "First": 1,
        "Second": 1,
    }


def test_receiver_qualified_method_recursion_scores_one() -> None:
    source = "package app\n\ntype Service struct{}\nfunc (s *Service) Run() { s.Run() }\n"

    assert score_functions(source) == {"Run": 1}


def test_non_receiver_qualified_call_does_not_score_recursion() -> None:
    source = "package app\n\ntype Service struct{}\nfunc (s *Service) Run() { other.Run() }\n"

    assert score_functions(source) == {"Run": 0}


def test_ruleset_registry_lists_known_rulesets() -> None:
    assert list_ruleset_ids() == ["go.control-flow", "go.default"]


def test_unknown_ruleset_errors_with_available_rulesets() -> None:
    with pytest.raises(ValueError, match="available: go.control-flow, go.default"):
        get_ruleset("go.missing")
