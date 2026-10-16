"""证据评分闸门与证据治理测试（Task E 1-8）。"""

from __future__ import annotations

import pytest

from decision_system.engine.weights import WeightTree
from decision_system.evidence.gate import (
    ClaimView,
    GateConfig,
    InMemoryEvidenceResolver,
    ScoreInput,
    SourceView,
    StrictEvidenceGate,
)
from decision_system.evidence.registry import (
    EvidenceGovernanceError,
    detect_and_record_conflict,
    link_claim_indicator,
    link_claim_path,
    register_claim,
    register_source,
    reject_auto_promotion,
    verify_claim,
)
from decision_system.models.entities import ClaimConflict, EvidenceClaim, EvidenceSource
from decision_system.models.enums import ClaimStatus, ScoreValidity, VerificationStatus

from ..conftest import PATH_KEY, SOURCE_ID, VERIFICATION_YEAR

IND = "L3-职业发展|AI工程就业|岗位与实习机会"


def _gate(
    tree: WeightTree,
    *,
    source_status: VerificationStatus = VerificationStatus.VERIFIED,
    years=(VERIFICATION_YEAR,),
    claim_status: ClaimStatus = ClaimStatus.VERIFIED,
    is_candidate: bool = False,
    path_key: str = PATH_KEY,
    indicator_code: str = IND,
    conflicts: set[str] | None = None,
    applicable: bool = True,
    supports: bool = True,
) -> StrictEvidenceGate:
    source = SourceView(SOURCE_ID, source_status, years)
    claim = ClaimView(
        claim_id=1,
        source_id=SOURCE_ID,
        status=claim_status,
        is_candidate=is_candidate,
        supports=supports,
        applicable=applicable,
        path_key=path_key,
        indicator_code=indicator_code,
        applicable_years=years,
    )
    resolver = InMemoryEvidenceResolver(
        sources={SOURCE_ID: source}, claims=[claim], conflicts=conflicts or set()
    )
    return StrictEvidenceGate(resolver, GateConfig())


def _input(score=4, source_id=SOURCE_ID, indicator=IND, path_key=PATH_KEY) -> ScoreInput:
    return ScoreInput(indicator_code=indicator, raw_score=score, source_id=source_id, path_key=path_key)


# ---------------- 1. 评分 1-5 合法性 ----------------
@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
def test_01_valid_scores_1_to_5(tree, score):
    result = _gate(tree).validate(_input(score=score), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.VALID
    assert result.score == score


@pytest.mark.parametrize("score", [0, 6, 99, -1])
def test_01b_out_of_range_rejected(tree, score):
    result = _gate(tree).validate(_input(score=score), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("范围" in r for r in result.reasons)


def test_01c_blank_is_unknown_not_zero(tree):
    result = _gate(tree).validate(_input(score=None), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.UNKNOWN
    assert result.score is None


# ---------------- 2. 非整数评分拒绝 ----------------
@pytest.mark.parametrize("score", [4.5, 0.5, True, "4", "abc", [4]])
def test_02_non_integer_rejected(tree, score):
    result = _gate(tree).validate(_input(score=score), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


def test_02b_float_integer_accepted(tree):
    result = _gate(tree).validate(_input(score=4.0), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.VALID
    assert result.score == 4


# ---------------- 3. 空来源拒绝 ----------------
@pytest.mark.parametrize("source_id", [None, "", "   "])
def test_03_empty_source_rejected(tree, source_id):
    result = _gate(tree).validate(_input(source_id=source_id), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("来源ID为空" in r for r in result.reasons)


# ---------------- 4. 不存在的 source_id 拒绝 ----------------
def test_04_unknown_source_id_rejected(tree):
    result = _gate(tree).validate(
        _input(source_id="SRC-NOT-REGISTERED"), evaluation_year=VERIFICATION_YEAR
    )
    assert result.validity is ScoreValidity.INVALID
    assert any("来源未登记" in r for r in result.reasons)


def test_04b_source_id_non_empty_is_not_sufficient(tree):
    """仅填写非空 source_id 不应使评分自动有效（U-01）。"""
    resolver = InMemoryEvidenceResolver(sources={}, claims=[], conflicts=set())
    gate = StrictEvidenceGate(resolver, GateConfig())
    result = gate.validate(_input(source_id="随便写一个"), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


# ---------------- 5. 来源与路径不匹配 ----------------
def test_05_source_not_applicable_to_path(tree):
    gate = _gate(tree, path_key="OTHER|999|999999|全日制|方向X|2028|统考|一志愿")
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("来源不适用于当前路径" in r for r in result.reasons)


def test_05b_claim_marked_not_applicable(tree):
    gate = _gate(tree, applicable=False)
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


# ---------------- 6. 来源与指标不匹配 ----------------
def test_06_source_does_not_support_indicator(tree):
    """来源真实存在且适用于该路径，但不支持当前指标，也必须拒绝。"""
    other = "L3-成本安排|经济成本|学费及住宿"
    gate = _gate(tree)  # 声明仅支持 IND
    result = gate.validate(_input(indicator=other), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("来源不支持当前指标" in r for r in result.reasons)


# ---------------- 7. 待核验/失效/冲突证据不得进入评分 ----------------
@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.PENDING,
        VerificationStatus.CONFLICT,
        VerificationStatus.INVALID,
        VerificationStatus.UNVERIFIABLE,
        VerificationStatus.UNREGISTERED,
    ],
)
def test_07_unverified_source_rejected(tree, status):
    gate = _gate(tree, source_status=status)
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


@pytest.mark.parametrize(
    "status", [ClaimStatus.CANDIDATE, ClaimStatus.PENDING, ClaimStatus.CONFLICT]
)
def test_07b_unverified_claim_rejected(tree, status):
    gate = _gate(tree, claim_status=status)
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


def test_07c_candidate_mapping_not_auto_promoted(tree):
    """候选证据映射即使来源已核验也不得进入正式评分。"""
    gate = _gate(
        tree, source_status=VerificationStatus.VERIFIED, is_candidate=True
    )
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("候选映射" in r for r in result.reasons)


def test_07d_year_mismatch_rejected(tree):
    gate = _gate(tree, years=(2026, 2027))
    result = gate.validate(_input(), evaluation_year=2028)
    assert result.validity is ScoreValidity.INVALID
    assert any("适用年份" in r for r in result.reasons)


def test_07e_year_unspecified_rejected(tree):
    gate = _gate(tree, years=())
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID


# ---------------- 8. 来源冲突不得自动合并 ----------------
def test_08_conflict_blocks_scoring(tree):
    gate = _gate(tree, conflicts={SOURCE_ID})
    result = gate.validate(_input(), evaluation_year=VERIFICATION_YEAR)
    assert result.validity is ScoreValidity.INVALID
    assert any("冲突" in r for r in result.reasons)


def test_08b_conflict_record_keeps_old_fact(empty_db):
    register_source(
        empty_db, source_id="S-A", title="来源A",
        verification_status=VerificationStatus.VERIFIED, applicable_years=[2028],
    )
    register_source(empty_db, source_id="S-B", title="来源B",
                    verification_status=VerificationStatus.VERIFIED, applicable_years=[2028])
    old = register_claim(empty_db, source_id="S-A", statement="2027 统考计划 40 人",
                         applicable_years=[2027])
    new = register_claim(empty_db, source_id="S-B", statement="2027 统考计划 68 人",
                         applicable_years=[2027])
    empty_db.flush()

    detect_and_record_conflict(
        empty_db, new_claim_id=new.id, existing_claim_id=old.id,
        description="同一路径同一年度名额口径冲突（40 vs 68）",
    )
    empty_db.flush()

    # 旧事实不被覆盖
    old_after = empty_db.get(EvidenceClaim, old.id)
    assert old_after.statement == "2027 统考计划 40 人"
    assert old_after.applicable_years == [2027]
    # 新声明被标记为冲突，且仍是候选（不得自动升级）
    new_after = empty_db.get(EvidenceClaim, new.id)
    assert new_after.status is ClaimStatus.CONFLICT
    assert new_after.is_candidate is True
    conflicts = empty_db.query(ClaimConflict).all()
    assert len(conflicts) == 1
    assert conflicts[0].resolved is False


def test_08c_verify_claim_requires_actor_and_basis(empty_db):
    register_source(empty_db, source_id="S-C", title="来源C")
    claim = register_claim(empty_db, source_id="S-C", statement="某事实")
    empty_db.flush()
    with pytest.raises(EvidenceGovernanceError):
        verify_claim(empty_db, claim.id, actor="", basis="x")
    with pytest.raises(EvidenceGovernanceError):
        verify_claim(empty_db, claim.id, actor="u", basis="")


def test_08d_manual_verification_is_only_legal_promotion(empty_db):
    register_source(empty_db, source_id="S-D", title="来源D")
    claim = register_claim(empty_db, source_id="S-D", statement="2028 目录已发布证据",
                           applicable_years=[2028])
    empty_db.flush()
    assert claim.is_candidate is True
    verify_claim(empty_db, claim.id, actor="reviewer", basis="已取得 2028 招生目录原件 PDF",
                 applicable_years=[2028])
    empty_db.flush()
    reject_auto_promotion(claim)
    assert claim.status is ClaimStatus.VERIFIED
    assert claim.is_candidate is False


def test_08e_register_claim_requires_registered_source(empty_db):
    with pytest.raises(EvidenceGovernanceError):
        register_claim(empty_db, source_id="S-MISSING", statement="无源之声明")


def test_08f_placeholder_source_recorded_as_unregistered(empty_db):
    src = register_source(
        empty_db, source_id="SRC-NA", title="（占位）尚未登记任何来源",
        verification_status=VerificationStatus.UNREGISTERED, is_placeholder=True,
    )
    empty_db.flush()
    assert src.verification_status is VerificationStatus.UNREGISTERED
    assert empty_db.get(EvidenceSource, src.id).is_placeholder is True
