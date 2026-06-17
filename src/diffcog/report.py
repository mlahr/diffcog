from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from diffcog.debug_analysis import ComplexityDebugResult, SymbolDebugResult
from diffcog.models import AnalysisResult, CallableComplexityDelta, LineRange, Thresholds

if TYPE_CHECKING:
    from diffcog.models import CallableSymbol


HOTSPOT_LIMIT = 10


def format_text(
    result: AnalysisResult,
    thresholds: Thresholds,
    details: bool = False,
    hotspots: bool = False,
) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        _format_rule_sets(result.ruleset_id, result.rule_set_ids),
        "",
    ]

    if result.files:
        lines.append(f"Analyzed files changed: {len(result.files)}")
    else:
        lines.append("No supported language changes found.")

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
        lines.extend(["", "Changed analyzed files:"])
        lines.extend(f"  {_format_changed_file(file.status, file.old_path, file.path)}" for file in result.files)
    elif hotspots and result.files:
        lines.extend(["", *_format_hotspots(result.file_deltas)])

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
        "ruleset": result.ruleset_id,
        "rulesets": list(result.rule_set_ids),
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
        _format_rule_sets(result.ruleset_id, result.rule_set_ids),
        "",
        "Snapshot dump",
    ]

    if not result.source_pairs:
        lines.extend(["", "No supported language changes found."])
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
        "ruleset": result.ruleset_id,
        "rulesets": list(result.rule_set_ids),
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


def format_symbol_text(result: SymbolDebugResult) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        "",
        "Symbol dump",
    ]

    if not result.files:
        lines.extend(["", "No supported language changes found."])
        return "\n".join(lines) + "\n"

    for file in result.files:
        lines.extend(
            [
                "",
                _format_changed_file(file.file.status, file.file.old_path, file.file.path),
                *_format_symbol_groups(file),
                *_format_unmapped_lines(file.unmapped_before_ranges, file.unmapped_after_ranges),
            ]
        )

    return "\n".join(lines) + "\n"


def format_symbol_json(result: SymbolDebugResult) -> str:
    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "debug": "show-symbols",
        "ruleset": result.ruleset_id,
        "rulesets": list(result.rule_set_ids),
        "files": [
            {
                "status": file.file.status,
                "path": file.file.path,
                "old_path": file.file.old_path,
                "before": _symbol_side_payload(
                    present=file.before_present,
                    parse_error=file.before_parse_error,
                    callables=[before for before, _ in file.modified] + file.removed,
                    outside_ranges=file.unmapped_before_ranges,
                ),
                "after": _symbol_side_payload(
                    present=file.after_present,
                    parse_error=file.after_parse_error,
                    callables=[after for _, after in file.modified] + file.added,
                    outside_ranges=file.unmapped_after_ranges,
                ),
            }
            for file in result.files
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def format_complexity_text(result: ComplexityDebugResult) -> str:
    lines = [
        f"Comparing {result.comparison.before.label} -> {result.comparison.after.label}",
        _format_rule_sets(result.ruleset_id, result.rule_set_ids),
        "",
        "Complexity dump",
    ]

    if not result.files:
        lines.extend(["", "No supported language changes found."])
        return "\n".join(lines) + "\n"

    for file in result.files:
        lines.extend(
            [
                "",
                _format_changed_file(file.file.status, file.file.old_path, file.file.path),
                *_format_complexity_groups(file.callables),
            ]
        )

    return "\n".join(lines) + "\n"


def format_complexity_json(result: ComplexityDebugResult) -> str:
    payload: dict[str, Any] = {
        "comparison": {
            "mode": result.comparison.mode,
            "before": result.comparison.before.label,
            "after": result.comparison.after.label,
        },
        "debug": "show-complexity",
        "ruleset": result.ruleset_id,
        "rulesets": list(result.rule_set_ids),
        "files": [],
    }
    for file in result.files:
        payload["files"].append(
            {
                "status": file.file.status,
                "path": file.file.path,
                "old_path": file.file.old_path,
                "callables": [
                    _complexity_payload(callable_)
                    for callable_ in file.callables
                ],
            }
        )

    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def _format_signed(value: int) -> str:
    if value >= 0:
        return f"+{value}"
    return str(value)


def _format_rule_sets(ruleset_id: str, rule_set_ids: tuple[str, ...]) -> str:
    if len(rule_set_ids) <= 1:
        return f"Rule set: {ruleset_id}"
    return f"Rule sets: {', '.join(rule_set_ids)}"


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
            lines.append("  no changed callables")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _format_hotspots(file_deltas: list[Any]) -> list[str]:
    hotspot_rows = sorted(
        [
            (file_delta, callable_delta)
            for file_delta in file_deltas
            for callable_delta in file_delta.callables
            if callable_delta.delta != 0
        ],
        key=_hotspot_sort_key,
    )
    if not hotspot_rows:
        return ["No complexity hotspots found."]

    lines = ["Hotspots:"]
    shown_rows = hotspot_rows[:HOTSPOT_LIMIT]
    display_paths = _shortest_unique_suffixes([file_delta.file.path for file_delta, _ in shown_rows])
    for index, (file_delta, callable_delta) in enumerate(shown_rows):
        callable_ = callable_delta.after_callable or callable_delta.before_callable
        lines.append(
            f"  {display_paths[index]}:{callable_.start_line} "
            f"{_format_hotspot_callable_signature(callable_, display_paths[index])} {callable_.kind} "
            f"{callable_delta.before_score} -> {callable_delta.after_score} "
            f"(delta {_format_signed(callable_delta.delta)})"
        )
        contribution = _top_changed_line_contribution(callable_delta, file_delta.file)
        if contribution is not None:
            lines.append(
                f"    top rule: {contribution.rule_id} line {contribution.line} "
                f"+{contribution.points}"
            )

    if len(hotspot_rows) > HOTSPOT_LIMIT:
        lines.append(
            f"Showing {HOTSPOT_LIMIT} of {len(hotspot_rows)} hotspots. "
            "Use --details for the full list."
        )
    return lines


def _shortest_unique_suffixes(paths: list[str]) -> list[str]:
    distinct_split_paths = [path.split("/") for path in dict.fromkeys(paths)]
    return [
        _shortest_unique_suffix(path.split("/"), distinct_split_paths)
        for path in paths
    ]


def _shortest_unique_suffix(path: list[str], all_paths: list[list[str]]) -> str:
    for suffix_length in range(1, len(path) + 1):
        suffix = path[-suffix_length:]
        if sum(other[-suffix_length:] == suffix for other in all_paths) == 1:
            return "/".join(suffix)
    return "/".join(path)


def _format_hotspot_callable_signature(callable_: "CallableSymbol", display_path: str) -> str:
    filename = display_path.rsplit("/", 1)[-1]
    filename_stem = filename.removesuffix(".java")
    if callable_.namespace_path == [filename_stem]:
        return f"{callable_.name}/{callable_.parameter_count}"
    return _format_callable_signature(callable_)


def _hotspot_sort_key(row: tuple[Any, CallableComplexityDelta]) -> tuple[int, str, int, str]:
    file_delta, callable_delta = row
    callable_ = callable_delta.after_callable or callable_delta.before_callable
    return (
        -abs(callable_delta.delta),
        file_delta.file.path,
        callable_.start_line,
        _format_callable_signature(callable_),
    )


def _top_changed_line_contribution(callable_delta: CallableComplexityDelta, file: Any) -> Any | None:
    contributions = _changed_line_contributions(callable_delta, file)
    if not contributions:
        return None
    return min(contributions, key=lambda contribution: (-contribution.points, contribution.line, contribution.rule_id))


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


def _format_symbol_groups(file: Any) -> list[str]:
    lines = []
    if file.before_parse_error:
        lines.append("  before parse error")
    if file.after_parse_error:
        lines.append("  after parse error")

    if file.modified:
        lines.append("  modified:")
        for before_callable, after_callable in file.modified:
            lines.extend(
                [
                    f"    {_format_callable_signature(after_callable)} {after_callable.kind}",
                    f"      before lines {before_callable.start_line}-{before_callable.end_line}",
                    f"      after  lines {after_callable.start_line}-{after_callable.end_line}",
                ]
            )

    if file.added:
        lines.append("  added:")
        lines.extend(f"    {_format_callable(callable_)}" for callable_ in file.added)

    if file.removed:
        lines.append("  removed:")
        lines.extend(f"    {_format_callable(callable_)}" for callable_ in file.removed)

    if not lines:
        lines.append("  no changed callables")

    return lines


def _format_unmapped_lines(
    before_outside: list[LineRange], after_outside: list[LineRange]
) -> list[str]:
    lines = []
    if before_outside or after_outside:
        lines.append("  changed lines not mapped to callables:")
    if before_outside:
        lines.append(f"    before {_format_ranges(before_outside)}")
    if after_outside:
        lines.append(f"    after {_format_ranges(after_outside)}")
    return lines


def _format_complexity_groups(callables: list[Any]) -> list[str]:
    lines = []
    for label in ("modified", "added", "removed"):
        group = [callable_ for callable_ in callables if callable_.status == label]
        if group:
            lines.append(f"  {label}:")
            for callable_ in group:
                lines.extend(_format_complexity_callable(callable_))
    if not lines:
        lines.append("  no changed callables")
    return lines


def _format_complexity_callable(callable_: Any) -> list[str]:
    lines = [
        f"    {_format_callable_signature(callable_.callable)} "
        f"{callable_.callable.kind} complexity {callable_.result.score}"
    ]
    lines.extend(
        f"      {contribution.rule_id} line {contribution.line} +{contribution.points}"
        for contribution in callable_.result.contributions
    )
    return lines


def _complexity_payload(callable_: Any) -> dict[str, Any]:
    return {
        "status": callable_.status,
        **_callable_payload(callable_.callable),
        "score": callable_.result.score,
        "contributions": [
            {
                "rule_id": contribution.rule_id,
                "line": contribution.line,
                "points": contribution.points,
                "message": contribution.message,
            }
            for contribution in callable_.result.contributions
        ],
    }


def _format_callable_signature(callable_: "CallableSymbol") -> str:
    namespace_prefix = ".".join(callable_.namespace_path)
    if namespace_prefix:
        return f"{namespace_prefix}#{callable_.name}/{callable_.parameter_count}"
    return f"{callable_.name}/{callable_.parameter_count}"


def _format_callable(callable_: "CallableSymbol") -> str:
    return (
        f"{_format_callable_signature(callable_)} {callable_.kind} "
        f"lines {callable_.start_line}-{callable_.end_line}"
    )


def _symbol_side_payload(
    *, present: bool, parse_error: bool, callables: list["CallableSymbol"], outside_ranges: list[LineRange]
) -> dict[str, Any]:
    return {
        "present": present,
        "parse_error": parse_error,
        "callables": [_callable_payload(callable_) for callable_ in callables],
        "outside_ranges": [
            {"start": range_.start, "end": range_.end}
            for range_ in outside_ranges
        ],
    }


def _callable_payload(callable_: "CallableSymbol") -> dict[str, Any]:
    return {
        "kind": callable_.kind,
        "name": callable_.name,
        "namespace_path": callable_.namespace_path,
        "parameter_count": callable_.parameter_count,
        "start_line": callable_.start_line,
        "end_line": callable_.end_line,
    }


def _format_ranges(ranges: list[LineRange]) -> str:
    return ", ".join(
        f"line {range_.start}" if range_.start == range_.end else f"lines {range_.start}-{range_.end}"
        for range_ in ranges
    )
