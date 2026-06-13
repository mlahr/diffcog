from __future__ import annotations

import re
import subprocess
from pathlib import Path

from diffcog.models import ChangedFile, Comparison, Endpoint, EndpointKind, LineRange, PathFilter, SourcePair


HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


class GitError(RuntimeError):
    pass


def run_git(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
        raise GitError(message)
    return proc.stdout


def ensure_git_repo(cwd: Path | None = None) -> None:
    run_git(["rev-parse", "--show-toplevel"], cwd=cwd)


def discover_changed_java_files(
    comparison: Comparison, cwd: Path | None = None, path_filter: PathFilter | None = None
) -> list[ChangedFile]:
    active_filter = path_filter or PathFilter()
    status_output = run_git(_diff_name_status_args(comparison, active_filter), cwd=cwd)
    range_output = run_git(_diff_ranges_args(comparison, active_filter), cwd=cwd)
    ranges_by_path = _parse_diff_ranges(range_output)
    files = []
    for line in status_output.splitlines():
        if not line.strip():
            continue
        file = _parse_name_status_line(line)
        if not _is_java_path(file.path):
            continue
        ranges = ranges_by_path.get(file.path, ([], []))
        files.append(
            ChangedFile(
                status=file.status,
                old_path=file.old_path,
                path=file.path,
                old_ranges=ranges[0],
                new_ranges=ranges[1],
            )
        )
    return files


def load_source_pairs(
    comparison: Comparison, files: list[ChangedFile], cwd: Path | None = None
) -> list[SourcePair]:
    return [
        SourcePair(
            file=file,
            before=_load_endpoint_source(comparison.before, file.old_path, cwd),
            after=_load_endpoint_source(comparison.after, file.path, cwd),
        )
        for file in files
    ]


def _diff_name_status_args(comparison: Comparison, path_filter: PathFilter | None = None) -> list[str]:
    before = comparison.before
    after = comparison.after
    pathspecs = _java_pathspecs(path_filter or PathFilter())

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.REF:
        return ["diff", "--name-status", "--find-renames", before.label, after.label, "--", *pathspecs]

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.WORKTREE:
        return ["diff", "--name-status", "--find-renames", before.label, "--", *pathspecs]

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.INDEX:
        return [
            "diff",
            "--cached",
            "--name-status",
            "--find-renames",
            before.label,
            "--",
            *pathspecs,
        ]

    if before.kind == EndpointKind.INDEX and after.kind == EndpointKind.WORKTREE:
        return ["diff", "--name-status", "--find-renames", "--", *pathspecs]

    raise GitError(f"unsupported comparison: {before.label} -> {after.label}")


def _diff_ranges_args(comparison: Comparison, path_filter: PathFilter | None = None) -> list[str]:
    args = _diff_name_status_args(comparison, path_filter)
    range_args = [arg for arg in args if arg != "--name-status"]
    pathspec_index = range_args.index("--")
    range_args.insert(pathspec_index, "--unified=0")
    return range_args


def _java_pathspecs(path_filter: PathFilter) -> list[str]:
    includes = list(path_filter.includes) or ["*.java"]
    excludes = [f":(exclude){pathspec}" for pathspec in path_filter.excludes]
    return [*includes, *excludes]


def _is_java_path(path: str) -> bool:
    return path.endswith(".java")


def _parse_name_status_line(line: str) -> ChangedFile:
    parts = line.split("\t")
    status = parts[0]
    status_kind = status[0]

    if status_kind in {"R", "C"}:
        if len(parts) != 3:
            raise GitError(f"unexpected rename/copy status line: {line}")
        return ChangedFile(status=status, old_path=parts[1], path=parts[2], old_ranges=[], new_ranges=[])

    if len(parts) != 2:
        raise GitError(f"unexpected status line: {line}")
    return ChangedFile(status=status, old_path=parts[1], path=parts[1], old_ranges=[], new_ranges=[])


def _parse_diff_ranges(output: str) -> dict[str, tuple[list[LineRange], list[LineRange]]]:
    ranges_by_path: dict[str, tuple[list[LineRange], list[LineRange]]] = {}
    current_path: str | None = None
    old_path: str | None = None

    for line in output.splitlines():
        if line.startswith("--- "):
            old_path = _parse_old_diff_path(line)
            continue

        if line.startswith("+++ "):
            current_path = _parse_new_diff_path(line) or old_path
            if current_path is not None:
                ranges_by_path.setdefault(current_path, ([], []))
            continue

        if current_path is None:
            continue

        match = HUNK_RE.match(line)
        if match is None:
            continue

        old_range = _line_range(match.group("old_start"), match.group("old_count"))
        new_range = _line_range(match.group("new_start"), match.group("new_count"))
        old_ranges, new_ranges = ranges_by_path.setdefault(current_path, ([], []))
        if old_range is not None:
            old_ranges.append(old_range)
        if new_range is not None:
            new_ranges.append(new_range)

    return ranges_by_path


def _parse_new_diff_path(line: str) -> str | None:
    path = line[4:]
    if path == "/dev/null":
        return None
    if path.startswith("b/"):
        return path[2:]
    return path


def _parse_old_diff_path(line: str) -> str | None:
    path = line[4:]
    if path == "/dev/null":
        return None
    if path.startswith("a/"):
        return path[2:]
    return path


def _line_range(start: str, count: str | None) -> LineRange | None:
    parsed_start = int(start)
    parsed_count = 1 if count is None else int(count)
    if parsed_count == 0:
        return None
    return LineRange(start=parsed_start, end=parsed_start + parsed_count - 1)


def _load_endpoint_source(endpoint: Endpoint, path: str, cwd: Path | None) -> str | None:
    if endpoint.kind == EndpointKind.WORKTREE:
        file_path = (cwd or Path.cwd()) / path
        try:
            return file_path.read_text()
        except FileNotFoundError:
            return None

    if endpoint.kind == EndpointKind.INDEX:
        return _git_show_optional(f":{path}", cwd)

    return _git_show_optional(f"{endpoint.label}:{path}", cwd)


def _git_show_optional(spec: str, cwd: Path | None) -> str | None:
    proc = subprocess.run(
        ["git", "show", spec],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout
