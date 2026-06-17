from __future__ import annotations

from pathlib import Path
from typing import Any
from dataclasses import replace

from diffcog.git import discover_changed_files, ensure_git_repo, load_source_pairs
from diffcog.languages.base import LanguageDefinition
from diffcog.languages.java import JAVA_LANGUAGE
from diffcog.languages.registry import LanguageSpec
from diffcog.models import (
    AnalysisResult,
    CallableComplexityDelta,
    Comparison,
    FileComplexityDelta,
    PathFilter,
    SourcePair,
)
from diffcog.selection import changed_callables, classify_callables, unmapped_ranges


def analyze(
    comparison: Comparison,
    cwd: Path | None = None,
    ruleset: Any | None = None,
    path_filter: PathFilter | None = None,
    language: LanguageDefinition = JAVA_LANGUAGE,
) -> AnalysisResult:
    active_ruleset = ruleset or language.default_ruleset
    ensure_git_repo(cwd)
    files = [
        replace(file, language_id=language.id)
        for file in discover_changed_files(comparison, language.file_extensions, cwd, path_filter)
    ]
    source_pairs = load_source_pairs(comparison, files, cwd)
    file_deltas = [
        _analyze_source_pair(source_pair, language, active_ruleset) for source_pair in source_pairs
    ]
    new_complexity = sum(
        max(callable_delta.delta, 0)
        for file_delta in file_deltas
        for callable_delta in file_delta.callables
    )
    removed_complexity = sum(
        max(-callable_delta.delta, 0)
        for file_delta in file_deltas
        for callable_delta in file_delta.callables
    )
    return AnalysisResult(
        comparison=comparison,
        files=files,
        source_pairs=source_pairs,
        ruleset_id=active_ruleset.id,
        rule_set_ids=(active_ruleset.id,),
        file_deltas=file_deltas,
        new_complexity=new_complexity,
        removed_complexity=removed_complexity,
        net_delta=new_complexity - removed_complexity,
    )


def analyze_languages(
    comparison: Comparison,
    language_specs: tuple[LanguageSpec, ...],
    cwd: Path | None = None,
    path_filter: PathFilter | None = None,
) -> AnalysisResult:
    results = [
        analyze(
            comparison,
            cwd,
            ruleset=spec.language.default_ruleset,
            path_filter=path_filter,
            language=spec.language,
        )
        for spec in language_specs
    ]
    rule_set_ids = tuple(result.ruleset_id for result in results)
    return AnalysisResult(
        comparison=comparison,
        files=[file for result in results for file in result.files],
        source_pairs=[source_pair for result in results for source_pair in result.source_pairs],
        ruleset_id="auto",
        rule_set_ids=rule_set_ids,
        file_deltas=[file_delta for result in results for file_delta in result.file_deltas],
        new_complexity=sum(result.new_complexity for result in results),
        removed_complexity=sum(result.removed_complexity for result in results),
        net_delta=sum(result.net_delta for result in results),
    )


def _analyze_source_pair(
    source_pair: SourcePair, language: LanguageDefinition, ruleset: Any
) -> FileComplexityDelta:
    before = language.parse_snapshot(source_pair.before)
    after = language.parse_snapshot(source_pair.after)
    before_semantics = language.resolve_semantics(before.callables)
    after_semantics = language.resolve_semantics(after.callables)
    before_callables = changed_callables(before.callables, source_pair.file.old_ranges)
    after_callables = changed_callables(after.callables, source_pair.file.new_ranges)
    modified, added, removed = classify_callables(before_callables, after_callables)

    callable_deltas = []
    for before_callable, after_callable in modified:
        before_result = language.score_callable(before_callable, ruleset, before_semantics)
        after_result = language.score_callable(after_callable, ruleset, after_semantics)
        callable_deltas.append(
            CallableComplexityDelta(
                status="modified",
                before_callable=before_callable,
                after_callable=after_callable,
                before_result=before_result,
                after_result=after_result,
                before_score=before_result.score,
                after_score=after_result.score,
                delta=after_result.score - before_result.score,
            )
        )

    for after_callable in added:
        after_result = language.score_callable(after_callable, ruleset, after_semantics)
        callable_deltas.append(
            CallableComplexityDelta(
                status="added",
                before_callable=None,
                after_callable=after_callable,
                before_result=None,
                after_result=after_result,
                before_score=0,
                after_score=after_result.score,
                delta=after_result.score,
            )
        )

    for before_callable in removed:
        before_result = language.score_callable(before_callable, ruleset, before_semantics)
        callable_deltas.append(
            CallableComplexityDelta(
                status="removed",
                before_callable=before_callable,
                after_callable=None,
                before_result=before_result,
                after_result=None,
                before_score=before_result.score,
                after_score=0,
                delta=-before_result.score,
            )
        )

    return FileComplexityDelta(
        file=source_pair.file,
        callables=callable_deltas,
        unmapped_before_ranges=unmapped_ranges(source_pair.file.old_ranges, before.callables),
        unmapped_after_ranges=unmapped_ranges(source_pair.file.new_ranges, after.callables),
    )
