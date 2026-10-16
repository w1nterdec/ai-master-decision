#!/usr/bin/env python3
"""Phase 5.0｜北邮（BUPT）真实招生数据最小迁移脚本。

约束（严格遵循 Phase 5.0 任务书）：
    1.  迁移前先备份数据库（data/backup/ 下），保留迁移前基线；
    2.  只登记**已实际取得本体**的真实来源，URL / 发布日期 / 发布机构均来自官方页面原文；
    3.  不覆盖、不删除任何历史记录（含历史候选映射），历史候选映射一律**不**自动升级；
    4.  未取得官方原文的，一律保持「待核验」，严禁标为已核验；
    5.  名额必须区分「目录计划数（含推免）/ 统考计划 / 实际录取」，不得混用，不得零填充未知数；
    6.  绝不生成 2028 年已确认记录，2028 一律保持未确认；
    7.  只触碰 BUPT（path_key 以 "BUPT|" 开头）的路径，其他学校一律不动；
    8.  绝不触碰权重（weight_profile / weight_node）与演示权重；
    9.  每一步写审计日志（audit_log）；
   10.  幂等：重复执行不新增重复行，第二次执行后各表计数与第一次执行后完全一致。

用法：
    PYTHONPATH=src python3 scripts/migrate_bupt_phase5_0.py --apply
    PYTHONPATH=src python3 scripts/migrate_bupt_phase5_0.py --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from decision_system.evidence.registry import _audit  # noqa: E402
from decision_system.models.entities import (  # noqa: E402
    AdmissionPath,
    AuditLog,
    EvidenceClaim,
    EvidenceSource,
)
from decision_system.models.enums import (  # noqa: E402
    ClaimStatus,
    SourceType,
    VerificationStatus,
)
from decision_system.services.db import (  # noqa: E402
    create_sqlite_engine,
    make_session_factory,
)
from decision_system.services import evidence_service as ev  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "decision.db"
BACKUP_PATH = ROOT / "data" / "backup" / "decision.db.bak_phase5_0"
REPORT_PATH = ROOT / "reports" / "phase5_0_bupt_migration.json"

ACTOR = "phase5.0-bupt"
FETCH_DATE = "2026-10-16"
MARKER = "[Phase5.0]"

# ---------------------------------------------------------------------------
# 来源清单（全部为实际访问过的官方页面；发布日期/发布机构取自页面原文）
# ---------------------------------------------------------------------------
SOURCES: list[dict[str, Any]] = [
    {
        "source_id": "S-BUPT-2027-CATALOG-005",
        "title": "2027年人工智能学院硕士专业目录（北京邮电大学研究生招生网）",
        "publisher": "北京邮电大学研究生招生网 / 北京邮电大学招生办公室",
        "url_or_file": (
            "https://yzb.bupt.edu.cn/info/1018/1482.htm"
            "；本地快照：data/raw/bupt_2027/2027_人工智能学院硕士专业目录_1482.txt"
        ),
        "source_type": SourceType.OFFICIAL_CATALOG,
        "published_year": 2026,
        # 页面原文标注「发布时间：2026-10-04」（register_source_strict 只接受年份，故另行精确回填）
        "published_date": "2026-10-04",
        "applicable_years": [2027],
        "verified": True,
        "basis": (
            "2026-10-16 以真实浏览器渲染官方 URL https://yzb.bupt.edu.cn/info/1018/1482.htm "
            "取得页面正文（页面标题『2027年人工智能学院硕士专业目录-北邮研究生招生网』，"
            "页面标注 发布时间：2026-10-04，页脚『版权所有 © 北京邮电大学招生办公室』）。"
            "正文人数自洽校验通过：085410 方向01 43 + 方向02 89 = 085410 合计 132；"
            "081000(2) + 085410(132) + 140500(138) = 学院合计 272。正文已落本地快照。"
        ),
        "note": "P1 官方招生目录；适用招生年份 2027（非 2028）。",
    },
    {
        "source_id": "S-BUPT-2027-EXAMADJ",
        "title": "北京邮电大学2027年硕士研究生招生考试初试科目调整公告",
        "publisher": "北京邮电大学 招生处",
        "url_or_file": (
            "https://yzb.bupt.edu.cn/info/1031/1412.htm"
            "；本地快照：data/raw/bupt_2027/2027_初试科目调整公告_1412.txt"
        ),
        "source_type": SourceType.OFFICIAL_NOTICE,
        "published_year": 2026,
        # 页面原文标注「发布时间：2026-06-09」，落款「北京邮电大学 招生处 2026年6月9日」
        "published_date": "2026-06-09",
        "applicable_years": [2027],
        "verified": True,
        "basis": (
            "2026-10-16 以真实浏览器渲染官方 URL https://yzb.bupt.edu.cn/info/1031/1412.htm "
            "取得页面正文（标题『北京邮电大学2027年硕士研究生招生考试初试科目调整公告』，"
            "页面标注 发布时间：2026-06-09，落款『北京邮电大学 招生处 2026年6月9日』）。"
            "正文含调整表：人工智能学院 / 085410人工智能 / 《809数据结构》→《408计算机学科专业基础》。"
        ),
        "note": "P1 官方公告；适用招生年份 2027（非 2028）。",
    },
    {
        "source_id": "S-BUPT-AI-COLLEGE-SITE",
        "title": "北京邮电大学人工智能学院官网（师资队伍-师资一览 / 研究生招生栏目）",
        "publisher": "北京邮电大学人工智能学院",
        "url_or_file": "https://ai.bupt.edu.cn/",
        "source_type": SourceType.OFFICIAL_WEB,
        "published_year": None,
        "applicable_years": [2027],
        "verified": False,
        "basis": "",
        "note": (
            "该 URL 来自 2027 官方招生目录『备注』栏原文指引（导师详见学院官网两个栏目）。"
            "2026-10-16 定向访问返回 HTTP 412（站点防护拦截），未取得页面正文，"
            "故保持「待核验」，不得据此生成任何已核验的导师/科研资源结论。"
        ),
    },
]

# ---------------------------------------------------------------------------
# 事实声明清单
#   status: "verified" 表示经官方原文核验；"pending" 表示待核验（不升级）
# ---------------------------------------------------------------------------
CLAIMS: list[dict[str, Any]] = [
    # --- 学院 / 专业总盘 ---
    {
        "key": "C1-college-total",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "招生名额（目录计划口径）",
        "statement": (
            "【已核验事实·适用2027】2027 年北邮 005 人工智能学院硕士专业目录合计 272 人；"
            "其中 085410 人工智能 132 人，目录原文标注『此专业为专业学位』。"
            "该人数为**目录计划数（含推免）**，非统考招生计划，亦非实际录取人数。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 目录原文（1482.htm）：『005 人工智能学院 … 272』『085410 人工智能 … 132』『此专业为专业学位』。",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [
            ("L3-报考可行性|招生路径|名额口径可靠性", True),
            ("L3-报考可行性|招生路径|全日制统考路径明确性", True),
        ],
    },
    # --- 方向 01 ---
    {
        "key": "C2-dir01",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "方向01 考试科目与名额",
        "statement": (
            "【已核验事实·适用2027】2027 年北邮 005 085410 人工智能 方向"
            "『01 人工智能与信息网络』：目录所列招生人数 43 人（**目录计划数，含推免**）；"
            "初试科目 ①101 思想政治理论 ②201 英语（一）③301 数学（一）④801 通信原理。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 目录原文（1482.htm）方向行：『01 人工智能与信息网络 … 43 … ④801|通信原理』。",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿"],
        "indicators": [
            ("L3-报考可行性|考试风险|初复试科目稳定性", True),
            ("L3-报考可行性|招生路径|名额口径可靠性", True),
            ("L3-报考可行性|招生路径|全日制统考路径明确性", True),
        ],
    },
    # --- 方向 02 ---
    {
        "key": "C3-dir02",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "方向02 考试科目与名额",
        "statement": (
            "【已核验事实·适用2027】2027 年北邮 005 085410 人工智能 方向"
            "『02 人工智能与大数据』：目录所列招生人数 89 人（**目录计划数，含推免**）；"
            "初试科目 ①101 思想政治理论 ②201 英语（一）③301 数学（一）④408 计算机学科专业基础。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 目录原文（1482.htm）方向行：『02 人工智能与大数据 … 89 … ④408|计算机学科专业基础』。",
        "paths": ["BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [
            ("L3-报考可行性|考试风险|初复试科目稳定性", True),
            ("L3-报考可行性|招生路径|名额口径可靠性", True),
            ("L3-报考可行性|招生路径|全日制统考路径明确性", True),
        ],
    },
    # --- 名额口径 ---
    {
        "key": "C4-quota-caliber",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "名额口径",
        "statement": (
            "【已核验事实·适用2027·名额口径】官方 2027 目录原注：『招生目录中所公布招生人数均包含推免生，"
            "推免生人数以最终录取推免生人数为准。招生人数仅供参考，最终以教育部下达的招生计划为准。』"
            "因此 43 / 89 / 132 / 272 均为**目录计划数（含推免）**，"
            "与『统考招生计划』『实际录取人数』是三个不同口径，本系统当前**未取得**后两者数据。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 目录原文（1482.htm）表下注释原文照录。",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [("L3-报考可行性|招生路径|名额口径可靠性", True)],
    },
    # --- 导师信息口径 ---
    {
        "key": "C5-mentor-not-listed",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "导师信息可得性",
        "statement": (
            "【已核验事实·适用2027】官方 2027 目录**未逐方向列出指导教师**，"
            "备注栏原文指引：『具体招生团队及导师详见人工智能学院官网（https://ai.bupt.edu.cn/）"
            "「人才培养-研究生培养-研究生招生」栏目，以及「师资队伍-师资一览」栏目』。"
            "即：导师名单须另查学院官网，本目录不提供；该指引页 2026-10-16 定向访问被拦截（HTTP 412），尚未取得。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 目录原文（1482.htm）备注栏原文照录。",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        # supports=False：该声明不足以正向支撑「导师招生路径证据」指标，明确记为不支持
        "indicators": [("L3-研究培养|科研匹配|导师招生路径证据", False)],
    },
    # --- 初试科目调整公告 ---
    {
        "key": "C6-exam-adjust",
        "source_id": "S-BUPT-2027-EXAMADJ",
        "topic": "初试科目调整（2027）",
        "statement": (
            "【已核验事实·适用2027】北京邮电大学 2027 年硕士研究生招生考试初试科目调整公告原文："
            "人工智能学院 085410人工智能 调整前《809数据结构》→ 调整后《408计算机学科专业基础》"
            "（140500智能科学与技术同口径调整）；公告落款『北京邮电大学 招生处 2026年6月9日』，"
            "并声明『各专业最终考试科目以我校正式发布的招生简章和招生专业目录为准』。"
        ),
        "applicable_years": [2027],
        "status": "verified",
        "basis": "官方 2027 调整公告原文（1412.htm）调整表行与落款、声明句原文照录。",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [("L3-报考可行性|考试风险|初复试科目稳定性", True)],
    },
    # --- 口径层级差异（待核验，不升级） ---
    {
        "key": "C7-granularity-caveat",
        "source_id": "S-BUPT-2027-EXAMADJ",
        "topic": "口径层级差异（待人工裁定）",
        "statement": (
            "【待核验事实·口径层级差异】该调整公告为**专业级**表述（085410 人工智能 809→408），"
            "而 2027 正式目录为**方向级**结果（方向01=④801 通信原理，仅方向02=④408）。"
            "二者层级不同：公告**不能**直接推出『085410 全部方向均改 408』。"
            "需人工确认 2026 年 085410 分方向科目的原始口径（本批未取得 2026 目录原件），"
            "才能判定『方向01 维持 801 未变更』这一历史表述。"
        ),
        "applicable_years": [2027],
        "status": "pending",
        "basis": "",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [("L3-报考可行性|考试风险|初复试科目稳定性", True)],
    },
    # --- 2028 未确认（推断，不得作为已核验事实） ---
    {
        "key": "C8-2028-not-published",
        "source_id": "S-BUPT-2027-CATALOG-005",
        "topic": "2028 招生资格",
        "statement": (
            "【推断·待核验·非已核验事实】截至 2026-10-16，北邮研究生招生网已发布的最高年度硕士专业目录为 2027 年"
            "（2026-10-04 发布），2028 年硕士专业目录尚未发布。"
            "因此 2028 年北邮 005 085410 是否招生、分方向设置、考试科目、招生名额**均无法确认**。"
            "本条为推断性记录，不构成 2028 年已确认事实，不得用于任何 2028 资格确认。"
        ),
        "applicable_years": [2028],
        "status": "pending",
        "basis": "",
        "paths": ["BUPT|005|085410|全日制|方向01|2028|统考|一志愿", "BUPT|005|085410|全日制|方向02|2028|统考|一志愿"],
        "indicators": [("L3-报考可行性|招生路径|全日制统考路径明确性", True)],
    },
]

# ---------------------------------------------------------------------------
# 路径补充说明（追加式，保留原文本；仅在未追加过时写入）
# ---------------------------------------------------------------------------
PATH_NOTE_SUFFIX = (
    f"{MARKER} 2026-10-16 经官方网页（2027 硕士专业目录 / 2027 初试科目调整公告）取得原文并核验；"
    "但官方事实适用年份为 **2027**，本路径目标年份为 2028，属跨年引用，2028 仍为未确认。"
    "名额 43/89/132 为目录计划数（含推免），非统考计划、非实际录取。"
)
PATH_NEW_KEY_RISK = {
    "BUPT|005|085410|全日制|方向01|2028|统考|一志愿": (
        "2028 目录未发布（截至2026-10-16），2028 仍未确认；2027 官方事实已核验但适用年份为2027，"
        "非2028；名额为目录计划数（含推免），统考计划与实际录取未取得"
    ),
    "BUPT|005|085410|全日制|方向02|2028|统考|一志愿": (
        "2028 目录未发布（截至2026-10-16），2028 仍未确认；2027 官方事实已核验但适用年份为2027，"
        "非2028；方向02 业务课 2027 已由 809 改 408，2028 是否延续未确认；"
        "名额为目录计划数（含推免），统考计划与实际录取未取得"
    ),
}

TABLES = [
    "admission_path",
    "admission_record",
    "admission_year",
    "audit_log",
    "claim_conflict",
    "claim_indicator_link",
    "claim_path_link",
    "college",
    "decision_result",
    "evidence_claim",
    "evidence_source",
    "hard_constraint_evaluation",
    "import_batch",
    "indicator",
    "mentor",
    "program",
    "research_resource",
    "resource_path_link",
    "scenario",
    "scenario_multiplier",
    "school",
    "score_record",
    "weight_node",
    "weight_profile",
]


def snapshot(session) -> dict[str, int]:
    out: dict[str, int] = {}
    for t in TABLES:
        out[t] = session.execute(text(f'select count(*) from "{t}"')).scalar()
    return out


def backup_db() -> str:
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not BACKUP_PATH.exists():
        shutil.copy2(DB_PATH, BACKUP_PATH)
        return f"已创建迁移前基线备份 {BACKUP_PATH}"
    return f"迁移前基线备份已存在，未覆盖：{BACKUP_PATH}"


def _find_claim(session, source_db_id: int, statement: str) -> EvidenceClaim | None:
    rows = session.execute(
        select(EvidenceClaim).where(EvidenceClaim.source_id_fk == source_db_id)
    ).scalars().all()
    for c in rows:
        if (c.statement or "").strip() == statement.strip():
            return c
    return None


def run(apply: bool) -> dict[str, Any]:
    engine = create_sqlite_engine(str(DB_PATH))
    sf = make_session_factory(engine)
    result: dict[str, Any] = {
        "apply": apply,
        "db": str(DB_PATH),
        "backup": "",
        "before": {},
        "after": {},
        "sources": [],
        "claims": [],
        "paths_updated": [],
        "warnings": [],
    }

    with sf() as s:
        result["before"] = snapshot(s)
        if apply:
            result["backup"] = backup_db()

        # --- 1. 来源登记 ---
        for spec in SOURCES:
            src = s.execute(
                select(EvidenceSource).where(EvidenceSource.source_id == spec["source_id"])
            ).scalar_one_or_none()
            action = "已存在-跳过"
            if src is None and apply:
                src = ev.register_source_strict(
                    s,
                    source_id=spec["source_id"],
                    title=spec["title"],
                    publisher=spec["publisher"],
                    url_or_file=spec["url_or_file"],
                    source_type=spec["source_type"],
                    published_year=spec["published_year"],
                    applicable_years=spec["applicable_years"],
                    verification_status=VerificationStatus.PENDING,
                    verification_note=spec["note"],
                    is_placeholder=False,
                    actor=ACTOR,
                )
                action = "新登记"
            if src is None:
                result["sources"].append(
                    {"source_id": spec["source_id"], "action": "计划登记（dry-run）", "status": "待核验"}
                )
                continue

            # 精确发布日期回填（仅新登记时执行，保证幂等）
            if apply and action == "新登记" and spec.get("published_date"):
                old = src.published_at
                src.published_at = _dt.date.fromisoformat(spec["published_date"])
                _audit(
                    s,
                    "source.published_at",
                    "EvidenceSource",
                    spec["source_id"],
                    {
                        "from": str(old),
                        "to": spec["published_date"],
                        "origin": "页面原文标注发布时间",
                    },
                    ACTOR,
                )

            if apply and spec["verified"] and src.verification_status is not VerificationStatus.VERIFIED:
                _audit(
                    s,
                    "phase5.migration",
                    "EvidenceSource",
                    spec["source_id"],
                    {"step": "verify", "basis": spec["basis"], "fetched_at": FETCH_DATE},
                    ACTOR,
                )
                src = ev.verify_source(s, spec["source_id"], actor=ACTOR, basis=spec["basis"])
                action += "+已核验"
            elif apply and not spec["verified"] and action == "新登记":
                s.add(
                    AuditLog(
                        actor=ACTOR,
                        action="phase5.migration",
                        entity_type="EvidenceSource",
                        entity_id=spec["source_id"],
                        detail={
                            "step": "keep_pending",
                            "reason": spec["note"],
                            "fetched_at": FETCH_DATE,
                        },
                    )
                )
                action += "+保持待核验（未取得原文）"
            result["sources"].append(
                {
                    "source_id": spec["source_id"],
                    "action": action,
                    "status": str(src.verification_status) if src else "?",
                    "verified_flag": spec["verified"],
                }
            )

        # --- 2. 事实声明登记 ---
        for spec in CLAIMS:
            src = s.execute(
                select(EvidenceSource).where(EvidenceSource.source_id == spec["source_id"])
            ).scalar_one_or_none()
            if src is None:
                result["warnings"].append(f"来源缺失，跳过声明 {spec['key']}")
                continue
            claim = _find_claim(s, src.id, spec["statement"])
            action = "已存在-跳过"
            if claim is None and apply:
                claim = ev.create_claim(
                    s,
                    source_id=spec["source_id"],
                    statement=spec["statement"],
                    topic=spec["topic"],
                    applicable_years=spec["applicable_years"],
                    actor=ACTOR,
                )
                action = "新登记（候选映射）"
            if claim is None:
                result["claims"].append({"key": spec["key"], "action": "计划登记（dry-run）"})
                continue

            if apply and spec["status"] == "verified" and claim.status is not ClaimStatus.VERIFIED:
                claim = ev.approve_claim(
                    s,
                    claim.id,
                    actor=ACTOR,
                    basis=spec["basis"],
                    applicable_years=spec["applicable_years"],
                )
                action += "+已核验"
            elif apply and spec["status"] == "pending" and claim.status is not ClaimStatus.PENDING:
                claim = ev.submit_for_verification(s, claim.id, actor=ACTOR, note=spec["topic"])
                action += "+置为待核验"

            # 关联（link_claim_path / link_claim_indicator 自带去重）
            linked: list[str] = []
            if apply:
                for pk in spec.get("paths", []):
                    try:
                        linked += ev.attach_claim_by_codes(s, claim.id, path_key=pk, actor=ACTOR)
                    except Exception as exc:  # noqa: BLE001
                        result["warnings"].append(f"{spec['key']} 关联路径失败 {pk}: {exc}")
                for code, supports in spec.get("indicators", []):
                    try:
                        linked += ev.attach_claim_by_codes(
                            s, claim.id, indicator_code=code, actor=ACTOR
                        )
                        # attach_claim_by_codes 默认 supports=True；需要不支持时显式改标记
                        if supports is False:
                            from decision_system.models.entities import (
                                ClaimIndicatorLink,
                                Indicator,
                            )

                            ind = s.execute(
                                select(Indicator).where(Indicator.code == code)
                            ).scalar_one_or_none()
                            link = s.execute(
                                select(ClaimIndicatorLink).where(
                                    ClaimIndicatorLink.claim_id == claim.id,
                                    ClaimIndicatorLink.indicator_id == ind.id,
                                )
                            ).scalar_one_or_none()
                            if link is not None and link.supports:
                                link.supports = False
                                _audit(
                                    s,
                                    "claim.link_indicator",
                                    "ClaimIndicatorLink",
                                    link.id,
                                    {"claim_id": claim.id, "indicator_code": code, "supports": False},
                                    ACTOR,
                                )
                    except Exception as exc:  # noqa: BLE001
                        result["warnings"].append(f"{spec['key']} 关联指标失败 {code}: {exc}")

            result["claims"].append(
                {
                    "key": spec["key"],
                    "claim_id": claim.id,
                    "action": action,
                    "status": str(claim.status),
                    "is_candidate": bool(claim.is_candidate),
                    "applicable_years": list(claim.applicable_years or []),
                    "linked": linked,
                }
            )

        # --- 3. 路径补充说明（追加式 + 审计，保留原文本） ---
        if apply:
            for pk, new_risk in PATH_NEW_KEY_RISK.items():
                path = s.execute(
                    select(AdmissionPath).where(AdmissionPath.path_key == pk)
                ).scalar_one_or_none()
                if path is None:
                    result["warnings"].append(f"路径不存在：{pk}")
                    continue
                old_risk = path.key_risk
                old_notes = path.notes
                if MARKER not in (path.notes or ""):
                    path.notes = (
                        f"{old_notes or ''}\n{PATH_NOTE_SUFFIX}"
                        f"\n原关键风险记录：{old_risk}"
                    )
                    path.key_risk = new_risk
                    _audit(
                        s,
                        "path.update",
                        "AdmissionPath",
                        path.id,
                        {
                            "path_key": pk,
                            "old_key_risk": old_risk,
                            "new_key_risk": new_risk,
                            "note_appended": True,
                            "old_notes_preserved": True,
                            "verification_2028_unchanged": str(path.verification_2028),
                        },
                        ACTOR,
                    )
                    result["paths_updated"].append(pk)
                else:
                    result["paths_updated"].append(f"{pk}（已追加过，跳过）")

        result["after"] = snapshot(s)
        if apply:
            s.commit()
        else:
            s.rollback()

    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    args = ap.parse_args()
    res = run(apply=args.apply)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n报告已写入：{REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
