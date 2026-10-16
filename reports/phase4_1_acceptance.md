# Phase 4.1 验收报告

生成时间：2026-10-16　|　工程：`ai-master-decision` v0.4.1　|　前置：Phase 4.0（有条件通过）

---

## 〇、Task A：Phase 4.0 实际检查（不依赖交接报告结论，逐项实跑）

| 检查项 | 命令 / 方式 | 实测结果 |
|---|---|---|
| 项目可安装 | `pip install -e ".[dev]"` | ✅ 成功，包版本 0.4.1，`decision_system.ui` 可导入 |
| SQLite 可读取 | `create_sqlite_engine` + `inspect` | ✅ 24 张表；school=5、college=9、program=9、admission_path=10、indicator=33（5/10/18）、weight_node=33、evidence_source=84、evidence_claim=48、claim_path_link=57、claim_indicator_link=180、score_record=180（raw_score 全 NULL）、admission_record=0、mentor=0、research_resource=0、claim_conflict=0、audit_log=44 |
| 决策引擎可调用 | `build_engine(...).evaluate(...)` | ✅ 10/10 路径输出「硬约束待确认-不可比较」，覆盖率 0.000，score=None |
| 现有 pytest 可运行 | `python3 -m pytest` | ✅ **122 passed**（Phase 4.0 基线，0 failed / 0 skipped） |
| 证据治理接口可复用 | `registry.register_source / verify_claim / detect_and_record_conflict / link_*` | ✅ 均可直接复用；仅缺「驳回」动作，已**最小新增** `reject_claim` / `submit_for_verification`（在 `services/evidence_service.py`，未改 registry） |
| 权重服务支持修改与保存 | `weight_service.update_weight` | ✅ 落库 + 审计（`weight.update`，含前后值与全局权重变化） |

**P0 缺陷检查结论：未发现 P0。** 无 NaN、无除零、无负权重、无补零、无伪造评分、无自动升级。
发现一处口径问题（非阻断，登记为 P2-1）：`is_placeholder=False` 的 83 条"引用式"来源实际**无本体登记**，
导致"84 条全部未登记"与"83 条缺本体"两种说法并存 —— 本阶段以 `is_registered_source()` 收敛口径并在页面公示，未改数据。

交接报告数字复核：24 表 ✅、5 校 ✅、10 路径 ✅、33 指标/18 三级 ✅、84 来源 ✅、48 声明 ✅、180 空评分格 ✅、122 测试 ✅ —— **全部与实测一致**。

---

## 一、十二项验收标准逐条核对

| # | 验收标准 | 结论 | 实测证据 |
|---|---|---|---|
| 1 | Streamlit 可以实际启动 | ✅ | `streamlit run app.py --server.headless=true --server.port=8599` → `Uvicorn server started`，HTTP `200`、`/healthz` 正常 |
| 2 | 五个页面可以正常访问 | ✅ | AppTest 逐一渲染 ①–⑤ 页，0 异常且有输出；空库下同样 0 异常 |
| 3 | 数据来自真实 SQLite 数据库 | ✅ | 总览页 metric 学校=5 / 路径=10 / 可比较=0，与 DB 实查一致；`DECISION_DB_PATH` 指向真实库文件 |
| 4 | 来源登记和核验功能可操作 | ✅ | 界面表单登记成功并回查 DB（`UI-TEST-001` 落库，状态"待核验"）；核验需填操作者+依据，否则服务层拒绝 |
| 5 | 证据治理规则未被绕过 | ✅ | spy `build_engine` 证明 UI 走服务层且闸门为 `StrictEvidenceGate`；未核验来源评分 `valid_count=0`，核验后 `≥1` |
| 6 | 三级权重可以交互修改 | ✅ | 33 个节点输入框（5+10+18），组内归一与全局权重实时预览，保存经 `weight_service` |
| 7 | 权重变更可以持久化 | ✅ | 新 Session 读到新值，审计含 old/new/全局权重前后 |
| 8 | 情景分析正确调用独立决策引擎 | ✅ | 三情景覆盖率/状态/分数均由 `DecisionEngine.evaluate` 输出，页面无自算逻辑 |
| 9 | 证据不足时不产生虚假评分 | ✅ | 分析页显示"当前尚不能形成可靠比较"，图表元素数 0，分数区显示"暂无评分" |
| 10 | 2028 资格未知时不产生虚假确认 | ✅ | 页面无"2028正式资格已确认"字样，全部显示"待2028核验"/"2028资格未确认" |
| 11 | 原有测试未回归失败 | ✅ | 122 项 Phase 4.0 用例全部通过（全量 149 中前 122 项） |
| 12 | 新增测试实际通过 | ✅ | 新增 27 项全部通过（`reports/pytest-junit-4_1.xml`：149 total / 0 failures / 0 errors / 0 skipped） |

---

## 二、里程碑记录

### M1｜项目检查 + 招生路径工作台
- 完成：Task A 六项实跑；`app.py` + 侧边栏导航；`ui/db_access.py`（`DECISION_DB_PATH` 支持）；
  `ui/decision_view.py`（统一调用引擎）；`pages_paths.py`（8 类字段 + 硬约束 + 2028 状态 + 数据完整度 + 三维筛选 + 详情/证据/缺失/历史）。
- 关键实现：缺失招生人数显示"暂无数据"（`quota_text()`），历史候选与 2028 正式资格显式区分。
- 遗留：无评分录入（P1-7）。

### M2｜证据管理工作台
- 完成：`services/evidence_service.py`（登记/关联/提交/通过/驳回/冲突/历史/缺口统计）；
  `pages_evidence.py` 四个标签页；口径在页面公示。
- 关键实现：重复 source_id 拒绝；占位符禁止核验；核验必须 actor+basis；冲突登记不覆盖旧事实。
- 遗留：`is_placeholder` 字段语义与本体登记口径不一致（P2-1，用判定函数收敛）。

### M3｜动态权重 + 决策分析
- 完成：`services/profile_service.py`（派生/确认/恢复默认）；`pages_model.py`（权重树 + 预览 + 保存 + 记录）；
  `pages_analysis.py`（三情景 + A/B 双目标 + 缺失指标 + 证据不足不排名）。
- 关键实现：演示配置不被覆盖；恢复默认只改数值不删历史。
- 遗留：演示倍率/相关度矩阵未获用户确认（P1-6）。

### M4｜总览 + 测试 + 交付
- 完成：`pages_overview.py`（8 指标 + 真实待办）；27 项新增测试；README 启动说明；
  `docs/db_compatibility_4_1.md`；`docs/known_limitations_4_1.md`；本报告。
- 实测：149 passed / 0 failed；正式库测试前后记录数一致（未污染）。

---

## 三、目录与文件变化

```
新增：
  app.py                                        # Streamlit 入口
  src/decision_system/ui/__init__.py
  src/decision_system/ui/db_access.py
  src/decision_system/ui/formatting.py
  src/decision_system/ui/decision_view.py
  src/decision_system/ui/pages_overview.py
  src/decision_system/ui/pages_paths.py
  src/decision_system/ui/pages_evidence.py
  src/decision_system/ui/pages_model.py
  src/decision_system/ui/pages_analysis.py
  src/decision_system/services/evidence_service.py
  src/decision_system/services/profile_service.py
  tests/ui/__init__.py  tests/ui/conftest.py  tests/ui/test_streamlit_app.py
  tests/integration/test_evidence_service.py
  tests/integration/test_profile_service.py
  docs/db_compatibility_4_1.md  docs/known_limitations_4_1.md
  reports/test_report_4_1.md  reports/pytest-junit-4_1.xml  reports/phase4_1_acceptance.md

修改（最小必要）：
  pyproject.toml          # 版本 0.4.1；新增 streamlit / pandas 依赖；packages 增加 decision_system.ui
  README.md               # 补充 Phase 4.1 启动方式、页面、依赖说明、测试分层

未改动（保持兼容）：
  src/decision_system/models/*   # 24 张表结构与枚举零改动
  src/decision_system/engine/*   # 决策算法零改动
  src/decision_system/evidence/* # 治理闸门与 registry 零改动（新增动作放在 services 层）
  src/decision_system/importers/*# 导入器零改动
```

---

## 四、当前数据库状态（实测）

| 项 | 值 |
|---|---|
| 表数量 | 24（未变） |
| 学校 / 学院 / 专业 / 路径 | 5 / 9 / 9 / 10 |
| 指标 | 33（L1=5、L2=10、L3=18） |
| 证据来源 | 84（**已登记本体 0**，占位符/引用式 84，已核验 0） |
| 事实声明 | 48（候选映射 48，已核验 0） |
| 评分格 | 180（**有效评分 0**，全为 NULL） |
| 2028 资格 | 10/10 条均为「待2028核验」 |
| 可比较路径 | **0** |
| 冲突 | 0（未解决 0） |
| `admission_record` / `mentor` / `research_resource` | 0 / 0 / 0 |
| `decision_result` / `hard_constraint_evaluation` | 0 / 0（MVP 只读评估，不落库） |

---

## 五、结论

**12/12 项验收标准全部满足，且原有 122 项测试无回归、新增 27 项测试实际通过。**

但按工程口径仍需如实区分：

- **工程/Web MVP 层面：通过。** 五个页面可启动、可操作、数据真实、治理规则未被绕过、测试真实通过。
- **决策可用性层面：仍不具备。** 2028 资格 0 条确认、来源本体 0 条登记、候选声明 0 条已核验、评分 0 条，
  因此系统当前唯一正确输出是「不可比较」，MVP 也确实如此显示。

综合判定：**有条件通过**（与 Phase 4.0 同口径）——Web MVP 可交付并进入下一阶段，
但在证据补齐前不得用于任何真实择校决策。

下一阶段建议：① 评分录入界面 + 覆盖率实时反馈；② 2028 资格确认工作流；③ 来源批量登记与模板导入；
④ 评估报告导出（PDF/Markdown）；⑤ 性能与并发加固。
