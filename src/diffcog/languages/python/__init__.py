"""Python parsing and analysis."""

from diffcog.languages.base import LanguageDefinition
from diffcog.languages.python.complexity import DEFAULT_PYTHON_RULESET, score_callable
from diffcog.languages.python.parser import parse_snapshot
from diffcog.languages.python.resolver import resolve_semantics

PYTHON_LANGUAGE = LanguageDefinition(
    id="python",
    file_extensions=(".py",),
    default_ruleset=DEFAULT_PYTHON_RULESET,
    parse_snapshot=parse_snapshot,
    resolve_semantics=resolve_semantics,
    score_callable=score_callable,
)

__all__ = ["PYTHON_LANGUAGE", "parse_snapshot"]
