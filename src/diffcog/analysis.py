from __future__ import annotations

from pathlib import Path

from diffcog.git import discover_changed_java_files, ensure_git_repo, load_source_pairs
from diffcog.languages.java.complexity import DEFAULT_JAVA_RULESET, RuleSet, score_callable
from diffcog.languages.java.parser import parse_snapshot
from diffcog.languages.java.resolver import resolve_semantics
from diffcog.languages.java.selection import changed_callables, classify_callables, unmapped_ranges
from diffcog.models import (
    AnalysisResult,
    CallableComplexityDelta,
    Comparison,
    FileComplexityDelta,
    SourcePair,
)


def analyze(
    comparison: Comparison, cwd: Path | None = None, ruleset: RuleSet | None = None
) -> AnalysisResult:
    active_ruleset = ruleset or DEFAULT_JAVA_RULESET
    ensure_git_repo(cwd)
    files = discover_changed_java_files(comparison, cwd)
    source_pairs = load_source_pairs(comparison, files, cwd)
    file_deltas = [
        _analyze_source_pair(source_pair, active_ruleset) for source_pair in source_pairs
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
        file_deltas=file_deltas,
        new_complexity=new_complexity,
        removed_complexity=removed_complexity,
        net_delta=new_complexity - removed_complexity,
    )


def _analyze_source_pair(source_pair: SourcePair, ruleset: RuleSet) -> FileComplexityDelta:
    before = parse_snapshot(source_pair.before)
    after = parse_snapshot(source_pair.after)
    before_semantics = resolve_semantics(before.callables)
    after_semantics = resolve_semantics(after.callables)
    before_callables = changed_callables(before.callables, source_pair.file.old_ranges)
    after_callables = changed_callables(after.callables, source_pair.file.new_ranges)
    modified, added, removed = classify_callables(before_callables, after_callables)

    callable_deltas = []
    for before_callable, after_callable in modified:
        before_result = score_callable(before_callable, ruleset, before_semantics)
        after_result = score_callable(after_callable, ruleset, after_semantics)
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
        after_result = score_callable(after_callable, ruleset, after_semantics)
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
        before_result = score_callable(before_callable, ruleset, before_semantics)
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
