from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JavaCallable:
    kind: str
    name: str
    class_path: list[str]
    parameter_count: int
    start_line: int
    end_line: int
    node: Any


@dataclass(frozen=True)
class ParsedSnapshot:
    present: bool
    parse_error: bool
    callables: list[JavaCallable]
