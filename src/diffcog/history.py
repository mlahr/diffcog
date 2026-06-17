from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

from diffcog.git import GitError, ensure_git_repo, run_git
from diffcog.languages.registry import LanguageSpec
from diffcog.models import (
    ChangeCoupling,
    Comparison,
    Endpoint,
    EndpointKind,
    HistoryHotspot,
    HistoryMetricsResult,
    PathFilter,
)


DEFAULT_HISTORY_DAYS = 90
MIN_COUPLED_COMMITS = 2


def analyze_history_metrics(
    comparison: Comparison,
    language_specs: tuple[LanguageSpec, ...],
    *,
    days: int = DEFAULT_HISTORY_DAYS,
    cwd: Path | None = None,
    path_filter: PathFilter | None = None,
) -> HistoryMetricsResult:
    if days <= 0:
        raise ValueError("--history-days must be a positive integer")

    ensure_git_repo(cwd)
    active_filter = path_filter or PathFilter()
    extensions = tuple(
        extension
        for spec in language_specs
        for extension in spec.language.file_extensions
    )
    languages_by_extension = {
        extension: spec.language
        for spec in language_specs
        for extension in spec.language.file_extensions
    }
    history_ref = _history_ref(comparison.after)
    history_files = _mine_history_files(
        history_ref,
        days,
        extensions,
        cwd,
        active_filter,
    )
    current_paths = set(
        _list_endpoint_files(comparison.after, extensions, cwd, active_filter)
    )
    candidate_paths = set(history_files.commit_counts) | current_paths
    current_complexities = {
        path: _score_current_file(
            comparison.after,
            path,
            languages_by_extension[_matching_extension(path, extensions)],
            cwd,
        )
        for path in candidate_paths
        if _matching_extension(path, extensions) is not None
    }

    hotspots = [
        HistoryHotspot(
            path=path,
            language_id=languages_by_extension[_matching_extension(path, extensions)].id,
            commit_count=commit_count,
            changed_lines=history_files.changed_lines[path],
            current_complexity=current_complexities.get(path, 0),
            score=current_complexities.get(path, 0) * commit_count,
        )
        for path, commit_count in history_files.commit_counts.items()
        if _matching_extension(path, extensions) is not None
    ]
    hotspots.sort(key=lambda row: (-row.score, -row.commit_count, row.path))

    return HistoryMetricsResult(
        comparison=comparison,
        history_ref=history_ref,
        days=days,
        language_ids=tuple(spec.language.id for spec in language_specs),
        hotspots=hotspots,
        change_couplings=_change_couplings(history_files),
    )


class _HistoryFiles:
    def __init__(self) -> None:
        self.commit_counts: Counter[str] = Counter()
        self.changed_lines: Counter[str] = Counter()
        self.pair_counts: Counter[tuple[str, str]] = Counter()


def _history_ref(endpoint: Endpoint) -> str:
    if endpoint.kind == EndpointKind.REF:
        return endpoint.label
    return "HEAD"


def _mine_history_files(
    history_ref: str,
    days: int,
    extensions: tuple[str, ...],
    cwd: Path | None,
    path_filter: PathFilter,
) -> _HistoryFiles:
    args = [
        "log",
        f"--since={days} days ago",
        "--pretty=format:%H",
        "--numstat",
        history_ref,
        "--",
        *_language_pathspecs(extensions, path_filter),
    ]
    output = run_git(args, cwd)
    history_files = _HistoryFiles()
    current_commit_paths: set[str] = set()

    for line in output.splitlines():
        if not line:
            _record_commit_paths(history_files, current_commit_paths)
            current_commit_paths = set()
            continue
        if "\t" not in line:
            _record_commit_paths(history_files, current_commit_paths)
            current_commit_paths = set()
            continue

        path, changed_lines = _parse_numstat_line(line)
        if path is None or not path.endswith(extensions):
            continue
        current_commit_paths.add(path)
        history_files.changed_lines[path] += changed_lines

    _record_commit_paths(history_files, current_commit_paths)
    return history_files


def _record_commit_paths(history_files: _HistoryFiles, paths: set[str]) -> None:
    if not paths:
        return
    for path in paths:
        history_files.commit_counts[path] += 1
    for left, right in combinations(sorted(paths), 2):
        history_files.pair_counts[(left, right)] += 1


def _parse_numstat_line(line: str) -> tuple[str | None, int]:
    parts = line.split("\t")
    if len(parts) < 3:
        return None, 0
    added, deleted, raw_path = parts[0], parts[1], "\t".join(parts[2:])
    path = _normalize_numstat_path(raw_path)
    if path is None:
        return None, 0
    return path, _numstat_count(added) + _numstat_count(deleted)


def _normalize_numstat_path(path: str) -> str | None:
    if " => " not in path:
        return path
    if path.startswith("{") and "} => " in path:
        prefix, rest = path[1:].split("} => ", 1)
        return f"{prefix}{rest}"
    return path.rsplit(" => ", 1)[-1]


def _numstat_count(value: str) -> int:
    if value == "-":
        return 0
    return int(value)


def _change_couplings(history_files: _HistoryFiles) -> list[ChangeCoupling]:
    couplings = []
    for (left, right), shared_count in history_files.pair_counts.items():
        if shared_count < MIN_COUPLED_COMMITS:
            continue
        left_count = history_files.commit_counts[left]
        right_count = history_files.commit_counts[right]
        denominator = min(left_count, right_count)
        coupling_percent = round((shared_count / denominator) * 100) if denominator else 0
        couplings.append(
            ChangeCoupling(
                left_path=left,
                right_path=right,
                shared_commit_count=shared_count,
                left_commit_count=left_count,
                right_commit_count=right_count,
                coupling_percent=coupling_percent,
            )
        )
    couplings.sort(
        key=lambda row: (
            -row.shared_commit_count,
            -row.coupling_percent,
            row.left_path,
            row.right_path,
        )
    )
    return couplings


def _list_endpoint_files(
    endpoint: Endpoint,
    extensions: tuple[str, ...],
    cwd: Path | None,
    path_filter: PathFilter,
) -> list[str]:
    pathspecs = _language_pathspecs(extensions, path_filter)
    if endpoint.kind == EndpointKind.REF:
        output = run_git(["ls-tree", "-r", "--name-only", endpoint.label, "--", *pathspecs], cwd)
    elif endpoint.kind == EndpointKind.INDEX:
        output = run_git(["ls-files", "--cached", "--", *pathspecs], cwd)
    elif endpoint.kind == EndpointKind.WORKTREE:
        output = run_git(["ls-files", "--", *pathspecs], cwd)
    else:
        raise GitError(f"unsupported endpoint: {endpoint.label}")
    return [line for line in output.splitlines() if line.endswith(extensions)]


def _score_current_file(
    endpoint: Endpoint,
    path: str,
    language: object,
    cwd: Path | None,
) -> int:
    source = _load_endpoint_source(endpoint, path, cwd)
    snapshot = language.parse_snapshot(source)
    if not snapshot.present or snapshot.parse_error:
        return 0
    semantics = language.resolve_semantics(snapshot.callables)
    return sum(
        language.score_callable(callable_, language.default_ruleset, semantics).score
        for callable_ in snapshot.callables
    )


def _load_endpoint_source(endpoint: Endpoint, path: str, cwd: Path | None) -> str | None:
    if endpoint.kind == EndpointKind.WORKTREE:
        try:
            return ((cwd or Path.cwd()) / path).read_text()
        except FileNotFoundError:
            return None
    if endpoint.kind == EndpointKind.INDEX:
        return _git_show_optional(f":{path}", cwd)
    return _git_show_optional(f"{endpoint.label}:{path}", cwd)


def _git_show_optional(spec: str, cwd: Path | None) -> str | None:
    try:
        return run_git(["show", spec], cwd)
    except GitError:
        return None


def _language_pathspecs(file_extensions: tuple[str, ...], path_filter: PathFilter) -> list[str]:
    includes = list(path_filter.includes) or [f"*{extension}" for extension in file_extensions]
    excludes = [f":(exclude){pathspec}" for pathspec in path_filter.excludes]
    return [*includes, *excludes]


def _matching_extension(path: str, extensions: tuple[str, ...]) -> str | None:
    return next((extension for extension in extensions if path.endswith(extension)), None)
