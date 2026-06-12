from __future__ import annotations

import subprocess
from pathlib import Path

from diffcog.analysis import analyze
from diffcog.cli import resolve_comparison
from diffcog.report import format_symbol_text


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
    write(repo, "README.txt", "hello\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def test_ref_to_ref_detects_modified_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    git(tmp_path, "tag", "base")
    write(tmp_path, "src/Foo.java", "class Foo { void a() {} }\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "modify java")

    result = analyze(resolve_comparison(["base", "HEAD"], staged=False, unstaged=False), tmp_path)

    assert [file.path for file in result.files] == ["src/Foo.java"]
    assert result.source_pairs[0].before == "class Foo {}\n"
    assert result.source_pairs[0].after == "class Foo { void a() {} }\n"


def test_ref_to_worktree_detects_tracked_java_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() {} }\n")

    result = analyze(resolve_comparison(["HEAD"], staged=False, unstaged=False), tmp_path)

    assert [file.status for file in result.files] == ["M"]
    assert result.source_pairs[0].after == "class Foo { void a() {} }\n"


def test_default_mode_is_head_to_worktree(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() {} }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.comparison.before.label == "HEAD"
    assert result.comparison.after.label == "working tree"
    assert [file.path for file in result.files] == ["src/Foo.java"]


def test_staged_detects_staged_java_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void staged() {} }\n")
    git(tmp_path, "add", "src/Foo.java")

    result = analyze(resolve_comparison([], staged=True, unstaged=False), tmp_path)

    assert result.comparison.mode == "ref_to_index"
    assert [file.path for file in result.files] == ["src/Foo.java"]
    assert result.source_pairs[0].after == "class Foo { void staged() {} }\n"


def test_unstaged_detects_unstaged_java_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void staged() {} }\n")
    git(tmp_path, "add", "src/Foo.java")
    write(tmp_path, "src/Foo.java", "class Foo { void staged() {} void unstaged() {} }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=True), tmp_path)

    assert result.comparison.mode == "index_to_worktree"
    assert [file.path for file in result.files] == ["src/Foo.java"]
    assert result.source_pairs[0].before == "class Foo { void staged() {} }\n"
    assert result.source_pairs[0].after == "class Foo { void staged() {} void unstaged() {} }\n"


def test_non_java_changes_are_ignored(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "README.txt", "changed\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.files == []


def test_untracked_java_files_are_excluded(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Untracked.java", "class Untracked {}\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.files == []


def test_two_explicit_refs_ignore_dirty_worktree(tmp_path: Path) -> None:
    init_repo(tmp_path)
    git(tmp_path, "tag", "base")
    write(tmp_path, "src/Foo.java", "class Foo { void committed() {} }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "committed")
    write(tmp_path, "src/Foo.java", "class Foo { void dirty() {} }\n")

    result = analyze(resolve_comparison(["base", "HEAD"], staged=False, unstaged=False), tmp_path)

    assert result.source_pairs[0].before == "class Foo {}\n"
    assert result.source_pairs[0].after == "class Foo { void committed() {} }\n"


def test_added_tracked_java_file_has_missing_before_snapshot(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/New.java", "class New {}\n")
    git(tmp_path, "add", "src/New.java")

    result = analyze(resolve_comparison([], staged=True, unstaged=False), tmp_path)

    assert [file.status for file in result.files] == ["A"]
    assert result.source_pairs[0].before is None
    assert result.source_pairs[0].after == "class New {}\n"


def test_deleted_tracked_java_file_has_missing_after_snapshot(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "src/Foo.java").unlink()

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert [file.status for file in result.files] == ["D"]
    assert result.source_pairs[0].before == "class Foo {}\n"
    assert result.source_pairs[0].after is None


def test_show_symbols_report_for_modified_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() {} }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    output = format_symbol_text(result)

    assert "Symbol dump" in output
    assert "Foo#a/0 method lines 1-1" in output


def test_show_symbols_report_for_added_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/New.java", "class New { void run() {} }\n")
    git(tmp_path, "add", "src/New.java")

    result = analyze(resolve_comparison([], staged=True, unstaged=False), tmp_path)
    output = format_symbol_text(result)

    assert "A src/New.java" in output
    assert "  added:" in output
    assert "New#run/0 method lines 1-1" in output


def test_show_symbols_report_for_deleted_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() {} }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "add method")
    (tmp_path / "src/Foo.java").unlink()

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    output = format_symbol_text(result)

    assert "D src/Foo.java" in output
    assert "  removed:" in output
    assert "Foo#a/0 method lines 1-1" in output
