"""权重配置版本服务（Phase 4.1 Task D）。

规则：
    * 演示配置（is_demo=True）**不**被覆盖：用户确认权重后生成独立的配置版本。
    * 「恢复默认」只把当前配置的数值改回演示配置的值，**不删除**任何审计历史。
    * 每一次改动都写 audit_log（action=weight.update / profile.*），保留修改前后值。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AuditLog,
    Indicator,
    WeightNode,
    WeightProfile,
)
from decision_system.services.weight_service import update_weight


class ProfileServiceError(RuntimeError):
    pass


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _audit(
    session: Session, action: str, entity_id: str, detail: dict[str, Any], actor: str
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type="WeightProfile",
            entity_id=entity_id,
            detail=detail,
        )
    )


def list_profiles(session: Session) -> Sequence[WeightProfile]:
    return session.execute(select(WeightProfile).order_by(WeightProfile.id)).scalars().all()


def get_profile(session: Session, code: str) -> WeightProfile:
    p = session.execute(
        select(WeightProfile).where(WeightProfile.code == code)
    ).scalar_one_or_none()
    if p is None:
        raise ProfileServiceError(f"权重配置不存在：{code}")
    return p


def clone_profile(
    session: Session,
    *,
    base_code: str,
    new_code: str,
    name: str,
    actor: str = "user",
    description: str | None = None,
) -> WeightProfile:
    """从演示配置派生一个**独立的用户配置版本**，不覆盖原演示配置。"""
    base = get_profile(session, base_code)
    exists = session.execute(
        select(WeightProfile).where(WeightProfile.code == new_code)
    ).scalar_one_or_none()
    if exists is not None:
        raise ProfileServiceError(f"配置代码已存在：{new_code}")

    profile = WeightProfile(
        code=new_code,
        name=name,
        is_demo=False,
        description=description or f"由 {base_code} 派生（等待用户确认为正式偏好）",
    )
    session.add(profile)
    session.flush()
    for node in base.nodes:
        session.add(
            WeightNode(
                profile_id=profile.id,
                indicator_id=node.indicator_id,
                level=node.level,
                raw_weight=float(node.raw_weight),
            )
        )
    _audit(
        session,
        "profile.clone",
        new_code,
        {"base_code": base_code, "node_count": len(base.nodes), "is_demo": False},
        actor,
    )
    session.flush()
    return profile


def restore_from_base(
    session: Session,
    profile_code: str,
    *,
    base_code: str,
    actor: str = "user",
) -> int:
    """把指定配置的权重恢复为基准（演示）配置的数值。返回被恢复的节点数。

    只改数值并留审计；**不删除**任何历史 audit_log，也不删除配置本身。
    """
    target = get_profile(session, profile_code)
    base = get_profile(session, base_code)
    base_map = {n.indicator_id: float(n.raw_weight) for n in base.nodes}
    changed = 0
    for node in target.nodes:
        want = base_map.get(node.indicator_id)
        if want is None or float(node.raw_weight) == want:
            continue
        old = float(node.raw_weight)
        node.raw_weight = want
        ind: Indicator | None = node.indicator
        _audit(
            session,
            "weight.restore",
            f"{profile_code}/{ind.code if ind else node.indicator_id}",
            {
                "profile_code": profile_code,
                "indicator_code": ind.code if ind else None,
                "old_raw_weight": old,
                "new_raw_weight": want,
                "base_code": base_code,
            },
            actor,
        )
        changed += 1
    _audit(
        session,
        "profile.restore",
        profile_code,
        {"base_code": base_code, "changed_nodes": changed},
        actor,
    )
    session.flush()
    return changed


def confirm_as_user_preference(
    session: Session, profile_code: str, *, actor: str = "user", note: str | None = None
) -> WeightProfile:
    """把配置标记为用户正式偏好（is_demo=False）。仅改标记，权重数值不变。"""
    p = get_profile(session, profile_code)
    before = bool(p.is_demo)
    p.is_demo = False
    _audit(
        session,
        "profile.confirm",
        profile_code,
        {"is_demo_before": before, "is_demo_after": False, "note": note},
        actor,
    )
    session.flush()
    return p


def apply_weight_change(
    session: Session,
    *,
    profile_code: str,
    indicator_code: str,
    new_raw_weight: float,
    actor: str = "user",
    reason: str | None = None,
):
    """经 weight_service 修改权重（负权重在此被拒绝），返回新的 WeightTree。"""
    return update_weight(
        session,
        profile_code=profile_code,
        indicator_code=indicator_code,
        new_raw_weight=new_raw_weight,
        actor=actor,
        reason=reason,
    )
