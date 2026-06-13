from __future__ import annotations

import argparse
import sys

from diffcog.analysis import analyze
from diffcog.debug_analysis import build_complexity_debug, build_symbol_debug
from diffcog.errors import DiffcogError
from diffcog.git import GitError
from diffcog.languages.java.complexity import DEFAULT_JAVA_RULESET, get_ruleset, list_ruleset_ids
from diffcog.models import Comparison, Endpoint, EndpointKind, Thresholds
from diffcog.report import (
    format_json,
    format_complexity_json,
    format_complexity_text,
    format_snapshot_json,
    format_snapshot_text,
    format_symbol_json,
    format_symbol_text,
    format_text,
)


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_THRESHOLD = 2


class DiffcogArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = DiffcogArgumentParser(
        prog="diffcog",
        description="Measure cognitive complexity introduced by Java code changes.",
    )
    parser.add_argument("refs", nargs="*", metavar="REF", help="optional BASE and TARGET refs")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="compare HEAD against the staged index",
    )
    parser.add_argument(
        "--unstaged",
        action="store_true",
        help="compare the staged index against the working tree",
    )
    parser.add_argument("--max-new", type=_non_negative_int, default=None)
    parser.add_argument("--max-delta", type=_non_negative_int, default=None)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    report_group = parser.add_mutually_exclusive_group()
    report_group.add_argument(
        "--details", action="store_true", help="include changed file details in text output"
    )
    report_group.add_argument(
        "--hotspots", action="store_true", help="show top complexity hotspots in text output"
    )
    parser.add_argument(
        "--ruleset",
        default=DEFAULT_JAVA_RULESET.id,
        help="Java complexity rule set to use",
    )
    parser.add_argument(
        "--list-rulesets",
        action="store_true",
        help="list available Java complexity rule sets and exit",
    )
    parser.add_argument(
        "--debug",
        choices=["show-snapshots", "show-symbols", "show-complexity"],
        default=None,
        help="run a debug report mode",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.list_rulesets:
            print(format_ruleset_list(list_ruleset_ids()), end="")
            return EXIT_OK

        ruleset = get_ruleset(args.ruleset)
        comparison = resolve_comparison(args.refs, staged=args.staged, unstaged=args.unstaged)
        thresholds = Thresholds(max_new=args.max_new, max_delta=args.max_delta)
        result = analyze(comparison, ruleset=ruleset)
    except (ValueError, GitError, DiffcogError) as exc:
        print(f"diffcog: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        if args.debug == "show-snapshots":
            if args.json:
                print(format_snapshot_json(result), end="")
            else:
                print(format_snapshot_text(result), end="")
        elif args.debug == "show-symbols":
            symbol_debug = build_symbol_debug(result)
            if args.json:
                print(format_symbol_json(symbol_debug), end="")
            else:
                print(format_symbol_text(symbol_debug), end="")
        elif args.debug == "show-complexity":
            complexity_debug = build_complexity_debug(result, ruleset)
            if args.json:
                print(format_complexity_json(complexity_debug), end="")
            else:
                print(format_complexity_text(complexity_debug), end="")
        elif args.json:
            print(format_json(result, thresholds), end="")
        else:
            print(format_text(result, thresholds, details=args.details, hotspots=args.hotspots), end="")
    except DiffcogError as exc:
        print(f"diffcog: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if result.threshold_failed(thresholds):
        return EXIT_THRESHOLD
    return EXIT_OK


def resolve_comparison(refs: list[str], *, staged: bool, unstaged: bool) -> Comparison:
    if staged and unstaged:
        raise ValueError("--staged and --unstaged cannot be combined")

    if (staged or unstaged) and refs:
        raise ValueError("--staged/--unstaged cannot be combined with refs")

    if len(refs) > 2:
        raise ValueError("expected at most two refs")

    if staged:
        return Comparison(
            mode="ref_to_index",
            before=Endpoint(EndpointKind.REF, "HEAD"),
            after=Endpoint(EndpointKind.INDEX, "index"),
        )

    if unstaged:
        return Comparison(
            mode="index_to_worktree",
            before=Endpoint(EndpointKind.INDEX, "index"),
            after=Endpoint(EndpointKind.WORKTREE, "working tree"),
        )

    if len(refs) == 2:
        return Comparison(
            mode="ref_to_ref",
            before=Endpoint(EndpointKind.REF, refs[0]),
            after=Endpoint(EndpointKind.REF, refs[1]),
        )

    if len(refs) == 1:
        return Comparison(
            mode="ref_to_worktree",
            before=Endpoint(EndpointKind.REF, refs[0]),
            after=Endpoint(EndpointKind.WORKTREE, "working tree"),
        )

    return Comparison(
        mode="ref_to_worktree",
        before=Endpoint(EndpointKind.REF, "HEAD"),
        after=Endpoint(EndpointKind.WORKTREE, "working tree"),
    )


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def format_ruleset_list(ruleset_ids: list[str]) -> str:
    lines = ["Available Java rule sets:", *[f"  {ruleset_id}" for ruleset_id in ruleset_ids]]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
