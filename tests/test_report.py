from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from diffcog.errors import DiffcogError
from diffcog.models import AnalysisResult, ChangedFile, Comparison, Endpoint, EndpointKind, LineRange, Thresholds
from diffcog.models import SourcePair
from diffcog.report import (
    format_json,
    format_snapshot_json,
    format_snapshot_text,
    format_symbol_json,
    format_symbol_text,
    format_text,
)


def _comparison() -> Comparison:
    return Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )


def _file(
    status: str = "M",
    path: str = "src/Foo.java",
    old_path: str | None = None,
    old_ranges: list[LineRange] | None = None,
    new_ranges: list[LineRange] | None = None,
) -> ChangedFile:
    return ChangedFile(
        status=status,
        old_path=old_path or path,
        path=path,
        old_ranges=old_ranges or [],
        new_ranges=new_ranges or [],
    )


def test_text_report_without_java_changes() -> None:
    result = AnalysisResult(comparison=_comparison(), files=[], source_pairs=[])

    output = format_text(result, Thresholds())

    assert "Comparing HEAD -> working tree" in output
    assert "No Java changes found." in output
    assert "New complexity: +0" in output
    assert "Net delta: +0" in output


def test_text_report_with_details() -> None:
    result = AnalysisResult(
        comparison=_comparison(),
        files=[_file()],
        source_pairs=[],
    )

    output = format_text(result, Thresholds(), details=True)

    assert "Java files changed: 1" in output
    assert "Changed Java files:" in output
    assert "  M src/Foo.java" in output


def test_json_report_shape() -> None:
    result = AnalysisResult(
        comparison=_comparison(),
        files=[_file()],
        source_pairs=[],
    )

    payload = json.loads(format_json(result, Thresholds(max_new=10, max_delta=5)))

    assert payload["comparison"] == {
        "mode": "ref_to_worktree",
        "before": "HEAD",
        "after": "working tree",
    }
    assert payload["files"] == [
        {"status": "M", "path": "src/Foo.java", "old_path": "src/Foo.java"}
    ]
    assert payload["thresholds"] == {"max_new": 10, "max_delta": 5}
    assert payload["threshold_failed"] is False


def test_snapshot_text_report() -> None:
    file = _file()
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo {}\n",
                after="class Foo {\n  void a() {}\n}\n",
            )
        ],
    )

    output = format_snapshot_text(result)

    assert "Comparing HEAD -> working tree" in output
    assert "Snapshot dump" in output
    assert "M src/Foo.java" in output
    assert "before: present, 1 lines, 13 bytes" in output
    assert "after:  present, 3 lines, 28 bytes" in output


def test_snapshot_text_report_missing_snapshot() -> None:
    file = _file(status="A", path="src/New.java")
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before=None, after="class New {}\n")],
    )

    output = format_snapshot_text(result)

    assert "A src/New.java" in output
    assert "before: missing" in output
    assert "after:  present, 1 lines, 13 bytes" in output


def test_snapshot_json_report_shape() -> None:
    file = _file()
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before="class Foo {}\n", after="class Foo {}\n")],
    )

    payload = json.loads(format_snapshot_json(result))

    assert payload["debug"] == "show-snapshots"
    assert payload["comparison"] == {
        "mode": "ref_to_worktree",
        "before": "HEAD",
        "after": "working tree",
    }
    assert payload["snapshots"] == [
        {
            "status": "M",
            "path": "src/Foo.java",
            "old_path": "src/Foo.java",
            "before": {"present": True, "lines": 1, "bytes": 13},
            "after": {"present": True, "lines": 1, "bytes": 13},
        }
    ]


def test_symbol_text_report_modified_callable() -> None:
    file = _file(old_ranges=[LineRange(2, 2)], new_ranges=[LineRange(2, 2)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo {\n  void a() {}\n}\n",
                after="class Foo {\n  void a() { int x = 1; }\n}\n",
            )
        ],
    )

    output = format_symbol_text(result)

    assert "Comparing HEAD -> working tree" in output
    assert "Symbol dump" in output
    assert "M src/Foo.java" in output
    assert "  modified:" in output
    assert "Foo#a/0 method" in output
    assert "before lines 2-2" in output
    assert "after  lines 2-2" in output


def test_symbol_text_report_added_callable() -> None:
    file = _file(new_ranges=[LineRange(3, 3)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo {\n  void a() {}\n}\n",
                after="class Foo {\n  void a() {}\n  void b(int x) {}\n}\n",
            )
        ],
    )

    output = format_symbol_text(result)

    assert "  added:" in output
    assert "Foo#b/1 method lines 3-3" in output


def test_symbol_text_report_missing_side() -> None:
    file = _file(status="A", path="src/New.java", new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before=None, after="class New { void run() {} }\n")],
    )

    output = format_symbol_text(result)

    assert "A src/New.java" in output
    assert "  added:" in output
    assert "New#run/0 method lines 1-1" in output


def test_symbol_text_report_no_callables() -> None:
    file = _file(old_ranges=[LineRange(1, 1)], new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before="class Foo {}\n", after="class Foo {}\n")],
    )

    output = format_symbol_text(result)

    assert "no changed methods/constructors" in output


def test_symbol_text_report_outside_symbols() -> None:
    file = _file(old_ranges=[LineRange(1, 1)], new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="import java.util.Map;\nclass Foo { void a() {} }\n",
                after="import java.util.Map;\nclass Foo { void a() {} }\n",
            )
        ],
    )

    output = format_symbol_text(result)

    assert "changed lines not mapped to methods/constructors:" in output
    assert "before line 1" in output
    assert "after line 1" in output


def test_symbol_json_report_shape() -> None:
    file = _file(old_ranges=[LineRange(1, 1)], new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo { void a() {} }\n",
                after="class Foo { void a(int x) {} }\n",
            )
        ],
    )

    payload = json.loads(format_symbol_json(result))

    assert payload["debug"] == "show-symbols"
    assert payload["files"][0]["before"]["present"] is True
    assert payload["files"][0]["before"]["parse_error"] is False
    assert payload["files"][0]["after"]["callables"] == [
        {
            "kind": "method",
            "name": "a",
            "class_path": ["Foo"],
            "parameter_count": 1,
            "start_line": 1,
            "end_line": 1,
        }
    ]


def test_symbol_json_report_parse_error() -> None:
    file = _file(old_ranges=[LineRange(1, 1)], new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before="class Foo {\n", after="class Foo {}\n")],
    )

    payload = json.loads(format_symbol_json(result))

    assert payload["files"][0]["before"]["parse_error"] is True


def test_symbol_report_missing_parser_dependency_has_clear_error() -> None:
    result = AnalysisResult(comparison=_comparison(), files=[], source_pairs=[])

    with patch("builtins.__import__", side_effect=ModuleNotFoundError(name="tree_sitter_java")):
        with pytest.raises(DiffcogError, match="Java symbol parsing dependencies are missing"):
            format_symbol_text(result)
