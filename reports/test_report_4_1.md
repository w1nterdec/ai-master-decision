# Phase 4.1 测试执行结果

生成时间：2026-10-16　|　工程版本：0.4.1　|　JUnit：`reports/pytest-junit-4_1.xml`

---

## 一、实际执行命令与结果

```bash
cd /workspace/ai-master-decision
pip install -e ".[dev]"
python3 -m pytest --junitxml=reports/pytest-junit-4_1.xml
```

```
........................................................................ [ 96%]
.....                                                                    [100%]
149 passed in 36.25s
```

| 指标 | 数量 |
|---|---|
| 通过（passed） | **149** |
| 失败（failed） | **0** |
| 错误（errors） | **0** |
| 跳过（skipped） | **0** |

JUnit 解析复核：`total=149, failures=0, errors=0, skipped=0`。

**原有 Phase 4.0 测试 122 项全部保持通过**（未回归失败），Phase 4.1 新增 **27 项**。

### 用例分布（按文件）

| 文件 | 用例数 | 归属 |
|---|---|---|
| `tests/unit/test_evidence_gate.py` | 42 | 4.0 |
| `tests/unit/test_objectives.py` | 13 | 4.0 |
| `tests/unit/test_pipeline.py` | 11 | 4.0 |
| `tests/unit/test_weights.py` | 10 | 4.0 |
| `tests/unit/test_constraints.py` | 9 | 4.0 |
| `tests/unit/test_coverage.py` | 9 | 4.0 |
| `tests/integration/test_import_and_paths.py` | 12 | 4.0 |
| `tests/integration/test_weight_service.py` | 5 | 4.0 |
| `tests/integration/test_decision_service.py` | 4 | 4.0 |
| `tests/golden/test_golden_phase37c.py` | 7 | 4.0 |
| **`tests/ui/test_streamlit_app.py`** | **11** | **4.1 新增** |
| **`tests/integration/test_evidence_service.py`** | **11** | **4.1 新增** |
| **`tests/integration/test_profile_service.py`** | **5** | **4.1 新增** |
| 合计 | **149** | |

---

## 二、Task G 15 项需求 → 测试映射

| # | 需求 | 测试 | 类型 | 结果 |
|---|---|---|---|---|
| 1 | 页面正常加载 | `test_01_all_pages_load_without_exception`（5 页逐一渲染并断言无异常、有输出） | **AppTest 真实渲染** | ✅ |
| 2 | 数据库为空时页面不崩溃 | `test_02_empty_database_does_not_crash`（空库 5 页无异常 + 提示「数据库中暂无招生路径」） | **AppTest 真实渲染** | ✅ |
| 3 | 路径筛选正确 | `test_03_path_filter_works`（界面 selectbox 筛选后表格行数 10 → N 且学校一致） | **AppTest 交互** | ✅ |
| 4 | 来源登记成功 | `test_04_register_source_via_ui`（界面表单登记并回查 DB）+ `test_register_source_success` | **AppTest 交互 + 服务** | ✅ |
| 5 | 重复 source_id 拒绝 | `test_05_duplicate_source_id_rejected_in_ui`（界面提示「拒绝重复登记」）+ `test_duplicate_source_id_rejected`（DB 仅 1 行且未被覆盖） | **AppTest 交互 + 服务** | ✅ |
| 6 | 来源占位符不能直接成为已核验来源 | `test_placeholder_source_cannot_be_verified`（SRC-NA 核验被拒）+ `test_quoted_reference_source_is_not_registered`（引用式记录不算已登记）+ `test_src_na_placeholder_id_rejected` | 服务 | ✅ |
| 7 | 证据核验必须记录依据 | `test_verification_requires_actor_and_basis`（空依据/空操作者被拒；通过后审计含 actor、basis、时间）+ `test_submit_and_reject_flow` | 服务 | ✅ |
| 8 | 无效来源无法参与评分 | `test_invalid_source_cannot_participate_in_scoring`（未核验→valid_count=0；核验后→≥1，走真实 StrictEvidenceGate） | 引擎端到端 | ✅ |
| 9 | 权重调整正确调用服务层 | `test_09_weight_adjust_goes_through_service_layer`（spy `weight_service.update_weight`，断言参数与权重合计=1.0） | 服务 | ✅ |
| 10 | 权重修改能够持久化 | `test_10_weight_change_is_persisted`（新 Session 读取 + 审计含前后值 + 重算合计 1.0） | 服务 | ✅ |
| 11 | 恢复默认配置不会破坏历史记录 | `test_11_restore_default_keeps_history`（恢复后数值回到演示值，审计条数不减且 `weight.update` 仍在，演示配置未被改） | 服务 | ✅ |
| 12 | 证据不足时不生成排名 | `test_12_no_ranking_when_evidence_insufficient`（页面出现「当前尚不能形成可靠比较」且图表元素数为 0） | **AppTest 真实渲染** | ✅ |
| 13 | 2028 资格未知时不显示已确认 | `test_13_2028_unknown_is_not_shown_as_confirmed`（路径页/分析页均无「2028正式资格已确认」，且含「待2028核验」） | **AppTest 真实渲染** | ✅ |
| 14 | 双目标状态独立展示 | `test_14_dual_objectives_displayed_independently`（A/B 两块标题与状态均渲染，分数区显示「暂无评分」而非 0） | **AppTest 真实渲染** | ✅ |
| 15 | 页面不会直接绕过严格证据闸门 | `test_15_ui_does_not_bypass_strict_gate`（spy `build_engine`，断言 UI 实际调用且闸门类型为 `StrictEvidenceGate`）+ `test_15b_ui_source_has_no_scoring_logic`（UI 源码无自行计算实现） | **AppTest 运行时 + 结构检查** | ✅ |

**关于"不得用纯函数测试冒充 UI 测试"**：第 1、2、3、4、5、12、13、14、15 项均为
`streamlit.testing.v1.AppTest` 加载 `app.py` 并真实执行渲染/交互后的断言，不是对纯函数的间接推断。
`filter_path_rows` 等纯函数仅在页面内部被间接覆盖，不作为 UI 合格的证据。

---

## 三、测试隔离与数据库保护

- UI 测试通过 `monkeypatch.setenv("DECISION_DB_PATH", <tmp_path 下的库>)` 指向临时库；
  集成测试使用 `mutating_db` 夹具（tmp_path 内独立 SQLite）。
- 全量测试执行前后核对正式库 `data/decision.db`：24 张表、school=5、admission_path=10、
  evidence_source=84、evidence_claim=48、score_record=180、audit_log=44 —— **记录数一致，未被污染**。

---

## 四、未覆盖（如实列出）

1. 真实浏览器端交互（仅覆盖 AppTest 的脚本级渲染，未做 Selenium/Playwright 端到端）。
2. 并发写入、性能/压力测试。
3. 移动端适配、浏览器兼容性。
4. 人工核验的**业务**正确性（代码只保证"必须留依据"，无法判断依据是否合理）。
