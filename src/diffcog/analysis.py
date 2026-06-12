from __future__ import annotations

from pathlib import Path

from diffcog.git import discover_changed_java_files, ensure_git_repo, load_source_pairs
from diffcog.models import AnalysisResult, Comparison


def analyze(comparison: Comparison, cwd: Path | None = None) -> AnalysisResult:
    ensure_git_repo(cwd)
    files = discover_changed_java_files(comparison, cwd)
    source_pairs = load_source_pairs(comparison, files, cwd)
    return AnalysisResult(
        comparison=comparison,
        files=files,
        source_pairs=source_pairs,
    )
