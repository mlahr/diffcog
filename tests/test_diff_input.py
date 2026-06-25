from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from diffcog.diff_input import source_pairs_from_diff
from diffcog.errors import DiffcogError


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return proc.stdout


def write(repo: Path, path: str, content: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def init_repo(repo: Path) -> None:
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    write(repo, "src/Foo.java", "class Foo {}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def test_source_pairs_from_diff_loads_modified_file_blobs(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() {} }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "modify")

    diff_text = git(tmp_path, "diff", "--unified=0", "HEAD~1..HEAD")

    source_pairs = source_pairs_from_diff(diff_text, (".java",), tmp_path)

    assert len(source_pairs) == 1
    assert source_pairs[0].file.status == "M"
    assert source_pairs[0].file.old_path == "src/Foo.java"
    assert source_pairs[0].file.path == "src/Foo.java"
    assert source_pairs[0].before == "class Foo {}\n"
    assert source_pairs[0].after == "class Foo { void run() {} }\n"
    assert source_pairs[0].file.old_ranges
    assert source_pairs[0].file.new_ranges


def test_source_pairs_from_diff_loads_added_and_deleted_file_blobs(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/New.java", "class New {}\n")
    (tmp_path / "src/Foo.java").unlink()
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "add and delete")

    diff_text = git(tmp_path, "diff", "--unified=0", "HEAD~1..HEAD")

    source_pairs = source_pairs_from_diff(diff_text, (".java",), tmp_path)

    by_path = {source_pair.file.path: source_pair for source_pair in source_pairs}
    assert by_path["src/New.java"].file.status == "A"
    assert by_path["src/New.java"].before is None
    assert by_path["src/New.java"].after == "class New {}\n"
    assert by_path["src/Foo.java"].file.status == "D"
    assert by_path["src/Foo.java"].before == "class Foo {}\n"
    assert by_path["src/Foo.java"].after is None


def test_source_pairs_from_diff_preserves_rename_paths(tmp_path: Path) -> None:
    init_repo(tmp_path)
    git(tmp_path, "mv", "src/Foo.java", "src/Renamed.java")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "rename")

    diff_text = git(tmp_path, "diff", "--find-renames", "--unified=0", "HEAD~1..HEAD")

    source_pairs = source_pairs_from_diff(diff_text, (".java",), tmp_path)

    assert len(source_pairs) == 1
    assert source_pairs[0].file.status.startswith("R")
    assert source_pairs[0].file.old_path == "src/Foo.java"
    assert source_pairs[0].file.path == "src/Renamed.java"


def test_source_pairs_from_diff_ignores_unsupported_files_before_validation() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/README.txt b/README.txt",
            "--- a/README.txt",
            "+++ b/README.txt",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            "",
        ]
    )

    assert source_pairs_from_diff(diff_text, (".java",)) == []


def test_source_pairs_from_diff_rejects_supported_patch_without_blob_ids() -> None:
    diff_text = "\n".join(
        [
            "diff --git a/src/Foo.java b/src/Foo.java",
            "--- a/src/Foo.java",
            "+++ b/src/Foo.java",
            "@@ -1 +1 @@",
            "-class Foo {}",
            "+class Foo { void run() {} }",
            "",
        ]
    )

    with pytest.raises(DiffcogError, match="missing a before blob"):
        source_pairs_from_diff(diff_text, (".java",))
