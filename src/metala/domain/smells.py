"""Domain model for code smells."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SmellKind(StrEnum):
    LONG_FUNCTION = "long_function"
    LONG_PARAMETER_LIST = "long_parameter_list"
    LARGE_CLASS = "large_class"
    DEEP_NESTING = "deep_nesting"
    COMPLEX_FLOW = "complex_flow"
    MAGIC_NUMBER = "magic_number"
    UNUSED_PARAMETER = "unused_parameter"
    EXCESSIVE_LOCALS = "excessive_locals"
    SWITCH_STATEMENT = "switch_statement"
    MESSAGE_CHAIN = "message_chain"
    DATA_CLUMP = "data_clump"
    FEATURE_ENVY = "feature_envy"
    PRIMITIVE_OBSESSION = "primitive_obsession"
    MIDDLE_MAN = "middle_man"
    SPECULATIVE_GENERALITY = "speculative_generality"
    DIVERGENT_CHANGE = "divergent_change"
    SHOTGUN_SURGERY = "shotgun_surgery"
    TEMPORARY_FIELD = "temporary_field"
    REFUSED_BEQUEST = "refused_bequest"
    COMMENT_DENSITY = "comment_density"
    DIVERGENT_BRANCH = "divergent_branch"
    RESOURCE_OVERLOAD = "resource_overload"
    ATOMIC_CONTENTION = "atomic_contention"


@dataclass(frozen=True, slots=True)
class CodeSmell:
    kind: SmellKind
    message: str
    location: str
    line: int
    column: int
    severity: str = "warning"
    context: str | None = None


@dataclass(frozen=True, slots=True)
class SourceSmellReport:
    source_location: str
    smells: tuple[CodeSmell, ...]

    @property
    def smell_count(self) -> int:
        return len(self.smells)
