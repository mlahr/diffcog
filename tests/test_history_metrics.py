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


def commit(repo: Path, message: str) -> None:
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)


def init_repo(repo: Path) -> None:
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    write(repo, "src/Foo.java", "class Foo { void run() {} }\n")
    write(repo, "src/Bar.java", "class Bar { void run() {} }\n")
    write(repo, "src/app.py", "def run():\n    return 1\n")
    commit(repo, "initial")


def test_history_metrics_text_reports_hotspots_and_coupling(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/Bar.java", "class Bar { void run() { if (x) { go(); } } }\n")
    commit(tmp_path, "first cochange")
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { if (y) { go(); } } } }\n")
    write(tmp_path, "src/Bar.java", "class Bar { void run() { if (x) { if (y) { go(); } } } }\n")
    commit(tmp_path, "second cochange")
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "history"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "History window: last 90 days from HEAD" in output
    assert "History hotspots" in output
    assert "src/Foo.java [java] score" in output
    assert "Change coupling" in output
    assert "src/Bar.java <-> src/Foo.java: 3 shared commits" in output


def test_history_metrics_json_includes_full_rows(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    commit(tmp_path, "touch java")
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "history", "--json", "--history-days", "30"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"] == "history"
    assert payload["history"]["days"] == 30
    assert payload["history"]["languages"] == ["java", "python"]
    assert payload["hotspots"][0]["path"] == "src/Foo.java"
    assert payload["hotspots"][0]["current_complexity"] == 1


def test_history_metrics_respects_explicit_language(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/app.py", "def run(value):\n    if value:\n        return 1\n    return 0\n")
    commit(tmp_path, "touch python")
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "history", "--language", "python", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    assert payload["history"]["languages"] == ["python"]
    assert [row["path"] for row in payload["hotspots"]] == ["src/app.py"]


def test_history_metrics_respects_path_filters(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    write(tmp_path, "src/main/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    write(tmp_path, "src/test/FooTest.java", "class FooTest { void run() { if (x) { go(); } } }\n")
    commit(tmp_path, "touch filtered paths")
    monkeypatch.chdir(tmp_path)

    assert main(["--metrics", "history", "--include", "src/main", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    paths = [row["path"] for row in payload["hotspots"]]
    assert "src/main/Foo.java" in paths
    assert "src/test/FooTest.java" not in paths


def test_history_metrics_explicit_target_uses_target_complexity(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    init_repo(tmp_path)
    git(tmp_path, "tag", "base")
    write(tmp_path, "src/Foo.java", "class Foo { void run() { if (x) { go(); } } }\n")
    commit(tmp_path, "add complexity")
    git(tmp_path, "tag", "target")
    write(tmp_path, "src/Foo.java", "class Foo { void run() {} }\n")
    commit(tmp_path, "remove complexity")
    monkeypatch.chdir(tmp_path)

    assert main(["base", "target", "--metrics", "history", "--json"]) == EXIT_OK

    payload = json.loads(capsys.readouterr().out)
    foo = next(row for row in payload["hotspots"] if row["path"] == "src/Foo.java")
    assert payload["history"]["ref"] == "target"
    assert foo["current_complexity"] == 1
