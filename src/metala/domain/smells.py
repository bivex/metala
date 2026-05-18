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
