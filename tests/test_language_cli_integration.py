from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

from diffcog.cli import EXIT_ERROR, EXIT_OK, main


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
    write(repo, "src/app.go", "package app\n\nconst Value = 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial")


def test_auto_language_reports_java_and_python_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main([]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule sets: java.default, python.default, go.default" in output
    assert "Analyzed files changed: 3" in output
    assert "New complexity: +3" in output


def test_piped_git_diff_reports_complexity(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "modify java")
    diff_text = git(tmp_path, "diff", "--unified=0", "HEAD~1..HEAD")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(diff_text))

    assert main([]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Comparing stdin diff before blobs -> stdin diff after blobs" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_piped_git_diff_supports_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "modify java")
    diff_text = git(tmp_path, "diff", "--unified=0", "HEAD~1..HEAD")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(diff_text))

    assert main(["--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["comparison"] == {
        "mode": "stdin_diff",
        "before": "stdin diff before blobs",
        "after": "stdin diff after blobs",
    }
    assert payload["files"][0]["path"] == "src/Foo.java"
    assert payload["new_complexity"] == 1


def test_piped_git_diff_supports_ck_metrics(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { Bar bar; void run() { bar.go(); } }\n")
    git(tmp_path, "add", "src/Foo.java")
    git(tmp_path, "commit", "-m", "modify java")
    diff_text = git(tmp_path, "diff", "--unified=0", "HEAD~1..HEAD")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(diff_text))

    assert main(["--metrics", "ck"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Comparing stdin diff before blobs -> stdin diff after blobs" in output
    assert "CK metrics" in output
    assert "M src/Foo.java" in output


def test_piped_git_diff_rejects_history_metrics(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("diff --git a/src/Foo.java b/src/Foo.java\n"))

    assert main(["--metrics", "history"]) == EXIT_ERROR

    assert "--metrics history cannot be used with piped diff input" in capsys.readouterr().err


def test_auto_language_details_group_by_language(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--details"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Java:\n  M src/Foo.java" in output
    assert "Python:\n  M src/app.py" in output
    assert "Go:\n  M src/app.go" in output
    assert output.index("Java:") < output.index("Python:")
    assert output.index("Python:") < output.index("Go:")


def test_auto_language_hotspots_include_language_labels_and_global_order(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n    if a and b and c:\n        return 1\n    return 0\n",
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--hotspots"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "[Python] app.py:1 run/3 function 0 -> 2 (delta +2)" in output
    assert "[Java] Foo.java:1 run/0 method 0 -> 1 (delta +1)" in output
    assert "[Go] app.go:3 app#Run/1 function 0 -> 1 (delta +1)" in output
    assert output.index("[Python]") < output.index("[Java]")


def test_explicit_language_hotspots_do_not_include_language_labels(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.py",
        "def run(a, b, c):\n    if a and b and c:\n        return 1\n    return 0\n",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python", "--hotspots"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "app.py:1 run/3 function 0 -> 2 (delta +2)" in output
    assert "[Python]" not in output


def test_explicit_java_language_ignores_python_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "java"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule set: java.default" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_explicit_python_language_ignores_java_changes(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule set: python.default" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_explicit_go_language_ignores_java_and_python_changes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "go"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Rule set: go.default" in output
    assert "Analyzed files changed: 1" in output
    assert "New complexity: +1" in output


def test_auto_language_json_includes_rulesets(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    write(tmp_path, "src/app.go", "package app\n\nfunc Run(value bool) { if value { work() } }\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["ruleset"] == "auto"
    assert payload["rulesets"] == ["java.default", "python.default", "go.default"]
    assert [file["path"] for file in payload["files"]] == [
        "src/Foo.java",
        "src/app.py",
        "src/app.go",
    ]
    assert [file["language"] for file in payload["files"]] == ["java", "python", "go"]


def test_auto_language_ck_metrics_report_includes_java_python_and_go(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { Bar bar; void run() { bar.go(); } }\n")
    write(
        tmp_path,
        "src/app.py",
        "from pkg import Client\n"
        "class Service:\n"
        "    def __init__(self, client: Client):\n"
        "        self.client = client\n",
    )
    write(
        tmp_path,
        "src/app.go",
        "package app\n\n"
        "type Service struct { client Client }\n"
        "func (s *Service) Run() { _ = s.client }\n",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "ck"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "CK metrics" in output
    assert "M src/Foo.java" in output
    assert "modified: Foo class" in output
    assert "M src/app.py" in output
    assert "added: Service class" in output
    assert "M src/app.go" in output
    assert "added: app.Service struct" in output


def test_auto_language_ck_metrics_json(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { Bar bar; void run() { bar.go(); } }\n")
    write(tmp_path, "src/app.py", "class Service:\n    def run(self):\n        return self.value\n")
    write(
        tmp_path, "src/app.go", "package app\n\ntype Worker interface { Run(ctx Context) error }\n"
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "ck", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"] == "ck"
    assert [file["language"] for file in payload["files"]] == ["java", "python", "go"]
    assert [file["classes"][0]["name"] for file in payload["files"]] == [
        "Foo",
        "Service",
        "Worker",
    ]


def test_explicit_go_ck_metrics_report(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(
        tmp_path,
        "src/app.go",
        "package app\n\n"
        "type Service struct { client Client }\n"
        "func (s *Service) Run() { _ = s.client }\n",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "ck", "--language", "go"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "M src/app.go" in output
    assert "added: app.Service struct" in output
    assert "CBO 0 -> 1 (delta +1)" in output
    assert "LCOM 0 -> 0 (delta +0)" in output
    assert "WMC 0 -> 1 (delta +1)" in output


def test_explicit_language_json_includes_language(tmp_path: Path, monkeypatch, capsys) -> None:
    init_repo(tmp_path)
    write(
        tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n"
    )
    monkeypatch.chdir(tmp_path)

    assert main(["--language", "python", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["ruleset"] == "python.default"
    assert payload["rulesets"] == ["python.default"]
    assert payload["files"][0]["language"] == "python"
