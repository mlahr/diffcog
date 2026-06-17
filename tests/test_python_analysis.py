from __future__ import annotations

import subprocess
from pathlib import Path

from diffcog.analysis import analyze
from diffcog.cli import resolve_comparison
from diffcog.debug_analysis import build_language_complexity_debug, build_symbol_debug
from diffcog.languages.python import PYTHON_LANGUAGE
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
    write(repo, "src/app.py", "VALUE = 1\n")
    write(repo, "README.txt", "hello\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def analyze_python(repo: Path):
    return analyze(
        resolve_comparison([], staged=False, unstaged=False),
        repo,
        language=PYTHON_LANGUAGE,
    )


def test_python_language_detects_tracked_python_change(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run():\n    return 1\n")

    result = analyze_python(tmp_path)

    assert result.ruleset_id == "python.default"
    assert [file.path for file in result.files] == ["src/app.py"]
    assert result.source_pairs[0].after == "def run():\n    return 1\n"


def test_python_language_ignores_non_python_changes(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "README.txt", "changed\n")

    result = analyze_python(tmp_path)

    assert result.files == []


def test_python_include_pathspec_does_not_widen_beyond_python(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    write(tmp_path, "src/notes.txt", "changed\n")

    result = analyze(
        resolve_comparison([], staged=False, unstaged=False),
        tmp_path,
        path_filter=PathFilter(includes=("src",)),
        language=PYTHON_LANGUAGE,
    )

    assert [file.path for file in result.files] == ["src/app.py"]


def test_added_simple_python_function_has_zero_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run():\n    return 1\n")

    result = analyze_python(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "added"
    assert callable_delta.after_callable.name == "run"
    assert callable_delta.after_score == 0
    assert callable_delta.delta == 0
    assert result.new_complexity == 0
    assert result.removed_complexity == 0
    assert result.net_delta == 0


def test_modified_python_function_matches_before_and_after(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    git(tmp_path, "add", "src/app.py")
    git(tmp_path, "commit", "-m", "add function")
    write(tmp_path, "src/app.py", "def run():\n    return 2\n")

    result = analyze_python(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "modified"
    assert callable_delta.before_callable.name == "run"
    assert callable_delta.after_callable.name == "run"
    assert callable_delta.before_score == 0
    assert callable_delta.after_score == 0
    assert callable_delta.delta == 0


def test_removed_simple_python_function_has_zero_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run():\n    return 1\n")
    git(tmp_path, "add", "src/app.py")
    git(tmp_path, "commit", "-m", "add function")
    write(tmp_path, "src/app.py", "VALUE = 1\n")

    result = analyze_python(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "removed"
    assert callable_delta.before_callable.name == "run"
    assert callable_delta.before_score == 0
    assert callable_delta.delta == 0
    assert result.net_delta == 0


def test_import_only_python_change_has_unmapped_ranges(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "import os\nVALUE = 1\n")

    result = analyze_python(tmp_path)
    file_delta = result.file_deltas[0]

    assert file_delta.callables == []
    assert file_delta.unmapped_after_ranges
    assert result.net_delta == 0


def test_python_symbol_debug_reports_functions_methods_and_nested_functions(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.py",
        "class Service:\n"
        "    def outer(self):\n"
        "        def inner(value):\n"
        "            return value\n"
        "        return inner(1)\n",
    )

    result = analyze_python(tmp_path)
    output = format_symbol_text(build_symbol_debug(result, PYTHON_LANGUAGE))

    assert "Symbol dump" in output
    assert "Service#outer/1 method lines 2-5" in output
    assert "Service.outer#inner/1 function lines 3-4" in output


def test_python_function_with_control_flow_contributes_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")

    result = analyze_python(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "added"
    assert callable_delta.after_score == 1
    assert callable_delta.delta == 1
    assert result.new_complexity == 1
    assert result.net_delta == 1


def test_python_function_with_boolean_chain_contributes_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n"
        "    if a and b and c:\n"
        "        return 1\n"
        "    return 0\n",
    )

    result = analyze_python(tmp_path)
    callable_delta = result.file_deltas[0].callables[0]

    assert callable_delta.status == "added"
    assert callable_delta.after_score == 2
    assert callable_delta.delta == 2
    assert result.new_complexity == 2
    assert result.net_delta == 2


def test_python_complexity_debug_reports_control_flow_complexity(tmp_path: Path) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n"
        "    if a and b and c:\n"
        "        return 1\n"
        "    return 0\n",
    )

    result = analyze_python(tmp_path)
    output = format_complexity_text(build_language_complexity_debug(result, PYTHON_LANGUAGE))

    assert "Rule set: python.default" in output
    assert "run/3 function complexity 2" in output
    assert "python.if line 2 +1" in output
    assert "python.boolean_chain line 2 +1" in output
