from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from diffcog.errors import DiffcogError
from diffcog.models import AnalysisResult, LineRange, Thresholds

if TYPE_CHECKING:
    from diffcog.languages.java.models import JavaCallable, ParsedSnapshot


def format_text(result: AnalysisResult, thresholds: Thresholds, details: bool = False) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
    ]

    if result.files:
        lines.append(f"Java files changed: {len(result.files)}")
    else:
        lines.append("No Java changes found.")

    lines.extend(
        [
            f"New complexity: +{result.new_complexity}",
            f"Removed complexity: -{result.removed_complexity}",
            f"Net delta: {_format_signed(result.net_delta)}",
        ]
    )

    if details and result.files:
        lines.extend(["", "Changed Java files:"])
        lines.extend(f"  {_format_changed_file(file.status, file.old_path, file.path)}" for file in result.files)

    if result.threshold_failed(thresholds):
        lines.extend(["", "Threshold failed."])

    return "\n".join(lines) + "\n"


def format_json(result: AnalysisResult, thresholds: Thresholds) -> str:
    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "files": [
            {
                "status": file.status,
                "path": file.path,
                "old_path": file.old_path,
            }
            for file in result.files
        ],
        "new_complexity": result.new_complexity,
        "removed_complexity": result.removed_complexity,
        "net_delta": result.net_delta,
        "thresholds": {
            "max_new": thresholds.max_new,
            "max_delta": thresholds.max_delta,
        },
        "threshold_failed": result.threshold_failed(thresholds),
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def format_snapshot_text(result: AnalysisResult) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
        "Snapshot dump",
    ]

    if not result.source_pairs:
        lines.extend(["", "No Java changes found."])
        return "\n".join(lines) + "\n"

    for pair in result.source_pairs:
        lines.extend(
            [
                "",
                _format_changed_file(pair.file.status, pair.file.old_path, pair.file.path),
                f"  before: {_format_snapshot_stats(pair.before)}",
                f"  after:  {_format_snapshot_stats(pair.after)}",
            ]
        )

    return "\n".join(lines) + "\n"


def format_snapshot_json(result: AnalysisResult) -> str:
    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "debug": "show-snapshots",
        "snapshots": [
            {
                "status": pair.file.status,
                "path": pair.file.path,
                "old_path": pair.file.old_path,
                "before": _snapshot_stats(pair.before),
                "after": _snapshot_stats(pair.after),
            }
            for pair in result.source_pairs
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def format_symbol_text(result: AnalysisResult) -> str:
    parse_snapshot = _load_java_parser()

    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
        "Symbol dump",
    ]

    if not result.source_pairs:
        lines.extend(["", "No Java changes found."])
        return "\n".join(lines) + "\n"

    for pair in result.source_pairs:
        before = parse_snapshot(pair.before)
        after = parse_snapshot(pair.after)
        before_callables = _touched_callables(before.callables, pair.file.old_ranges)
        after_callables = _touched_callables(after.callables, pair.file.new_ranges)
        before_outside = _outside_ranges(pair.file.old_ranges, before.callables)
        after_outside = _outside_ranges(pair.file.new_ranges, after.callables)
        modified, added, removed = _classify_callables(before_callables, after_callables)
        lines.extend(
            [
                "",
                _format_changed_file(pair.file.status, pair.file.old_path, pair.file.path),
                *_format_symbol_groups(modified, added, removed, before, after),
                *_format_unmapped_lines(before_outside, after_outside),
            ]
        )

    return "\n".join(lines) + "\n"


def format_symbol_json(result: AnalysisResult) -> str:
    parse_snapshot = _load_java_parser()

    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "debug": "show-symbols",
        "files": [
            {
                "status": pair.file.status,
                "path": pair.file.path,
                "old_path": pair.file.old_path,
                "before": _touched_parsed_snapshot_payload(
                    parse_snapshot(pair.before), pair.file.old_ranges
                ),
                "after": _touched_parsed_snapshot_payload(
                    parse_snapshot(pair.after), pair.file.new_ranges
                ),
            }
            for pair in result.source_pairs
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _format_signed(value: int) -> str:
    if value >= 0:
        return f"+{value}"
    return str(value)


def _format_changed_file(status: str, old_path: str, path: str) -> str:
    if status.startswith("R") or status.startswith("C"):
        return f"{status} {old_path} -> {path}"
    return f"{status} {path}"


def _format_snapshot_stats(source: str | None) -> str:
    stats = _snapshot_stats(source)
    if not stats["present"]:
        return "missing"
    return f"present, {stats['lines']} lines, {stats['bytes']} bytes"


def _snapshot_stats(source: str | None) -> dict[str, bool | int]:
    if source is None:
        return {"present": False, "lines": 0, "bytes": 0}
    return {
        "present": True,
        "lines": len(source.splitlines()),
        "bytes": len(source.encode("utf-8")),
    }


def _format_symbol_groups(
    modified: list[tuple[JavaCallable, JavaCallable]],
    added: list[JavaCallable],
    removed: list[JavaCallable],
    before: ParsedSnapshot,
    after: ParsedSnapshot,
) -> list[str]:
    lines = []
    if before.present and before.parse_error:
        lines.append("  before parse error")
    if after.present and after.parse_error:
        lines.append("  after parse error")

    if modified:
        lines.append("  modified:")
        for before_callable, after_callable in modified:
            lines.extend(
                [
                    f"    {_format_callable_signature(after_callable)} {after_callable.kind}",
                    f"      before lines {before_callable.start_line}-{before_callable.end_line}",
                    f"      after  lines {after_callable.start_line}-{after_callable.end_line}",
                ]
            )

    if added:
        lines.append("  added:")
        lines.extend(f"    {_format_callable(callable_)}" for callable_ in added)

    if removed:
        lines.append("  removed:")
        lines.extend(f"    {_format_callable(callable_)}" for callable_ in removed)

    if not lines:
        lines.append("  no changed methods/constructors")

    return lines


def _format_unmapped_lines(
    before_outside: list[LineRange], after_outside: list[LineRange]
) -> list[str]:
    lines = []
    if before_outside or after_outside:
        lines.append("  changed lines not mapped to methods/constructors:")
    if before_outside:
        lines.append(f"    before {_format_ranges(before_outside)}")
    if after_outside:
        lines.append(f"    after {_format_ranges(after_outside)}")
    return lines


def _classify_callables(
    before_callables: list[JavaCallable], after_callables: list[JavaCallable]
) -> tuple[list[tuple[JavaCallable, JavaCallable]], list[JavaCallable], list[JavaCallable]]:
    before_by_key = {_callable_key(callable_): callable_ for callable_ in before_callables}
    after_by_key = {_callable_key(callable_): callable_ for callable_ in after_callables}

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


def _callable_key(callable_: JavaCallable) -> tuple[tuple[str, ...], str, int, str]:
    return (
        tuple(callable_.class_path),
        callable_.name,
        callable_.parameter_count,
        callable_.kind,
    )


def _format_callable_signature(callable_: JavaCallable) -> str:
    class_prefix = ".".join(callable_.class_path)
    if class_prefix:
        return f"{class_prefix}#{callable_.name}/{callable_.parameter_count}"
    return f"{callable_.name}/{callable_.parameter_count}"


def _format_callable(callable_: JavaCallable) -> str:
    return (
        f"{_format_callable_signature(callable_)} {callable_.kind} "
        f"lines {callable_.start_line}-{callable_.end_line}"
    )


def _touched_parsed_snapshot_payload(
    snapshot: ParsedSnapshot, changed_ranges: list[LineRange]
) -> dict[str, Any]:
    return {
        "present": snapshot.present,
        "parse_error": snapshot.parse_error,
        "callables": [
            _callable_payload(callable_)
            for callable_ in _touched_callables(snapshot.callables, changed_ranges)
        ],
        "outside_ranges": [
            {"start": range_.start, "end": range_.end}
            for range_ in _outside_ranges(changed_ranges, snapshot.callables)
        ],
    }


def _callable_payload(callable_: JavaCallable) -> dict[str, Any]:
    return {
        "kind": callable_.kind,
        "name": callable_.name,
        "class_path": callable_.class_path,
        "parameter_count": callable_.parameter_count,
        "start_line": callable_.start_line,
        "end_line": callable_.end_line,
    }


def _touched_callables(
    callables: list[JavaCallable], changed_ranges: list[LineRange]
) -> list[JavaCallable]:
    return [
        callable_
        for callable_ in callables
        if any(_ranges_intersect(callable_.start_line, callable_.end_line, range_) for range_ in changed_ranges)
    ]


def _outside_ranges(
    changed_ranges: list[LineRange], callables: list[JavaCallable]
) -> list[LineRange]:
    return [
        range_
        for range_ in changed_ranges
        if not any(_ranges_intersect(callable_.start_line, callable_.end_line, range_) for callable_ in callables)
    ]


def _ranges_intersect(start: int, end: int, range_: LineRange) -> bool:
    return start <= range_.end and range_.start <= end


def _format_ranges(ranges: list[LineRange]) -> str:
    return ", ".join(
        f"line {range_.start}" if range_.start == range_.end else f"lines {range_.start}-{range_.end}"
        for range_ in ranges
    )


def _load_java_parser() -> Any:
    try:
        from diffcog.languages.java.parser import parse_snapshot
    except ModuleNotFoundError as exc:
        if exc.name in {"tree_sitter", "tree_sitter_java"}:
            raise DiffcogError(
                "Java symbol parsing dependencies are missing. "
                "Refresh the installed tool with: "
                "uv tool install --force -e /Users/michael/Code/mlahr/diff-complexity"
            ) from exc
        raise
    return parse_snapshot
