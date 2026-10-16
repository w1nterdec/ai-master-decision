# 2028 AI 硕士动态择校决策系统 · v1.0.0

> 面向「只有一次考研机会」的 2028 级 AI 相关全日制硕士择校：先看证据，再看偏好，最后才谈比较。

本项目已完成预期目标并发布 **v1.0.0**。它把分散的历史招生研究（导师、平台、就业、历史统考名额）
整合为可核查的证据，并给出一份**面向考生**的择校结论——同时严格区分两类信息：

- 🟦 **历史研究判断**：基于 2023–2027 各校官网/学院级资料，证明"资源真实存在"，**不等于 2028 官方招生确认**。
- 🟥 **2028 正式招生资格**：截至 v1.0.0，五校 2028 目录均未发布，全部路径"2028 资格未确认"。

---

## ⚠️ 重要声明：本系统不是录取概率预测工具

> **本系统是研究与决策辅助工具，不是录取概率预测工具，也不是院校排名产品。**

- 系统**从不输出、也拒绝输出**任何录取概率 / 上岸率 / 录取率（由 `engine/pipeline.py` 的
  `assert_no_admission_probability` 与单元测试强制）。
- 缺失数据不补零；空白评分保持"未知"，不计入分子分母。
- 候选证据映射永不自动升级为已核验证据；来源冲突保留记录，不自动覆盖旧事实。
- 历史候选 ≠ 2028 正式资格。所有"无法判断"均为证据不足时的正确系统行为。

---

## 快速开始（从 GitHub 克隆的最简路径）

```bash
# 1) 克隆
git clone https://github.com/w1nterdec/ai-master-decision.git
cd ai-master-decision

# 2) 创建虚拟环境并安装（含开发依赖）
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3) 从已入库的研究原件重建 SQLite 数据库（幂等，可重复执行）
python scripts/import_excel.py --replay-check

# 4) 导出「择校结果总览」与报告共用的整合研究数据 JSON（纯投影，幂等）
python scripts/export_consolidated.py

# 5) 启动 Streamlit Web（默认 http://localhost:8501）
streamlit run app.py

# 6) 跑测试
pytest
```

> **"择校结果总览"页不依赖数据库**：它只读 `data/school_research_consolidated.json`。
> 即使跳过第 3 步（不建库），该页也能正常打开；其余决策页面需要第 3 步生成的数据库。
> 数据库**不入库**（见 `.gitignore` 的 `data/*.db`），但研究原件 `data/raw/*.xlsx` 已入库，可随时重建。

---

## 功能概览

入口：`app.py`（项目根目录）。侧边栏导航：

| 侧边栏 | 页面文件 | 能力 |
|---|---|---|
| ① 决策驾驶舱 | `src/decision_system/ui/pages_cockpit.py` | 路径总览、资格闸门、四层决策解释 |
| ② 院校探索 | `src/decision_system/ui/pages_explore.py` | 按学校/学院/专业筛选路径与证据 |
| ③ 多校对比 | `src/decision_system/ui/pages_compare.py` | 多条路径横向比较（缺失值不补零） |
| ④ 动态决策树 | `src/decision_system/ui/pages_tree.py` | 情景化决策引导 |
| ⑤ 风险与路径规划 | `src/decision_system/ui/pages_risk.py` | 考研风险与一次机会策略 |
| ⑥ 我的决策档案 | `src/decision_system/ui/pages_profile.py` | 用户偏好与标记（本地，不改证据） |
| **⑦ 择校结果总览** | `src/decision_system/ui/pages_result.py` | **最终结论页**：重点研究对象 / 五校对比矩阵 / 学校详细分析 / 一次考研策略 / 决策敏感性 |
| ⚙️ 高级功能 | `pages_evidence/pages_paths/pages_model/pages_analysis/pages_overview` | 证据登记核验、数据维护、模型参数、决策分析、系统状态 |

**面向考生的最终结论**集中在两处，二者同源（均读 `data/school_research_consolidated.json`）：

- Web：**⑦ 择校结果总览**（移动端优先，🟦/🟥 双层展示）。
- 文档：**`docs/2028_AI_MASTER_DECISION_REPORT.md`**（15 节，含 Q1–Q8 问答）。

---

## 数据结构

### 1) SQLite 数据库（由研究原件重建，非手工维护）

| 表 | 内容 |
|---|---|
| `school` / `college` / `program` | 学校 / 学院 / 专业代码 |
| `admission_path` | 招生路径（学校+学院+专业+方向+年份+方式+路径角色，含 2028 核验状态） |
| `evidence_source` / `evidence_claim` / `claim_path_link` | 来源登记 / 证据声明 / 声明-路径关联 |
| `indicator` / `score_record` | 三级指标树 / 评分记录（未知保持未知） |
| `admission_record` / `mentor` / `research_resource` | 招生记录 / 导师 / 科研资源（当前为空，待补充） |
| `weight_profile` / `scenario` | 权重配置 / 情景倍率 |
| `audit_log` | 每次写入留痕（actor / action / detail） |

> 重建命令：`python scripts/import_excel.py --excel data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx --db data/decision.db --replay-check`
> 导入**幂等**（`get_or_create` 自然键），重复执行不产生重复记录，也**不覆盖、不删除**已有历史记录。

### 2) 整合研究数据 JSON（Web 与报告的单一可信源）

`data/school_research_consolidated.json` 由 `scripts/export_consolidated.py` 从 Excel 投影生成：

```jsonc
{
  "source_file": "data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx",
  "source_year_note": "研究证据多为 2023–2027 历史事实/学院级资源；均非 2028 官方招生资格确认",
  "paths": [ { "path_id":"P01", "school":"北京邮电大学", "college":"005",
               "program":"085410", "direction":"方向01", "exam4":"801 通信原理",
               "city":"北京", "verify2028":"待2028核验", "risk":"…",
               "admission_status":"待确认", "qual2028":"2028资格未确认", "note":"…" }, … ],
  "research_by_path": { "P01": [ { "path_id":"P01", "school":"…", "college":"…",
               "program":"…", "indicator":"岗位与实习机会", "stage":"2D资源",
               "theme":"D4-就业与产业连接", "statement":"…原文…", "source_id":"…",
               "grade":"S4", "accessibility":"P3", "verify_status":"线索(全校级)",
               "match_limit":"…", "score_status":"待人工评价" }, … ], … },
  "research_flat": [ … 207 条全部证据 … ],
  "open_questions": [ "P0 | 北邮005 | 2027目录原件… | 备考路径 | 已闭合（原：未闭合）", … ]
}
```

- 证据等级 `grade`：S1 官方/目录级 · S2 学院级已证实资源 · S3 实验室/研究院级 · S4 全校级线索。
- 该文件是**派生产物**（可由 Excel 重生成），既入库便于直接运行，也保留可重建性。

---

## 如何追加院校与研究数据

数据更新**不会覆盖已有研究记录**（导入幂等 + 投影导出），追加流程如下：

1. **改源表**：在 `data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx` 中
   - `路径` 表：新增一行（路径ID / 学校 / 学院码 / 专业码 / 方向 / 初试第四单元 / 培养地 / 2028核验状态 / 关键风险 / 资格说明…）；
   - `3_2证据映射候选` 表：追加证据行，用 `路径ID` 关联到对应路径。
2. **重建数据库**（幂等，保留旧记录）：`python scripts/import_excel.py --replay-check`
3. **重导整合 JSON**（纯投影，不丢弃任何研究行）：`python scripts/export_consolidated.py`
4. **同步结论文本**：`docs/2028_AI_MASTER_DECISION_REPORT.md` 与 `pages_result.py` 中的
   定性判断（重点分组 `FOCUS_GROUP`、对比矩阵 `MATRIX`、策略 `STRATEGY`、敏感性 `SENSITIVITY`）
   为**分析师人工撰写的结论**，不会自动生成——新增院校后需同步修订这两处的对应段落。
5. Web 与报告均读整合 JSON，结构化证据自动同步；上述第 4 步保证结论与数据一致。

> 数据库导入脚本在**冲突时只记录、不覆盖旧事实**；不同年份记录互不覆盖（由
> `test_21_different_years_do_not_overwrite` 强制）。

---

## 设计原则（由代码与测试强制）

> 正确性 > 可追溯性 > 可测试性 > 可维护性 > 界面美观

- 决策引擎不输出任何录取概率（`assert_no_admission_probability` 自检）。
- 缺失数据不补零；空白评分保持"未知"，不计入分子分母。
- 候选证据映射永不自动升级为已核验证据。
- 来源冲突保留记录，不自动覆盖旧事实。
- 历史候选 ≠ 2028 正式资格。
- 每个情景/目标用**自身**覆盖率判断是否输出评分。

---

## 模块速览

| 模块 | 职责 |
|---|---|
| `engine/weights.py` | 三级权重树：组内归一、全局归一、负权重拒绝、零权重分组防除零 |
| `engine/constraints.py` | 硬约束三态 + 2028 资格判定 |
| `engine/coverage.py` | 覆盖率与加权平均（缺失不入分母） |
| `engine/scenarios.py` | 情景倍率与独立归一化 |
| `engine/objectives.py` | 双目标相关度矩阵 + 必备分组门槛 |
| `engine/pipeline.py` | 门面：PathContext → PathDecision（含禁概率自检） |
| `evidence/gate.py` | 严格闸门 / Excel 兼容闸门（仅测试） |
| `evidence/registry.py` | 来源与声明登记、冲突治理、人工核验唯一入口（幂等 upsert） |
| `importers/excel_importer.py` | Excel → SQLite，幂等，不做推断 |
| `services/` | DB 会话、路径身份、装配层、权重修改审计 |
| `ui/pages_result.py` | **⑦ 择校结果总览**（只读整合 JSON，无评分逻辑） |

---

## 测试

`pytest` → **294 passed**（单元 / 集成 / 黄金比对 / UI 真实渲染）。

| 目录 | 内容 |
|---|---|
| `tests/unit/` | 权重、证据闸门、覆盖率、硬约束、双目标、引擎（纯内存，无 DB 依赖） |
| `tests/integration/` | 导入幂等、不同年份/学院/路径角色不混淆、DB 端到端、权重修改审计 |
| `tests/golden/` | 与 Phase 3.7C Excel/LibreOffice 实测结果逐格比对 |
| `tests/ui/` | 用 `streamlit.testing.v1.AppTest` **真实渲染**页面并模拟交互 |

---

## 部署

```bash
pip install -e ".[dev]"
streamlit run app.py
```

- 默认读取 `data/decision.db`；可用环境变量 `DECISION_DB_PATH` 指向其它库（测试即用此隔离）：
  ```bash
  DECISION_DB_PATH=/tmp/my.db streamlit run app.py
  ```
- 数据库缺失时，`ui/db_access.py` 会自动建表（空库），页面不会崩溃；"择校结果总览"页不受影响。

---

## 已知限制（v1.0.0）

| 项 | 状态 |
|---|---|
| 2028 招生资格 | 五校 2028 目录均未发布，全部路径"2028 资格未确认" |
| 有效评分 | 0（评分记录有效性全部为"未知"，属正确行为） |
| 导师 / 科研资源 / 招生记录 | 三类数据均为 0 条（Excel 研究证据尚未结构化入库，见 `docs/DATA_UTILIZATION_AUDIT.md`） |
| 权重配置 | 演示配置（`is_demo=True`），尚未确认为用户真实偏好 |
| 结论性质 | 候选判断，不构成录取预测或院校排名；2028 目录发布后需复核 |

详细数据利用审计见 **`docs/DATA_UTILIZATION_AUDIT.md`**；择校结论见 **`docs/2028_AI_MASTER_DECISION_REPORT.md`**。
