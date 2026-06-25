from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EndpointKind(str, Enum):
    REF = "ref"
    WORKTREE = "worktree"
    INDEX = "index"
    DIFF = "diff"


@dataclass(frozen=True)
class Endpoint:
    kind: EndpointKind
    label: str


@dataclass(frozen=True)
class Comparison:
    mode: str
    before: Endpoint
    after: Endpoint


@dataclass(frozen=True)
class PathFilter:
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangedFile:
    status: str
    path: str
    old_path: str
    old_ranges: list["LineRange"]
    new_ranges: list["LineRange"]
    language_id: str = ""


@dataclass(frozen=True)
class LineRange:
    start: int
    end: int


@dataclass(frozen=True)
class SourcePair:
    file: ChangedFile
    before: str | None
    after: str | None


@dataclass(frozen=True)
class CallableSymbol:
    kind: str
    name: str
    namespace_path: list[str]
    parameter_count: int
    start_line: int
    end_line: int
    node: Any


@dataclass(frozen=True)
class ClassSymbol:
    name: str
    namespace_path: list[str]
    kind: str
    start_line: int
    end_line: int
    node: Any


@dataclass(frozen=True)
class ParsedSnapshot:
    present: bool
    parse_error: bool
    callables: list[CallableSymbol]
    classes: list[ClassSymbol] = field(default_factory=list)


@dataclass(frozen=True)
class ComplexityContribution:
    rule_id: str
    line: int
    points: int
    message: str


@dataclass(frozen=True)
class ComplexityResult:
    score: int
    contributions: list[ComplexityContribution]


@dataclass(frozen=True)
class CallableComplexityDelta:
    status: str
    before_callable: CallableSymbol | None
    after_callable: CallableSymbol | None
    before_result: ComplexityResult | None
    after_result: ComplexityResult | None
    before_score: int
    after_score: int
    delta: int


@dataclass(frozen=True)
class FileComplexityDelta:
    file: ChangedFile
    callables: list[CallableComplexityDelta]
    unmapped_before_ranges: list[LineRange]
    unmapped_after_ranges: list[LineRange]


@dataclass(frozen=True)
class ClassMetrics:
    cbo: int
    lcom: int
    wmc: int


@dataclass(frozen=True)
class ClassMetricsDelta:
    status: str
    before_class: ClassSymbol | None
    after_class: ClassSymbol | None
    before_metrics: ClassMetrics | None
    after_metrics: ClassMetrics | None
    delta: ClassMetrics


@dataclass(frozen=True)
class FileClassMetricsDelta:
    file: ChangedFile
    before_present: bool
    after_present: bool
    before_parse_error: bool
    after_parse_error: bool
    classes: list[ClassMetricsDelta]


@dataclass(frozen=True)
class HistoryHotspot:
    path: str
    language_id: str
    commit_count: int
    changed_lines: int
    current_complexity: int
    score: int


@dataclass(frozen=True)
class ChangeCoupling:
    left_path: str
    right_path: str
    shared_commit_count: int
    left_commit_count: int
    right_commit_count: int
    coupling_percent: int


@dataclass(frozen=True)
class HistoryMetricsResult:
    comparison: Comparison
    history_ref: str
    days: int
    language_ids: tuple[str, ...]
    hotspots: list[HistoryHotspot]
    change_couplings: list[ChangeCoupling]


@dataclass(frozen=True)
class Thresholds:
    max_new: int | None = None
    max_delta: int | None = None


@dataclass(frozen=True)
class AnalysisResult:
    comparison: Comparison
    files: list[ChangedFile]
    source_pairs: list[SourcePair]
    ruleset_id: str = "java.default"
    rule_set_ids: tuple[str, ...] = ("java.default",)
    file_deltas: list[FileComplexityDelta] = field(default_factory=list)
    class_metric_deltas: list[FileClassMetricsDelta] = field(default_factory=list)
    new_complexity: int = 0
    removed_complexity: int = 0
    net_delta: int = 0

    def threshold_failed(self, thresholds: Thresholds) -> bool:
        if thresholds.max_new is not None and self.new_complexity > thresholds.max_new:
            return True
        if thresholds.max_delta is not None and self.net_delta > thresholds.max_delta:
            return True
        return False
