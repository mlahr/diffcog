from __future__ import annotations

import pytest

from diffcog.cli import EXIT_ERROR, build_parser, resolve_comparison
from diffcog.models import EndpointKind


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
