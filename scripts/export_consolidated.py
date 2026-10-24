"""导出整合研究数据：Excel（Phase3_7C）-> data/school_research_consolidated.json。

用途：
    1. 把分散在 Excel 三张表（路径 / 3_2证据映射候选 / 待核问题）的研究证据，
       投影为 Web『⑦ 择校结果总览』与 Markdown 报告共用的单一可信源 JSON。
    2. 让 JSON 可由已入库的 Excel **重新生成**（纯投影，不丢弃任何原始研究行），
       从而保证：更新 Excel 后重新导出不会覆盖 / 丢失已有研究记录。

纪律：
    * 只读 Excel，不写数据库、不做任何推断 / 评分。
    * 输出字段与现有 consolidated JSON 保持一致，Web 与报告无需改动即可读取。
    * 可重复执行，幂等（每次都基于完整源表重建，结果等价于源表的完整投影）。

用法：
    python scripts/export_consolidated.py
    python scripts/export_consolidated.py --excel data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx \
        --out data/school_research_consolidated.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_EXCEL = os.path.join(ROOT, "data", "raw", "Phase3_7C_情景覆盖率门槛修复版.xlsx")
DEFAULT_OUT = os.path.join(ROOT, "data", "school_research_consolidated.json")

SOURCE_YEAR_NOTE = (
    "研究证据多为 2023–2027 历史事实/学院级资源；均非 2028 官方招生资格确认"
)

# 路径表列（按表头精确匹配，避免位置变化导致错位）
PATH_COLS = {
    "路径ID": "path_id",
    "学校": "school",
    "学院码": "college",
    "专业码": "program",
    "学习方式": "mode",
    "方向/类别": "direction",
    "初试第四单元": "exam4",
    "培养地": "city",
    "2028核验状态": "verify2028",
    "关键风险": "risk",
    "准入状态": "admission_status",
    "2028正式资格状态": "qual2028",
    "资格说明": "note",
}

# 证据映射表列
EVIDENCE_COLS = {
    "路径ID": "path_id",
    "学校": "school",
    "学院": "college",
    "专业": "program",
    "三级指标": "indicator",
    "来源阶段": "stage",
    "证据主题": "theme",
    "证据陈述（原文）": "statement",
    "来源ID": "source_id",
    "证据等级": "grade",
    "可进入性": "accessibility",
    "核验状态": "verify_status",
    "匹配限制": "match_limit",
    "评分状态": "score_status",
}


def _rows(ws) -> List[tuple]:
    return list(ws.iter_rows(values_only=True))


def _header_index(header, name):
    try:
        return header.index(name)
    except ValueError:
        return None


def _cell(row, header, name):
    idx = _header_index(header, name)
    return row[idx] if idx is not None and idx < len(row) else None


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _build_paths(wb) -> List[Dict]:
    ws = wb["路径"]
    rows = _rows(ws)
    if not rows:
        return []
    header = list(rows[0])
    out: List[Dict] = []
    for row in rows[1:]:
        pid = _clean(_cell(row, header, "路径ID"))
        if not pid:
            continue
        item = {}
        for cn, key in PATH_COLS.items():
            item[key] = _clean(_cell(row, header, cn))
        out.append(item)
    return out


def _build_evidence(wb) -> Dict:
    ws = wb["3_2证据映射候选"]
    rows = _rows(ws)
    if not rows:
        return {"by_path": {}, "flat": []}
    header = list(rows[0])
    by_path: Dict[str, List[Dict]] = {}
    flat: List[Dict] = []
    for row_number, row in enumerate(rows[1:], start=2):
        pid = _clean(_cell(row, header, "路径ID"))
        if not pid:
            continue
        item = {}
        for cn, key in EVIDENCE_COLS.items():
            item[key] = _clean(_cell(row, header, cn))
        item["record_id"] = f"R{row_number:04d}"
        item["source_sheet"] = ws.title
        item["source_row"] = row_number
        by_path.setdefault(pid, []).append(item)
        flat.append(item)
    return {"by_path": by_path, "flat": flat}


def _build_open_questions(wb) -> List[str]:
    if "待核问题" not in wb.sheetnames:
        return []
    ws = wb["待核问题"]
    rows = _rows(ws)
    if len(rows) < 2:
        return []
    header = list(rows[0])
    out: List[str] = []
    for row in rows[1:]:
        pri = _clean(_cell(row, header, "优先级"))
        who = _clean(_cell(row, header, "学校/路径"))
        content = _clean(_cell(row, header, "待核内容"))
        impact = _clean(_cell(row, header, "决策影响"))
        status = _clean(_cell(row, header, "状态"))
        if not who and not content:
            continue
        out.append(" | ".join([x or "" for x in (pri, who, content, impact, status)]))
    return out


def export(excel_path: str, out_path: str) -> Dict:
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    paths = _build_paths(wb)
    ev = _build_evidence(wb)
    openq = _build_open_questions(wb)
    wb.close()

    result = {
        "schema_version": 2,
        "source_file": os.path.relpath(excel_path, ROOT).replace(os.sep, "/"),
        "source_sha256": hashlib.sha256(Path(excel_path).read_bytes()).hexdigest(),
        "source_year_note": SOURCE_YEAR_NOTE,
        "paths": paths,
        "research_by_path": ev["by_path"],
        "research_flat": ev["flat"],
        "open_questions": openq,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    return {
        "paths": len(paths),
        "flat": len(ev["flat"]),
        "open_questions": len(openq),
        "out": out_path,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="导出整合研究数据 JSON")
    ap.add_argument("--excel", default=DEFAULT_EXCEL)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    if not os.path.exists(args.excel):
        raise SystemExit(f"找不到 Excel 原件：{args.excel}")
    summary = export(args.excel, args.out)
    print(
        f"[OK] 已导出：路径 {summary['paths']} 条 / 研究证据 {summary['flat']} 条 / "
        f"待核问题 {summary['open_questions']} 条 -> {summary['out']}"
    )


if __name__ == "__main__":
    main()
