"""Tests for code smell detection."""

from __future__ import annotations

from pathlib import Path

from metala.application.smells import CodeSmellService, SmellFileCommand, SmellDirectoryCommand
from metala.infrastructure.antlr.smell_detector import AntlrMetalCodeSmellDetector
from metala.infrastructure.filesystem.source_repository import FileSystemSourceRepository


def test_smell_file_detects_all_smells():
    # Given
    fixture_path = Path(__file__).parent / "fixtures" / "smelly.metal"
    service = CodeSmellService(
        source_repository=FileSystemSourceRepository(),
        detector=AntlrMetalCodeSmellDetector(),
    )

    # When
    report = service.smell_file(SmellFileCommand(path=str(fixture_path)))

    # Then
    kinds = {smell.kind for smell in report.smells}
    assert "long_parameter_list" in kinds
    assert "deep_nesting" in kinds
    assert "complex_flow" in kinds
    assert "long_function" in kinds
    assert "unused_parameter" in kinds
    assert "excessive_locals" in kinds
    assert "magic_number" in kinds
    assert "large_class" in kinds

    # Verify unused parameters specific
    unused_params = [s.message for s in report.smells if s.kind == "unused_parameter"]
    assert any("p2" in msg for msg in unused_params)
    assert not any("p1" in msg for msg in unused_params)

    # Verify magic numbers
    magic_numbers = [s.message for s in report.smells if s.kind == "magic_number"]
    assert any("3.14" in msg for msg in magic_numbers)
    # Ensure MY_PI definition is NOT flagged
    assert not any("3.14159" in msg for msg in magic_numbers)


def test_smell_directory_scans_all_files():
    # Given
    fixtures_root = Path(__file__).parent / "fixtures"
    service = CodeSmellService(
        source_repository=FileSystemSourceRepository(),
        detector=AntlrMetalCodeSmellDetector(),
    )

    # When
    bundle = service.smell_directory(SmellDirectoryCommand(root_path=str(fixtures_root)))

    # Then
    assert bundle.total_smell_count >= 4
    assert len(bundle.reports) >= 3  # control_flow.metal, valid.metal, smelly.metal
    smelly_report = next(r for r in bundle.reports if "smelly.metal" in r.source_location)
    assert smelly_report.smell_count >= 4
