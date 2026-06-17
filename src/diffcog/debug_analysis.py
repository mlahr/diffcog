from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from diffcog.languages.base import LanguageDefinition
from diffcog.languages.java import JAVA_LANGUAGE
from diffcog.languages.registry import LanguageSpec
from diffcog.models import (
    AnalysisResult,
    CallableSymbol,
    ChangedFile,
    Comparison,
    ComplexityResult,
    LineRange,
)
from diffcog.selection import changed_callables, classify_callables, unmapped_ranges


@dataclass(frozen=True)
class SymbolFile:
    file: ChangedFile
    modified: list[tuple[CallableSymbol, CallableSymbol]]
    added: list[CallableSymbol]
    removed: list[CallableSymbol]
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
    rule_set_ids: tuple[str, ...]
    files: list[SymbolFile]


@dataclass(frozen=True)
class ComplexityCallable:
    status: str
    callable: CallableSymbol
    result: ComplexityResult


@dataclass(frozen=True)
class ComplexityFile:
    file: ChangedFile
    callables: list[ComplexityCallable]


@dataclass(frozen=True)
class ComplexityDebugResult:
    comparison: Comparison
    ruleset_id: str
    rule_set_ids: tuple[str, ...]
    files: list[ComplexityFile]


def build_symbol_debug(
    result: AnalysisResult, language: LanguageDefinition = JAVA_LANGUAGE
) -> SymbolDebugResult:
    files = []
    for pair in result.source_pairs:
        before = language.parse_snapshot(pair.before)
        after = language.parse_snapshot(pair.after)
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
        rule_set_ids=result.rule_set_ids,
        files=files,
    )


def build_symbol_debug_for_languages(
    result: AnalysisResult, language_specs: tuple[LanguageSpec, ...]
) -> SymbolDebugResult:
    results = [
        build_symbol_debug(_filter_result_for_language(result, spec), spec.language)
        for spec in language_specs
    ]
    return SymbolDebugResult(
        comparison=result.comparison,
        ruleset_id=result.ruleset_id,
        rule_set_ids=result.rule_set_ids,
        files=[file for debug_result in results for file in debug_result.files],
    )


def build_complexity_debug(result: AnalysisResult, ruleset: object | None = None) -> ComplexityDebugResult:
    return build_language_complexity_debug(result, JAVA_LANGUAGE, ruleset)


def build_language_complexity_debug(
    result: AnalysisResult, language: LanguageDefinition, ruleset: Any | None = None
) -> ComplexityDebugResult:
    active_ruleset = ruleset or language.default_ruleset
    files = []
    for pair in result.source_pairs:
        before = language.parse_snapshot(pair.before)
        after = language.parse_snapshot(pair.after)
        before_semantics = language.resolve_semantics(before.callables)
        after_semantics = language.resolve_semantics(after.callables)
        before_callables = changed_callables(before.callables, pair.file.old_ranges)
        after_callables = changed_callables(after.callables, pair.file.new_ranges)
        modified, added, removed = classify_callables(before_callables, after_callables)
        callables = []
        for _, after_callable in modified:
            callables.append(
                ComplexityCallable(
                    status="modified",
                    callable=after_callable,
                    result=language.score_callable(after_callable, active_ruleset, after_semantics),
                )
            )
        for after_callable in added:
            callables.append(
                ComplexityCallable(
                    status="added",
                    callable=after_callable,
                    result=language.score_callable(after_callable, active_ruleset, after_semantics),
                )
            )
        for before_callable in removed:
            callables.append(
                ComplexityCallable(
                    status="removed",
                    callable=before_callable,
                    result=language.score_callable(before_callable, active_ruleset, before_semantics),
                )
            )
        files.append(ComplexityFile(file=pair.file, callables=callables))
    ruleset_id = getattr(active_ruleset, "id", result.ruleset_id)
    return ComplexityDebugResult(
        comparison=result.comparison,
        ruleset_id=ruleset_id,
        rule_set_ids=(ruleset_id,),
        files=files,
    )


def build_complexity_debug_for_languages(
    result: AnalysisResult, language_specs: tuple[LanguageSpec, ...]
) -> ComplexityDebugResult:
    results = [
        build_language_complexity_debug(_filter_result_for_language(result, spec), spec.language)
        for spec in language_specs
    ]
    return ComplexityDebugResult(
        comparison=result.comparison,
        ruleset_id=result.ruleset_id,
        rule_set_ids=result.rule_set_ids,
        files=[file for debug_result in results for file in debug_result.files],
    )


def _filter_result_for_language(result: AnalysisResult, spec: LanguageSpec) -> AnalysisResult:
    files = [
        file
        for file in result.files
        if file.path.endswith(spec.language.file_extensions)
    ]
    source_pairs = [
        source_pair
        for source_pair in result.source_pairs
        if source_pair.file.path.endswith(spec.language.file_extensions)
    ]
    file_deltas = [
        file_delta
        for file_delta in result.file_deltas
        if file_delta.file.path.endswith(spec.language.file_extensions)
    ]
    return AnalysisResult(
        comparison=result.comparison,
        files=files,
        source_pairs=source_pairs,
        ruleset_id=spec.language.default_ruleset.id,
        rule_set_ids=(spec.language.default_ruleset.id,),
        file_deltas=file_deltas,
        new_complexity=sum(
            max(callable_delta.delta, 0)
            for file_delta in file_deltas
            for callable_delta in file_delta.callables
        ),
        removed_complexity=sum(
            max(-callable_delta.delta, 0)
            for file_delta in file_deltas
            for callable_delta in file_delta.callables
        ),
        net_delta=sum(
            callable_delta.delta
            for file_delta in file_deltas
            for callable_delta in file_delta.callables
        ),
    )
