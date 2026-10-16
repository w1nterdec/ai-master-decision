#!/usr/bin/env python3
"""运行 pytest 并生成 Markdown 测试结果报告。

    python scripts/run_tests.py --out reports/test_report.md
"""

from __future__ import annotations

import argparse
import datetime as _dt
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 需求条目 -> 覆盖该条目的测试名（子串匹配）
REQUIREMENTS: list[tuple[str, str, list[str]]] = [
    ("1", "评分 1–5 合法性", ["test_01_valid_scores_1_to_5", "test_01b_out_of_range_rejected", "test_01c_blank_is_unknown_not_zero"]),
    ("2", "非整数评分拒绝", ["test_02_non_integer_rejected", "test_02b_float_integer_accepted"]),
    ("3", "空来源拒绝", ["test_03_empty_source_rejected"]),
    ("4", "不存在的 source_id 拒绝", ["test_04_unknown_source_id_rejected", "test_04b_source_id_non_empty_is_not_sufficient"]),
    ("5", "来源与路径不匹配拒绝", ["test_05_source_not_applicable_to_path", "test_05b_claim_marked_not_applicable"]),
    ("6", "来源与指标不匹配拒绝", ["test_06_source_does_not_support_indicator"]),
    ("7", "待核验证据不得进入正式评分", ["test_07_unverified_source_rejected", "test_07b_unverified_claim_rejected", "test_07c_candidate_mapping_not_auto_promoted", "test_07d_year_mismatch_rejected", "test_07e_year_unspecified_rejected"]),
    ("8", "来源冲突不得自动合并", ["test_08_conflict_blocks_scoring", "test_08b_conflict_record_keeps_old_fact", "test_08c_", "test_08d_", "test_08e_", "test_08f_"]),
    ("9", "一级权重修改正确传播", ["test_09_level1_weight_change_propagates"]),
    ("10", "二级权重修改正确传播", ["test_10_level2_weight_change_propagates"]),
    ("11", "三级权重修改正确传播", ["test_11_level3_weight_change_propagates"]),
    ("12", "负权重拒绝", ["test_12_negative_weight_rejected", "test_weight_update_rejects_negative", "test_scenario_negative_multiplier_rejected"]),
    ("13", "零权重分组处理", ["test_13_zero_weight_group_handled"]),
    ("14", "全局权重归一化", ["test_14_global_weight_normalized", "test_golden_db_weights_match_excel"]),
    ("15", "情景权重归一化", ["test_15_scenario_weights_independently_normalized"]),
    ("16", "情景覆盖率独立判断", ["test_16_scenario_coverage_judged_independently", "test_16b_base_pass_does_not_license_other_scenarios"]),
    ("17", "低覆盖率不输出评分", ["test_17_low_coverage_outputs_insufficient", "test_17b_zero_valid_cells_no_score", "test_17c_threshold_configurable"]),
    ("18", "硬约束排除生效", ["test_18_exclusion_effective", "test_18b_any_no_excludes", "test_18c_unknown_yields_pending", "test_18d_all_yes_is_historical_candidate", "test_excluded_path_no_scores"]),
    ("19", "2028 资格未知不标记确认", ["test_19_2028_unknown_never_confirmed", "test_19b_", "test_19c_", "test_19d_", "test_imported_paths_all_pending_2028"]),
    ("20", "重复导入幂等", ["test_20_reimport_is_idempotent", "test_20b_import_batch_recorded_once"]),
    ("21", "不同年份记录不互相覆盖", ["test_21_different_years_do_not_overwrite", "test_21b_admission_records_separate_methods_and_basis"]),
    ("22", "不同学院招生路径不混淆", ["test_22_different_colleges_not_confused", "test_22b_same_school_multiple_colleges_present"]),
    ("23", "调剂与一志愿记录不混淆", ["test_23_first_choice_and_adjustment_not_confused"]),
    ("24", "缺失数据不自动补零", ["test_24_missing_scores_are_not_zero", "test_24b_invalid_scores_excluded_from_coverage", "test_24c_na_marker_is_unknown_not_zero", "test_imported_scores_all_unknown"]),
    ("25", "决策输出不包含虚构录取概率", ["test_25_output_contains_no_admission_probability", "test_25b_prohibited_field_detected"]),
]

EXTRA: list[tuple[str, list[str]]] = [
    ("双目标独立输出（A/B 不复制同一综合分）", ["test_objective_weights_are_different", "test_dual_objective_outputs_are_not_the_same_score", "test_objective_b_requires_confirmed_2028", "test_objective_a_does_not_require_2028", "test_objective_b_requires_admission_group_evidence", "test_objective_a_requires_research_group_evidence", "test_insufficient_evidence_outputs_pending"]),
    ("黄金对照：与 Phase 3.7C Excel 实测一致", ["test_golden_constant_matches_excel", "test_golden_full", "test_golden_divergence", "test_golden_excluded", "test_golden_invalid_scores"]),
    ("严格闸门严格于旧 Excel（U-01 修复）", ["test_strict_gate_is_stricter_than_excel", "test_strict_gate_rejects_unregistered_source"]),
    ("权重修改记录与审计", ["test_weight_update_persisted_and_audited", "test_level3_weight_update_propagates", "test_hard_constraint_evaluation_persisted"]),
    ("端到端：DB -> 引擎 -> 落库", ["test_end_to_end_pending_hard_constraint_blocks_output", "test_end_to_end_full_candidate", "test_all_imported_paths_are_undecidable", "test_build_engine_from_db"]),
]


def run_pytest(junit_path: Path) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-q", f"--junitxml={junit_path}"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr)


def load_results(junit_path: Path) -> list[tuple[str, str, str]]:
    """返回 [(classname, testname, status)]"""
    tree = ET.parse(junit_path)
    out = []
    for tc in tree.iter("testcase"):
        status = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                status = "failed"
            elif child.tag == "skipped":
                status = "skipped"
        out.append((tc.get("classname", ""), tc.get("name", ""), status))
    return out


def evaluate(results, patterns) -> tuple[bool, list[str]]:
    matched = []
    for _, name, status in results:
        if any(p in name for p in patterns):
            matched.append((name, status))
    ok = bool(matched) and all(s == "passed" for _, s in matched)
    return ok, [f"{n}" for n, _ in matched]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "reports" / "test_report.md"))
    args = parser.parse_args(argv)

    junit = ROOT / "reports" / "pytest-junit.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    code, raw = run_pytest(junit)
    try:
        results = load_results(junit)
    except FileNotFoundError:
        print(raw)
        return 1

    total = len(results)
    passed = sum(1 for r in results if r[2] == "passed")
    failed = [r for r in results if r[2] == "failed"]
    skipped = [r for r in results if r[2] == "skipped"]

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 测试结果报告（Phase 4.0）",
        "",
        f"- 生成时间：{now}",
        f"- 命令：`python -m pytest -q`",
        f"- 结果：**{passed}/{total} 通过**" + (f"，{len(failed)} 失败，{len(skipped)} 跳过" if failed or skipped else "，0 失败，0 跳过"),
        f"- 环境：Python {sys.version.split()[0]} / SQLite / SQLAlchemy / pytest",
        "",
        "## 一、需求测试项覆盖（Task E 25 项）",
        "",
        "| # | 测试项 | 结果 | 覆盖测试 |",
        "|---|---|---|---|",
    ]

    all_ok = True
    for num, desc, patterns in REQUIREMENTS:
        ok, names = evaluate(results, patterns)
        all_ok = all_ok and ok
        lines.append(
            f"| {num} | {desc} | {'✅ 通过' if ok else '❌ 未通过'} | {len(names)} 项 |"
        )

    lines += ["", "## 二、附加测试项", "", "| 测试项 | 结果 | 覆盖测试 |", "|---|---|---|"]
    for desc, patterns in EXTRA:
        ok, names = evaluate(results, patterns)
        all_ok = all_ok and ok
        lines.append(f"| {desc} | {'✅ 通过' if ok else '❌ 未通过'} | {len(names)} 项 |")

    lines += [
        "",
        "## 三、失败与跳过明细",
        "",
        "无" if not (failed or skipped) else "",
    ]
    for c, n, s in failed + skipped:
        lines.append(f"- `{c}::{n}` — {s}")

    lines += [
        "",
        "## 四、测试清单（按文件）",
        "",
    ]
    by_file: dict[str, list[tuple[str, str]]] = {}
    for c, n, s in results:
        by_file.setdefault(c.replace(".", "/") + ".py", []).append((n, s))
    for f in sorted(by_file):
        lines.append(f"### `{f}`（{len(by_file[f])} 项）")
        lines.append("")
        for n, s in sorted(by_file[f]):
            lines.append(f"- {'✅' if s == 'passed' else '❌'} `{n}`")
        lines.append("")

    lines += [
        "## 五、结论",
        "",
        (
            "Task E 的 25 项需求测试**全部有对应测试用例且全部通过**，附加测试项同样通过。"
            if all_ok
            else "存在未通过项，Phase 4.0 不得宣称完成。"
        ),
        "",
        "> 说明：黄金测试使用 `LegacyPhase37CGate` 复现 Phase 3.7C 的\"格式有效\"语义，",
        "> 用于在**共同支持的计算规则**上与 Excel 基线对齐；生产路径使用严格闸门，结果更严格。",
        "",
    ]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] 测试报告 -> {out}")
    print(f"     {passed}/{total} passed")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
