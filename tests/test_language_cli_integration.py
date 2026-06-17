from __future__ import annotations

import json
import subprocess
from pathlib import Path

from diffcog.cli import EXIT_OK, main


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
    write(repo, "src/app.py", "VALUE = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def test_auto_language_reports_java_and_python_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main([]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule sets: java.default, python.default" in output
    assert "Analyzed files changed: 2" in output
    assert "New complexity: +2" in output


def test_auto_language_details_group_by_language(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--details"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Java:\n  M src/Foo.java" in output
    assert "Python:\n  M src/app.py" in output
    assert output.index("Java:") < output.index("Python:")


def test_auto_language_hotspots_include_language_labels_and_global_order(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n"
        "    if a and b and c:\n"
        "        return 1\n"
        "    return 0\n",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--hotspots"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "[Python] app.py:1 run/3 function 0 -> 2 (delta +2)" in output
    assert "[Java] Foo.java:1 run/0 method 0 -> 1 (delta +1)" in output
    assert output.index("[Python]") < output.index("[Java]")


def test_explicit_language_hotspots_do_not_include_language_labels(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n"
        "    if a and b and c:\n"
        "        return 1\n"
        "    return 0\n",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python", "--hotspots"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "app.py:1 run/3 function 0 -> 2 (delta +2)" in output
    assert "[Python]" not in output


def test_explicit_java_language_ignores_python_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "java"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule set: java.default" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_explicit_python_language_ignores_java_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule set: python.default" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_auto_language_json_includes_rulesets(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["ruleset"] == "auto"
    assert payload["rulesets"] == ["java.default", "python.default"]
    assert [file["path"] for file in payload["files"]] == ["src/Foo.java", "src/app.py"]
    assert [file["language"] for file in payload["files"]] == ["java", "python"]


def test_explicit_language_json_includes_language(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["ruleset"] == "python.default"
    assert payload["rulesets"] == ["python.default"]
    assert payload["files"][0]["language"] == "python"
