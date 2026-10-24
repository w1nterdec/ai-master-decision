"""【择校结果总览】面向考生的最终决策视图（Task 9 / Task 12）。

职责：
    * 只读 `data/school_research_consolidated.json`（与 Markdown 报告同源），
      不写数据库、不做任何评分计算。
    * 把"历史研究判断"与"2028 正式资格"两层**并排、不合并**展示。
    * 五个部分：① 当前重点研究对象 ② 五校横向对比矩阵
               ③ 学校详细分析 ④ 一次考研策略 ⑤ 决策敏感性。
    * 移动端优先：少列、短文本、用 expander 折叠细节，避免宽表溢出。

纪律：本页是**展示层**，结论以 `docs/2028_AI_MASTER_DECISION_REPORT.md` 为权威文本；
      本模块内嵌的定性判断（较强/中等/待核验）逐字对齐报告，不另起一套排名或概率。
"""

from __future__ import annotations

import json
import os
from typing import Dict, List

import streamlit as st
from decision_system.services.research_catalog import CatalogError, load_catalog

_JSON_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "data", "school_research_consolidated.json"
    )
)


def _load_consolidated() -> Dict:
    try:
        return load_catalog().data
    except CatalogError:
        return {}


# ---------------------------------------------------------------------------
# 内嵌定性判断（与 Markdown 报告逐字对齐；仅用于展示层着色与矩阵）
# ---------------------------------------------------------------------------
# 各组路径归属（研究分组 ≠ 录取概率分组）
FOCUS_GROUP = {
    "P01": "需先确认（801 通信原理与备考方向的匹配）",
    "P02": "主目标候选 · 重点研究",
    "P05": "主目标候选 · 重点研究",
    "P06": "主目标候选 · 重点研究",
    "P10": "主目标候选 · 重点研究",
    "P03": "需先确认（非 085410，先核目标吻合度）",
    "P04": "暂缓（异地/科目待核）",
    "P07": "暂缓（统考极少）",
    "P08": "暂缓（统考极少/推免高）",
    "P09": "暂缓（偏交通 AI）",
}

# 五校横向对比矩阵（取每校最具代表性的 AI 路径；等级后附依据，均来自报告）
MATRIX = [
    {
        "学校/路径": "北邮 005 · 085410 · 方向02（北京·408）",
        "培养价值": ("较强", "具身导师（方斌/郭迪）+ 平台（国家 AI 产教融合、DeepTouch）"),
        "就业发展": ("中等", "全校级就业线索（阿里/华为/腾讯/字节，2022 届）"),
        "考试匹配": ("较强", "考 408 统考，与信计课程重合高"),
        "招生风险": ("高", "仅含推免目录计划，统考名额全未知（五校最不透明）"),
        "当前建议": "重点研究（等 2028）",
    },
    {
        "学校/路径": "电子科大 008 · 085404 · 计算机技术（成都·408）",
        "培养价值": ("中等", "具身方向有（王国庆 Embodied AI），但路径是计算机技术非 085410"),
        "就业发展": ("较强", "5 名华为天才少年、60%+ 去国防/西部、国家重点单位 51.76%"),
        "考试匹配": ("较强", "408 统考"),
        "招生风险": ("中", "复试线波动大（335→320→355）"),
        "当前建议": "研究（先确认是否算 AI 目标）",
    },
    {
        "学校/路径": "东南 009 · 085410 · 人工智能（南京·408）",
        "培养价值": ("较强", "SAIL（具身感知交互）、COOLAS（大模型智能体/具身）、智元平台"),
        "就业发展": ("较强", "落实率 99.13%、近 50% 互联网头部"),
        "考试匹配": ("较强", "408 统考；2025 起自命题改 408"),
        "招生风险": ("中", "统考名额下降（33→32→28）"),
        "当前建议": "重点研究（强但名额降）",
    },
    {
        "学校/路径": "合工大 005 · 085410 · 人工智能（合肥·408）",
        "培养价值": ("较强", "绳驱人形机器人实验室、多位具身/大模型导师"),
        "就业发展": ("中等", "小米训练营、140 家联培（待核验开放度）"),
        "考试匹配": ("较强", "408 统考"),
        "招生风险": ("较低", "统考名额上升（23→26→46）"),
        "当前建议": "重点研究（风险较平衡）",
    },
    {
        "学校/路径": "西南交大 048 · 085410 · 人工智能（成都·408）",
        "培养价值": ("较强", "具身智能联合研究中心、多具身/多模态导师"),
        "就业发展": ("中等", "研究院就业（微软亚研院/华为/腾讯，S3）"),
        "考试匹配": ("较强", "408 统考"),
        "招生风险": ("中", "统考约 14（2027），推免约 48%"),
        "当前建议": "值得研究",
    },
]

# 一次考研策略梯队（培养价值优先 + 一次风险控制）
STRATEGY = [
    ("第一梯队（重点备考）", "东南 009 + 合工大 005",
     "历史底稿分别记录了平台资源与统考名额变化，需核验年份、口径和开放度。并行研究不等于同时报考，最终一志愿只能选定一条。"),
    ("第二梯队（高价值高不确定）", "北邮方向02（北京+具身，统考全未知）、西南交大 048（具身+统考约14）",
     "作为『若 2028 目录利好则升级为主攻』的候选。"),
    ("待定", "电子科大 008",
     "先确认『085404 计算机技术』是否符合你的 AI 专硕目标；若符合且成都可接受，可替入第一梯队。"),
    ("调剂底线", "只接受『值得读』的调剂",
     "具身/AI 资源明确对统考生开放才考虑；否则直接就业。"),
    ("不二战意味着", "初复试都要稳",
     "宁选统考盘子较大、科目稳定的路径，也不赌最不透明的最高名气路径。"),
]

# 决策敏感性：关键未知与核验优先级（揭晓后可能改变结论）
SENSITIVITY = [
    ("1", "2028 招生目录：各校 085410 是否招生、是否分方向、科目", "唯一一次机会的前提，直接决定哪些路径还存在"),
    ("2", "2028 初试科目（北邮方向01 是否仍 801、方向02 是否仍 408；电子科大 028 科目）", "科目变动直接改备考路线，可能推翻『方向02 更贴背景』"),
    ("3", "统考实际名额（剔除推免）", "决定真实竞争强度；合工大若骤降、北邮若揭晓极小则结论重排"),
    ("4", "推免实际占比", "与第 3 项耦合，同影响竞争强度"),
    ("5", "复试细则（权重/形式/线）", "初试过线≠录取，改变一志愿风险评估"),
    ("6", "具身/LLM 导师是否招 085410 统考硕士", "你长期方向的关键，影响『值不值得读三年』"),
    ("7", "产业平台对统考生开放度（小米训练营、智元平台等）", "资源可否实际获得，影响培养价值论证强度"),
]

_GRADE_LEGEND = {
    "S1": "官方/目录级",
    "S2": "学院级资料（核验状态另列）",
    "S3": "实验室/研究院级",
    "S4": "全校级线索",
}


def _grade_badge(grade: str) -> str:
    label = _GRADE_LEGEND.get(grade, grade)
    return f"`{grade}` {label}"


def _path_label(p: Dict) -> str:
    bits = [p.get("school", "")]
    if p.get("college"):
        bits.append(p.get("college"))
    if p.get("program"):
        bits.append(p.get("program"))
    if p.get("direction"):
        bits.append(p.get("direction"))
    return " · ".join(bits)


def render(session=None, *, profile_code: str = "phase37c_demo") -> None:
    """入口函数：被 app.py 以与现有页面一致的方式调用。"""
    data = _load_consolidated()
    if not data:
        st.error(
            f"未找到整合研究数据文件：`{_JSON_PATH}`。"
            "请先运行数据整合，或确认 `data/school_research_consolidated.json` 存在。"
        )
        return

    paths = data.get("paths", [])
    by_path = data.get("research_by_path", {})
    flat = data.get("research_flat", [])
    openq = data.get("open_questions", [])

    # 顶部双层标识（贯穿全页）
    st.info(
        "🟦 **历史研究判断**：基于 2023–2027 各校官网/学院级资料（导师、平台、就业、历史统考名额），"
        "是**底稿记录的资源线索**，需按来源与适用范围核验，**不等于 2028 官方招生确认**。\n\n"
        "🟥 **2028 正式招生资格**：本地资料快照未收录可确认资格的 2028 目录，全部路径『2028 资格未确认』。这不是实时发布状态。"
        "历史招生事实不得冒充 2028。"
    )

    # ── ① 当前重点研究对象 ───────────────────────────────────────────────
    st.subheader("① 当前重点研究对象")
    st.caption("研究分组 ≠ 录取概率分组。以下为『最该优先深挖』的路径。")
    focus = [p for p in paths if FOCUS_GROUP.get(p["path_id"], "").startswith("主目标候选")]
    need_confirm = [p for p in paths if FOCUS_GROUP.get(p["path_id"], "").startswith("需先确认")]
    defer = [p for p in paths if FOCUS_GROUP.get(p["path_id"], "").startswith("暂缓")]

    st.markdown("**🎯 主目标候选（重点研究）**")
    for p in focus:
        st.markdown(
            f"- **{_path_label(p)}**（{p.get('city','')}·{p.get('exam4','')}）— "
            f"{FOCUS_GROUP.get(p['path_id'])}"
        )
    st.markdown("**❓ 需先确认**")
    for p in need_confirm:
        st.markdown(f"- **{_path_label(p)}** — {FOCUS_GROUP.get(p['path_id'])}")
    st.markdown("**⏸ 暂缓判断**")
    for p in defer:
        st.markdown(f"- **{_path_label(p)}** — {FOCUS_GROUP.get(p['path_id'])}")

    st.success(
        "一句话：最该优先深挖的是 **东南 009、合工大 005、北邮方向02、西南交大 048** "
        "这四条『AI 专硕 + 具身智能方向 + 考 408』的路径；"
        "**电子科大 008 是 085404 计算机技术（非 085410），需先确认是否算你的 AI 目标**；"
        "合工大 021/023、西南交大 004 统考名额极少或偏交通，建议暂缓。"
    )

    # ── ② 五校横向对比矩阵 ───────────────────────────────────────────────
    st.subheader("② 五校横向对比矩阵")
    st.caption(
        "等级含义：**较强 / 中等 / 待核验 / 证据不足**，所有定性等级后附依据。"
        "比较单位是『路径』，不是学校；下表取每校最具代表性的 AI 路径。全部为 🟦 历史研究判断，🟥 2028 未确认。"
    )
    for row in MATRIX:
        label = row["学校/路径"]
        with st.expander(label, expanded=False):
            st.markdown(f"- **培养价值（AI/具身）**：{row['培养价值'][0]} — {row['培养价值'][1]}")
            st.markdown(f"- **AI 就业与长期发展**：{row['就业发展'][0]} — {row['就业发展'][1]}")
            st.markdown(f"- **考试匹配（信计背景）**：{row['考试匹配'][0]} — {row['考试匹配'][1]}")
            st.markdown(f"- **招生风险（统考透明度）**：{row['招生风险'][0]} — {row['招生风险'][1]}")
            st.markdown(f"- **当前建议**：{row['当前建议']}")
    st.caption(
        "⚠️ 上表『培养价值/就业』几乎所有证据都是 2023–2027 学院级或全校级研究资料（S2/S3/S4），"
        "记录了资源线索，**不证明你 2028 能进该方向、跟到该导师**，需核验原件。"
        "北邮方向02 的科目（408）是 2027 官方已核验；其余四校科目/名额多为历史口径推算。"
    )

    # ── ③ 学校详细分析 ───────────────────────────────────────────────────
    st.subheader("③ 学校详细分析")
    st.caption(
        "按『你能实际获得的 AI/具身智能资源』比较，不凭 985/211 头衔直接给分。"
        "每层展开可看到 🟦 真实研究证据原文与来源等级。"
    )
    for p in paths:
        pid = p["path_id"]
        items = by_path.get(pid, [])
        with st.expander(f"{_path_label(p)} — {FOCUS_GROUP.get(pid, '未分组')}", expanded=False):
            # 路径身份卡
            st.markdown(
                f"**路径身份**：{p.get('school')} · 学院 {p.get('college')} · "
                f"专业 {p.get('program')} · {p.get('direction','')} · "
                f"{p.get('mode','')} · {p.get('city','')} · 第四单元 {p.get('exam4','')}"
            )
            col_a, col_b = st.columns(2)
            col_a.markdown(f"🟦 历史核验：{p.get('verify2028','')}")
            col_b.markdown(f"🟥 2028 资格：{p.get('qual2028','')}")
            st.markdown(f"**风险线索**：{p.get('risk','') or '暂无'}")
            if p.get("note"):
                st.caption(f"备注：{p['note']}")

            # 真实证据按主题归并展示
            if items:
                st.markdown(f"**🟦 历史研究证据（{len(items)} 条）**")
                for it in items:
                    st.markdown(
                        f"- {_grade_badge(it.get('grade',''))} ｜ {it.get('verify_status','')} ｜ "
                        f"指标：{it.get('indicator','')}"
                    )
                    st.caption(f"　{it.get('statement','')}")
                    if it.get("match_limit"):
                        st.caption(f"　⚠️ 匹配限制：{it['match_limit']}")
            else:
                st.caption("该路径暂无逐条研究证据记录。")

    # ── ④ 一次考研策略 ───────────────────────────────────────────────────
    st.subheader("④ 一次考研策略")
    st.caption("你『只考一次、不二战』：并行研究 2–3 条候选路径、共用基础备考，报名时确定一个一志愿。研究分组是历史分析师意见，需要用最新目录复核。")
    for title, targets, why in STRATEGY:
        st.markdown(f"**{title}**：{targets}")
        st.caption(f"　{why}")

    # ── ⑤ 决策敏感性 ─────────────────────────────────────────────────────
    st.subheader("⑤ 决策敏感性（哪些新证据会改变结论）")
    st.caption("按『一旦揭晓是否让当前结论整体失效』排序。")
    for rank, item, reason in SENSITIVITY:
        st.markdown(f"**#{rank}｜{item}**")
        st.caption(f"　为何排这里：{reason}")

    # ── 来源与年份说明 ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("来源与年份说明")
    st.markdown(
        f"- 数据来源：`data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx` 的 `3_2证据映射候选` 表"
        f"（共 **{len(flat)}** 条逐路径证据）。\n"
        f"- {data.get('source_year_note','')}\n"
        "- 名额数字：北邮为含推免目录计划；其余为复试阶段公开招考或目录推算（已扣推免），口径不一，"
        "**仅作横向感受，非 2028 统考名额、非录取概率**。\n"
        "- 统一可信源：本页与 `docs/2028_AI_MASTER_DECISION_REPORT.md` 均基于 "
        "`data/school_research_consolidated.json`，保证一致。"
    )
    st.markdown("**证据来源等级图例**")
    st.markdown("｜".join(f"`{k}` {v}" for k, v in _GRADE_LEGEND.items()))

    if openq:
        with st.expander(f"待核问题清单（{len(openq)} 条，来自历史研究底稿）", expanded=False):
            for q in openq:
                st.markdown(f"- {q}")
