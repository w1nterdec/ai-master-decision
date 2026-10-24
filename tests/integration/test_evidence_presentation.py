from __future__ import annotations

import shutil

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from decision_system.engine.pipeline import EngineConfig
from decision_system.models.entities import (
    AdmissionPath,
    ClaimConflict,
    ClaimPathLink,
    EvidenceClaim,
    EvidenceSource,
)
from decision_system.models.enums import VerificationStatus
from decision_system.services import view_service
from decision_system.ui.decision_view import load_path_rows


@pytest.fixture
def presentation_session(tmp_path, research_migrated_db):
    path = tmp_path / "presentation.db"
    shutil.copy2(research_migrated_db, path)
    engine = create_engine(f"sqlite:///{path}")
    with sessionmaker(bind=engine)() as session:
        yield session
    engine.dispose()


def test_invalidated_sources_do_not_remain_school_strengths(presentation_session):
    session = presentation_session
    for source in session.scalars(select(EvidenceSource)):
        source.verification_status = VerificationStatus.INVALID
    session.flush()
    summaries = view_service.load_path_summaries(
        session, load_path_rows(session, EngineConfig())
    )
    schools = view_service.build_school_summaries(session, summaries)
    assert all(not school.strengths for school in schools)


def test_unresolved_conflict_downgrades_both_sides_and_counts(presentation_session):
    session = presentation_session
    path = session.scalar(
        select(AdmissionPath).where(
            AdmissionPath.path_key == "BUPT|005|085410|全日制|方向01|2028|统考|一志愿"
        )
    )
    evidence = view_service.build_evidence_summary(session, path)
    verified = [it for it in evidence.items if it.status == "已核验"]
    assert verified
    links = session.scalars(
        select(ClaimPathLink).where(ClaimPathLink.path_id == path.id)
    ).all()
    cids = [
        next(
            link.claim_id
            for link in links
            if session.get(EvidenceClaim, link.claim_id).statement == item.statement
        )
        for item in verified[:2]
    ]
    session.add(
        ClaimConflict(
            claim_id=cids[0],
            conflicting_claim_id=cids[1],
            description="测试冲突",
            resolved=False,
        )
    )
    session.flush()
    evidence = view_service.build_evidence_summary(session, path)
    assert evidence.conflicts == 1
    assert evidence.state == "存在冲突"
    for original in verified[:2]:
        item = next(it for it in evidence.items if it.statement == original.statement)
        fact = view_service._fact_from_claim(item)
        assert fact.grade == "B 待核验研究资料"
        assert "冲突" in fact.limitation
