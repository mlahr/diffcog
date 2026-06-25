from __future__ import annotations

import argparse
from dataclasses import replace
import sys

from diffcog.analysis import analyze, analyze_languages, analyze_source_pairs
from diffcog.debug_analysis import (
    build_complexity_debug_for_languages,
    build_language_complexity_debug,
    build_symbol_debug,
    build_symbol_debug_for_languages,
)
from diffcog.diff_input import source_pairs_from_diff
from diffcog.errors import DiffcogError
from diffcog.git import GitError
from diffcog.history import DEFAULT_HISTORY_DAYS, analyze_history_metrics
from diffcog.languages.registry import (
    LANGUAGE_ORDER,
    LanguageSpec,
    get_language_spec,
    get_ruleset,
    list_ruleset_ids,
)
from diffcog.models import (
    AnalysisResult,
    Comparison,
    Endpoint,
    EndpointKind,
    PathFilter,
    Thresholds,
)
from diffcog.report import (
    format_ck_metrics_json,
    format_ck_metrics_text,
    format_delta_totals_json,
    format_delta_totals_text,
    format_history_metrics_json,
    format_history_metrics_text,
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
        description="Measure cognitive complexity introduced by code changes.",
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
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATHSPEC",
        help="include changed files matching a git pathspec",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATHSPEC",
        help="exclude changed files matching a git pathspec",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--delta-totals",
        action="store_true",
        help="print one-line cognitive and CK metric delta totals",
    )
    parser.add_argument(
        "--language",
        choices=["auto", "java", "python", "go"],
        default="auto",
        help="language to analyze",
    )
    report_group = parser.add_mutually_exclusive_group()
    report_group.add_argument(
        "--details", action="store_true", help="include changed file details in text output"
    )
    report_group.add_argument(
        "--hotspots", action="store_true", help="show top complexity hotspots in text output"
    )
    parser.add_argument(
        "--metrics",
        choices=["ck", "history"],
        default=None,
        help="show an alternate metric report",
    )
    parser.add_argument(
        "--history-days",
        type=_positive_int,
        default=DEFAULT_HISTORY_DAYS,
        help="number of recent days to mine for --metrics history",
    )
    parser.add_argument(
        "--ruleset",
        default=None,
        help="complexity rule set to use with an explicit language",
    )
    parser.add_argument(
        "--list-rulesets",
        action="store_true",
        help="list available complexity rule sets and exit",
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
        _validate_report_mode(args)
        if args.list_rulesets:
            print(format_ruleset_list(_selected_language_specs(args.language)), end="")
            return EXIT_OK

        language_specs = _selected_language_specs(args.language)
        if args.language == "auto" and args.ruleset is not None:
            raise ValueError("--ruleset cannot be used with --language auto")

        ruleset = None
        thresholds = Thresholds(max_new=args.max_new, max_delta=args.max_delta)
        path_filter = PathFilter(includes=tuple(args.include), excludes=tuple(args.exclude))
        diff_text = _stdin_diff_text(args)
        if diff_text is not None and args.metrics == "history":
            raise ValueError("--metrics history cannot be used with piped diff input")

        comparison = (
            _stdin_diff_comparison()
            if diff_text is not None
            else resolve_comparison(args.refs, staged=args.staged, unstaged=args.unstaged)
        )

        if diff_text is not None:
            if args.language != "auto":
                ruleset = get_ruleset(language_specs[0], args.ruleset)
            result = _analyze_stdin_diff(
                diff_text,
                comparison,
                language_specs,
                ruleset=ruleset,
                explicit_language=args.language != "auto",
            )
        elif args.metrics == "history":
            result = analyze_history_metrics(
                comparison,
                language_specs,
                days=args.history_days,
                path_filter=path_filter if path_filter.includes or path_filter.excludes else None,
            )
            thresholds = Thresholds()
        elif args.language == "auto":
            ruleset = None
            result = analyze_languages(
                comparison,
                language_specs,
                path_filter=path_filter if path_filter.includes or path_filter.excludes else None,
            )
        else:
            language_spec = language_specs[0]
            ruleset = get_ruleset(language_spec, args.ruleset)
            result = analyze(
                comparison,
                ruleset=ruleset,
                path_filter=path_filter if path_filter.includes or path_filter.excludes else None,
                language=language_spec.language,
            )
    except (ValueError, GitError, DiffcogError) as exc:
        print(f"diffcog: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    try:
        if args.delta_totals:
            if args.json:
                print(format_delta_totals_json(result), end="")
            else:
                print(format_delta_totals_text(result), end="")
        elif args.metrics == "ck":
            if args.json:
                print(format_ck_metrics_json(result), end="")
            else:
                print(format_ck_metrics_text(result), end="")
        elif args.metrics == "history":
            if args.json:
                print(format_history_metrics_json(result), end="")
            else:
                print(format_history_metrics_text(result), end="")
        elif args.debug == "show-snapshots":
            if args.json:
                print(format_snapshot_json(result), end="")
            else:
                print(format_snapshot_text(result), end="")
        elif args.debug == "show-symbols":
            if args.language == "auto":
                symbol_debug = build_symbol_debug_for_languages(result, language_specs)
            else:
                symbol_debug = build_symbol_debug(result, language_specs[0].language)
            if args.json:
                print(format_symbol_json(symbol_debug), end="")
            else:
                print(format_symbol_text(symbol_debug), end="")
        elif args.debug == "show-complexity":
            if args.language == "auto":
                complexity_debug = build_complexity_debug_for_languages(result, language_specs)
            else:
                complexity_debug = build_language_complexity_debug(
                    result, language_specs[0].language, ruleset
                )
            if args.json:
                print(format_complexity_json(complexity_debug), end="")
            else:
                print(format_complexity_text(complexity_debug), end="")
        elif args.json:
            print(format_json(result, thresholds), end="")
        else:
            print(
                format_text(result, thresholds, details=args.details, hotspots=args.hotspots),
                end="",
            )
    except DiffcogError as exc:
        print(f"diffcog: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if hasattr(result, "threshold_failed") and result.threshold_failed(thresholds):
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


def _stdin_diff_text(args: argparse.Namespace) -> str | None:
    if args.refs or args.staged or args.unstaged or args.list_rulesets:
        return None
    try:
        if sys.stdin.isatty():
            return None
        return sys.stdin.read()
    except OSError:
        return None


def _stdin_diff_comparison() -> Comparison:
    return Comparison(
        mode="stdin_diff",
        before=Endpoint(EndpointKind.DIFF, "stdin diff before blobs"),
        after=Endpoint(EndpointKind.DIFF, "stdin diff after blobs"),
    )


def _analyze_stdin_diff(
    diff_text: str,
    comparison: Comparison,
    language_specs: tuple[LanguageSpec, ...],
    *,
    ruleset: object | None,
    explicit_language: bool,
) -> AnalysisResult:
    results = []
    for spec in language_specs:
        active_ruleset = ruleset if explicit_language else spec.language.default_ruleset
        source_pairs = source_pairs_from_diff(diff_text, spec.language.file_extensions)
        results.append(
            analyze_source_pairs(
                comparison,
                source_pairs,
                ruleset=active_ruleset,
                language=spec.language,
            )
        )

    if len(results) == 1:
        return results[0]

    return replace(
        results[0],
        files=[file for result in results for file in result.files],
        source_pairs=[source_pair for result in results for source_pair in result.source_pairs],
        ruleset_id="auto",
        rule_set_ids=tuple(result.ruleset_id for result in results),
        file_deltas=[file_delta for result in results for file_delta in result.file_deltas],
        class_metric_deltas=[
            file_delta for result in results for file_delta in result.class_metric_deltas
        ],
        new_complexity=sum(result.new_complexity for result in results),
        removed_complexity=sum(result.removed_complexity for result in results),
        net_delta=sum(result.net_delta for result in results),
    )


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _selected_language_specs(language: str) -> tuple[LanguageSpec, ...]:
    if language == "auto":
        return LANGUAGE_ORDER
    return (get_language_spec(language),)


def _validate_report_mode(args: argparse.Namespace) -> None:
    if args.metrics is None:
        if args.history_days != DEFAULT_HISTORY_DAYS:
            raise ValueError("--history-days can only be used with --metrics history")
        if args.delta_totals:
            if args.details:
                raise ValueError("--delta-totals cannot be combined with --details")
            if args.hotspots:
                raise ValueError("--delta-totals cannot be combined with --hotspots")
            if args.debug is not None:
                raise ValueError("--delta-totals cannot be combined with --debug")
            if args.list_rulesets:
                raise ValueError("--delta-totals cannot be combined with --list-rulesets")
        return
    if args.delta_totals:
        raise ValueError("--delta-totals cannot be combined with --metrics")
    if args.details:
        raise ValueError("--metrics cannot be combined with --details")
    if args.hotspots:
        raise ValueError("--metrics cannot be combined with --hotspots")
    if args.debug is not None:
        raise ValueError("--metrics cannot be combined with --debug")
    if args.list_rulesets:
        raise ValueError("--metrics cannot be combined with --list-rulesets")
    if args.ruleset is not None:
        raise ValueError("--metrics cannot be combined with --ruleset")
    if args.metrics != "history" and args.history_days != DEFAULT_HISTORY_DAYS:
        raise ValueError("--history-days can only be used with --metrics history")


def format_ruleset_list(language_specs: tuple[LanguageSpec, ...]) -> str:
    if len(language_specs) == 1:
        spec = language_specs[0]
        lines = [
            f"Available {spec.display_name} rule sets:",
            *[f"  {ruleset_id}" for ruleset_id in list_ruleset_ids(spec)],
        ]
        return "\n".join(lines) + "\n"

    lines = ["Available rule sets:"]
    for spec in language_specs:
        lines.append(f"  {spec.display_name}:")
        lines.extend(f"    {ruleset_id}" for ruleset_id in list_ruleset_ids(spec))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
