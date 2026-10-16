"""Streamlit UI 层（Phase 4.1）。

约束：
    * 本层**不实现**任何决策算法：所有计算调用 engine / services。
    * 所有写操作经 services（evidence_service / profile_service / weight_service）。
    * 未知值一律显示「暂无数据 / 待核验 / 证据不足」，绝不补 0 或补默认分。
"""

from decision_system.ui import db_access  # noqa: F401

__all__ = ["db_access"]
