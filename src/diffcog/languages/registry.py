from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from diffcog.languages.base import LanguageDefinition
from diffcog.languages.go import GO_LANGUAGE
from diffcog.languages.go.complexity import GO_RULESETS
from diffcog.languages.java import JAVA_LANGUAGE
from diffcog.languages.java.complexity import JAVA_RULESETS
from diffcog.languages.python import PYTHON_LANGUAGE
from diffcog.languages.python.complexity import PYTHON_RULESETS


@dataclass(frozen=True)
class LanguageSpec:
    id: str
    display_name: str
    language: LanguageDefinition
    rule_sets: dict[str, Any]


JAVA_SPEC = LanguageSpec(
    id="java",
    display_name="Java",
    language=JAVA_LANGUAGE,
    rule_sets=JAVA_RULESETS,
)

PYTHON_SPEC = LanguageSpec(
    id="python",
    display_name="Python",
    language=PYTHON_LANGUAGE,
    rule_sets=PYTHON_RULESETS,
)

GO_SPEC = LanguageSpec(
    id="go",
    display_name="Go",
    language=GO_LANGUAGE,
    rule_sets=GO_RULESETS,
)

LANGUAGE_SPECS = {
    JAVA_SPEC.id: JAVA_SPEC,
    PYTHON_SPEC.id: PYTHON_SPEC,
    GO_SPEC.id: GO_SPEC,
}

LANGUAGE_ORDER = (JAVA_SPEC, PYTHON_SPEC, GO_SPEC)


def get_language_spec(language_id: str) -> LanguageSpec:
    try:
        return LANGUAGE_SPECS[language_id]
    except KeyError as exc:
        available = ", ".join(sorted(LANGUAGE_SPECS))
        raise ValueError(f"unknown language '{language_id}' (available: {available})") from exc


def get_ruleset(spec: LanguageSpec, ruleset_id: str | None) -> Any:
    active_ruleset_id = ruleset_id or spec.language.default_ruleset.id
    try:
        return spec.rule_sets[active_ruleset_id]
    except KeyError as exc:
        available = ", ".join(list_ruleset_ids(spec))
        raise ValueError(
            f"unknown {spec.display_name} rule set '{active_ruleset_id}' "
            f"(available: {available})"
        ) from exc


def list_ruleset_ids(spec: LanguageSpec) -> list[str]:
    return sorted(spec.rule_sets)
