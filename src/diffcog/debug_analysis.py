from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from diffcog.languages.java.selection import changed_callables, classify_callables, unmapped_ranges
from diffcog.errors import DiffcogError
from diffcog.models import AnalysisResult, ChangedFile, Comparison, LineRange

if TYPE_CHECKING:
    from diffcog.languages.java.complexity import ComplexityResult
    from diffcog.languages.java.models import JavaCallable


@dataclass(frozen=True)
class SymbolFile:
    file: ChangedFile
    modified: list[tuple[JavaCallable, JavaCallable]]
    added: list[JavaCallable]
    removed: list[JavaCallable]
    before_present: bool
    after_present: bool
    before_parse_error: bool
    after_parse_error: bool
    unmapped_before_ranges: list[LineRange]
    unmapped_after_ranges: list[LineRange]


@dataclass(frozen=True)
class SymbolDebugResult:
    comparison: Comparison
    ruleset_id: str
    files: list[SymbolFile]


@dataclass(frozen=True)
class ComplexityCallable:
    status: str
    callable: JavaCallable
    result: ComplexityResult


@dataclass(frozen=True)
class ComplexityFile:
    file: ChangedFile
    callables: list[ComplexityCallable]


@dataclass(frozen=True)
class ComplexityDebugResult:
    comparison: Comparison
    ruleset_id: str
    files: list[ComplexityFile]


def build_symbol_debug(result: AnalysisResult) -> SymbolDebugResult:
    parse_snapshot = _load_java_parser()
    files = []
    for pair in result.source_pairs:
        before = parse_snapshot(pair.before)
        after = parse_snapshot(pair.after)
        before_callables = changed_callables(before.callables, pair.file.old_ranges)
        after_callables = changed_callables(after.callables, pair.file.new_ranges)
        modified, added, removed = classify_callables(before_callables, after_callables)
        files.append(
            SymbolFile(
                file=pair.file,
                modified=modified,
                added=added,
                removed=removed,
                before_present=before.present,
                after_present=after.present,
                before_parse_error=before.present and before.parse_error,
                after_parse_error=after.present and after.parse_error,
                unmapped_before_ranges=unmapped_ranges(pair.file.old_ranges, before.callables),
                unmapped_after_ranges=unmapped_ranges(pair.file.new_ranges, after.callables),
            )
        )
    return SymbolDebugResult(
        comparison=result.comparison,
        ruleset_id=result.ruleset_id,
        files=files,
    )


def build_complexity_debug(result: AnalysisResult, ruleset: object | None = None) -> ComplexityDebugResult:
    score_callable = _load_java_scorer()
    active_ruleset = ruleset
    files = []
    for symbol_file in build_symbol_debug(result).files:
        callables = []
        for _, after_callable in symbol_file.modified:
            callables.append(
                ComplexityCallable(
                    status="modified",
                    callable=after_callable,
                    result=score_callable(after_callable, active_ruleset),
                )
            )
        for after_callable in symbol_file.added:
            callables.append(
                ComplexityCallable(
                    status="added",
                    callable=after_callable,
                    result=score_callable(after_callable, active_ruleset),
                )
            )
        for before_callable in symbol_file.removed:
            callables.append(
                ComplexityCallable(
                    status="removed",
                    callable=before_callable,
                    result=score_callable(before_callable, active_ruleset),
                )
            )
        files.append(ComplexityFile(file=symbol_file.file, callables=callables))
    ruleset_id = getattr(active_ruleset, "id", result.ruleset_id)
    return ComplexityDebugResult(comparison=result.comparison, ruleset_id=ruleset_id, files=files)


def _load_java_parser():
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


def _load_java_scorer():
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
