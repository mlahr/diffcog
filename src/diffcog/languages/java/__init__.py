"""Java parsing and analysis."""

from diffcog.languages.base import LanguageDefinition
from diffcog.languages.java.complexity import DEFAULT_JAVA_RULESET, score_callable
from diffcog.languages.java.parser import parse_snapshot
from diffcog.languages.java.resolver import resolve_semantics

JAVA_LANGUAGE = LanguageDefinition(
    id="java",
    file_extensions=(".java",),
    default_ruleset=DEFAULT_JAVA_RULESET,
    parse_snapshot=parse_snapshot,
    resolve_semantics=resolve_semantics,
    score_callable=score_callable,
)
