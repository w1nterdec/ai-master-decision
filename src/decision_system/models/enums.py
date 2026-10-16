"""全局枚举。

说明：所有枚举值以中文字符串持久化，便于与既有 Excel 基线（"是/否/候选/排除/证据不足" 等）
直接对齐与人工阅读；SQLAlchemy 侧使用 native_enum=False 以字符串形式落库。
"""

from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    """值为中文字符串、可直接与 Excel/JSON 对齐的枚举基类。"""

    def __str__(self) -> str:  # pragma: no cover - 便利性
        return str(self.value)

    @classmethod
    def values(cls) -> list[str]:
        return [m.value for m in cls]


# ---------------------------------------------------------------------------
# 证据治理
# ---------------------------------------------------------------------------
class VerificationStatus(_StrEnum):
    """来源 / 事实声明的核验状态。

    只有 VERIFIED 允许进入正式评分。
    """

    VERIFIED = "已核验"
    PENDING = "待核验"
    CONFLICT = "来源冲突"
    INVALID = "已失效"
    UNVERIFIABLE = "无法核验"
    UNREGISTERED = "未登记"


class SourceType(_StrEnum):
    OFFICIAL_CATALOG = "官方招生目录"
    OFFICIAL_NOTICE = "官方公告"
    OFFICIAL_WEB = "官方网页"
    PDF_ORIGINAL = "PDF原件"
    QUALITY_REPORT = "就业质量报告"
    RESEARCH_REPORT = "研究报告"
    INTERVIEW = "访谈/宣讲"
    MEDIA = "媒体报道"
    UNKNOWN = "未知"


class ClaimStatus(_StrEnum):
    """事实声明的状态。CANDIDATE 明确表示"候选映射"，**不得**自动升级为已核验。"""

    VERIFIED = "已核验"
    CANDIDATE = "候选映射"
    PENDING = "待核验"
    CONFLICT = "来源冲突"
    INVALID = "已失效"


class EvidenceLevel(_StrEnum):
    """证据强度等级（沿用 Phase 2D 口径）。"""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    UNKNOWN = "未知"


class Accessibility(_StrEnum):
    """资源可进入性等级（沿用 Phase 2D 口径）。P3 不能推断为可用。"""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    NA = "不适用"


# ---------------------------------------------------------------------------
# 招生路径
# ---------------------------------------------------------------------------
class StudyMode(_StrEnum):
    FULL_TIME = "全日制"
    PART_TIME = "非全日制"
    UNKNOWN = "待核"


class AdmissionMethod(_StrEnum):
    """招生方式。统考 / 推免 / 专项计划 / 调剂 分开记录，不合并。"""

    UNIFIED_EXAM = "统考"
    RECOMMENDED = "推免"
    SPECIAL_PLAN = "专项计划"
    ADJUSTMENT = "调剂"
    UNKNOWN = "未知"


class PathKind(_StrEnum):
    """路径在决策中的角色：一志愿 / 调剂 / 直接就业备选。"""

    FIRST_CHOICE = "一志愿"
    ADJUSTMENT = "调剂"
    DIRECT_EMPLOYMENT = "直接就业"
    UNCLASSIFIED = "未分类"


# ---------------------------------------------------------------------------
# 硬约束与资格
# ---------------------------------------------------------------------------
class TriState(_StrEnum):
    YES = "是"
    NO = "否"
    UNKNOWN = "待确认"


class PathEligibility(_StrEnum):
    """硬约束引擎输出。注意：CANDIDATE（历史候选）≠ 2028 正式招生资格。"""

    EXCLUDED = "排除"
    CANDIDATE = "候选"
    PENDING = "待核验"


class Qualification2028(_StrEnum):
    CONFIRMED = "2028正式资格已确认"
    NOT_CONFIRMED = "2028资格未确认"
    NOT_MET = "未满足"


class Verification2028(_StrEnum):
    VERIFIED = "已核验2028"
    PENDING = "待2028核验"
    UNKNOWN = "未知"


# ---------------------------------------------------------------------------
# 评分与结果
# ---------------------------------------------------------------------------
class ScoreValidity(_StrEnum):
    VALID = "有效"
    INVALID = "无效"
    UNKNOWN = "未知"


class ComparisonStatus(_StrEnum):
    """与 Excel 基线保持同字面量，便于黄金比对。"""

    COMPARABLE = "可比较（非录取预测）"
    INSUFFICIENT = "证据不足"
    EXCLUDED = "硬约束不符-排除"
    PENDING = "硬约束待确认-不可比较"


class ObjectiveStatus(_StrEnum):
    AVAILABLE = "可输出"
    INSUFFICIENT_EVIDENCE = "待补充证据"
    UNDECIDABLE = "暂无法判断"
    PENDING_VERIFICATION = "待核验"
    EXCLUDED = "已排除"
    NOT_APPLICABLE = "不适用"


class ScenarioCode(_StrEnum):
    BASE = "base"
    CAREER = "career"
    ADMISSION = "admission"
    RESEARCH = "research"
