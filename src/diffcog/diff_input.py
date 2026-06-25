from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from diffcog.errors import DiffcogError
from diffcog.models import ChangedFile, LineRange, SourcePair


HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)
INDEX_RE = re.compile(r"^index (?P<old>[0-9a-f]+)\.\.(?P<new>[0-9a-f]+)(?: .*)?$")


@dataclass
class _DiffFile:
    old_path: str
    path: str
    old_blob: str | None = None
    new_blob: str | None = None
    status: str = "M"
    old_ranges: list[LineRange] | None = None
    new_ranges: list[LineRange] | None = None


def source_pairs_from_diff(
    diff_text: str,
    file_extensions: tuple[str, ...],
    cwd: Path | None = None,
) -> list[SourcePair]:
    files = _parse_diff(diff_text)
    source_pairs: list[SourcePair] = []
    for file in files:
        if not _has_supported_extension(file.path, file_extensions):
            continue
        old_ranges = file.old_ranges or []
        new_ranges = file.new_ranges or []
        is_metadata_only_rename = file.status.startswith("R") and not old_ranges and not new_ranges
        if file.old_blob is None and file.status not in {"A"} and not is_metadata_only_rename:
            raise DiffcogError(f"diff is missing a before blob for {file.old_path}")
        if file.new_blob is None and file.status not in {"D"} and not is_metadata_only_rename:
            raise DiffcogError(f"diff is missing an after blob for {file.path}")
        changed_file = ChangedFile(
            status=file.status,
            old_path=file.old_path,
            path=file.path,
            old_ranges=old_ranges,
            new_ranges=new_ranges,
        )
        source_pairs.append(
            SourcePair(
                file=changed_file,
                before=_load_blob(file.old_blob, cwd),
                after=_load_blob(file.new_blob, cwd),
            )
        )
    return source_pairs


def _parse_diff(diff_text: str) -> list[_DiffFile]:
    files: list[_DiffFile] = []
    current: _DiffFile | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current = _parse_diff_git_line(line)
            files.append(current)
            continue

        if current is None:
            continue

        if line.startswith("index "):
            match = INDEX_RE.match(line)
            if match is not None:
                current.old_blob = _blob_or_none(match.group("old"))
                current.new_blob = _blob_or_none(match.group("new"))
            continue

        if line.startswith("new file mode "):
            current.status = "A"
            current.old_blob = None
            continue

        if line.startswith("deleted file mode "):
            current.status = "D"
            current.new_blob = None
            continue

        if line.startswith("similarity index "):
            current.status = f"R{line.removeprefix('similarity index ').removesuffix('%')}"
            continue

        if line.startswith("rename from "):
            current.old_path = line.removeprefix("rename from ")
            continue

        if line.startswith("rename to "):
            current.path = line.removeprefix("rename to ")
            continue

        match = HUNK_RE.match(line)
        if match is None:
            continue

        if current.old_ranges is None:
            current.old_ranges = []
        if current.new_ranges is None:
            current.new_ranges = []
        old_range = _line_range(match.group("old_start"), match.group("old_count"))
        new_range = _line_range(match.group("new_start"), match.group("new_count"))
        if old_range is not None:
            current.old_ranges.append(old_range)
        if new_range is not None:
            current.new_ranges.append(new_range)

    return files


def _parse_diff_git_line(line: str) -> _DiffFile:
    paths = line.removeprefix("diff --git ").split(" ")
    if len(paths) != 2:
        raise DiffcogError(f"unsupported diff path header: {line}")
    old_path = _strip_prefix(paths[0], "a/")
    path = _strip_prefix(paths[1], "b/")
    return _DiffFile(old_path=old_path, path=path)


def _strip_prefix(value: str, prefix: str) -> str:
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def _blob_or_none(blob: str) -> str | None:
    if set(blob) == {"0"}:
        return None
    return blob


def _line_range(start: str, count: str | None) -> LineRange | None:
    parsed_start = int(start)
    parsed_count = 1 if count is None else int(count)
    if parsed_count == 0:
        return None
    return LineRange(start=parsed_start, end=parsed_start + parsed_count - 1)


def _has_supported_extension(path: str, file_extensions: tuple[str, ...]) -> bool:
    return path.endswith(file_extensions)


def _load_blob(blob: str | None, cwd: Path | None) -> str | None:
    if blob is None:
        return None
    proc = subprocess.run(
        ["git", "show", blob],
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        message = proc.stderr.strip() or proc.stdout.strip() or "git show failed"
        raise DiffcogError(f"cannot load blob {blob}: {message}")
    return proc.stdout
