from __future__ import annotations

import subprocess
from pathlib import Path

from diffcog.models import ChangedFile, Comparison, Endpoint, EndpointKind, SourcePair


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


def discover_changed_java_files(comparison: Comparison, cwd: Path | None = None) -> list[ChangedFile]:
    args = _diff_name_status_args(comparison)
    output = run_git(args, cwd=cwd)
    return [_parse_name_status_line(line) for line in output.splitlines() if line.strip()]


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


def _diff_name_status_args(comparison: Comparison) -> list[str]:
    before = comparison.before
    after = comparison.after

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.REF:
        return ["diff", "--name-status", "--find-renames", before.label, after.label, "--", "*.java"]

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.WORKTREE:
        return ["diff", "--name-status", "--find-renames", before.label, "--", "*.java"]

    if before.kind == EndpointKind.REF and after.kind == EndpointKind.INDEX:
        return [
            "diff",
            "--cached",
            "--name-status",
            "--find-renames",
            before.label,
            "--",
            "*.java",
        ]

    if before.kind == EndpointKind.INDEX and after.kind == EndpointKind.WORKTREE:
        return ["diff", "--name-status", "--find-renames", "--", "*.java"]

    raise GitError(f"unsupported comparison: {before.label} -> {after.label}")


def _parse_name_status_line(line: str) -> ChangedFile:
    parts = line.split("\t")
    status = parts[0]
    status_kind = status[0]

    if status_kind in {"R", "C"}:
        if len(parts) != 3:
            raise GitError(f"unexpected rename/copy status line: {line}")
        return ChangedFile(status=status, old_path=parts[1], path=parts[2])

    if len(parts) != 2:
        raise GitError(f"unexpected status line: {line}")
    return ChangedFile(status=status, old_path=parts[1], path=parts[1])


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
