"""Use cases for code smell detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metala.domain.ports import MetalCodeSmellDetector, SourceRepository
from metala.domain.smells import SourceSmellReport


@dataclass(frozen=True, slots=True)
class SmellFileCommand:
    path: str


@dataclass(frozen=True, slots=True)
class SmellDirectoryCommand:
    root_path: str


@dataclass(frozen=True, slots=True)
class CodeSmellDTO:
    kind: str
    message: str
    line: int
    column: int
    context: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "context": self.context,
        }


@dataclass(frozen=True, slots=True)
class SourceSmellReportDTO:
    source_location: str
    smells: tuple[CodeSmellDTO, ...]
    smell_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "source_location": self.source_location,
            "smells": [smell.to_dict() for smell in self.smells],
            "smell_count": self.smell_count,
        }


@dataclass(frozen=True, slots=True)
class SmellBundleDTO:
    root_path: str
    reports: tuple[SourceSmellReportDTO, ...]
    total_smell_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "root_path": self.root_path,
            "reports": [report.to_dict() for report in self.reports],
            "total_smell_count": self.total_smell_count,
        }


@dataclass(slots=True)
class CodeSmellService:
    source_repository: SourceRepository
    detector: MetalCodeSmellDetector

    def smell_file(self, command: SmellFileCommand) -> SourceSmellReportDTO:
        source_unit = self.source_repository.load_file(command.path)
        report = self.detector.detect(source_unit)
        return self._map_report(report)

    def smell_directory(self, command: SmellDirectoryCommand) -> SmellBundleDTO:
        source_units = tuple(self.source_repository.list_metal_sources(command.root_path))
        reports = tuple(self._map_report(self.detector.detect(source_unit)) for source_unit in source_units)
        return SmellBundleDTO(
            root_path=str(Path(command.root_path).expanduser().resolve()),
            reports=reports,
            total_smell_count=sum(report.smell_count for report in reports),
        )

    def _map_report(self, report: SourceSmellReport) -> SourceSmellReportDTO:
        smells = tuple(
            CodeSmellDTO(
                kind=smell.kind.value,
                message=smell.message,
                line=smell.line,
                column=smell.column,
                context=smell.context,
            )
            for smell in report.smells
        )
        return SourceSmellReportDTO(
            source_location=report.source_location,
            smells=smells,
            smell_count=len(smells),
        )
