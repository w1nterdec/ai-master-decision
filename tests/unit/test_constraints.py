"""硬约束引擎测试（Task E 18、19）。"""

from __future__ import annotations

from decision_system.engine.constraints import (
    HardConstraintFacts,
    evaluate_hard_constraints,
)
from decision_system.models.enums import (
    ComparisonStatus,
    PathEligibility,
    Qualification2028,
    TriState,
    Verification2028,
)


def test_18_exclusion_effective():
    outcome = evaluate_hard_constraints(
        HardConstraintFacts(
            full_time_ok=TriState.NO,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.YES,
        )
    )
    assert outcome.eligibility is PathEligibility.EXCLUDED
    assert outcome.is_excluded is True
    from decision_system.engine.constraints import forced_status_for

    assert forced_status_for(outcome) is ComparisonStatus.EXCLUDED


def test_18b_any_no_excludes():
    from dataclasses import replace

    for field in ("full_time_ok", "program_code_acceptable", "other_constraints_ok"):
        facts = HardConstraintFacts(
            full_time_ok=TriState.YES,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.YES,
        )
        outcome = evaluate_hard_constraints(replace(facts, **{field: TriState.NO}))
        assert outcome.eligibility is PathEligibility.EXCLUDED, field


def test_18c_unknown_yields_pending():
    outcome = evaluate_hard_constraints(
        HardConstraintFacts(
            full_time_ok=TriState.YES,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.UNKNOWN,
        )
    )
    assert outcome.eligibility is PathEligibility.PENDING
    assert outcome.qualification_2028 is Qualification2028.NOT_CONFIRMED


def test_18d_all_yes_is_historical_candidate():
    outcome = evaluate_hard_constraints(
        HardConstraintFacts(
            full_time_ok=TriState.YES,
            program_code_acceptable=TriState.YES,
            other_constraints_ok=TriState.YES,
        )
    )
    assert outcome.eligibility is PathEligibility.CANDIDATE
    # 历史候选 ≠ 2028 正式资格
    assert outcome.qualification_2028 is Qualification2028.NOT_CONFIRMED


def test_19_2028_unknown_never_confirmed():
    """2028 资格未知时不得标记为已确认。"""
    facts = HardConstraintFacts(
        full_time_ok=TriState.YES,
        program_code_acceptable=TriState.YES,
        other_constraints_ok=TriState.YES,
        verification_2028=Verification2028.PENDING,
    )
    outcome = evaluate_hard_constraints(facts)
    assert outcome.qualification_2028 is not Qualification2028.CONFIRMED


def test_19b_confirmed_requires_verification_and_evidence():
    facts = HardConstraintFacts(
        full_time_ok=TriState.YES,
        program_code_acceptable=TriState.YES,
        other_constraints_ok=TriState.YES,
        verification_2028=Verification2028.VERIFIED,
        has_verified_2028_evidence=True,
    )
    outcome = evaluate_hard_constraints(facts)
    assert outcome.qualification_2028 is Qualification2028.CONFIRMED
    assert outcome.confirmed_2028 is True


def test_19c_verified_flag_without_evidence_not_confirmed():
    """仅标记"已核验2028"但缺少已核验 2028 来源证据，仍不得确认。"""
    facts = HardConstraintFacts(
        full_time_ok=TriState.YES,
        program_code_acceptable=TriState.YES,
        other_constraints_ok=TriState.YES,
        verification_2028=Verification2028.VERIFIED,
        has_verified_2028_evidence=False,
    )
    outcome = evaluate_hard_constraints(facts)
    assert outcome.qualification_2028 is Qualification2028.NOT_CONFIRMED


def test_19d_excluded_path_not_met():
    facts = HardConstraintFacts(
        full_time_ok=TriState.NO,
        verification_2028=Verification2028.VERIFIED,
        has_verified_2028_evidence=True,
    )
    outcome = evaluate_hard_constraints(facts)
    assert outcome.qualification_2028 is Qualification2028.NOT_MET


def test_imported_paths_all_pending_2028(db):
    """导入的 10 条路径均不得被判定为 2028 资格已确认。"""
    from decision_system.models.entities import AdmissionPath
    from decision_system.services.decision_service import (
        _has_verified_2028_evidence,
        path_context_from_db,
    )

    paths = db.query(AdmissionPath).all()
    assert len(paths) == 10
    for path in paths:
        ctx = path_context_from_db(db, path)
        assert path.verification_2028 is not Verification2028.VERIFIED
        assert _has_verified_2028_evidence(db, path) is False
        assert ctx.facts.verification_2028 is not Verification2028.VERIFIED
