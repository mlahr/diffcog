from __future__ import annotations

import json

from diffcog.debug_analysis import build_complexity_debug, build_symbol_debug
from diffcog.languages.java.complexity import ComplexityContribution, ComplexityResult
from diffcog.languages.java.complexity import score_callable
from diffcog.languages.java.parser import parse_snapshot
from diffcog.models import AnalysisResult, ChangedFile, Comparison, Endpoint, EndpointKind, LineRange, Thresholds
from diffcog.models import CallableComplexityDelta, ClassMetrics, ClassMetricsDelta
from diffcog.models import FileClassMetricsDelta, FileComplexityDelta
from diffcog.models import SourcePair
from diffcog.report import (
    format_ck_metrics_json,
    format_ck_metrics_text,
    format_delta_totals_json,
    format_delta_totals_text,
    format_json,
    format_complexity_json,
    format_complexity_text,
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


def _complexity_result(points: int) -> ComplexityResult:
    return ComplexityResult(
        score=points,
        contributions=[
            ComplexityContribution(
                rule_id="java.if",
                line=1,
                points=points,
                message="if statement at nesting depth 0",
            )
        ],
    )


def test_text_report_without_java_changes() -> None:
    result = AnalysisResult(comparison=_comparison(), files=[], source_pairs=[])

    output = format_text(result, Thresholds())

    assert "Comparing HEAD -> working tree" in output
    assert "No supported language changes found." in output
    assert "New complexity: +0" in output
    assert "Net delta: +0" in output


def test_text_report_with_details() -> None:
    result = AnalysisResult(
        comparison=_comparison(),
        files=[_file()],
        source_pairs=[],
    )

    output = format_text(result, Thresholds(), details=True)

    assert "Analyzed files changed: 1" in output
    assert "Changed analyzed files:" in output
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
    assert payload["ruleset"] == "java.default"
    assert payload["rulesets"] == ["java.default"]
    assert payload["files"] == [
        {"status": "M", "path": "src/Foo.java", "old_path": "src/Foo.java", "language": ""}
    ]
    assert payload["thresholds"] == {"max_new": 10, "max_delta": 5}
    assert payload["threshold_failed"] is False


def test_text_report_with_complexity_delta_details() -> None:
    file = _file(new_ranges=[LineRange(1, 1)])
    before_callable = parse_snapshot("class Foo { void a() { if (x) { run(); } } }\n").callables[0]
    after_callable = parse_snapshot(
        "class Foo { void a() { if (x) { if (y) { run(); } } } }\n"
    ).callables[0]
    before_result = score_callable(before_callable)
    after_result = score_callable(after_callable)
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=file,
                callables=[
                    CallableComplexityDelta(
                        status="modified",
                        before_callable=before_callable,
                        after_callable=after_callable,
                        before_result=before_result,
                        after_result=after_result,
                        before_score=before_result.score,
                        after_score=after_result.score,
                        delta=after_result.score - before_result.score,
                    )
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            )
        ],
        new_complexity=2,
        removed_complexity=0,
        net_delta=2,
    )

    output = format_text(result, Thresholds(), details=True)

    assert "New complexity: +2" in output
    assert "M src/Foo.java" in output
    assert "modified:" in output
    assert "before complexity 1" in output
    assert "after  complexity 3" in output
    assert "delta +2" in output
    assert "complexity on changed lines:" in output
    assert "java.if line 1 +1" in output


def test_text_report_with_hotspots() -> None:
    file = _file(
        path="src/main/java/com/example/Foo.java",
        old_ranges=[LineRange(1, 1)],
        new_ranges=[LineRange(1, 1)],
    )
    small_callable = parse_snapshot("class Foo { void small() { if (x) { run(); } } }\n").callables[0]
    large_callable = parse_snapshot("class Foo { void large() { if (x) { run(); } } }\n").callables[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=file,
                callables=[
                    CallableComplexityDelta(
                        status="modified",
                        before_callable=small_callable,
                        after_callable=small_callable,
                        before_result=_complexity_result(5),
                        after_result=_complexity_result(8),
                        before_score=5,
                        after_score=8,
                        delta=3,
                    ),
                    CallableComplexityDelta(
                        status="removed",
                        before_callable=large_callable,
                        after_callable=None,
                        before_result=_complexity_result(9),
                        after_result=None,
                        before_score=9,
                        after_score=0,
                        delta=-9,
                    ),
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            )
        ],
        new_complexity=3,
        removed_complexity=9,
        net_delta=-6,
    )

    output = format_text(result, Thresholds(), hotspots=True)

    assert "Hotspots:" in output
    assert "src/main/java/com/example/Foo.java" not in output
    assert "Foo.java:1 large/0 method 9 -> 0 (delta -9)" in output
    assert "Foo#large/0" not in output
    assert output.index("large/0 method 9 -> 0 (delta -9)") < output.index(
        "small/0 method 5 -> 8 (delta +3)"
    )
    assert "top rule: java.if line 1 +9" in output
    assert "complexity on changed lines:" not in output


def test_text_report_hotspots_keep_paths_unique() -> None:
    first_file = _file(
        path="src/main/java/com/example/service/Foo.java",
        new_ranges=[LineRange(1, 1)],
    )
    second_file = _file(
        path="src/test/java/com/example/service/Foo.java",
        new_ranges=[LineRange(1, 1)],
    )
    first_callable = parse_snapshot("class Foo { void first() { if (x) { run(); } } }\n").callables[0]
    second_callable = parse_snapshot("class Foo { void second() { if (x) { run(); } } }\n").callables[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[first_file, second_file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=first_file,
                callables=[
                    CallableComplexityDelta(
                        status="added",
                        before_callable=None,
                        after_callable=first_callable,
                        before_result=None,
                        after_result=_complexity_result(2),
                        before_score=0,
                        after_score=2,
                        delta=2,
                    )
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            ),
            FileComplexityDelta(
                file=second_file,
                callables=[
                    CallableComplexityDelta(
                        status="added",
                        before_callable=None,
                        after_callable=second_callable,
                        before_result=None,
                        after_result=_complexity_result(1),
                        before_score=0,
                        after_score=1,
                        delta=1,
                    )
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            ),
        ],
        new_complexity=3,
        removed_complexity=0,
        net_delta=3,
    )

    output = format_text(result, Thresholds(), hotspots=True)

    assert "main/java/com/example/service/Foo.java:1 first/0" in output
    assert "test/java/com/example/service/Foo.java:1 second/0" in output


def test_text_report_hotspots_keep_nested_class_name() -> None:
    file = _file(path="src/main/java/com/example/Foo.java", new_ranges=[LineRange(1, 1)])
    callable_ = parse_snapshot(
        "class Foo { class Inner { void run() { if (x) { work(); } } } }\n"
    ).callables[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=file,
                callables=[
                    CallableComplexityDelta(
                        status="added",
                        before_callable=None,
                        after_callable=callable_,
                        before_result=None,
                        after_result=_complexity_result(1),
                        before_score=0,
                        after_score=1,
                        delta=1,
                    )
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            )
        ],
        new_complexity=1,
        removed_complexity=0,
        net_delta=1,
    )

    output = format_text(result, Thresholds(), hotspots=True)

    assert "Foo.java:1 Foo.Inner#run/0 method 0 -> 1 (delta +1)" in output


def test_text_report_hotspots_limit_mentions_details() -> None:
    file = _file(new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=file,
                callables=[
                    CallableComplexityDelta(
                        status="added",
                        before_callable=None,
                        after_callable=parse_snapshot(
                            f"class Foo {{ void m{index}() {{ if (x) {{ run(); }} }} }}\n"
                        ).callables[0],
                        before_result=None,
                        after_result=_complexity_result(index + 1),
                        before_score=0,
                        after_score=index + 1,
                        delta=index + 1,
                    )
                    for index in range(11)
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            )
        ],
        new_complexity=66,
        removed_complexity=0,
        net_delta=66,
    )

    output = format_text(result, Thresholds(), hotspots=True)

    assert "Showing 10 of 11 hotspots. Use --details for the full list." in output
    assert "m10/0 method 0 -> 11 (delta +11)" in output
    assert "m0/0 method 0 -> 1 (delta +1)" not in output


def test_text_report_hotspots_without_complexity_changes() -> None:
    file = _file(new_ranges=[LineRange(1, 1)])
    callable_ = parse_snapshot("class Foo { void a() { run(); } }\n").callables[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        file_deltas=[
            FileComplexityDelta(
                file=file,
                callables=[
                    CallableComplexityDelta(
                        status="modified",
                        before_callable=callable_,
                        after_callable=callable_,
                        before_result=_complexity_result(0),
                        after_result=_complexity_result(0),
                        before_score=0,
                        after_score=0,
                        delta=0,
                    )
                ],
                unmapped_before_ranges=[],
                unmapped_after_ranges=[],
            )
        ],
    )

    output = format_text(result, Thresholds(), hotspots=True)

    assert "No complexity hotspots found." in output


def test_json_report_ignores_hotspots_mode() -> None:
    result = AnalysisResult(
        comparison=_comparison(),
        files=[_file()],
        source_pairs=[],
    )

    payload = json.loads(format_json(result, Thresholds()))

    assert "hotspots" not in payload
    assert payload["files"] == [
        {"status": "M", "path": "src/Foo.java", "old_path": "src/Foo.java", "language": ""}
    ]


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
                "language": "",
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

    output = format_symbol_text(build_symbol_debug(result))

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

    output = format_symbol_text(build_symbol_debug(result))

    assert "  added:" in output
    assert "Foo#b/1 method lines 3-3" in output


def test_symbol_text_report_missing_side() -> None:
    file = _file(status="A", path="src/New.java", new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[SourcePair(file=file, before=None, after="class New { void run() {} }\n")],
    )

    output = format_symbol_text(build_symbol_debug(result))

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

    output = format_symbol_text(build_symbol_debug(result))

    assert "no changed callables" in output


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

    output = format_symbol_text(build_symbol_debug(result))

    assert "changed lines not mapped to callables:" in output
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

    payload = json.loads(format_symbol_json(build_symbol_debug(result)))

    assert payload["debug"] == "show-symbols"
    assert payload["files"][0]["before"]["present"] is True
    assert payload["files"][0]["before"]["parse_error"] is False
    assert payload["files"][0]["after"]["callables"] == [
        {
            "kind": "method",
            "name": "a",
            "namespace_path": ["Foo"],
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

    payload = json.loads(format_symbol_json(build_symbol_debug(result)))

    assert payload["files"][0]["before"]["parse_error"] is True


def test_complexity_text_report() -> None:
    file = _file(new_ranges=[LineRange(2, 2)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo {}\n",
                after="class Foo {\n  void a() { if (x) { run(); } }\n}\n",
            )
        ],
    )

    output = format_complexity_text(build_complexity_debug(result))

    assert "Complexity dump" in output
    assert "  added:" in output
    assert "Foo#a/0 method complexity 1" in output
    assert "java.if line 2 +1" in output


def test_complexity_json_report_shape() -> None:
    file = _file(new_ranges=[LineRange(1, 1)])
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[
            SourcePair(
                file=file,
                before="class Foo {}\n",
                after="class Foo { void a() { if (x) { run(); } } }\n",
            )
        ],
    )

    payload = json.loads(format_complexity_json(build_complexity_debug(result)))

    assert payload["debug"] == "show-complexity"
    assert payload["ruleset"] == "java.default"
    assert payload["files"][0]["callables"][0]["status"] == "added"
    assert payload["files"][0]["callables"][0]["score"] == 1
    assert payload["files"][0]["callables"][0]["contributions"][0]["rule_id"] == "java.if"


def test_ck_metrics_text_report() -> None:
    file = _file()
    before_class = parse_snapshot("class Foo { void a() {} }\n").classes[0]
    after_class = parse_snapshot("class Foo { Bar bar; void a() { bar.go(); } }\n").classes[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=file,
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="modified",
                        before_class=before_class,
                        after_class=after_class,
                        before_metrics=ClassMetrics(cbo=0, lcom=0, wmc=1),
                        after_metrics=ClassMetrics(cbo=1, lcom=0, wmc=1),
                        delta=ClassMetrics(cbo=1, lcom=0, wmc=0),
                    )
                ],
            )
        ],
    )

    output = format_ck_metrics_text(result)

    assert "CK metrics" in output
    assert (
        "CBO = external type coupling; LCOM = lack of shared field use; "
        "WMC = participating method count"
    ) in output
    assert "M src/Foo.java" in output
    assert "Old totals: CBO 0, LCOM 0, WMC 1" in output
    assert "New totals: CBO 1, LCOM 0, WMC 1" in output
    assert "Delta totals: CBO +1, LCOM +0, WMC +0" in output
    assert "modified: Foo class" in output
    assert "CBO 0 -> 1 (delta +1)" in output
    assert "LCOM 0 -> 0 (delta +0)" in output
    assert "WMC 1 -> 1 (delta +0)" in output


def test_delta_totals_text_report_is_one_line() -> None:
    file = _file()
    before_class = parse_snapshot("class Foo { A a; B b; void a() {} void b() {} }\n").classes[0]
    after_class = parse_snapshot("class Foo { C c; void a() {} }\n").classes[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        net_delta=1,
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=file,
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="modified",
                        before_class=before_class,
                        after_class=after_class,
                        before_metrics=ClassMetrics(cbo=0, lcom=18, wmc=1),
                        after_metrics=ClassMetrics(cbo=7, lcom=0, wmc=1),
                        delta=ClassMetrics(cbo=7, lcom=-18, wmc=0),
                    )
                ],
            )
        ],
    )

    assert format_delta_totals_text(result) == "COG +1, CBO +7, LCOM -18, WMC +0\n"


def test_delta_totals_json_report_shape() -> None:
    file = _file()
    before_class = parse_snapshot("class Foo { A a; B b; void a() {} void b() {} }\n").classes[0]
    after_class = parse_snapshot("class Foo { C c; void a() {} }\n").classes[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        net_delta=1,
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=file,
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="modified",
                        before_class=before_class,
                        after_class=after_class,
                        before_metrics=ClassMetrics(cbo=0, lcom=18, wmc=1),
                        after_metrics=ClassMetrics(cbo=7, lcom=0, wmc=1),
                        delta=ClassMetrics(cbo=7, lcom=-18, wmc=0),
                    )
                ],
            )
        ],
    )

    output = format_delta_totals_json(result)
    payload = json.loads(output)

    assert payload == {
        "comparison": {
            "mode": "ref_to_worktree",
            "before": "HEAD",
            "after": "working tree",
        },
        "metrics": "delta_totals",
        "deltas": {"cog": 1, "cbo": 7, "lcom": -18, "wmc": 0},
    }
    assert output.count("\n") == 1
    assert output.endswith("\n")


def test_ck_metrics_json_report_shape() -> None:
    file = _file()
    class_ = parse_snapshot("class Foo { void a() {} }\n").classes[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[file],
        source_pairs=[],
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=file,
                before_present=False,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="added",
                        before_class=None,
                        after_class=class_,
                        before_metrics=None,
                        after_metrics=ClassMetrics(cbo=0, lcom=0, wmc=1),
                        delta=ClassMetrics(cbo=0, lcom=0, wmc=1),
                    )
                ],
            )
        ],
    )

    payload = json.loads(format_ck_metrics_json(result))

    assert payload["metrics"] == "ck"
    assert payload["totals"] == {
        "old": {"cbo": 0, "lcom": 0, "wmc": 0},
        "new": {"cbo": 0, "lcom": 0, "wmc": 1},
        "delta": {"cbo": 0, "lcom": 0, "wmc": 1},
    }
    assert payload["files"][0]["classes"][0]["status"] == "added"
    assert payload["files"][0]["classes"][0]["after"] == {"cbo": 0, "lcom": 0, "wmc": 1}
    assert payload["files"][0]["classes"][0]["delta"] == {"cbo": 0, "lcom": 0, "wmc": 1}


def test_ck_metrics_text_report_suppresses_unchanged_and_no_class_files() -> None:
    unchanged_class = parse_snapshot("class Foo {}\n").classes[0]
    class_file = _file(path="src/Foo.java")
    no_class_file = _file(path="src/package-info.java")
    result = AnalysisResult(
        comparison=_comparison(),
        files=[class_file, no_class_file],
        source_pairs=[],
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=class_file,
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="unchanged",
                        before_class=unchanged_class,
                        after_class=unchanged_class,
                        before_metrics=ClassMetrics(cbo=0, lcom=0, wmc=0),
                        after_metrics=ClassMetrics(cbo=0, lcom=0, wmc=0),
                        delta=ClassMetrics(cbo=0, lcom=0, wmc=0),
                    )
                ],
            ),
            FileClassMetricsDelta(
                file=no_class_file,
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[],
            ),
        ],
    )

    output = format_ck_metrics_text(result)

    assert "unchanged" not in output
    assert "no classes" not in output
    assert "src/Foo.java" not in output
    assert "src/package-info.java" not in output
    assert "Old totals: CBO 0, LCOM 0, WMC 0" in output
    assert "New totals: CBO 0, LCOM 0, WMC 0" in output
    assert "Delta totals: CBO +0, LCOM +0, WMC +0" in output
    assert "No CK metric changes found." in output


def test_ck_metrics_json_report_suppresses_unchanged_and_no_class_files() -> None:
    unchanged_class = parse_snapshot("class Foo {}\n").classes[0]
    result = AnalysisResult(
        comparison=_comparison(),
        files=[],
        source_pairs=[],
        class_metric_deltas=[
            FileClassMetricsDelta(
                file=_file(path="src/Foo.java"),
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[
                    ClassMetricsDelta(
                        status="unchanged",
                        before_class=unchanged_class,
                        after_class=unchanged_class,
                        before_metrics=ClassMetrics(cbo=0, lcom=0, wmc=0),
                        after_metrics=ClassMetrics(cbo=0, lcom=0, wmc=0),
                        delta=ClassMetrics(cbo=0, lcom=0, wmc=0),
                    )
                ],
            ),
            FileClassMetricsDelta(
                file=_file(path="src/package-info.java"),
                before_present=True,
                after_present=True,
                before_parse_error=False,
                after_parse_error=False,
                classes=[],
            ),
        ],
    )

    payload = json.loads(format_ck_metrics_json(result))

    assert payload["totals"] == {
        "old": {"cbo": 0, "lcom": 0, "wmc": 0},
        "new": {"cbo": 0, "lcom": 0, "wmc": 0},
        "delta": {"cbo": 0, "lcom": 0, "wmc": 0},
    }
    assert payload["files"] == []
