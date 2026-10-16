#!/usr/bin/env python3
"""比对两份 Excel 快照，输出「结构 / 公式 / 数据」三类差异报告。

检查维度：
    A. 结构：工作表数量、顺序、名称、维度、冻结窗格、可见性
    B. 公式：公式单元格的新增 / 删除 / 内容变更（逐格）
    C. 数据：非公式单元格的新增 / 删除 / 内容变更（逐格）
    D. 计算值：公式求值结果是否变化（data_only 视图）
    E. 专项护栏：评分 / 权重 / 其他学校数据是否被触碰

用法：
    python3 scripts/diff_xlsx_snapshots.py <before.json> <after.json> [--md 输出.md]
"""

from __future__ import annotations

import sys
from typing import Any

import json

# 护栏：这些表属于「评分 / 权重 / 公式密集区」，本次只允许零变更
PROTECTED_SHEETS = {
    "证据评分": "评分",
    "三级证据评分": "三级评分",
    "结果": "结果",
    "三级结果与敏感性": "结果",
    "3_2情景比较": "结果",
    "权重": "权重",
    "三级指标树": "权重树",
    "3_2情景权重": "情景权重",
    "参数": "参数",
    "来源登记": "来源登记",
}

# 其他学校的路径行（路径表第 4~11 行 = P03~P10），本次只允许零变更
OTHER_SCHOOL_ROWS = set(range(4, 12))


def load(p: str) -> dict:
    return json.loads(open(p, encoding="utf-8").read())


def diff(before: dict, after: dict) -> dict:
    out: dict[str, Any] = {
        "structure": {"status": "一致", "details": [], "growth": []},
        "formulas": {"added": [], "removed": [], "changed": [], "count_before": 0, "count_after": 0},
        "values": {"added": [], "removed": [], "changed": []},
        "computed": {"changed": [], "note": ""},
        "guards": [],
    }

    # ---------- A. 结构 ----------
    if before["sheetnames"] != after["sheetnames"]:
        out["structure"]["status"] = "**不一致**"
        out["structure"]["details"].append(
            f"工作表集合/顺序变化：{before['sheetnames']} -> {after['sheetnames']}"
        )
    for name in before["sheetnames"]:
        pb, pa = before["sheet_props"].get(name), after["sheet_props"].get(name)
        if pb is None or pa is None:
            out["structure"]["status"] = "**不一致**"
            out["structure"]["details"].append(f"工作表 {name} 缺失")
            continue
        for k in pb:
            if pb[k] != pa[k]:
                # 行数/维度增长属于「新增行」的正常结果，与结构性破坏区分开
                if k in ("max_row", "max_column", "dimensions"):
                    out["structure"]["growth"].append(f"{name}.{k}: {pb[k]} -> {pa[k]}")
                else:
                    out["structure"]["status"] = "**不一致**"
                    out["structure"]["details"].append(f"{name}.{k}: {pb[k]} -> {pa[k]}")
    if out["structure"]["status"] == "一致":
        out["structure"]["details"].append(
            f"工作表 {len(before['sheetnames'])} 张：名称、顺序、sheetId、冻结窗格、可见性全部一致（无增删/改名/重排）"
        )
    if out["structure"]["growth"]:
        out["structure"]["details"].append(
            "行数/维度增长（新增行所致，非结构性破坏）：" + "；".join(out["structure"]["growth"])
        )

    # ---------- B/C. 逐格 ----------
    all_sheets = list(dict.fromkeys(list(before["sheets"].keys()) + list(after["sheets"].keys())))
    for name in all_sheets:
        b = before["sheets"].get(name, {}).get("formula_view", {})
        a = after["sheets"].get(name, {}).get("formula_view", {})
        for coord in sorted(set(b) | set(a)):
            cb, ca = b.get(coord), a.get(coord)
            if cb is None and ca is not None:
                rec = {"sheet": name, "cell": coord, "after": ca["v"]}
                (out["formulas"] if ca["f"] == "F" else out["values"])["added"].append(rec)
                if ca["f"] == "F":
                    out["formulas"]["count_after"] += 1
            elif cb is not None and ca is None:
                rec = {"sheet": name, "cell": coord, "before": cb["v"]}
                (out["formulas"] if cb["f"] == "F" else out["values"])["removed"].append(rec)
            elif cb is not None and ca is not None and cb["v"] != ca["v"]:
                rec = {"sheet": name, "cell": coord, "before": cb["v"], "after": ca["v"]}
                (out["formulas"] if (cb["f"] == "F" or ca["f"] == "F") else out["values"])[
                    "changed"
                ].append(rec)

    for name in all_sheets:
        b = before["sheets"].get(name, {}).get("formula_view", {})
        a = after["sheets"].get(name, {}).get("formula_view", {})
        out["formulas"]["count_before"] += sum(1 for c in b.values() if c["f"] == "F")
        out["formulas"]["count_after"] += sum(1 for c in a.values() if c["f"] == "F")

    # ---------- D. 计算值 ----------
    if "value_view_error" in after:
        out["computed"]["note"] = "无法取得计算值视图"
    else:
        for name in all_sheets:
            b = before["sheets"].get(name, {}).get("value_view", {})
            a = after["sheets"].get(name, {}).get("value_view", {})
            for coord in sorted(set(b) | set(a)):
                if b.get(coord) != a.get(coord):
                    out["computed"]["changed"].append(
                        {"sheet": name, "cell": coord, "before": b.get(coord), "after": a.get(coord)}
                    )

    # ---------- E. 专项护栏 ----------
    touched = set()
    for key, bucket in (("formulas", out["formulas"]), ("values", out["values"])):
        for kind in ("added", "removed", "changed"):
            for r in bucket[kind]:
                touched.add(r["sheet"])

    for sheet, label in PROTECTED_SHEETS.items():
        hit = sheet in touched
        out["guards"].append(
            {
                "item": f"护栏·{label}（{sheet}）",
                "status": "**被改动**" if hit else "零变更",
                "count": sum(
                    1
                    for key in ("formulas", "values")
                    for kind in ("added", "removed", "changed")
                    for r in out[key][kind]
                    if r["sheet"] == sheet
                ),
            }
        )

    other_hit = [
        r
        for key in ("formulas", "values")
        for kind in ("added", "removed", "changed")
        for r in out[key][kind]
        if r["sheet"] == "路径" and int("".join(ch for ch in r["cell"] if ch.isdigit())) in OTHER_SCHOOL_ROWS
    ]
    out["guards"].append(
        {
            "item": "护栏·其他 4 所学校路径行（路径表 P03~P10）",
            "status": "**被改动**" if other_hit else "零变更",
            "count": len(other_hit),
        }
    )
    out["guards"].append(
        {
            "item": "护栏·公式总数",
            "status": "一致" if out["formulas"]["count_before"] == out["formulas"]["count_after"] else "**不一致**",
            "count": f'{out["formulas"]["count_before"]} -> {out["formulas"]["count_after"]}',
        }
    )

    # 缓存值丢失检测：openpyxl 保存会丢弃公式缓存，是本次重点防范的意外破坏
    lost = [
        (name, coord)
        for name in all_sheets
        for coord in before["sheets"].get(name, {}).get("value_view", {})
        if coord not in after["sheets"].get(name, {}).get("value_view", {})
    ]
    out["guards"].append(
        {
            "item": "护栏·公式缓存计算值（是否被清空）",
            "status": "**被清空**" if lost else "未丢失",
            "count": len(lost),
        }
    )
    return out


def to_markdown(d: dict, before_path: str, after_path: str) -> str:
    L: list[str] = []
    L.append("# Phase 3.7C 研究 Excel 修改前后差异报告\n")
    L.append(f"- 修改前（原始备份）：`{before_path}`")
    L.append(f"- 修改后（现行文件）：`{after_path}`\n")

    L.append("## 一、结构比对\n")
    L.append(f"**结论：{d['structure']['status']}**\n")
    for x in d["structure"]["details"]:
        L.append(f"- {x}")

    L.append("\n## 二、公式比对\n")
    f = d["formulas"]
    L.append(f"公式总数：**{f['count_before']} → {f['count_after']}**（{'一致' if f['count_before']==f['count_after'] else '**不一致**'}）\n")
    for kind, label in (("added", "新增"), ("removed", "删除"), ("changed", "内容变更")):
        rows = f[kind]
        L.append(f"- 公式{label}：**{len(rows)} 条**")
        for r in rows[:20]:
            L.append(f"  - `{r['sheet']}!{r['cell']}`：{r.get('before','(空)')!r} → {r.get('after','(空)')!r}")

    L.append("\n## 三、数据（非公式单元格）比对\n")
    v = d["values"]
    for kind, label in (("added", "新增"), ("removed", "删除"), ("changed", "内容变更")):
        rows = v[kind]
        L.append(f"- 数据{label}：**{len(rows)} 处**")
        for r in rows[:40]:
            L.append(f"  - `{r['sheet']}!{r['cell']}`：{r.get('before','(空)')!r} → {r.get('after','(空)')!r}")

    L.append("\n## 四、公式计算值比对\n")
    c = d["computed"]
    if c["note"]:
        L.append(c["note"])
    L.append(f"计算值发生变化的单元格：**{len(c['changed'])} 处**")
    for r in c["changed"][:20]:
        L.append(f"  - `{r['sheet']}!{r['cell']}`：{r.get('before')!r} → {r.get('after')!r}")

    L.append("\n## 五、专项护栏\n")
    L.append("| 护栏项 | 结果 | 变更数 |")
    L.append("|---|---|---:|")
    for g in d["guards"]:
        L.append(f"| {g['item']} | {g['status']} | {g['count']} |")
    return "\n".join(L) + "\n"


def main() -> int:
    if len(sys.argv) < 3:
        print("用法: python3 scripts/diff_xlsx_snapshots.py <before.json> <after.json> [--md out.md]")
        return 1
    d = diff(load(sys.argv[1]), load(sys.argv[2]))
    md = to_markdown(d, sys.argv[1], sys.argv[2])
    if "--md" in sys.argv:
        out = sys.argv[sys.argv.index("--md") + 1]
        open(out, "w", encoding="utf-8").write(md)
        print(f"[OK] 差异报告 -> {out}")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
