from __future__ import annotations

from diffcog.models import CallableSymbol, LineRange


def changed_callables(
    callables: list[CallableSymbol], changed_ranges: list[LineRange]
) -> list[CallableSymbol]:
    return [
        callable_
        for callable_ in callables
        if any(_ranges_intersect(callable_.start_line, callable_.end_line, range_) for range_ in changed_ranges)
    ]


def unmapped_ranges(
    changed_ranges: list[LineRange], callables: list[CallableSymbol]
) -> list[LineRange]:
    return [
        range_
        for range_ in changed_ranges
        if not any(_ranges_intersect(callable_.start_line, callable_.end_line, range_) for callable_ in callables)
    ]


def classify_callables(
    before_callables: list[CallableSymbol], after_callables: list[CallableSymbol]
) -> tuple[list[tuple[CallableSymbol, CallableSymbol]], list[CallableSymbol], list[CallableSymbol]]:
    before_by_key = {callable_key(callable_): callable_ for callable_ in before_callables}
    after_by_key = {callable_key(callable_): callable_ for callable_ in after_callables}

    modified = [
        (before_by_key[key], after_by_key[key])
        for key in before_by_key.keys() & after_by_key.keys()
    ]
    added = [
        after_by_key[key]
        for key in after_by_key.keys() - before_by_key.keys()
    ]
    removed = [
        before_by_key[key]
        for key in before_by_key.keys() - after_by_key.keys()
    ]

    return (
        sorted(modified, key=lambda pair: pair[1].start_line),
        sorted(added, key=lambda callable_: callable_.start_line),
        sorted(removed, key=lambda callable_: callable_.start_line),
    )


def callable_key(callable_: CallableSymbol) -> tuple[tuple[str, ...], str, int, str]:
    return (
        tuple(callable_.namespace_path),
        callable_.name,
        callable_.parameter_count,
        callable_.kind,
    )


def _ranges_intersect(start: int, end: int, range_: LineRange) -> bool:
    return start <= range_.end and range_.start <= end
