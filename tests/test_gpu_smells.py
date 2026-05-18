import pytest
from metala.domain.model import SourceUnit, SourceUnitId
from metala.domain.smells import SmellKind
from metala.infrastructure.antlr.smell_detector import AntlrMetalCodeSmellDetector, SmellThresholds

def test_gpu_specific_smells():
    detector = AntlrMetalCodeSmellDetector()
    with open("tests/fixtures/gpu_smelly.metal", "r") as f:
        source = SourceUnit(
            identifier=SourceUnitId("gpu_smelly"),
            location="gpu_smelly.metal",
            content=f.read()
        )
    
    report = detector.detect(source)
    kinds = [s.kind for s in report.smells]
    
    # Memory Smells
    assert SmellKind.EXCESSIVE_THREADGROUP_ALLOCATION in kinds
    assert SmellKind.THREADGROUP_BANK_CONFLICT in kinds
    assert SmellKind.NON_COALESCED_ACCESS in kinds
    
    # Precision Smells
    assert SmellKind.HALF_PRECISION_NEGLECT in kinds
    
    # Synchronization Smells
    assert SmellKind.THREADGROUP_BARRIER_OVERUSE in kinds
    assert SmellKind.SIMDGROUP_OPPORTUNITY_MISSED in kinds
    
    # Control Flow Smells
    assert SmellKind.DIVERGENT_BRANCH in kinds
    assert SmellKind.DIVERGENT_TEXTURE_SAMPLE in kinds

def test_custom_thresholds():
    thresholds = SmellThresholds(threadgroup_limit_kb=64)
    detector = AntlrMetalCodeSmellDetector(thresholds=thresholds)
    with open("tests/fixtures/gpu_smelly.metal", "r") as f:
        source = SourceUnit(
            identifier=SourceUnitId("gpu_smelly"),
            location="gpu_smelly.metal",
            content=f.read()
        )
    
    report = detector.detect(source)
    # 32KB shared array should NOT trigger with 64KB threshold
    assert not any(s.kind == SmellKind.EXCESSIVE_THREADGROUP_ALLOCATION for s in report.smells)
