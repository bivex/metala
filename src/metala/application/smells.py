"""Use cases for code smell detection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metala.domain.ports import MetalCodeSmellDetector, SourceRepository, SmellReportRenderer
from metala.domain.smells import SmellBundle, SourceSmellReport


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
    html: str | None = None

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
    index_html: str | None = None

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
    renderer: SmellReportRenderer | None = None

    def smell_file(self, command: SmellFileCommand) -> SourceSmellReportDTO:
        source_unit = self.source_repository.load_file(command.path)
        report = self.detector.detect(source_unit)
        html = self.renderer.render_file(report) if self.renderer else None
        return self._map_report(report, html)

    def smell_directory(self, command: SmellDirectoryCommand) -> SmellBundleDTO:
        source_units = tuple(self.source_repository.list_metal_sources(command.root_path))
        domain_reports = tuple(self.detector.detect(source_unit) for source_unit in source_units)
        
        reports_dto = tuple(
            self._map_report(
                report, 
                self.renderer.render_file(report) if self.renderer else None
            ) 
            for report in domain_reports
        )
        
        bundle = SmellBundle(
            root_path=str(Path(command.root_path).expanduser().resolve()),
            reports=domain_reports,
        )
        
        index_html = self.renderer.render_bundle(bundle) if self.renderer else None
        
        return SmellBundleDTO(
            root_path=bundle.root_path,
            reports=reports_dto,
            total_smell_count=bundle.total_smell_count,
            index_html=index_html,
        )

    def _map_report(self, report: SourceSmellReport, html: str | None = None) -> SourceSmellReportDTO:
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
            html=html,
        )
