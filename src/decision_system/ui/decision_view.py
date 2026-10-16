"""页面共享的决策视图：统一调用 Phase 4.0 引擎，保证页面之间数据一致。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.engine.pipeline import EngineConfig, PathDecision
from decision_system.models.entities import AdmissionPath, Indicator, ScoreRecord
from decision_system.services.decision_service import (
    build_engine,
    path_context_from_db,
)


@dataclass(frozen=True)
class PathRow:
    path: AdmissionPath
    decision: PathDecision

    @property
    def path_key(self) -> str:
        return self.path.path_key

    @property
    def school_name(self) -> str:
        return self.path.school.name if self.path.school else ""

    @property
    def college_name(self) -> str:
        return self.path.college.name or "" if self.path.college else ""

    @property
    def college_code(self) -> str:
        return self.path.college.college_code if self.path.college else ""

    @property
    def program_code(self) -> str:
        return self.path.program.program_code if self.path.program else ""


def load_path_rows(
    session: Session, config: EngineConfig | None = None, *, profile_code: str | None = None
) -> list[PathRow]:
    """读取全部路径并逐条调用引擎（硬约束 + 覆盖率 + 双目标）。"""
    paths = session.execute(select(AdmissionPath).order_by(AdmissionPath.id)).scalars().all()
    if not paths:
        return []
    engine = build_engine(session, config, profile_code=profile_code)
    rows: list[PathRow] = []
    for p in paths:
        decision = engine.evaluate(path_context_from_db(session, p))
        rows.append(PathRow(path=p, decision=decision))
    return rows


def filter_path_rows(
    rows: Sequence[PathRow],
    *,
    school: str | None = None,
    college: str | None = None,
    program_code: str | None = None,
) -> list[PathRow]:
    """按学校 / 学院 / 专业代码筛选（纯函数，可单测）。"""

    def keep(r: PathRow) -> bool:
        if school and r.school_name != school:
            return False
        if college and f"{r.college_name}（{r.college_code}）" != college and r.college_name != college:
            return False
        if program_code and r.program_code != program_code:
            return False
        return True

    return [r for r in rows if keep(r)]


def row_to_dict(r: PathRow) -> dict[str, Any]:
    d = r.decision
    base = d.base
    return {
        "路径标识": r.path.legacy_path_id or r.path_key,
        "学校": r.school_name,
        "学院": f"{r.college_name}（{r.college_code}）" if r.college_name else r.college_code,
        "专业代码": r.program_code,
        "学习方式": str(r.path.study_mode),
        "招生方向": r.path.direction or "暂无数据",
        "招生年份": r.path.admission_year,
        "招生方式": str(r.path.admission_method),
        "路径角色": str(r.path.path_kind),
        "2028资格核验": str(r.path.verification_2028),
        "硬约束状态": str(d.eligibility),
        "2028正式资格": str(d.qualification_2028),
        "数据完整度": f"{base.valid_count}/{base.total_count}",
        "有效覆盖率": round(base.weight_coverage, 4),
    }


def missing_indicators(session: Session, path: AdmissionPath) -> list[str]:
    """列出该路径尚无有效评分的三级指标。"""
    scored = {
        sr.indicator_id: sr.raw_score
        for sr in session.execute(
            select(ScoreRecord).where(ScoreRecord.path_id == path.id)
        ).scalars().all()
    }
    leaves = session.execute(
        select(Indicator).where(Indicator.level == 3).order_by(Indicator.sort_order)
    ).scalars().all()
    return [f"{i.code} · {i.name}" for i in leaves if scored.get(i.id) is None]


def comparable_count(rows: Sequence[PathRow]) -> int:
    """可比较路径数（硬约束通过且基础覆盖率达标且状态为可比较）。"""
    return sum(1 for r in rows if str(r.decision.base.status).startswith("可比较"))


def scenario_summary(rows: Sequence[PathRow]) -> dict[str, list[tuple[str, Any, str]]]:
    """{情景: [(路径标识, 分数, 状态), ...]}，仅用于展示；证据不足时分数为 None。"""
    out: dict[str, list[tuple[str, Any, str]]] = {}
    for r in rows:
        for code, agg in r.decision.scenarios.items():
            out.setdefault(code, []).append(
                (
                    r.path.legacy_path_id or r.path.path_key,
                    agg.weighted_score,
                    str(agg.status),
                )
            )
    return out
