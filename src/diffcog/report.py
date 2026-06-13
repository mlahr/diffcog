from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from diffcog.errors import DiffcogError
from diffcog.languages.java.selection import changed_callables, classify_callables, unmapped_ranges
from diffcog.models import AnalysisResult, CallableComplexityDelta, LineRange, Thresholds

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

    if details and result.file_deltas:
        lines.extend(["", *_format_file_delta_details(result.file_deltas)])
    elif details and result.files:
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
        "files": _json_files_payload(result),
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
        before_callables = changed_callables(before.callables, pair.file.old_ranges)
        after_callables = changed_callables(after.callables, pair.file.new_ranges)
        before_outside = unmapped_ranges(pair.file.old_ranges, before.callables)
        after_outside = unmapped_ranges(pair.file.new_ranges, after.callables)
        modified, added, removed = classify_callables(before_callables, after_callables)
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


def format_complexity_text(result: AnalysisResult) -> str:
    parse_snapshot = _load_java_parser()
    score_callable = _load_java_scorer()

    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
        "Complexity dump",
    ]

    if not result.source_pairs:
        lines.extend(["", "No Java changes found."])
        return "\n".join(lines) + "\n"

    for pair in result.source_pairs:
        before = parse_snapshot(pair.before)
        after = parse_snapshot(pair.after)
        before_callables = changed_callables(before.callables, pair.file.old_ranges)
        after_callables = changed_callables(after.callables, pair.file.new_ranges)
        modified, added, removed = classify_callables(before_callables, after_callables)
        lines.extend(
            [
                "",
                _format_changed_file(pair.file.status, pair.file.old_path, pair.file.path),
                *_format_complexity_groups(modified, added, removed, score_callable),
            ]
        )

    return "\n".join(lines) + "\n"


def format_complexity_json(result: AnalysisResult) -> str:
    parse_snapshot = _load_java_parser()
    score_callable = _load_java_scorer()

    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "debug": "show-complexity",
        "files": [],
    }
    for pair in result.source_pairs:
        before = parse_snapshot(pair.before)
        after = parse_snapshot(pair.after)
        before_callables = changed_callables(before.callables, pair.file.old_ranges)
        after_callables = changed_callables(after.callables, pair.file.new_ranges)
        modified, added, removed = classify_callables(before_callables, after_callables)
        payload["files"].append(
            {
                "status": pair.file.status,
                "path": pair.file.path,
                "old_path": pair.file.old_path,
                "callables": [
                    *_complexity_payloads("modified", [after for _, after in modified], score_callable),
                    *_complexity_payloads("added", added, score_callable),
                    *_complexity_payloads("removed", removed, score_callable),
                ],
            }
        )

    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _format_signed(value: int) -> str:
    if value >= 0:
        return f"+{value}"
    return str(value)


def _format_changed_file(status: str, old_path: str, path: str) -> str:
    if status.startswith("R") or status.startswith("C"):
        return f"{status} {old_path} -> {path}"
    return f"{status} {path}"


def _json_files_payload(result: AnalysisResult) -> list[dict[str, Any]]:
    if result.file_deltas:
        return [
            {
                "status": file_delta.file.status,
                "path": file_delta.file.path,
                "old_path": file_delta.file.old_path,
                "callables": [
                    _callable_delta_payload(callable_delta, file_delta.file)
                    for callable_delta in file_delta.callables
                ],
            }
            for file_delta in result.file_deltas
        ]
    return [
        {
            "status": file.status,
            "path": file.path,
            "old_path": file.old_path,
        }
        for file in result.files
    ]


def _format_file_delta_details(file_deltas: list[Any]) -> list[str]:
    lines = []
    for file_delta in file_deltas:
        lines.append(_format_changed_file(file_delta.file.status, file_delta.file.old_path, file_delta.file.path))
        added = [delta for delta in file_delta.callables if delta.status == "added"]
        modified = [delta for delta in file_delta.callables if delta.status == "modified"]
        removed = [delta for delta in file_delta.callables if delta.status == "removed"]
        lines.extend(_format_callable_delta_group("modified", modified, file_delta.file))
        lines.extend(_format_callable_delta_group("added", added, file_delta.file))
        lines.extend(_format_callable_delta_group("removed", removed, file_delta.file))
        if not file_delta.callables:
            lines.append("  no changed methods/constructors")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _format_callable_delta_group(
    label: str, callable_deltas: list[CallableComplexityDelta], file: Any
) -> list[str]:
    if not callable_deltas:
        return []

    lines = [f"  {label}:"]
    for callable_delta in callable_deltas:
        callable_ = callable_delta.after_callable or callable_delta.before_callable
        lines.append(f"    {_format_callable_signature(callable_)} {callable_.kind}")
        if callable_delta.before_callable is not None:
            lines.append(f"      before complexity {callable_delta.before_score}")
        if callable_delta.after_callable is not None:
            lines.append(f"      after  complexity {callable_delta.after_score}")
        lines.append(f"      delta {_format_signed(callable_delta.delta)}")
        contributions = _changed_line_contributions(callable_delta, file)
        if contributions:
            lines.append("      complexity on changed lines:")
            lines.extend(
                f"        {contribution.rule_id} line {contribution.line} +{contribution.points}"
                for contribution in contributions
            )
    return lines


def _callable_delta_payload(callable_delta: CallableComplexityDelta, file: Any) -> dict[str, Any]:
    callable_ = callable_delta.after_callable or callable_delta.before_callable
    return {
        "status": callable_delta.status,
        **_callable_payload(callable_),
        "before_score": callable_delta.before_score,
        "after_score": callable_delta.after_score,
        "delta": callable_delta.delta,
        "changed_line_contributions": [
            {
                "rule_id": contribution.rule_id,
                "line": contribution.line,
                "points": contribution.points,
                "message": contribution.message,
            }
            for contribution in _changed_line_contributions(callable_delta, file)
        ],
    }


def _changed_line_contributions(callable_delta: CallableComplexityDelta, file: Any) -> list[Any]:
    if callable_delta.status in {"added", "modified"}:
        result = callable_delta.after_result
        ranges = file.new_ranges
    else:
        result = callable_delta.before_result
        ranges = file.old_ranges

    if result is None:
        return []

    return [
        contribution
        for contribution in result.contributions
        if any(_line_in_range(contribution.line, range_) for range_ in ranges)
    ]


def _line_in_range(line: int, range_: LineRange) -> bool:
    return range_.start <= line <= range_.end


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


def _format_complexity_groups(
    modified: list[tuple[JavaCallable, JavaCallable]],
    added: list[JavaCallable],
    removed: list[JavaCallable],
    score_callable: Any,
) -> list[str]:
    lines = []
    if modified:
        lines.append("  modified:")
        for _, after_callable in modified:
            lines.extend(_format_complexity_callable(after_callable, score_callable))
    if added:
        lines.append("  added:")
        for callable_ in added:
            lines.extend(_format_complexity_callable(callable_, score_callable))
    if removed:
        lines.append("  removed:")
        for callable_ in removed:
            lines.extend(_format_complexity_callable(callable_, score_callable))
    if not lines:
        lines.append("  no changed methods/constructors")
    return lines


def _format_complexity_callable(callable_: JavaCallable, score_callable: Any) -> list[str]:
    result = score_callable(callable_)
    lines = [f"    {_format_callable_signature(callable_)} {callable_.kind} complexity {result.score}"]
    lines.extend(
        f"      {contribution.rule_id} line {contribution.line} +{contribution.points}"
        for contribution in result.contributions
    )
    return lines


def _complexity_payloads(status: str, callables: list[JavaCallable], score_callable: Any) -> list[dict[str, Any]]:
    return [
        {
            "status": status,
            **_callable_payload(callable_),
            "score": result.score,
            "contributions": [
                {
                    "rule_id": contribution.rule_id,
                    "line": contribution.line,
                    "points": contribution.points,
                    "message": contribution.message,
                }
                for contribution in result.contributions
            ],
        }
        for callable_ in callables
        for result in [score_callable(callable_)]
    ]


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
            for callable_ in changed_callables(snapshot.callables, changed_ranges)
        ],
        "outside_ranges": [
            {"start": range_.start, "end": range_.end}
            for range_ in unmapped_ranges(changed_ranges, snapshot.callables)
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


def _load_java_scorer() -> Any:
    try:
        from diffcog.languages.java.complexity import score_callable
    except ModuleNotFoundError as exc:
        if exc.name in {"tree_sitter", "tree_sitter_java"}:
            raise DiffcogError(
                "Java complexity dependencies are missing. "
                "Refresh the installed tool with: "
                "uv tool install --force -e /Users/michael/Code/mlahr/diff-complexity"
            ) from exc
        raise
    return score_callable
