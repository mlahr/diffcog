from __future__ import annotations

from diffcog.languages.python.complexity import PYTHON_CONTROL_FLOW_RULESET, score_callable
from diffcog.languages.python.parser import parse_snapshot
from diffcog.languages.python.resolver import resolve_semantics


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
    return score_callable(snapshot.callables[0], PYTHON_CONTROL_FLOW_RULESET).score


def score_functions(source: str) -> dict[str, int]:
    snapshot = parse_snapshot(source)
    semantics = resolve_semantics(snapshot.callables)
    return {
        callable_.name: score_callable(callable_, semantic_context=semantics).score
        for callable_ in snapshot.callables
    }


def test_empty_function_scores_zero() -> None:
    assert score_function("def run():\n    pass\n") == 0


def test_single_if_scores_one() -> None:
    assert score_function("def run(x):\n    if x:\n        return 1\n") == 1


def test_nested_if_scores_three() -> None:
    assert score_function("def run(x, y):\n    if x:\n        if y:\n            return 1\n") == 3


def test_if_else_scores_two() -> None:
    source = "def run(x):\n    if x:\n        return 1\n    else:\n        return 2\n"

    assert score_function(source) == 2
    assert contribution_ids(source).count("python.else") == 1


def test_if_elif_else_chain_does_not_add_nested_if_penalty() -> None:
    source = (
        "def run(x):\n"
        "    if x == 1:\n"
        "        return 1\n"
        "    elif x == 2:\n"
        "        return 2\n"
        "    else:\n"
        "        return 3\n"
    )

    assert score_function(source) == 3


def test_loop_scores_one() -> None:
    assert score_function("def run(items):\n    for item in items:\n        pass\n") == 1
    assert score_function("def run(x):\n    while x:\n        x -= 1\n") == 1


def test_if_inside_loop_scores_three() -> None:
    assert (
        score_function(
            "def run(items):\n"
            "    for item in items:\n"
            "        if item:\n"
            "            return item\n"
        )
        == 3
    )


def test_async_for_scores_one() -> None:
    assert score_function("async def run(items):\n    async for item in items:\n        pass\n") == 1


def test_except_scores_one_per_clause() -> None:
    source = (
        "def run():\n"
        "    try:\n"
        "        risky()\n"
        "    except ValueError:\n"
        "        recover()\n"
        "    except Exception:\n"
        "        fallback()\n"
    )

    assert score_function(source) == 2
    assert contribution_ids(source).count("python.except") == 2


def test_ternary_scores_one() -> None:
    assert score_function("def run(x):\n    return 1 if x else 2\n") == 1


def test_boolean_chain_scores_one() -> None:
    source = "def run(a, b, c):\n    if a and b and c:\n        return 1\n"

    assert score_function(source) == 2
    assert contribution_ids(source).count("python.boolean_chain") == 1


def test_mixed_boolean_operator_sequences_score_each_run() -> None:
    source = "def run(a, b, c, d):\n    if a and b or c and d:\n        return 1\n"

    assert score_function(source) == 4


def test_nested_boolean_expression_does_not_double_count() -> None:
    source = "def run(a, b, c):\n    if a and (b or c):\n        return 1\n"

    assert score_function(source) == 3
    assert contribution_ids(source).count("python.boolean_chain") == 1


def test_not_operator_splits_boolean_operator_sequences() -> None:
    source = "def run(a, b, c):\n    if not (a and b) or c:\n        return 1\n"

    assert score_function(source) == 3
    assert contribution_ids(source).count("python.boolean_chain") == 1


def test_control_flow_ruleset_excludes_boolean_chain() -> None:
    source = "def run(a, b, c):\n    if a and b and c:\n        return 1\n"

    assert score_function(source) == 2
    assert score_function_control_flow(source) == 1


def test_direct_recursion_scores_one() -> None:
    assert score_functions("def run():\n    return run()\n") == {"run": 1}


def test_self_qualified_recursion_scores_one() -> None:
    assert score_functions("class Service:\n    def run(self):\n        return self.run()\n") == {
        "run": 1
    }


def test_cls_qualified_recursion_scores_one() -> None:
    assert score_functions("class Service:\n    def run(cls):\n        return cls.run()\n") == {
        "run": 1
    }


def test_class_qualified_recursion_scores_one() -> None:
    assert score_functions("class Service:\n    def run(self):\n        return Service.run()\n") == {
        "run": 1
    }


def test_mutual_recursion_scores_each_function_once() -> None:
    assert score_functions("def a():\n    return b()\n\ndef b():\n    return a()\n") == {
        "a": 1,
        "b": 1,
    }


def test_non_recursive_helper_call_does_not_score_recursion() -> None:
    assert score_functions("def a():\n    return b()\n\ndef b():\n    return 1\n") == {
        "a": 0,
        "b": 0,
    }


def test_variable_qualified_call_does_not_score_recursion() -> None:
    assert score_functions("class Service:\n    def run(self):\n        return other.run()\n") == {
        "run": 0
    }
