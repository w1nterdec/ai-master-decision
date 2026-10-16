# 测试结果报告（Phase 4.0）

- 生成时间：2026-10-16 19:34:19
- 命令：`python -m pytest -q`
- 结果：**122/122 通过**，0 失败，0 跳过
- 环境：Python 3.11.1 / SQLite / SQLAlchemy / pytest

## 一、需求测试项覆盖（Task E 25 项）

| # | 测试项 | 结果 | 覆盖测试 |
|---|---|---|---|
| 1 | 评分 1–5 合法性 | ✅ 通过 | 10 项 |
| 2 | 非整数评分拒绝 | ✅ 通过 | 7 项 |
| 3 | 空来源拒绝 | ✅ 通过 | 3 项 |
| 4 | 不存在的 source_id 拒绝 | ✅ 通过 | 2 项 |
| 5 | 来源与路径不匹配拒绝 | ✅ 通过 | 2 项 |
| 6 | 来源与指标不匹配拒绝 | ✅ 通过 | 1 项 |
| 7 | 待核验证据不得进入正式评分 | ✅ 通过 | 11 项 |
| 8 | 来源冲突不得自动合并 | ✅ 通过 | 6 项 |
| 9 | 一级权重修改正确传播 | ✅ 通过 | 1 项 |
| 10 | 二级权重修改正确传播 | ✅ 通过 | 1 项 |
| 11 | 三级权重修改正确传播 | ✅ 通过 | 1 项 |
| 12 | 负权重拒绝 | ✅ 通过 | 3 项 |
| 13 | 零权重分组处理 | ✅ 通过 | 1 项 |
| 14 | 全局权重归一化 | ✅ 通过 | 2 项 |
| 15 | 情景权重归一化 | ✅ 通过 | 1 项 |
| 16 | 情景覆盖率独立判断 | ✅ 通过 | 2 项 |
| 17 | 低覆盖率不输出评分 | ✅ 通过 | 3 项 |
| 18 | 硬约束排除生效 | ✅ 通过 | 5 项 |
| 19 | 2028 资格未知不标记确认 | ✅ 通过 | 5 项 |
| 20 | 重复导入幂等 | ✅ 通过 | 2 项 |
| 21 | 不同年份记录不互相覆盖 | ✅ 通过 | 2 项 |
| 22 | 不同学院招生路径不混淆 | ✅ 通过 | 2 项 |
| 23 | 调剂与一志愿记录不混淆 | ✅ 通过 | 1 项 |
| 24 | 缺失数据不自动补零 | ✅ 通过 | 4 项 |
| 25 | 决策输出不包含虚构录取概率 | ✅ 通过 | 2 项 |

## 二、附加测试项

| 测试项 | 结果 | 覆盖测试 |
|---|---|---|
| 双目标独立输出（A/B 不复制同一综合分） | ✅ 通过 | 7 项 |
| 黄金对照：与 Phase 3.7C Excel 实测一致 | ✅ 通过 | 5 项 |
| 严格闸门严格于旧 Excel（U-01 修复） | ✅ 通过 | 2 项 |
| 权重修改记录与审计 | ✅ 通过 | 3 项 |
| 端到端：DB -> 引擎 -> 落库 | ✅ 通过 | 4 项 |

## 三、失败与跳过明细

无

## 四、测试清单（按文件）

### `tests/golden/test_golden_phase37c.py`（7 项）

- ✅ `test_golden_constant_matches_excel`
- ✅ `test_golden_db_weights_match_excel`
- ✅ `test_golden_divergence`
- ✅ `test_golden_excluded`
- ✅ `test_golden_full`
- ✅ `test_golden_invalid_scores`
- ✅ `test_strict_gate_is_stricter_than_excel`

### `tests/integration/test_decision_service.py`（4 项）

- ✅ `test_all_imported_paths_are_undecidable`
- ✅ `test_build_engine_from_db`
- ✅ `test_end_to_end_full_candidate`
- ✅ `test_end_to_end_pending_hard_constraint_blocks_output`

### `tests/integration/test_import_and_paths.py`（12 项）

- ✅ `test_20_reimport_is_idempotent`
- ✅ `test_20b_import_batch_recorded_once`
- ✅ `test_21_different_years_do_not_overwrite`
- ✅ `test_21b_admission_records_separate_methods_and_basis`
- ✅ `test_22_different_colleges_not_confused`
- ✅ `test_22b_same_school_multiple_colleges_present`
- ✅ `test_23_first_choice_and_adjustment_not_confused`
- ✅ `test_imported_claims_are_candidates`
- ✅ `test_imported_scores_all_unknown`
- ✅ `test_imported_sources_not_verified`
- ✅ `test_open_questions_and_audit_logged`
- ✅ `test_placeholder_source_registered`

### `tests/integration/test_weight_service.py`（5 项）

- ✅ `test_hard_constraint_evaluation_persisted`
- ✅ `test_level3_weight_update_propagates`
- ✅ `test_weight_update_persisted_and_audited`
- ✅ `test_weight_update_rejects_negative`
- ✅ `test_weight_update_unknown_indicator`

### `tests/unit/test_constraints.py`（9 项）

- ✅ `test_18_exclusion_effective`
- ✅ `test_18b_any_no_excludes`
- ✅ `test_18c_unknown_yields_pending`
- ✅ `test_18d_all_yes_is_historical_candidate`
- ✅ `test_19_2028_unknown_never_confirmed`
- ✅ `test_19b_confirmed_requires_verification_and_evidence`
- ✅ `test_19c_verified_flag_without_evidence_not_confirmed`
- ✅ `test_19d_excluded_path_not_met`
- ✅ `test_imported_paths_all_pending_2028`

### `tests/unit/test_coverage.py`（9 项）

- ✅ `test_16_scenario_coverage_judged_independently`
- ✅ `test_16b_base_pass_does_not_license_other_scenarios`
- ✅ `test_17_low_coverage_outputs_insufficient`
- ✅ `test_17b_zero_valid_cells_no_score`
- ✅ `test_17c_threshold_configurable`
- ✅ `test_24_missing_scores_are_not_zero`
- ✅ `test_24b_invalid_scores_excluded_from_coverage`
- ✅ `test_24c_na_marker_is_unknown_not_zero`
- ✅ `test_indicator_count_coverage_reported`

### `tests/unit/test_evidence_gate.py`（42 项）

- ✅ `test_01_valid_scores_1_to_5[1]`
- ✅ `test_01_valid_scores_1_to_5[2]`
- ✅ `test_01_valid_scores_1_to_5[3]`
- ✅ `test_01_valid_scores_1_to_5[4]`
- ✅ `test_01_valid_scores_1_to_5[5]`
- ✅ `test_01b_out_of_range_rejected[-1]`
- ✅ `test_01b_out_of_range_rejected[0]`
- ✅ `test_01b_out_of_range_rejected[6]`
- ✅ `test_01b_out_of_range_rejected[99]`
- ✅ `test_01c_blank_is_unknown_not_zero`
- ✅ `test_02_non_integer_rejected[0.5]`
- ✅ `test_02_non_integer_rejected[4.5]`
- ✅ `test_02_non_integer_rejected[4]`
- ✅ `test_02_non_integer_rejected[True]`
- ✅ `test_02_non_integer_rejected[abc]`
- ✅ `test_02_non_integer_rejected[score5]`
- ✅ `test_02b_float_integer_accepted`
- ✅ `test_03_empty_source_rejected[   ]`
- ✅ `test_03_empty_source_rejected[None]`
- ✅ `test_03_empty_source_rejected[]`
- ✅ `test_04_unknown_source_id_rejected`
- ✅ `test_04b_source_id_non_empty_is_not_sufficient`
- ✅ `test_05_source_not_applicable_to_path`
- ✅ `test_05b_claim_marked_not_applicable`
- ✅ `test_06_source_does_not_support_indicator`
- ✅ `test_07_unverified_source_rejected[\u5df2\u5931\u6548]`
- ✅ `test_07_unverified_source_rejected[\u5f85\u6838\u9a8c]`
- ✅ `test_07_unverified_source_rejected[\u65e0\u6cd5\u6838\u9a8c]`
- ✅ `test_07_unverified_source_rejected[\u672a\u767b\u8bb0]`
- ✅ `test_07_unverified_source_rejected[\u6765\u6e90\u51b2\u7a81]`
- ✅ `test_07b_unverified_claim_rejected[\u5019\u9009\u6620\u5c04]`
- ✅ `test_07b_unverified_claim_rejected[\u5f85\u6838\u9a8c]`
- ✅ `test_07b_unverified_claim_rejected[\u6765\u6e90\u51b2\u7a81]`
- ✅ `test_07c_candidate_mapping_not_auto_promoted`
- ✅ `test_07d_year_mismatch_rejected`
- ✅ `test_07e_year_unspecified_rejected`
- ✅ `test_08_conflict_blocks_scoring`
- ✅ `test_08b_conflict_record_keeps_old_fact`
- ✅ `test_08c_verify_claim_requires_actor_and_basis`
- ✅ `test_08d_manual_verification_is_only_legal_promotion`
- ✅ `test_08e_register_claim_requires_registered_source`
- ✅ `test_08f_placeholder_source_recorded_as_unregistered`

### `tests/unit/test_objectives.py`（13 项）

- ✅ `test_dual_objective_outputs_are_not_the_same_score`
- ✅ `test_excluded_path_not_evaluated`
- ✅ `test_group_coverage_helper`
- ✅ `test_insufficient_evidence_outputs_pending`
- ✅ `test_negative_relevance_rejected`
- ✅ `test_objective_a_does_not_require_2028`
- ✅ `test_objective_a_excludes_admission_feasibility_from_denominator`
- ✅ `test_objective_a_requires_research_group_evidence`
- ✅ `test_objective_b_requires_admission_group_evidence`
- ✅ `test_objective_b_requires_confirmed_2028`
- ✅ `test_objective_defs_are_demo_configs`
- ✅ `test_objective_weights_are_different`
- ✅ `test_pending_hard_constraint_blocks_objectives`

### `tests/unit/test_pipeline.py`（11 项）

- ✅ `test_25_output_contains_no_admission_probability`
- ✅ `test_25b_prohibited_field_detected`
- ✅ `test_engine_has_no_gate_marks_unknown`
- ✅ `test_excluded_path_no_scores`
- ✅ `test_full_valid_scoring`
- ✅ `test_full_valid_with_2028_confirmed`
- ✅ `test_legacy_gate_reproduces_excel_semantics`
- ✅ `test_limitations_always_present`
- ✅ `test_pending_hard_constraint_no_scores`
- ✅ `test_strict_gate_rejects_unregistered_source`
- ✅ `test_threshold_configurable`

### `tests/unit/test_weights.py`（10 项）

- ✅ `test_09_level1_weight_change_propagates`
- ✅ `test_10_level2_weight_change_propagates`
- ✅ `test_11_level3_weight_change_propagates`
- ✅ `test_12_negative_weight_rejected`
- ✅ `test_13_zero_weight_group_handled`
- ✅ `test_14_global_weight_normalized`
- ✅ `test_15_scenario_weights_independently_normalized`
- ✅ `test_scenario_degenerate_all_zero_multiplier`
- ✅ `test_scenario_negative_multiplier_rejected`
- ✅ `test_weight_profile_is_demo_config`

## 五、结论

Task E 的 25 项需求测试**全部有对应测试用例且全部通过**，附加测试项同样通过。

> 说明：黄金测试使用 `LegacyPhase37CGate` 复现 Phase 3.7C 的"格式有效"语义，
> 用于在**共同支持的计算规则**上与 Excel 基线对齐；生产路径使用严格闸门，结果更严格。

