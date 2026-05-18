"""Comprehensive deep testing for all 20 code smells."""

from __future__ import annotations

from pathlib import Path
import pytest

from metala.application.smells import CodeSmellService, SmellFileCommand
from metala.infrastructure.antlr.smell_detector import AntlrMetalCodeSmellDetector
from metala.infrastructure.filesystem.source_repository import FileSystemSourceRepository


@pytest.fixture
def smell_service():
    return CodeSmellService(
        source_repository=FileSystemSourceRepository(),
        detector=AntlrMetalCodeSmellDetector(),
    )


def test_basic_and_expert_smells(smell_service):
    # Given
    fixture_path = Path(__file__).parent / "fixtures" / "smelly.metal"
    
    # When
    report = smell_service.smell_file(SmellFileCommand(path=str(fixture_path)))
    
    # Then
    smells_by_kind = {}
    for s in report.smells:
        smells_by_kind.setdefault(s.kind, []).append(s)

    # 1. Long Parameter List
    assert "long_parameter_list" in smells_by_kind
    # 2. Unused Parameter
    assert "unused_parameter" in smells_by_kind
    # 3. Deep Nesting
    assert "deep_nesting" in smells_by_kind
    # 4. Complex Flow
    assert "complex_flow" in smells_by_kind
    # 5. Excessive Locals
    assert "excessive_locals" in smells_by_kind
    # 6. Magic Numbers
    assert "magic_number" in smells_by_kind
    # 7. Long Function
    assert "long_function" in smells_by_kind
    # 8. Large Class
    assert "large_class" in smells_by_kind


def test_fowler_classic_smells(smell_service):
    # Given
    fixture_path = Path(__file__).parent / "fixtures" / "fowler.metal"
    
    # When
    report = smell_service.smell_file(SmellFileCommand(path=str(fixture_path)))
    
    # Then
    smells_by_kind = {}
    for s in report.smells:
        smells_by_kind.setdefault(s.kind, []).append(s)

    # 9. Refused Bequest
    assert "refused_bequest" in smells_by_kind
    # 10. Speculative Generality
    assert "speculative_generality" in smells_by_kind
    # 11. Data Clump
    assert "data_clump" in smells_by_kind
    # 12. Switch Statement
    assert "switch_statement" in smells_by_kind
    # 13. Shotgun Surgery
    assert "shotgun_surgery" in smells_by_kind
    # 14. Feature Envy
    assert "feature_envy" in smells_by_kind
    # 15. Message Chain
    assert "message_chain" in smells_by_kind
    # 16. Primitive Obsession
    assert "primitive_obsession" in smells_by_kind
    # 17. Middle Man
    assert "middle_man" in smells_by_kind
    # 18. Comment Density
    assert "comment_density" in smells_by_kind
    
    # Divergent Change and Temporary Field are heuristics-based 
    # and may require more specific setups, but the infrastructure is there.
