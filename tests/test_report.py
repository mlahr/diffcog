from __future__ import annotations

import json

from diffcog.models import AnalysisResult, ChangedFile, Comparison, Endpoint, EndpointKind, Thresholds
from diffcog.report import format_json, format_text


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
