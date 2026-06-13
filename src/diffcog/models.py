from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diffcog.languages.java.complexity import ComplexityResult
    from diffcog.languages.java.models import JavaCallable


class EndpointKind(str, Enum):
    REF = "ref"
    WORKTREE = "worktree"
    INDEX = "index"


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
class ChangedFile:
    status: str
    path: str
    old_path: str
    old_ranges: list["LineRange"]
    new_ranges: list["LineRange"]


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
class CallableComplexityDelta:
    status: str
    before_callable: JavaCallable | None
    after_callable: JavaCallable | None
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
class Thresholds:
    max_new: int | None = None
    max_delta: int | None = None


@dataclass(frozen=True)
class AnalysisResult:
    comparison: Comparison
    files: list[ChangedFile]
    source_pairs: list[SourcePair]
    file_deltas: list[FileComplexityDelta] = field(default_factory=list)
    new_complexity: int = 0
    removed_complexity: int = 0
    net_delta: int = 0

    def threshold_failed(self, thresholds: Thresholds) -> bool:
        if thresholds.max_new is not None and self.new_complexity > thresholds.max_new:
            return True
        if thresholds.max_delta is not None and self.net_delta > thresholds.max_delta:
            return True
        return False
