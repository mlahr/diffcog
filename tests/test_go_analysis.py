from __future__ import annotations

import subprocess
from pathlib import Path

from diffcog.analysis import analyze
from diffcog.cli import resolve_comparison
from diffcog.debug_analysis import build_language_complexity_debug, build_symbol_debug
from diffcog.languages.go import GO_LANGUAGE
from diffcog.models import PathFilter
from diffcog.report import format_complexity_text, format_symbol_text


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
    write(repo, "src/app.go", "package app\n\nconst Value = 1\n")
    write(repo, "README.txt", "hello\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def analyze_go(repo: Path):
    return analyze(
        resolve_comparison([], staged=False, unstaged=False),
        repo,
        language=GO_LANGUAGE,
    )


def test_go_language_detects_tracked_go_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.go", "package app\n\nfunc Run() { if ready() { work() } }\n")

    result = analyze_go(tmp_path)

    assert result.ruleset_id == "go.default"
    assert [file.path for file in result.files] == ["src/app.go"]
    assert result.source_pairs[0].after == "package app\n\nfunc Run() { if ready() { work() } }\n"


def test_go_language_ignores_non_go_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "README.txt", "changed\n")

    result = analyze_go(tmp_path)

    assert result.files == []


def test_go_include_pathspec_does_not_widen_beyond_go(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.go", "package app\n\nfunc Run() {}\n")
    write(tmp_path, "src/notes.txt", "changed\n")

    result = analyze(
        resolve_comparison([], staged=False, unstaged=False),
        tmp_path,
        path_filter=PathFilter(includes=("src",)),
        language=GO_LANGUAGE,
    )

    assert [file.path for file in result.files] == ["src/app.go"]


def test_added_go_function_with_control_flow_contributes_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")

    result = analyze_go(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "added"
    assert callable_delta.after_callable.name == "Run"
    assert callable_delta.after_score == 1
    assert callable_delta.delta == 1
    assert result.new_complexity == 1
    assert result.net_delta == 1


def test_go_symbol_debug_reports_functions_and_methods(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.go",
        "package app\n\n"
        "type Service struct{}\n"
        "func Run() {}\n"
        "func (s *Service) Handle(ctx Context) {}\n",
    )

    result = analyze_go(tmp_path)
    output = format_symbol_text(build_symbol_debug(result, GO_LANGUAGE))

    assert "Symbol dump" in output
    assert "app#Run/0 function lines 4-4" in output
    assert "app.Service#Handle/1 method lines 5-5" in output


def test_go_complexity_debug_reports_control_flow_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")

    result = analyze_go(tmp_path)
    output = format_complexity_text(build_language_complexity_debug(result, GO_LANGUAGE))

    assert "Rule set: go.default" in output
    assert "app#Run/1 function complexity 1" in output
    assert "go.if line 3 +1" in output
