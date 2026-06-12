from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
class Thresholds:
    max_new: int | None = None
    max_delta: int | None = None


@dataclass(frozen=True)
class AnalysisResult:
    comparison: Comparison
    files: list[ChangedFile]
    source_pairs: list[SourcePair]
    new_complexity: int = 0
    removed_complexity: int = 0
    net_delta: int = 0

    def threshold_failed(self, thresholds: Thresholds) -> bool:
        if thresholds.max_new is not None and self.new_complexity > thresholds.max_new:
            return True
        if thresholds.max_delta is not None and self.net_delta > thresholds.max_delta:
            return True
        return False
