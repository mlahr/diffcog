from __future__ import annotations

import subprocess
import json
from pathlib import Path

from diffcog.analysis import analyze
from diffcog.cli import resolve_comparison
from diffcog.debug_analysis import build_complexity_debug, build_symbol_debug
from diffcog.report import format_json
from diffcog.report import format_text
from diffcog.report import format_complexity_text
from diffcog.report import format_symbol_text
from diffcog.models import Thresholds


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
    output = format_symbol_text(build_symbol_debug(result))

    assert "Symbol dump" in output
    assert "Foo#a/0 method lines 1-1" in output


def test_show_symbols_report_for_added_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/New.java", "class New { void run() {} }\n")
    git(tmp_path, "add", "src/New.java")

    result = analyze(resolve_comparison([], staged=True, unstaged=False), tmp_path)
    output = format_symbol_text(build_symbol_debug(result))

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
    output = format_symbol_text(build_symbol_debug(result))

    assert "D src/Foo.java" in output
    assert "  removed:" in output
    assert "Foo#a/0 method lines 1-1" in output


def test_show_complexity_report_for_changed_java_file(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    output = format_complexity_text(build_complexity_debug(result))

    assert "Complexity dump" in output
    assert "Foo#a/0 method complexity 1" in output
    assert "java.if line 1 +1" in output


def test_added_callable_contributes_new_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.new_complexity == 1
    assert result.removed_complexity == 0
    assert result.net_delta == 1
    assert result.file_deltas[0].callables[0].status == "added"


def test_modified_callable_computes_delta(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "add if")
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { if (y) { run(); } } } }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "modified"
    assert callable_delta.before_score == 1
    assert callable_delta.after_score == 3
    assert callable_delta.delta == 2
    assert result.new_complexity == 2
    assert result.net_delta == 2


def test_removed_callable_contributes_removed_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "add if")
    write(tmp_path, "src/Foo.java", "class Foo {}\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.new_complexity == 0
    assert result.removed_complexity == 1
    assert result.net_delta == -1
    assert result.file_deltas[0].callables[0].status == "removed"


def test_import_only_change_has_zero_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "import java.util.Map;\nclass Foo {}\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)

    assert result.new_complexity == 0
    assert result.removed_complexity == 0
    assert result.net_delta == 0
    assert result.file_deltas[0].callables == []


def test_text_details_include_complexity_delta(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    output = format_text(result, Thresholds(), details=True)

    assert "New complexity: +1" in output
    assert "Foo#a/0 method" in output
    assert "after  complexity 1" in output
    assert "delta +1" in output
    assert "complexity on changed lines:" in output
    assert "java.if line 1 +1" in output


def test_json_details_include_changed_line_contributions(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void a() { if (x) { run(); } } }\n")

    result = analyze(resolve_comparison([], staged=False, unstaged=False), tmp_path)
    payload = json.loads(format_json(result, Thresholds()))

    callable_payload = payload["files"][0]["callables"][0]
    assert callable_payload["changed_line_contributions"] == [
        {
            "rule_id": "java.if",
            "line": 1,
            "points": 1,
            "message": "if statement at nesting depth 0",
        }
    ]
