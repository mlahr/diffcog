from __future__ import annotations

from diffcog.models import CallableSymbol, LineRange
from diffcog.selection import callable_key, changed_callables, classify_callables, unmapped_ranges


def _callable(
    name: str,
    *,
    namespace_path: list[str] | None = None,
    parameter_count: int = 0,
    start_line: int = 1,
    end_line: int = 1,
) -> CallableSymbol:
    return CallableSymbol(
        kind="function",
        name=name,
        namespace_path=namespace_path or [],
        parameter_count=parameter_count,
        start_line=start_line,
        end_line=end_line,
        node=None,
    )


def test_callable_key_uses_language_neutral_namespace_path() -> None:
    callable_ = _callable("run", namespace_path=["Service"], parameter_count=1)

    assert callable_key(callable_) == (("Service",), "run", 1, "function")


def test_changed_callables_selects_intersecting_line_ranges() -> None:
    first = _callable("first", start_line=1, end_line=3)
    second = _callable("second", start_line=8, end_line=10)

    assert changed_callables([first, second], [LineRange(2, 2)]) == [first]


def test_classify_callables_matches_by_callable_identity() -> None:
    before_same = _callable("same", namespace_path=["Service"])
    after_same = _callable("same", namespace_path=["Service"], start_line=5)
    before_removed = _callable("removed")
    after_added = _callable("added")

    modified, added, removed = classify_callables(
        [before_removed, before_same],
        [after_added, after_same],
    )

    assert modified == [(before_same, after_same)]
    assert added == [after_added]
    assert removed == [before_removed]


def test_unmapped_ranges_returns_ranges_outside_callables() -> None:
    callable_ = _callable("run", start_line=3, end_line=5)

    assert unmapped_ranges([LineRange(1, 1), LineRange(4, 4)], [callable_]) == [LineRange(1, 1)]
