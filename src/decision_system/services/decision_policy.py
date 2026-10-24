"""Phase 7.0｜四层决策解释层（独立只读服务，不改动现有评分引擎）。

设计原则（见 docs/V4_MODEL_SEMANTIC_AUDIT.md 审计 A-02..A-11）：
    * 本层**只解释**，不重算分数、不引入新权重；所有输入来自
      engine / decision_service / view_service / viewmodels。
    * 原案例的「仅一次正式考研机会、不二战」是**示例全局决策政策**，不是当前用户的默认事实或某所学校的属性
      （修复 A-02）：它贯穿失败后备路径评估，且「落空后果」被显式建模为终局性代价
      （修复 A-03），而非可调低的风险权重。
    * 动态权重（情景倍率）只在第四层用于**可补偿因素**的比较，且必须区分
      「演示配置」与「用户已确认偏好」（修复 A-01 / A-10）；任何情景都不得把
      「职业发展优先」与「重视唯一一次机会的风险」做成互斥（修复 A-04）。
    * 每层都输出可核查的判断依据，绝不编造综合评分或录取概率。

四层结构：
    L1 是否值得读   —— 培养价值 / 就业 / 科研 / 产业生态 / 方向匹配 / 长期发展
    L2 是否值得考   —— 在 L1 可接受前提下：科目匹配 / 招生稳定性 / 统考名额 /
                       推免影响 / 复试规则 / 竞争风险 / 2028 资格
    L3 失败后备路径 —— 一志愿 / 有培养价值的调剂 / 直接就业；「不二战」为全局政策
    L4 动态偏好比较 —— 仅在前面条件允许时使用；演示状态必须显式标注
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from decision_system.ui.viewmodels import (
    QUAL_CONFIRMED,
    QUAL_UNCONFIRMED,
    USER_CONFIRMED_BACKGROUND,
)

# 历史案例的示例全局决策政策；不表示当前使用者已确认这些条件。
GLOBAL_POLICY_NO_SECOND_TRY = (
    "仅一次正式考研机会，不二战：一志愿失败的代价是终局性的（无硕士可读），"
    "不能仅用「概率低一点」的风险权重来表达。"
)
GLOBAL_POLICY_MATH_OK = "接受数学一：考试科目含数学一的路径不构成硬约束冲突。"
GLOBAL_POLICY_TRAINING_VALUE_FIRST = (
    "优先级：培养价值 / 就业质量 / 学校与专业实力 属**优先级排序**，"
    "不是权重比例；不得用「学费低+气候好」在加权平均下覆盖培养价值明显不足的项目。"
)


@dataclass(frozen=True)
class LayerResult:
    """单层决策结果：结论 + 可核查依据。"""

    layer: str
    verdict: str
    reasons: tuple[str, ...]
    blocked: bool = False

    @property
    def is_favorable(self) -> bool:
        return self.verdict in ("重点研究", "重点评估", "值得重点准备")


@dataclass(frozen=True)
class DecisionExplanation:
    """一条招生路径的四层决策解释。"""

    path_key: str
    title: str
    subtitle: str
    global_policy: tuple[str, ...]
    layer1_worth_reading: LayerResult
    layer2_worth_testing: LayerResult
    layer3_fallback: LayerResult
    layer4_preference: LayerResult
    gaps: tuple[str, ...] = ()

    @property
    def can_proceed_to_test(self) -> bool:
        """L1 可接受（值得读）且未因硬约束阻断，才进入「是否值得考」。"""
        return (
            self.layer1_worth_reading.verdict
            in ("重点研究", "保留候选", "值得重点准备")
            and not self.layer1_worth_reading.blocked
        )


# ---------------------------------------------------------------------------
# L1｜是否值得读
# ---------------------------------------------------------------------------
def _layer1_worth_reading(
    title: str,
    verified_facts: Sequence[str],
    evidence_state: str,
    qualification_text: str,
    exam_unit4: str | None,
    key_risk: str | None,
) -> LayerResult:
    reasons: list[str] = []
    a_facts = list(verified_facts)
    if a_facts:
        head = "；".join(a_facts[:3])
        reasons.append(f"已核验事实 {len(a_facts)} 条，含：{head}")
    else:
        reasons.append("暂无可支撑「培养价值/就业/学校专业实力」的已核验事实。")

    blocked = False
    if exam_unit4 and "数学一" in (exam_unit4 or ""):
        reasons.append("初试含数学一，与用户「接受数学一」一致。")
    if evidence_state in ("待核验", "暂无数据") and not a_facts:
        reasons.append("培养价值证据不足，暂不能判定「值得读」。")
        return LayerResult("L1 是否值得读", "培养价值证据不足", tuple(reasons), blocked)

    if a_facts:
        reasons.append("基于已核验事实，可纳入重点研究或保留候选。")
        verdict = "重点研究" if len(a_facts) >= 2 else "保留候选"
    else:
        verdict = "培养价值证据不足"
    if key_risk:
        reasons.append(f"已知风险：{key_risk}")
    return LayerResult("L1 是否值得读", verdict, tuple(reasons), blocked)


# ---------------------------------------------------------------------------
# L2｜是否值得考
# ---------------------------------------------------------------------------
def _layer2_worth_testing(
    title: str,
    qualification_text: str,
    qualification_reasons: Sequence[str],
    exam_unit4: str | None,
    has_verified_2028: bool,
    quota_state: str,
) -> LayerResult:
    reasons: list[str] = []
    if qualification_text == QUAL_CONFIRMED and has_verified_2028:
        reasons.append("2028 招生资格已取得已核验证据。")
    else:
        reasons.append("2028 招生资格尚未确认（历史 2027 资料不能证明 2028）。")
        for r in qualification_reasons[:3]:
            reasons.append("  - " + r)
        return LayerResult(
            "L2 是否值得考", "资格尚未确认", tuple(reasons), blocked=True
        )

    if exam_unit4:
        reasons.append(f"初试第四单元：{exam_unit4}。")
    else:
        reasons.append("初试科目未登记，需补充。")

    reasons.append(f"招生名额记录：{quota_state}。")
    reasons.append("在资格已确认前提下，可进入科目匹配与竞争风险的重点评估。")
    return LayerResult("L2 是否值得考", "重点评估", tuple(reasons), blocked=False)


# ---------------------------------------------------------------------------
# L3｜失败后备路径（「不二战」为全局政策）
# ---------------------------------------------------------------------------
def _layer3_fallback(title: str, qualification_text: str) -> LayerResult:
    reasons: list[str] = [
        GLOBAL_POLICY_NO_SECOND_TRY,
        "失败后果必须同时考虑：(a) 失败可能性的不确定性 + (b) 失败后的实际后果。",
        "后备路径三选一：① 一志愿；② 有培养价值的调剂（仅当培养价值足够）；③ 直接就业。",
    ]
    if qualification_text != QUAL_CONFIRMED:
        reasons.append("因 2028 资格未确认，一志愿路径本身尚未成立，须先补充资格证据。")
    else:
        reasons.append("一志愿路径资格成立；是否值得押上唯一一次机会，取决于 L2 风险与 L1 培养价值。")
    reasons.append("不得因「降低考试风险」而选择培养价值明显不值得读的项目（全局政策）。")
    return LayerResult("L3 失败后备路径", "后备路径需结合 L1/L2 判断", tuple(reasons), blocked=False)


# ---------------------------------------------------------------------------
# L4｜动态偏好比较
# ---------------------------------------------------------------------------
def _layer4_preference(title: str, is_demo: bool, confirmed_profile: bool) -> LayerResult:
    reasons: list[str] = []
    if is_demo and not confirmed_profile:
        reasons.append(
            "当前权重为**演示配置（待确认）**，不是用户真实偏好；"
            "任何基于权重的排序/评分均不可当作最终择校结论。"
        )
        verdict = "演示配置·未确认"
    elif confirmed_profile:
        reasons.append("权重已确认为用户真实偏好，可用于可补偿因素的动态比较。")
        verdict = "已确认偏好"
    else:
        reasons.append("未设置任何权重配置，动态比较不可用。")
        verdict = "无偏好配置"
    reasons.append(
        "动态权重只用于比较**可补偿因素**（如学费、气候），"
        "不得用它完全抵消培养价值明显不足。"
    )
    reasons.append(
        "任何情景都不得把「职业发展优先」与「重视唯一一次机会的风险」做成互斥滑杆。"
    )
    return LayerResult("L4 动态偏好比较", verdict, tuple(reasons), blocked=False)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def build_decision_explanation(
    *,
    path_key: str,
    title: str,
    subtitle: str,
    verified_facts: Sequence[str],
    evidence_state: str,
    qualification_text: str,
    qualification_reasons: Sequence[str],
    exam_unit4: str | None,
    key_risk: str | None,
    quota_state: str,
    has_verified_2028: bool,
    is_demo_profile: bool,
    confirmed_profile: bool,
    gaps: Sequence[str] = (),
) -> DecisionExplanation:
    """组装一条路径的四层决策解释。纯函数，不访问数据库、不写状态。"""
    return DecisionExplanation(
        path_key=path_key,
        title=title,
        subtitle=subtitle,
        global_policy=(
            GLOBAL_POLICY_NO_SECOND_TRY,
            GLOBAL_POLICY_MATH_OK,
            GLOBAL_POLICY_TRAINING_VALUE_FIRST,
        ),
        layer1_worth_reading=_layer1_worth_reading(
            title, verified_facts, evidence_state, qualification_text, exam_unit4, key_risk
        ),
        layer2_worth_testing=_layer2_worth_testing(
            title, qualification_text, qualification_reasons, exam_unit4, has_verified_2028, quota_state
        ),
        layer3_fallback=_layer3_fallback(title, qualification_text),
        layer4_preference=_layer4_preference(title, is_demo_profile, confirmed_profile),
        gaps=tuple(gaps),
    )
