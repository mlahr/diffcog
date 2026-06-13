from __future__ import annotations

import pytest

from diffcog.cli import EXIT_ERROR, EXIT_OK, EXIT_THRESHOLD, build_parser, main, resolve_comparison
from diffcog.models import AnalysisResult, Comparison, Endpoint, EndpointKind


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
    monkeypatch.setattr("diffcog.cli.analyze", lambda _comparison, ruleset: result)

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
    monkeypatch.setattr("diffcog.cli.analyze", lambda _comparison, ruleset: result)

    assert main(["--max-delta", "1"]) == EXIT_THRESHOLD


def test_list_rulesets_exits_without_analysis(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail_analysis(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("analysis should not run")

    monkeypatch.setattr("diffcog.cli.analyze", fail_analysis)

    assert main(["--list-rulesets"]) == EXIT_OK

    output = capsys.readouterr().out
    assert "Available Java rule sets:" in output
    assert "java.default" in output
    assert "java.control-flow" in output


def test_unknown_ruleset_exits_with_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--ruleset", "java.missing"]) == EXIT_ERROR

    error = capsys.readouterr().err
    assert "unknown Java rule set 'java.missing'" in error
