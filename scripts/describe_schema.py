#!/usr/bin/env python3
"""生成数据库结构说明（Markdown）。

    python scripts/describe_schema.py --out docs/data_dictionary.md --append
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from decision_system.models.base import Base  # noqa: E402
from decision_system.models import entities  # noqa: F401,E402

TABLE_PURPOSE = {
    "school": "学校",
    "college": "学院（学校一对多）",
    "program": "专业（同一专业代码可在多个学院存在）",
    "admission_year": "招生年度维度（目录是否已发布）",
    "admission_path": "招生路径（决策对象，path_key 唯一）",
    "admission_record": "招生计划/实际录取记录（计划数与实际录取数分离）",
    "research_resource": "研究资源（平台/实验室/校企合作）",
    "mentor": "导师",
    "resource_path_link": "研究资源 ↔ 招生路径 的证据化关联",
    "evidence_source": "证据来源登记（核验状态决定是否可进入评分）",
    "evidence_claim": "事实声明（来源支持的具体事实）",
    "claim_path_link": "事实声明 ↔ 招生路径 关联",
    "claim_indicator_link": "事实声明 ↔ 指标 关联（是否支持该指标）",
    "claim_conflict": "来源冲突登记（保留冲突，不自动合并）",
    "indicator": "三级指标树节点（level=1/2/3）",
    "weight_profile": "权重配置（is_demo 标记演示配置）",
    "weight_node": "权重节点（组内相对权重）",
    "scenario": "情景定义（职业/报考/科研优先）",
    "scenario_multiplier": "情景倍率（作用于一级或三级指标）",
    "score_record": "（路径 × 指标）评分记录",
    "hard_constraint_evaluation": "硬约束评估留痕",
    "decision_result": "决策输出快照（JSON）",
    "audit_log": "审计日志",
    "import_batch": "导入批次（幂等控制与报告留痕）",
}


def render() -> str:
    lines = ["## 数据库表结构（自动生成）", ""]
    lines.append("| 表名 | 用途 | 字段 |")
    lines.append("|---|---|---|")
    for table in Base.metadata.sorted_tables:
        cols = []
        for c in table.columns:
            parts = [f"`{c.name}`", str(c.type)]
            if c.primary_key:
                parts.append("PK")
            if c.foreign_keys:
                parts.append("FK")
            if not c.nullable and not c.primary_key:
                parts.append("NOT NULL")
            cols.append(" ".join(parts))
        uniques = [", ".join(u.columns.keys()) for u in table.constraints if u.__class__.__name__ == "UniqueConstraint"]
        unique_text = f"<br>**唯一约束**: {'; '.join(uniques)}" if uniques else ""
        lines.append(
            f"| `{table.name}` | {TABLE_PURPOSE.get(table.name, '-')}{unique_text} | "
            + "<br>".join(cols)
            + " |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "reports" / "db_schema.md"))
    parser.add_argument("--append", default="", help="追加到指定 Markdown 文件末尾")
    args = parser.parse_args(argv)

    text = render()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"[OK] 数据库结构说明 -> {args.out}")

    if args.append:
        target = Path(args.append)
        content = target.read_text(encoding="utf-8")
        marker = "<!-- AUTO_SCHEMA -->"
        if marker in content:
            head = content.split(marker)[0]
            target.write_text(head + marker + "\n\n" + text, encoding="utf-8")
        else:
            target.write_text(content + "\n" + text, encoding="utf-8")
        print(f"[OK] 已追加到 -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
