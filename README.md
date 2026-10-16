# 2028 AI 硕士动态择校系统 — Phase 4.0 / 4.1 / 5.0

数据架构、证据治理、独立决策引擎（Phase 4.0）+ Streamlit Web MVP（Phase 4.1）+ 北邮试点数据迁移（Phase 5.0）。

---

## ⚠️ 重要声明：本系统不是录取概率预测工具

> **当前系统是研究与决策辅助工具，不是录取概率预测工具，也不是院校排名产品。**

- 系统**从不输出、也拒绝输出**任何录取概率 / 上岸率 / 录取率（由 `engine/pipeline.py`
  的 `assert_no_admission_probability` 与 9 项单测强制）。
- 当前 10 条路径**全部处于「硬约束待确认-不可比较」**，基础覆盖率 0.000 —— 这是**正确行为**，
  不是缺陷：2028 招生资格未确认、87 个来源中 84 个无本体登记、56 条声明中仅 6 条已核验、
  180 条评分记录有效性全部为「未知」。
- 权重为**演示配置**（`is_demo=True`），**尚未确认为用户真实偏好**。
- **后续开发方向尚未确定**：使用者反馈「更像数据管理后台，而不是择校助手」，
  功能开发已暂停，代码正移交独立审查（见 `docs/CHAIN_CODE_REVIEW_HANDOFF.md`）。

---

## 快速开始（干净环境）

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 1) 导入 Phase 3.7C Excel（可重复执行，幂等）
python scripts/import_excel.py --replay-check

# 2) 运行独立决策引擎（命令行）
python scripts/run_decision.py

# 3) 启动 Streamlit Web MVP（Phase 4.1）
streamlit run app.py
#   默认 http://localhost:8501

# 4) 跑测试（含 UI 真实渲染测试）
pytest

# 5) 生成数据库结构说明
python scripts/describe_schema.py --out reports/db_schema.md
```

产出：

| 文件 | 内容 |
|---|---|
| `data/decision.db` | SQLite 数据库 |
| `reports/import_report.json` | 导入报告（含幂等校验） |
| `reports/decision_report.json` | 10 条路径的决策输出 |
| `reports/db_schema.md` | 数据库结构说明 |

---

## 交付物对照

| Phase 4.0 要求 | 位置 |
|---|---|
| 完整 Python 项目源码 | `src/decision_system/` |
| SQLite 数据库及结构说明 | `data/decision.db` + `docs/data_dictionary.md` + `reports/db_schema.md` |
| 数据导入脚本 | `scripts/import_excel.py` + `src/decision_system/importers/` |
| 独立决策引擎 | `src/decision_system/engine/`（零 UI / 零 ORM 依赖） |
| pytest 自动化测试 | `tests/`（unit / integration / golden） |
| 测试结果报告 | `reports/test_report.md` |
| 架构说明文档 | `docs/architecture.md` |
| 决策规则规范 | `docs/decision_rules.md` |
| 数据字典 | `docs/data_dictionary.md` |
| 已知限制与下一阶段建议 | `docs/known_limitations.md` |

---

## 设计原则

> 正确性 > 可追溯性 > 可测试性 > 可维护性 > 界面美观

硬性约束（由代码与测试强制）：

- 决策引擎不输出任何录取概率（`assert_no_admission_probability` 自检）。
- 缺失数据不补零；空白评分保持「未知」，不计入分子分母。
- 候选证据映射永不自动升级为已核验证据。
- 来源冲突保留记录，不自动覆盖旧事实。
- 历史候选 ≠ 2028 正式资格。
- 每个情景/目标用**自身**覆盖率判断是否输出评分。
- 双目标（A 是否值得读 / B 是否值得押唯一一次机会）独立输出。

---

## 模块速览

| 模块 | 职责 |
|---|---|
| `engine/weights.py` | 三级权重树：组内归一、全局归一、负权重拒绝、零权重分组防除零 |
| `engine/constraints.py` | 硬约束三态 + 2028 资格判定 |
| `engine/coverage.py` | 覆盖率与加权平均（缺失不入分母） |
| `engine/scenarios.py` | 情景倍率与独立归一化 |
| `engine/objectives.py` | 双目标相关度矩阵 + 必备分组门槛 |
| `engine/pipeline.py` | 门面：PathContext → PathDecision |
| `evidence/gate.py` | 严格闸门 / Excel 兼容闸门（仅测试） |
| `evidence/registry.py` | 来源与声明登记、冲突治理、人工核验唯一入口 |
| `importers/excel_importer.py` | Excel → SQLite，幂等，不做推断 |
| `services/` | DB 会话、路径身份、装配层、权重修改审计 |

---

## 测试分层

| 目录 | 内容 |
|---|---|
| `tests/unit/` | 权重、证据闸门、覆盖率、硬约束、双目标、引擎（纯内存，无 DB 依赖） |
| `tests/integration/` | 导入幂等、不同年份/学院/路径角色不混淆、DB 驱动端到端、权重修改审计 |
| `tests/golden/` | 与 Phase 3.7C Excel/LibreOffice 实测结果逐格比对（4 个场景） |

黄金基线：`data/raw/Phase3_7C_实际回归测试结果.json`（Phase 3.7C 端到端回归实测值）。

关于严格性差异：Python 引擎默认严格闸门**比旧 Excel 更严格**；黄金测试使用
`LegacyPhase37CGate` 复现 Excel 的"格式有效"语义做数值对齐，详见 `docs/decision_rules.md` R3
与 `docs/known_limitations.md` 第四节。

---

## 当前状态速览（由 `scripts/run_decision.py` 实测）

```
P01..P10  准入=待核验  2028=2028资格未确认  基础覆盖=0.000  状态=硬约束待确认-不可比较
```

解锁评分输出的前置条件见 `docs/known_limitations.md` 第五节 P0 项。

---

# Phase 4.1｜Streamlit Web MVP

## 启动

```bash
pip install -e ".[dev]"
streamlit run app.py
```

入口文件：**`app.py`**（项目根目录）。默认读取 `data/decision.db`；
可用环境变量 `DECISION_DB_PATH` 指向其它库（UI 测试即用它指向临时库）：

```bash
DECISION_DB_PATH=/tmp/my.db streamlit run app.py
```

## 五个页面

| 侧边栏 | 文件 | 能力 |
|---|---|---|
| ① 项目总览 | `src/decision_system/ui/pages_overview.py` | 8 项状态指标 + 基于真实 DB 的下一步待办 |
| ② 招生路径 | `src/decision_system/ui/pages_paths.py` | 10 条路径全字段、学校/学院/专业代码筛选、详情、证据、缺失数据、历史记录 |
| ③ 证据管理 | `src/decision_system/ui/pages_evidence.py` | 来源登记 / 证据关联 / 人工核验（通过·驳回·冲突）/ 缺口统计 |
| ④ 决策模型 | `src/decision_system/ui/pages_model.py` | 三级权重树、组内归一与全局权重、调整预览、保存、派生用户配置、恢复默认、修改记录 |
| ⑤ 决策分析 | `src/decision_system/ui/pages_analysis.py` | 三情景 + A/B 双目标、覆盖率与门槛、缺失指标、证据不足时不排名 |

## 新增依赖及原因

| 依赖 | 原因 |
|---|---|
| `streamlit>=1.30` | 任务书指定的 Web 框架；本阶段交付形态为可操作 Web 工作台 |
| `pandas>=2.0` | 页面表格（`st.dataframe`）与统计口径展示的数据容器 |

> 未引入 Plotly：任务书要求「仅在必要时使用」，当前所有图表用 Streamlit 原生
> `st.bar_chart` / `st.progress` 即可表达，且在证据不足时**不绘制**排名图。

## UI 层约束（由测试强制）

- UI 不实现决策算法，全部调用 `engine/` 与 `services/`（`test_15_ui_does_not_bypass_strict_gate`、
  `test_15b_ui_source_has_no_scoring_logic`）。
- 所有写操作经 `services/evidence_service.py` 与 `services/profile_service.py`。
- 未知值显示「暂无数据 / 待核验 / 证据不足 / 暂无评分」，绝不补 0。
- 历史候选 ≠ 2028 正式资格，页面显式提示。

## 测试

| 目录 | 内容 |
|---|---|
| `tests/ui/` | 用 `streamlit.testing.v1.AppTest` **真实渲染** 5 个页面并模拟交互（登记来源、筛选、切换页） |
| `tests/integration/test_evidence_service.py` | 来源登记、重复拒绝、占位符不可核验、核验须留依据、闸门端到端、缺口统计口径 |
| `tests/integration/test_profile_service.py` | 权重调整走服务层、持久化、恢复默认保留历史、派生不污染演示配置 |

全部测试（Phase 4.0 + 4.1）：`pytest` → **149 passed**（详见 `reports/test_report_4_1.md`）。

---

# Phase 5.0｜北京邮电大学试点数据迁移

仅针对北邮一所学校做了真实招生研究数据迁移（不改动评分、权重、公式与其他学校数据）：

| 项 | 数量 | 说明 |
|---|---|---|
| 新增来源 | 3 | 2027 专业目录、2027 初试科目调整公告、人工智能学院官网（官网反爬 412，记为待核验） |
| 新增声明 | 8 | 2027 官方事实；**适用年份为 2027，不会泄漏进 2028 判定** |
| 已核验声明 | 6 | 经 `verify_claim(actor, basis)` 唯一合法路径升级 |
| 待核验声明 | 2 | 需 2026 目录才能判断「方向01 业务课是否变更」 |

关键口径纪律：**目录计划数（含推免）／统考计划／实际录取三者不得混用**；
调整公告是**专业级**（085410 业务课 809→408），目录是**方向级**（方向01=801、仅方向02=408），
因此**不能推断「所有方向都改为 408」**。

> 2028 招生目录尚未发布（截至 2026-10-16），**2028 任何结论目前都无法确认**。
> 2027 已核验事实在 `StrictEvidenceGate` 下于 `evaluation_year=2028` 会被**年份不匹配规则拒绝**。

---

# 数据库初始化

数据库**不入库**（见 `.gitignore`），由研究原件重建，三步：

```bash
# 1) 建表并导入 Phase 3.7C 研究原件（幂等，可重复执行）
python scripts/import_excel.py \
    --excel data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx \
    --db data/decision.db --replay-check

# 2) （可选）导入北邮 Phase 5.0 真实来源与声明，同样幂等
python scripts/migrate_bupt_phase5_0.py

# 3) 生成数据库结构说明
python scripts/describe_schema.py --out reports/db_schema.md
```

指向其它库用 `--db`（导入脚本）或环境变量 `DECISION_DB_PATH`（Web / 测试）：

```bash
DECISION_DB_PATH=/tmp/my.db streamlit run app.py
```

若缺少研究原件 `data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx`，第 1 步无法执行，
数据库需自行提供；此时 `tests/golden/` 黄金比对测试也会因缺少输入而不可用。

---

# 证据治理规则（硬性，由代码与测试强制）

| 规则 | 内容 |
|---|---|
| 来源登记 | `register_source_strict` 拒绝重复 `source_id`、拒绝占位来源、必须提供 URL/文件 or 发布方 |
| 声明升级 | **唯一合法路径**是 `verify_claim(actor, basis)`；候选映射永不自动升级为已核验 |
| 年份匹配 | 证据年份必须**精确等于**评估年份（`year_window=0`），历史事实不泄漏到 2028 |
| 缺失处理 | 不补零；未知保持未知，不计入分子分母 |
| 冲突处理 | `detect_and_record_conflict` 只记录，**不覆盖**旧事实 |
| 写操作 | 全部经 `services/evidence_service.py` / `services/profile_service.py`，页面不直接改 ORM 字段 |
| 审计 | 每次写入落 `audit_log`（actor / action / detail） |

---

# 项目当前状态与后续方向

| 项 | 状态 |
|---|---|
| 功能开发 | **已暂停**，等待独立审查结论 |
| 数据覆盖 | 5 所学校 / 10 条路径；导师、科研资源、招生记录**三类数据均为 0 条** |
| 有效评分 | 0（180 条全部「未知」） |
| 可比较路径 | 0（10 条全部硬约束待确认） |
| 用户反馈 | 「更像一个数据管理后台，而不是择校助手」 |
| 后续方向 | **尚未确定**，不做承诺 |

已知问题与审查重点见 `docs/CHAIN_CODE_REVIEW_HANDOFF.md` 与 `docs/known_limitations.md`。

