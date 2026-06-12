from __future__ import annotations

import json

from diffcog.models import AnalysisResult, ChangedFile, Comparison, Endpoint, EndpointKind, Thresholds
from diffcog.models import SourcePair
from diffcog.report import format_json, format_snapshot_json, format_snapshot_text, format_text


def _comparison() -> Comparison:
    return Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
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
        files=[ChangedFile(status="M", old_path="src/Foo.java", path="src/Foo.java")],
        source_pairs=[],
    )

    output = format_text(result, Thresholds(), details=True)

    assert "Java files changed: 1" in output
    assert "Changed Java files:" in output
    assert "  M src/Foo.java" in output


def test_json_report_shape() -> None:
    result = AnalysisResult(
        comparison=_comparison(),
        files=[ChangedFile(status="M", old_path="src/Foo.java", path="src/Foo.java")],
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
    file = ChangedFile(status="M", old_path="src/Foo.java", path="src/Foo.java")
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
    file = ChangedFile(status="A", old_path="src/New.java", path="src/New.java")
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
    file = ChangedFile(status="M", old_path="src/Foo.java", path="src/Foo.java")
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
