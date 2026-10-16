"""Phase 6.0｜只读展示模型（ViewModel）。

作用：把 ORM 实体 + 引擎输出组织成**页面可直接渲染**的结构。

纪律：
    * 这里是**展示层数据组织**，不实现任何决策算法、不复制计算公式；
      一切评分/资格/覆盖率均来自 engine 与 services。
    * 不建立第二套业务实体：不新增 ORM 模型、不写业务字段。
    * 未知一律保持未知：None → 「暂无数据 / 待核验 / 证据不足 / 无法判断」，
      **绝不**用 0 或空字符串冒充数值。

状态取值（全站统一）：
    未知 / 待核验 / 已核实 / 存在冲突 / 不适用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

UNKNOWN = "暂无数据"
PENDING = "待核验"
# 注意：数据层枚举 `ClaimStatus.VERIFIED` / `VerificationStatus.VERIFIED` 的取值是
# 「已核验」，而展示层文案沿用「已核实」。二者长期并存导致过判定失效
# （Phase 6.1 实测发现：已核验证据被误判为待核验）。判定一律走下面的取值集合，
# 展示文案继续用 VERIFIED = "已核实"。
VERIFIED = "已核实"
VERIFIED_TEXTS: frozenset[str] = frozenset({"已核验", "已核实"})
CONFLICT = "存在冲突"
NOT_APPLICABLE = "不适用"
UNJUDGEABLE = "无法判断"

EVALUATED = "已评估"
PARTIAL = "部分评估"
NOT_EVALUATED = "待评估"

QUAL_CONFIRMED = "已确认"
QUAL_UNCONFIRMED = "未确认"

# 千问 V4.0 五维 → 现有库内一级维度 code
# 说明：V4.0「02 家庭条件与地理关系」在现有库中拆为两部分，故为多值。
V4_DIMENSION_MAP: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("01 地域与 AI 产业生态", "L1-地域生态", ()),
    ("02 家庭条件与地理关系", "L1-成本安排", ("L2-地域生态|生活适配",)),
    ("03 院校、专业与科研平台", "L1-研究培养", ()),
    ("04 考研可行性与失败风险", "L1-报考可行性", ()),
    ("05 长期职业发展与衔接", "L1-职业发展", ()),
)

# 对比矩阵维度：（维度名, 关联一级维度 code 或 None, 是否依赖评分）
COMPARE_DIMENSIONS: tuple[tuple[str, str | None], ...] = (
    ("职业发展与就业", "L1-职业发展"),
    ("AI 产业生态", "L1-地域生态"),
    ("学校与专业实力", "L1-研究培养"),
    ("培养与科研资源", "L1-研究培养"),
    ("考试科目", None),          # 来自 AdmissionPath.exam_unit4
    ("历史招生规模", None),       # 来自 AdmissionRecord
    ("复试风险", "L1-报考可行性"),
    ("学费与住宿", "L1-成本安排"),
    ("调剂价值", None),          # 来自 path_kind + 硬约束（不做评分）
    ("数据可信度", None),         # 来自证据统计
)


def v4_order(level1_codes: Sequence[str]) -> list[str]:
    """按 V4.0 顺序排列一级维度 code（未映射的排在其后）。"""
    ordered: list[str] = []
    for _label, code, extra in V4_DIMENSION_MAP:
        for c in (code, *extra):
            if c in level1_codes and c not in ordered:
                ordered.append(c)
    for c in level1_codes:
        if c not in ordered:
            ordered.append(c)
    return ordered


def v4_label(code: str) -> str:
    for label, c, extra in V4_DIMENSION_MAP:
        if c == code or code in extra:
            return label
    return code


# 用户已确认的个人背景（**非系统推断**，仅用于展示上下文）。
# 来源：用户在本项目中的明确陈述。任何一条都不得被系统改写或推断覆盖。
USER_CONFIRMED_BACKGROUND: tuple[tuple[str, str], ...] = (
    ("本科专业", "信息与计算科学"),
    ("目标方向", "AI 工程 / LLM · Agent"),
    ("长期方向", "具身智能 / 机器人"),
    ("考试机会", "仅一次正式考研机会，不二战"),
    ("数学科目", "接受数学一"),
    ("优先项", "培养价值 / 就业质量 / 学校与专业实力"),
    ("地域倾向", "看重中国 AI 产业中心；不强制上海；过冷地区不优先"),
    ("调剂态度", "仅在培养价值足够时考虑"),
    ("学费", "非绝对硬约束"),
)


# ---------------------------------------------------------------------------
# ViewModel
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClaimItem:
    """一条声明的展示视图（含年份，便于区分历史与 2028）。"""

    statement: str
    topic: str | None
    status: str
    applicable_years: tuple[int, ...]
    source_title: str
    source_status: str
    source_type: str | None
    url_or_file: str | None
    is_candidate: bool

    @property
    def year_text(self) -> str:
        if not self.applicable_years:
            return "年份未标注"
        return "、".join(str(y) for y in sorted(self.applicable_years))

    @property
    def is_2028(self) -> bool:
        return 2028 in self.applicable_years


@dataclass(frozen=True)
class EvidenceSummary:
    total_claims: int = 0
    verified_claims: int = 0
    candidate_claims: int = 0
    pending_claims: int = 0
    verified_sources: int = 0
    unregistered_sources: int = 0
    conflicts: int = 0
    verified_2028_claims: int = 0
    items: tuple[ClaimItem, ...] = ()
    state: str = PENDING

    @property
    def summary_text(self) -> str:
        return (
            f"声明 {self.total_claims} 条（已核验 {self.verified_claims}、"
            f"候选 {self.candidate_claims}、待核验 {self.pending_claims}）；"
            f"来源已核验 {self.verified_sources} 个、未登记 {self.unregistered_sources} 个"
        )


@dataclass(frozen=True)
class QuotaItem:
    """名额口径条目：不同口径严格分列，不合并。"""

    year: int
    basis: str          # 目录计划 / 复试统考计划 / 实际录取
    method: str
    planned: int | None
    actual: int | None
    note: str | None
    claim_status: str | None


@dataclass(frozen=True)
class PathSummary:
    """一条招生路径的展示视图（比较单位 = 路径，不是学校）。"""

    path_id: int
    path_key: str                 # 仅高级功能展示
    legacy_id: str | None
    school_name: str
    school_code: str
    college_name: str
    college_code: str
    program_code: str
    program_name: str | None
    study_mode: str
    direction: str | None
    exam_unit4: str | None
    admission_year: int
    admission_method: str
    path_kind: str
    training_location: str | None
    qualification_2028: str
    eligibility: str
    key_risk: str | None
    notes: str | None
    evidence: EvidenceSummary
    quotas: tuple[QuotaItem, ...] = ()
    decision: Any | None = None   # PathDecision，可能为 None
    coverage: float | None = None
    unknown_indicators: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        """用户可读标题：学校 + 学院 + 专业代码 + 学习方式 + 方向。"""
        parts = [self.school_name]
        if self.college_name:
            parts.append(self.college_name)
        if self.program_code:
            parts.append(self.program_code)
        if self.direction:
            parts.append(self.direction)
        return "　".join(parts)

    @property
    def subtitle(self) -> str:
        bits: list[str] = []
        if self.study_mode:
            bits.append(str(self.study_mode))
        if self.path_kind:
            bits.append(str(self.path_kind))
        bits.append(f"{self.admission_year} 年")
        return " · ".join(bits)

    @property
    def qualification_is_confirmed(self) -> bool:
        return self.qualification_2028 == QUAL_CONFIRMED


# --- Phase 6.1｜研究资料四类分级（A/B/C/D） ---------------------------------
# 分级只影响「怎么展示」，不影响任何评分与资格判定：
#   A 已核实事实  —— 来源已核验 + 声明已核验；可展示，须带年份与来源
#   B 待核验研究资料 —— 候选映射 / 来源未登记 / 待核验；可展示，不可作为决策依据
#   C 推断或主观评价 —— 由 A/B 推导的判断；可展示，须标注为推断
#   D 未知        —— 无任何材料；显示「未知」，严禁补 0
GRADE_A = "A 已核实事实"
GRADE_B = "B 待核验研究资料"
GRADE_C = "C 推断或主观评价"
GRADE_D = "D 未知"

# 声明原文中出现这些前缀时，判为「推断」而非事实
_INFERENCE_MARKERS = ("【推断", "推断·", "（推断）", "推测")


@dataclass(frozen=True)
class FactItem:
    """一条带分级的研究事实（Phase 6.1）。"""

    grade: str
    statement: str
    year_text: str
    source_title: str
    source_status: str
    is_2028: bool
    limitation: str | None = None


def grade_claim(item: "ClaimItem") -> str:
    """按证据状态把声明归入 A/B/C/D 之一（只做分类，不改数据）。"""
    text = item.statement or ""
    if any(m in text for m in _INFERENCE_MARKERS):
        return GRADE_C
    if item.status in VERIFIED_TEXTS and item.source_status in VERIFIED_TEXTS:
        return GRADE_A
    return GRADE_B


@dataclass(frozen=True)
class ResearchDossier:
    """历史研究档案（Phase 6.1｜M7 双层展示的第一层）。

    与 2028 正式评分**严格分离**：这里只放历史/待核验材料，
    不参与任何评分、不参与 2028 资格判定。
    """

    title: str
    grade_a: tuple[FactItem, ...] = ()
    grade_b: tuple[FactItem, ...] = ()
    grade_c: tuple[FactItem, ...] = ()
    unknown_topics: tuple[str, ...] = ()   # D 类：尚未取得数据的指标/主题

    @property
    def is_empty(self) -> bool:
        return not (self.grade_a or self.grade_b or self.grade_c or self.unknown_topics)

    @property
    def counts_text(self) -> str:
        return (
            f"A 已核实 {len(self.grade_a)} 条 · "
            f"B 待核验 {len(self.grade_b)} 条 · "
            f"C 推断 {len(self.grade_c)} 条 · "
            f"D 未知 {len(self.unknown_topics)} 项"
        )


@dataclass(frozen=True)
class SchoolSummary:
    """学校卡片视图（聚合其下全部路径）。"""

    code: str
    name: str
    region: str | None
    city: str | None
    path_count: int
    career_value_state: str = NOT_EVALUATED
    risk_state: str = NOT_EVALUATED
    qualification_2028: str = QUAL_UNCONFIRMED
    strengths: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    evidence: EvidenceSummary = field(default_factory=EvidenceSummary)
    paths: tuple[PathSummary, ...] = ()

    @property
    def location_text(self) -> str:
        bits = [b for b in (self.region, self.city) if b]
        return " · ".join(bits) if bits else UNKNOWN


@dataclass(frozen=True)
class ComparisonCell:
    dimension: str
    text: str
    judgeable: bool          # 是否有足够证据判断
    highlight: bool = False  # 有足够证据的差异才高亮


@dataclass(frozen=True)
class ComparisonSummary:
    paths: tuple[PathSummary, ...]
    rows: tuple[tuple[str, tuple[ComparisonCell, ...]], ...] = ()

    @property
    def judgeable_rows(self) -> int:
        return sum(1 for _dim, cells in self.rows if any(c.judgeable for c in cells))

    @property
    def has_winner(self) -> bool:
        """证据不足时不得宣布绝对赢家。"""
        return False


@dataclass
class RiskGap:
    topic: str
    reason: str
    affects_hard_constraint: bool
    affects_first_choice_risk: bool
    may_change_choice: bool
    data_exists_but_unstructured: bool
    score: int = 0

    @property
    def priority_text(self) -> str:
        return "高" if self.score >= 3 else ("中" if self.score >= 2 else "低")


@dataclass(frozen=True)
class RiskSummary:
    path: PathSummary
    hard_constraint_state: str
    hard_constraint_reasons: tuple[str, ...]
    first_choice: tuple[str, ...]
    transfer: tuple[str, ...]
    employment: tuple[str, ...]
    gaps: tuple[RiskGap, ...]
    risk_level: str = UNKNOWN


@dataclass
class DecisionArchive:
    """我的决策档案（轻量持久化，不动数据库结构）。"""

    candidate_path_ids: list[int] = field(default_factory=list)
    favorite_path_ids: list[int] = field(default_factory=list)
    excluded_path_ids: list[int] = field(default_factory=list)   # 暂不考虑
    path_notes: dict[str, str] = field(default_factory=dict)     # {"<path_id>": "我的理由"}
    active_profile_code: str = "phase37c_demo"
    is_demo_profile: bool = True
    scenario_code: str | None = None
    notes: list[str] = field(default_factory=list)
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_path_ids": list(self.candidate_path_ids),
            "favorite_path_ids": list(self.favorite_path_ids),
            "excluded_path_ids": list(self.excluded_path_ids),
            "path_notes": dict(self.path_notes),
            "active_profile_code": self.active_profile_code,
            "is_demo_profile": self.is_demo_profile,
            "scenario_code": self.scenario_code,
            "notes": list(self.notes),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DecisionArchive":
        return cls(
            candidate_path_ids=list(d.get("candidate_path_ids") or []),
            favorite_path_ids=list(d.get("favorite_path_ids") or []),
            excluded_path_ids=list(d.get("excluded_path_ids") or []),
            path_notes={
                str(k): str(v) for k, v in (d.get("path_notes") or {}).items()
            },
            active_profile_code=str(d.get("active_profile_code") or "phase37c_demo"),
            is_demo_profile=bool(d.get("is_demo_profile", True)),
            scenario_code=d.get("scenario_code"),
            notes=list(d.get("notes") or []),
            updated_at=d.get("updated_at"),
        )

    def note_of(self, path_id: int) -> str:
        return self.path_notes.get(str(path_id), "")

    def set_note(self, path_id: int, text: str) -> None:
        key = str(path_id)
        if text.strip():
            self.path_notes[key] = text.strip()
        else:
            self.path_notes.pop(key, None)
