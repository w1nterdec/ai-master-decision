# Chain 独立代码审查交接文档

> 项目：2028 AI 硕士动态择校决策系统（工程名 `ai-master-decision`）
> 交接日期：2026-10-16　|　阶段：Phase 5.2（归档交接）
> **本文只做事实交接与审查建议，不代替审查结论，不宣布审查通过。**

审查者请先读一句前提：**本系统不是录取概率预测工具**，是研究与决策辅助工具。
当前它不产出、也不允许产出择校排名结论（原因见第 3、4 节）。

---

## 1. 工程架构

### 1.1 分层与依赖方向

```
app.py                      Streamlit 入口（仅装配页面，无业务逻辑）
   │
   ├── src/decision_system/ui/*.py          页面层：渲染 + 收集输入
   │        │  依赖 ↓（禁止自带算法，由测试强制）
   ├── src/decision_system/services/*.py    装配层：DB → 引擎输入 / 写操作 / 审计
   │        │  依赖 ↓
   ├── src/decision_system/engine/*.py      决策引擎：纯函数式，零 ORM、零 UI 依赖
   │        └── evidence/gate.py            证据闸门（引擎判断是否采信评分的唯一入口）
   │
   ├── src/decision_system/models/*.py      SQLAlchemy ORM + 枚举
   ├── src/decision_system/importers/*.py   Excel → SQLite（幂等，不做推断）
   └── src/decision_system/schemas/*.py     Pydantic 输入输出模型
```

依赖方向是**单向**的：`ui → services → engine`，`engine` 不反向依赖任何上层。
`importers` 只写库，不参与决策判定。

### 1.2 各模块职责

| 模块 | 职责 |
|---|---|
| `engine/weights.py` | 三级权重树归一：组内归一、全局归一、拒绝负权重、零权重分组防除零 |
| `engine/coverage.py` | 覆盖率与加权平均；**缺失不入分子也不入分母** |
| `engine/scenarios.py` | 三情景（基础/职业/报考·科研）倍率与独立归一化 |
| `engine/objectives.py` | 双目标（A 是否值得读 / B 是否值得押唯一一次机会）相关度矩阵 + 必备分组门槛 |
| `engine/constraints.py` | 硬约束三态判定 + 2028 资格判定 |
| `engine/pipeline.py` | 门面 `DecisionEngine`：`PathContext → PathDecision`；含 `assert_no_admission_probability` 自检 |
| `evidence/gate.py` | `StrictEvidenceGate`（9 条规则，含年份精确匹配）与 `LegacyPhase37CGate`（**仅供黄金比对**） |
| `evidence/registry.py` | 来源/声明登记、冲突记录、`verify_claim` 唯一升级入口、审计 |
| `services/evidence_service.py` | 证据写操作服务层（登记、核验、驳回、冲突、缺口统计） |
| `services/decision_service.py` | DB → 引擎输入装配（`SqlAlchemyEvidenceResolver`、`path_context_from_db`） |
| `services/weight_service.py` / `profile_service.py` | 权重调整与用户配置派生，全部落审计 |
| `services/path_identity.py` | `path_key` 8 段身份构造与解析 |
| `importers/excel_importer.py` | Excel → SQLite，幂等 upsert，**不做任何推断** |
| `ui/pages_*.py` | 五个页面（总览/路径/证据/模型/分析） |

### 1.3 关键领域概念

- **`path_key`**：`学校码|学院码|专业码|学习方式|方向|招生年份|招生方式|路径角色`（8 段），
  是路径的唯一身份，用于避免"不同年份/学院/路径角色被混淆"。
- **证据三态**：未登记 → 候选映射 → 已核验。**候选映射永不自动升级**。
- **年份纪律**：证据年份必须精确等于评估年份（`year_window=0`）。2027 事实不能用于 2028 判定。
- **配额三口径**：目录计划数（含推免）／统考计划／实际录取，**不得混用**。

---

## 2. 核心代码入口（建议优先阅读顺序）

| 优先级 | 文件 | 为什么先看 |
|---|---|---|
| 1 | `src/decision_system/engine/pipeline.py` | 决策引擎入口，`DecisionEngine.evaluate()` 是全系统唯一决策出口 |
| 2 | `src/decision_system/evidence/gate.py` | 证据闸门，决定"哪些评分能被采信"，是数据可信度的守门人 |
| 3 | `src/decision_system/models/entities.py` | 24 张表的数据模型，理解领域语义的起点 |
| 4 | `src/decision_system/engine/weights.py` | 权重计算（三级归一） |
| 5 | `src/decision_system/engine/scenarios.py` | 情景分析（倍率与独立归一化） |
| 6 | `src/decision_system/services/decision_service.py` | DB → 引擎装配层，最可能出现"口径泄漏"的地方 |
| 7 | `src/decision_system/ui/pages_analysis.py` | 决策分析页，用户反馈「像后台」的主要来源 |
| 8 | `scripts/migrate_bupt_phase5_0.py` | Phase 5.0 北邮迁移脚本，真实数据进入系统的样例 |
| 9 | `src/decision_system/importers/excel_importer.py` | 导入层（44 KB，最大文件，值得评估是否需要拆分） |
| 10 | `src/decision_system/engine/coverage.py` / `objectives.py` / `constraints.py` | 覆盖率、双目标、硬约束三块核心规则 |

测试入口：`tests/unit/`（纯内存）、`tests/integration/`（DB 驱动）、
`tests/golden/`（与旧 Excel 逐格比对）、`tests/ui/`（Streamlit 真实渲染）。

---

## 3. 数据现状（2026-10-16 对 `data/decision.db` 实际查询）

| 指标 | 实际值 | 说明 |
|---|---|---|
| 学校数量 | **5** | 北邮、电子科大、东南大学、合工大、西南交大 |
| 学院 / 专业 | 9 / 9 | |
| 招生路径数量 | **10** | 全部 `admission_year=2028` |
| 来源登记数量 | **87** | 其中 已核验 2、待核验 1、**未登记本体 84** |
| 声明数量 | 56 | 其中 **已核验 6**、候选映射 48、待核验 2 |
| 有效评分数量 | **0** | 180 条 `score_record` 的 `validity` **全部为「未知」**，`raw_score` 全为 NULL |
| 当前可比较路径数量 | **0** | 10 条全部「硬约束待确认-不可比较」，基础覆盖率 0.000 |
| 导师资源 | **0** | `mentor` 表空 |
| 科研资源 | **0** | `research_resource` 表空 |
| 招生录取记录 | **0** | `admission_record` 表空 |
| 决策结果 | 0 | `decision_result` 表空（引擎每次现算） |
| 审计记录 | 100 | `audit_log`（actor 均为系统标识，无个人信息） |

**结论：系统当前一处真实择校结论都给不出来**，且这是当前数据状态下的正确行为，
不是缺陷。审查时请把"能否产出结论"与"结论是否可信"分开看。

> 数据库不在仓库中（见 `.gitignore`），重建方式见 README「数据库初始化」一节，
> 依赖研究原件 `data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx`。

---

## 4. 已知问题

### 4.1 用户体验（用户原话）

> 「更像一个数据管理后台，而不是择校助手。」

- 五个页面（总览/路径/证据/模型/分析）都偏向**数据浏览与治理操作**，
  缺少"我该怎么选"的引导式表达。
- 由于数据不足，分析页在证据不足时**不排名**（这是正确设计），
  但页面没有把"为什么没有结论、还差什么"讲成用户能行动的步骤。
- 疑似过度暴露内部结构：`path_key`、来源 ID、覆盖率数值等实现细节直接呈现。

### 4.2 真实择校结论不足

- 有效评分 0、可比较路径 0、覆盖率 0.000 —— 评分矩阵尚未真正建立。
- 权重是**演示配置**（`is_demo=True`），**尚未确认为用户真实偏好**，
  任何"评分"即便算出来也不代表用户偏好。

### 4.3 历史年份与 2028 候选路径的关系

- 10 条 2028 路径来自**历史数据推演的候选**，不是 2028 正式招生目录
  （2028 目录截至 2026-10-16 **尚未发布**）。
- 系统刻意不做"历史 → 2028"推断，`StrictEvidenceGate` 会因年份不匹配拒绝 2027 证据。
- 风险：用户可能把候选路径误解为"已确认可报考"。UI 有提示，但强度是否足够值得审查。

### 4.4 数据覆盖率不足

- 5 所学校、10 条路径，样本极小；84/87 来源**无本体登记**（缺 URL/发布方），
  无法核验。
- Phase 5.0 只完成北邮一所学校，其余四所仍停留在导入阶段。

### 4.5 导师 / 科研资源 / 招生记录缺口

- 三张表均为 **0 条**。而这三类恰恰是"择校"（而非"报考资格"）最核心的信息。
- 表结构已预留（`mentor`、`research_resource`、`resource_path_link`、
  `admission_record`），但从未填充 —— 审查时请评估这些表的设计是否合理、
  还是属于**先建表后无用**的过度设计。

### 4.6 其他待确认项

- Excel 研究原件含 24 个工作表、跨 Phase 3.x 多轮修复，历史包袱较重。
- 黄金测试使用 `LegacyPhase37CGate` 复现旧 Excel 语义，与默认严格闸门并存，
  两套闸门是否会让维护者困惑，值得评估。

---

## 5. 独立审查建议（供参考，不预设结论）

### 5.1 可能过度工程化的模块

1. **`importers/excel_importer.py`（44 KB，单文件最大）** —— 是否应拆分；
   其中"待核问题""冲突计数"等逻辑是否该属于导入层。
2. **24 张表** —— 对 5 所学校 / 10 条路径的数据量是否过多；
   特别是 `claim_indicator_link`、`scenario_multiplier`、`weight_node` 等。
3. **双目标 × 三情景 × 三级权重 = 18 个组合** —— 在有效评分为 0 的前提下，
   这套机制是否已超出当前数据能支撑的程度。
4. **两套证据闸门**（严格 + 遗留兼容）是否必要。

### 5.2 潜在架构风险

- `services/decision_service.py` 是 DB → 引擎的装配层，也是**口径最容易泄漏**的地方
  （如把 2027 证据误装配进 2028）。建议重点核对其年份与适用性过滤。
- 引擎宣称"零 ORM 依赖"，请验证是否真的没有反向依赖泄漏。
- 写操作是否全部经过服务层并落审计（UI 测试有断言，建议抽查真实路径）。
- 幂等性：导入与迁移脚本都声称幂等，建议审查其 get-or-create 实现是否真的无副作用。

### 5.3 数据可信度风险

- 未登记本体的 84 个来源若被误当作证据，会直接污染结论。
- 候选映射（48 条）与已核验（6 条）在 UI 上是否可能被用户混淆。
- 2027 已核验事实与 2028 判定之间的隔离是否足够强（建议实测跨年份闸门）。
- 配额三口径（目录计划 / 统考计划 / 实际录取）在模型里是否有明确字段区分，
  还是共用字段易混用。

### 5.4 用户体验问题

- 页面是"数据后台"形态，缺少结论导向的任务流。
- 未知值展示（暂无数据 / 待核验 / 证据不足）是否过于密集，导致用户无所适从。
- 手机端侧边栏默认折叠，导航可达性较差（实测现象）。

### 5.5 最值得优先审查的代码（建议顺序）

1. `engine/pipeline.py` —— 决策出口与概率自检
2. `evidence/gate.py` —— 数据可信度守门人
3. `services/decision_service.py` —— 装配层口径泄漏风险最高
4. `engine/coverage.py` —— 缺失值处理（不补零）是否彻底
5. `ui/pages_analysis.py` —— 用户"像后台"感受的主要来源
6. `importers/excel_importer.py` —— 最大单一文件，可维护性风险

---

## 6. 审查环境

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/import_excel.py --replay-check      # 重建数据库
python scripts/run_decision.py                     # 引擎输出
pytest                                             # 169 passed（实测）
streamlit run app.py                               # http://localhost:8501
```

- Python 3.11.1；关键依赖版本见 README。
- 必需环境变量：**无强制项**（`DECISION_DB_PATH` 可选，指向其它数据库）。
- 已知限制：缺少研究原件 Excel 时，`tests/golden/` 黄金比对不可用。

**实测基线（2026-10-16，干净虚拟环境）**：依赖安装成功、导入幂等通过、
引擎评估 10 条路径全部不可比较、`pytest` **169 passed**、Streamlit 启动 HTTP 200。
