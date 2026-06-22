"""Go parsing and analysis."""

from diffcog.languages.base import LanguageDefinition
from diffcog.languages.go.complexity import DEFAULT_GO_RULESET, score_callable
from diffcog.languages.go.parser import parse_snapshot
from diffcog.languages.go.resolver import resolve_semantics

GO_LANGUAGE = LanguageDefinition(
    id="go",
    file_extensions=(".go",),
    default_ruleset=DEFAULT_GO_RULESET,
    parse_snapshot=parse_snapshot,
    resolve_semantics=resolve_semantics,
    score_callable=score_callable,
)

__all__ = ["GO_LANGUAGE", "parse_snapshot"]
