from __future__ import annotations

import pytest

from diffcog.cli import EXIT_ERROR, EXIT_OK, EXIT_THRESHOLD, build_parser, main, resolve_comparison
from diffcog.models import AnalysisResult, Comparison, Endpoint, EndpointKind, PathFilter


def test_default_resolves_head_to_worktree() -> None:
    comparison = resolve_comparison([], staged=False, unstaged=False)

    assert comparison.mode == "ref_to_worktree"
    assert comparison.before.kind == EndpointKind.REF
    assert comparison.before.label == "HEAD"
    assert comparison.after.kind == EndpointKind.WORKTREE
    assert comparison.after.label == "working tree"


def test_one_ref_resolves_ref_to_worktree() -> None:
    comparison = resolve_comparison(["main"], staged=False, unstaged=False)

    assert comparison.mode == "ref_to_worktree"
    assert comparison.before.label == "main"
    assert comparison.after.label == "working tree"


def test_two_refs_resolves_ref_to_ref() -> None:
    comparison = resolve_comparison(["main", "HEAD"], staged=False, unstaged=False)

    assert comparison.mode == "ref_to_ref"
    assert comparison.before.label == "main"
    assert comparison.after.label == "HEAD"


def test_staged_resolves_head_to_index() -> None:
    comparison = resolve_comparison([], staged=True, unstaged=False)

    assert comparison.mode == "ref_to_index"
    assert comparison.before.label == "HEAD"
    assert comparison.after.label == "index"


def test_unstaged_resolves_index_to_worktree() -> None:
    comparison = resolve_comparison([], staged=False, unstaged=True)

    assert comparison.mode == "index_to_worktree"
    assert comparison.before.label == "index"
    assert comparison.after.label == "working tree"


@pytest.mark.parametrize(
    ("refs", "staged", "unstaged"),
    [
        ([], True, True),
        (["main"], True, False),
        (["main"], False, True),
        (["a", "b", "c"], False, False),
    ],
)
def test_invalid_comparison_combinations(
    refs: list[str], staged: bool, unstaged: bool
) -> None:
    with pytest.raises(ValueError):
        resolve_comparison(refs, staged=staged, unstaged=unstaged)


def test_negative_threshold_exits_with_error() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--max-new", "-1"])

    assert exc.value.code == EXIT_ERROR


def test_hotspots_parses() -> None:
    parser = build_parser()

    args = parser.parse_args(["--hotspots"])

    assert args.hotspots is True


def test_language_defaults_to_auto() -> None:
    parser = build_parser()

    args = parser.parse_args([])

    assert args.language == "auto"


def test_language_parses_java_and_python() -> None:
    parser = build_parser()

    assert parser.parse_args(["--language", "java"]).language == "java"
    assert parser.parse_args(["--language", "python"]).language == "python"


def test_unknown_language_exits_with_error() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--language", "ruby"])

    assert exc.value.code == EXIT_ERROR


def test_include_and_exclude_parse_as_repeatable_pathspecs() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "--include",
            "src/main",
            "--include",
            "src/test",
            "--exclude",
            "**/generated/**",
            "--exclude",
            "legacy",
        ]
    )

    assert args.include == ["src/main", "src/test"]
    assert args.exclude == ["**/generated/**", "legacy"]


def test_main_passes_path_filter_when_include_or_exclude_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comparison = Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )
    result = AnalysisResult(
        comparison=comparison,
        files=[],
        source_pairs=[],
        new_complexity=0,
        removed_complexity=0,
        net_delta=0,
    )
    captured_filter = None

    def fake_analysis_languages(
        _comparison: Comparison, _language_specs: object, *, path_filter: PathFilter | None = None
    ) -> AnalysisResult:
        nonlocal captured_filter
        captured_filter = path_filter
        return result

    monkeypatch.setattr("diffcog.cli.analyze_languages", fake_analysis_languages)

    assert main(["--include", "src/main", "--exclude", "**/generated/**"]) == EXIT_OK
    assert captured_filter == PathFilter(
        includes=("src/main",), excludes=("**/generated/**",)
    )


def test_details_and_hotspots_are_mutually_exclusive() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--details", "--hotspots"])

    assert exc.value.code == EXIT_ERROR


def test_debug_show_snapshots_parses() -> None:
    parser = build_parser()

    args = parser.parse_args(["--debug", "show-snapshots"])

    assert args.debug == "show-snapshots"


def test_debug_show_symbols_parses() -> None:
    parser = build_parser()

    args = parser.parse_args(["--debug", "show-symbols"])

    assert args.debug == "show-symbols"


def test_debug_show_complexity_parses() -> None:
    parser = build_parser()

    args = parser.parse_args(["--debug", "show-complexity"])

    assert args.debug == "show-complexity"


def test_unknown_debug_mode_exits_with_error() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--debug", "dump-snapshots"])

    assert exc.value.code == EXIT_ERROR


def test_max_new_threshold_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    comparison = Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )
    result = AnalysisResult(
        comparison=comparison,
        files=[],
        source_pairs=[],
        new_complexity=2,
        removed_complexity=0,
        net_delta=2,
    )
    monkeypatch.setattr(
        "diffcog.cli.analyze_languages",
        lambda _comparison, _language_specs, path_filter=None: result,
    )

    assert main(["--max-new", "1"]) == EXIT_THRESHOLD


def test_max_delta_threshold_exits_two(monkeypatch: pytest.MonkeyPatch) -> None:
    comparison = Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )
    result = AnalysisResult(
        comparison=comparison,
        files=[],
        source_pairs=[],
        new_complexity=2,
        removed_complexity=0,
        net_delta=2,
    )
    monkeypatch.setattr(
        "diffcog.cli.analyze_languages",
        lambda _comparison, _language_specs, path_filter=None: result,
    )

    assert main(["--max-delta", "1"]) == EXIT_THRESHOLD


def test_list_rulesets_exits_without_analysis(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail_analysis(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("analysis should not run")

    monkeypatch.setattr("diffcog.cli.analyze", fail_analysis)

    assert main(["--list-rulesets"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Available rule sets:" in output
    assert "Java:" in output
    assert "java.default" in output
    assert "java.control-flow" in output
    assert "Python:" in output
    assert "python.default" in output
    assert "python.control-flow" in output


def test_list_rulesets_can_filter_by_language(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_analysis(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("analysis should not run")

    monkeypatch.setattr("diffcog.cli.analyze", fail_analysis)

    assert main(["--language", "python", "--list-rulesets"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Available Python rule sets:" in output
    assert "python.default" in output
    assert "python.control-flow" in output
    assert "java.default" not in output


def test_auto_language_rejects_custom_ruleset(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--ruleset", "java.default"]) == EXIT_ERROR

    error = capsys.readouterr().err
    assert "--ruleset cannot be used with --language auto" in error


def test_unknown_ruleset_exits_with_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--language", "java", "--ruleset", "java.missing"]) == EXIT_ERROR

    error = capsys.readouterr().err
    assert "unknown Java rule set 'java.missing'" in error


def test_language_ruleset_mismatch_exits_with_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--language", "python", "--ruleset", "java.default"]) == EXIT_ERROR

    error = capsys.readouterr().err
    assert "unknown Python rule set 'java.default'" in error


def test_explicit_python_ruleset_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    comparison = Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )
    result = AnalysisResult(comparison=comparison, files=[], source_pairs=[])
    captured = None

    def fake_analysis(
        _comparison: Comparison,
        *,
        ruleset: object,
        path_filter: PathFilter | None = None,
        language: object,
    ) -> AnalysisResult:
        nonlocal captured
        captured = (getattr(ruleset, "id", None), getattr(language, "id", None), path_filter)
        return result

    monkeypatch.setattr("diffcog.cli.analyze", fake_analysis)

    assert main(["--language", "python", "--ruleset", "python.control-flow"]) == EXIT_OK
    assert captured == ("python.control-flow", "python", None)


def test_explicit_java_uses_java_default(monkeypatch: pytest.MonkeyPatch) -> None:
    comparison = Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )
    result = AnalysisResult(comparison=comparison, files=[], source_pairs=[])
    captured = None

    def fake_analysis(
        _comparison: Comparison,
        *,
        ruleset: object,
        path_filter: PathFilter | None = None,
        language: object,
    ) -> AnalysisResult:
        nonlocal captured
        captured = (getattr(ruleset, "id", None), getattr(language, "id", None), path_filter)
        return result

    monkeypatch.setattr("diffcog.cli.analyze", fake_analysis)

    assert main(["--language", "java"]) == EXIT_OK
    assert captured == ("java.default", "java", None)
