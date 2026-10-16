#!/usr/bin/env python3
"""Phase 5.0｜把北邮 2027 目录原件核验结果回写到 Phase 3.7C 研究 Excel。

实现方式：**直接编辑 XLSX 内部 XML**，不用 openpyxl 保存。
原因：openpyxl 保存会丢弃全部公式的缓存计算值（实测 959 处公式单元格的
`data_only=True` 取值由数值变为 None），属于对既有文件的意外破坏。
直编 XML 可保证除目标单元格外的所有字节（含缓存值、样式、数据验证）原样保留。

严格约束（对应用户指令）：
    1.  修改前必须已存在原始 Excel 备份，否则拒绝执行；
    2.  只改「待核问题」页（E2 闭合状态 + 新增行）与「路径」页北邮两行「关键风险」（J2/J3）；
    3.  保留原有记录：不删除任何原单元格；闭合一律采用「原文 + 追加说明」，原文完整留在单元格里；
    4.  **不得**把 2027 已核验事实升级为 2028 已确认事实——所有新增文本均显式标注「适用2027，非2028」；
    5.  **不得**触碰评分（证据评分 / 三级证据评分）、权重（权重 / 三级指标树 / 3_2情景权重）、
        任何公式、以及其他 4 所学校的任何数据；
    6.  幂等：以 CLOSURE_MARKER 判断是否已回写，重复执行不产生第二份记录。

用法：
    python3 scripts/update_phase37c_bupt_closure.py --apply     # 实际写入
    python3 scripts/update_phase37c_bupt_closure.py             # 预演（不写文件）
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "data" / "raw" / "Phase3_7C_情景覆盖率门槛修复版.xlsx"
BACKUP = ROOT / "data" / "backup" / "Phase3_7C_情景覆盖率门槛修复版.bak_phase5_0.xlsx"

TARGET_SHEETS = {"待核问题": "xl/worksheets/sheet9.xml", "路径": "xl/worksheets/sheet5.xml"}

CLOSURE_MARKER = "【Phase5.0 闭合】"
VERIFY_DATE = "2026-10-16"
YEAR_NOTE = "适用2027，非2028"

CATALOG_URL = "https://yzb.bupt.edu.cn/info/1018/1482.htm"
ADJ_URL = "https://yzb.bupt.edu.cn/info/1031/1412.htm"
CATALOG_SNAP = "data/raw/bupt_2027/2027_人工智能学院硕士专业目录_1482.txt"
ADJ_SNAP = "data/raw/bupt_2027/2027_初试科目调整公告_1412.txt"

# ---------------------------------------------------------------------------
# 「待核问题」页：1 条闭合记录 + 6 条新增待核问题（追加在原有 7 行之后）
# ---------------------------------------------------------------------------
CLOSURE_ROW = [
    "P0",
    "北邮005",
    (
        f"{CLOSURE_MARKER}2027 目录原件缺失已闭合（核验日期 {VERIFY_DATE}）。"
        f"官方来源：北京邮电大学研究生招生网《2027年人工智能学院硕士专业目录》{CATALOG_URL}"
        f"（页面标注发布时间 2026-10-04）；"
        f"配套官方公告《2027年硕士研究生招生考试初试科目调整公告》{ADJ_URL}"
        f"（发布时间 2026-06-09，落款 北京邮电大学 招生处）。"
        f"原文快照：{CATALOG_SNAP}、{ADJ_SNAP}。"
        f"对应已核验事实：005 人工智能学院合计 272 人；085410 人工智能 132 人（此专业为专业学位）；"
        f"方向01 人工智能与信息网络 43 人、初试第四单元 801 通信原理；"
        f"方向02 人工智能与大数据 89 人、初试第四单元 408 计算机学科专业基础；"
        f"085410 初试业务课由《809数据结构》调整为《408计算机学科专业基础》；"
        f"名额口径为目录计划数（含推免），非统考计划、非实际录取。"
        f"自洽校验：43+89=132，2+132+138=272。"
        f"**以上全部 {YEAR_NOTE}，不构成 2028 已确认事实。**"
        f"原记录：P0 北邮005「2027目录原件、方向01/02科目与名额」，原状态 未闭合。"
    ),
    "备考路径",
    f"已闭合（原：未闭合）· {VERIFY_DATE}",
]

NEW_QUESTIONS: list[list[str]] = [
    [
        "P0",
        "北邮005",
        (
            "2026 年 085410 分方向考试科目原件仍未取得，无法判定历史表述"
            "「方向01 维持 801 通信原理（未变更）」中的『未变更』是否成立；"
            "现有第三方聚合站旁证（2026 方向02=809数据结构）仅有检索片段，按规则不予采信"
        ),
        "科目可信度",
        "未闭合",
    ],
    [
        "P0",
        "北邮005",
        (
            "统考招生计划数与实际录取人数均未取得；现有 43/89/132/272 为**目录计划数（含推免）**，"
            "官方原注明示『招生人数仅供参考，最终以教育部下达的招生计划为准』，三者口径不得混用"
        ),
        "名额风险",
        "未闭合",
    ],
    [
        "P1",
        "北邮005",
        (
            "口径层级差异待人工裁定：官方调整公告为**专业级**表述（085410 人工智能 809→408），"
            "而官方 2027 目录为**方向级**结果（方向01 仍为 801、仅方向02 为 408）；"
            "公告不能直接推出『085410 全部方向改 408』"
        ),
        "科目可信度",
        "待裁定",
    ],
    [
        "P1",
        "北邮005",
        (
            "导师与科研资源无证据：官方 2027 目录未逐方向列导师，备注指引的学院官网"
            "『师资队伍-师资一览』『人才培养-研究生培养-研究生招生』栏目"
            f"定向访问返回 HTTP 412（站点防护拦截，{VERIFY_DATE}），页面正文未取得"
        ),
        "导师与资源可进入性",
        "未闭合",
    ],
    [
        "P2",
        "北邮005",
        "复试细则、复试科目与成绩计算办法未取得；初复试权重与淘汰口径无法评估",
        "考试风险",
        "未闭合",
    ],
    [
        "P2",
        "北邮140500",
        (
            "同院 140500 智能科学与技术（138 人；方向01 801/42 人、方向02 408/96 人）"
            f"与 085410 科目结构相同，本系统未纳入，是否作为候选路径待评估（仅据 2027 官方目录，{YEAR_NOTE}）"
        ),
        "路径覆盖",
        "待评估",
    ],
]

# ---------------------------------------------------------------------------
# 「路径」页：北邮两行「关键风险」（J 列）——原文保留，追加闭合说明
# ---------------------------------------------------------------------------
RISK_SUFFIX = f"（原件已于 {VERIFY_DATE} 取得官方原文并核验，{YEAR_NOTE}）"
PATH_RISK_CELLS = {"J2": "北邮2027目录原件未取得", "J3": "2027改408；原件未取得"}


def _cell_xml(ref: str, text: str) -> str:
    return (
        f'<x:c r="{ref}" t="inlineStr"><x:is>'
        f'<x:t xml:space="preserve">{escape(text)}</x:t>'
        f"</x:is></x:c>"
    )


def _row_xml(row_no: int, values: list[str]) -> str:
    cells = "".join(_cell_xml(f"{col}{row_no}", v) for col, v in zip("ABCDE", values))
    return f'<x:row r="{row_no}">{cells}</x:row>'


def _set_inline_text(xml: str, ref: str, new_text: str) -> tuple[str, str, str]:
    """把 inlineStr 单元格文本替换为 new_text。返回 (新xml, 旧文本, 新文本)。"""
    pat = re.compile(
        r'(<x:c r="' + re.escape(ref) + r'" t="inlineStr"><x:is><x:t[^>]*>)(.*?)(</x:t></x:is></x:c>)',
        re.S,
    )
    m = pat.search(xml)
    if not m:
        raise SystemExit(f"[FAIL] 未找到单元格 {ref} 的 inlineStr 结构，格式可能与预期不符")
    old = m.group(2)
    return pat.sub(lambda _: m.group(1) + escape(new_text) + m.group(3), xml, count=1), old, new_text


def build_patch() -> dict[str, str]:
    """返回 {zip内路径: 新XML内容}，并收集动作清单。"""
    z = zipfile.ZipFile(XLSX)
    src9 = z.read(TARGET_SHEETS["待核问题"]).decode("utf-8")
    src5 = z.read(TARGET_SHEETS["路径"]).decode("utf-8")
    z.close()

    actions: list[dict] = []

    # --- 待核问题 ---
    if CLOSURE_MARKER in src9:
        actions.append({"sheet": "待核问题", "cell": "—", "note": "已回写过，跳过（幂等）"})
        out9 = src9
    else:
        out9, old_e2, new_e2 = _set_inline_text(src9, "E2", "已闭合（原：未闭合）")
        actions.append({"sheet": "待核问题", "cell": "E2", "from": old_e2, "to": new_e2})

        rows = [CLOSURE_ROW] + NEW_QUESTIONS
        start = 9
        block = "".join(_row_xml(start + i, row) for i, row in enumerate(rows))
        marker = "</x:sheetData>"
        if marker not in out9:
            raise SystemExit("[FAIL] 待核问题 页未找到 </x:sheetData>")
        out9 = out9.replace(marker, block + marker, 1)
        for i, row in enumerate(rows):
            r = start + i
            actions.append(
                {
                    "sheet": "待核问题",
                    "cell": f"A{r}:E{r}",
                    "from": "(新增行)",
                    "to": f"{row[0]} / {row[1]} / {row[3]} / {row[4]}",
                }
            )

    # --- 路径 ---
    out5 = src5
    for ref, expect in PATH_RISK_CELLS.items():
        pat = re.compile(
            r'(<x:c r="' + re.escape(ref) + r'" t="inlineStr"><x:is><x:t[^>]*>)(.*?)(</x:t></x:is></x:c>)',
            re.S,
        )
        m = pat.search(out5)
        if not m:
            raise SystemExit(f"[FAIL] 未找到 路径!{ref}")
        cur = m.group(1 + 1)
        if RISK_SUFFIX in cur:
            actions.append({"sheet": "路径", "cell": ref, "note": "已追加过，跳过（幂等）"})
            continue
        if not cur.startswith(expect):
            raise SystemExit(f"[FAIL] 路径!{ref} 原文前缀不符（现为 {cur!r}），拒绝修改以免误改")
        new_text = f"{cur}{RISK_SUFFIX}"
        out5, old_v, new_v = _set_inline_text(out5, ref, new_text)
        actions.append({"sheet": "路径", "cell": ref, "from": old_v, "to": new_v})

    return {"files": {TARGET_SHEETS["待核问题"]: out9, TARGET_SHEETS["路径"]: out5}, "actions": actions}


def apply_patch(files: dict[str, str]) -> None:
    """重建 zip：除目标 sheet 外，所有条目按原 ZipInfo 原样复制。"""
    tmp = XLSX.with_suffix(".xlsx.tmp")
    zin = zipfile.ZipFile(XLSX)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in files:
                data = files[info.filename].encode("utf-8")
            new_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.internal_attr = info.internal_attr
            new_info.create_system = info.create_system
            zout.writestr(new_info, data)
    zin.close()
    shutil.move(str(tmp), str(XLSX))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（默认仅预演）")
    args = ap.parse_args()

    if not BACKUP.is_file():
        print(f"[FAIL] 未找到原始 Excel 备份：{BACKUP}（必须先备份再修改）", file=sys.stderr)
        return 1

    patch = build_patch()
    for a in patch["actions"]:
        if "note" in a:
            print(f"[{a['sheet']}] {a['cell']}: {a['note']}")
        else:
            print(f"[{a['sheet']}] {a['cell']}: {a['from']!r} -> {a['to']!r}")

    if args.apply:
        apply_patch(patch["files"])
        print(f"\n已写入：{XLSX}")
    else:
        print(f"\n预演完成（未保存）：{XLSX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
