from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from diffcog.models import CallableSymbol, ComplexityResult, ParsedSnapshot


@dataclass(frozen=True)
class LanguageDefinition:
    id: str
    file_extensions: tuple[str, ...]
    default_ruleset: Any
    parse_snapshot: Callable[[str | None], ParsedSnapshot]
    resolve_semantics: Callable[[list[CallableSymbol]], Any]
    score_callable: Callable[[CallableSymbol, Any, Any], ComplexityResult]
