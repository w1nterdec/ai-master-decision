"""权重配置服务：修改权重 -> 落库 -> 审计 -> 返回重算后的权重树。

规则：
    * 拒绝负权重（由 WeightTree 抛出 NegativeWeightError）。
    * 修改后返回**新的** WeightTree，全局三级权重自动重算。
    * 每一次修改写入 audit_log，保留修改前后值。
    * 演示配置（is_demo=True）被修改时，审计记录中标注"仍为演示配置"，
      不会自动变为用户最终偏好。
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.engine.weights import WeightTree
from decision_system.models.entities import AuditLog, Indicator, WeightNode, WeightProfile
from decision_system.services.decision_service import build_weight_tree


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def update_weight(
    session: Session,
    *,
    profile_code: str,
    indicator_code: str,
    new_raw_weight: float,
    actor: str = "user",
    reason: str | None = None,
) -> WeightTree:
    """修改某指标的组内相对权重，落库、审计并返回重算后的权重树。"""
    profile = session.execute(
        select(WeightProfile).where(WeightProfile.code == profile_code)
    ).scalar_one_or_none()
    if profile is None:
        raise ValueError(f"权重配置不存在：{profile_code}")
    indicator = session.execute(
        select(Indicator).where(Indicator.code == indicator_code)
    ).scalar_one_or_none()
    if indicator is None:
        raise ValueError(f"指标不存在：{indicator_code}")
    node = session.execute(
        select(WeightNode).where(
            WeightNode.profile_id == profile.id, WeightNode.indicator_id == indicator.id
        )
    ).scalar_one_or_none()
    if node is None:
        raise ValueError(f"权重节点不存在：{profile_code}/{indicator_code}")

    old = float(node.raw_weight)
    # 先经 WeightTree 校验（负权重在此被拒绝），再落库，避免出现非法中间态
    tree_before = build_weight_tree(session, profile_code)
    tree_after = tree_before.with_updated_weight(indicator_code, new_raw_weight)

    node.raw_weight = float(new_raw_weight)
    session.add(
        AuditLog(
            actor=actor,
            action="weight.update",
            entity_type="WeightNode",
            entity_id=f"{profile_code}/{indicator_code}",
            detail={
                "profile_code": profile_code,
                "indicator_code": indicator_code,
                "level": indicator.level,
                "old_raw_weight": old,
                "new_raw_weight": float(new_raw_weight),
                "reason": reason,
                "still_demo_config": bool(profile.is_demo),
                "global_weight_before": tree_before.global_weights().get(indicator_code),
                "global_weight_after": tree_after.global_weights().get(indicator_code),
            },
        )
    )
    session.flush()
    return tree_after


def weight_change_history(session: Session, profile_code: str | None = None) -> list[dict[str, Any]]:
    rows = (
        session.execute(
            select(AuditLog).where(AuditLog.action == "weight.update").order_by(AuditLog.id)
        )
        .scalars()
        .all()
    )
    out = []
    for r in rows:
        detail = dict(r.detail or {})
        if profile_code and detail.get("profile_code") != profile_code:
            continue
        out.append(
            {
                "at": r.at.isoformat(timespec="seconds") if r.at else None,
                "actor": r.actor,
                "entity": r.entity_id,
                **detail,
            }
        )
    return out
