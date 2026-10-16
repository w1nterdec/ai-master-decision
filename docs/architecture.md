# 架构说明（Phase 4.0）

## 1. 目标与边界

Phase 4.0 把 Phase 3.x 的 Excel 研究成果转化为**可测试、可维护、可扩展**的软件系统，
为 Phase 4.1（Web 可视化）、PDF 报告、GitHub 版本管理打底层。

**本阶段不做**：重新研究学校、重新设计 Excel、完整 Web UI、调剂/就业推荐算法、排行榜。

**本阶段做**：数据架构、证据治理、独立决策引擎、Excel 迁移、自动化测试、规则文档。

## 2. 分层与依赖方向

```
scripts/           命令行入口（导入 / 评估 / 生成结构说明）
   │
services/          装配层：把数据库实体组装成引擎输入（唯一知道 ORM 的引擎侧）
   │
engine/            决策引擎（纯 Python，零 ORM / 零 UI / 零 IO 依赖）
evidence/          证据闸门与治理服务
   │
models/            SQLAlchemy ORM 实体 + 枚举
schemas/           Pydantic 模型（导入、API、报告）
importers/         Excel -> SQLite 迁移
```

依赖方向严格单向：`scripts → services → engine/evidence → models`。
**engine 不 import services / importers / 任何 UI 框架**，这是"决策引擎与 UI 解耦"的可验证约束。

## 3. 关键架构取舍（含理由与代价）

### 取舍 1：决策引擎使用纯 Python 数据结构，不直接读 ORM

- 做法：`WeightTree`、`ScoreCell`、`HardConstraintFacts` 都是 dataclass；`DecisionEngine` 只接受这些结构。
- 理由：单元测试不需要数据库，规则可独立回归；引擎可复用于 Web / CLI / PDF / 批处理。
- 代价：需要一个装配层（`services/decision_service.py`）做 ORM → 引擎输入转换，多一层代码。

### 取舍 2：路径身份用 `path_key` 复合键，而非「学校 + 专业代码」

- 做法：`path_key = 学校码|学院码|专业码|学习方式|方向|年份|招生方式|路径角色`。
- 理由：需求明确禁止只用学校名+专业码；同一专业码在不同学院、不同年份、一志愿与调剂都必须是不同记录。
- 代价：`path_key` 字符串较长；`direction` 依赖人工填写的规范性（不规范值会生成新路径，已在导入报告中标为异常）。

### 取舍 3：候选证据映射永不自动升级

- 做法：Excel「3_2证据映射候选」导入后 `status=CANDIDATE, is_candidate=True`；只有 `verify_claim(actor, basis)` 才能升级。
- 理由：修复 Phase 3 遗留 U-01；Excel 中"已证实"是人工标注文本，不等于可追溯核验。
- 代价：当前数据状态下**所有评分都无效**，覆盖率恒为 0，系统不会给出任何分数。这是预期行为，不是缺陷。

### 取舍 4：严格闸门与 Excel 兼容闸门并存

- 做法：`StrictEvidenceGate`（默认）/ `LegacyPhase37CGate`（仅黄金测试）。
- 理由：既要修复 U-01，又要能证明"共同支持的计算规则与 Excel 一致"。
- 代价：两套闸门需同时维护；已用测试锁死 Legacy 闸门不得用于生产路径（`test_strict_gate_is_stricter_than_excel`）。

### 取舍 5：双目标用「相关度矩阵」而非两套独立打分

- 做法：A/B 共享同一份评分证据，用不同相关度矩阵重算权重，并各自设必备分组门槛。
- 理由：避免"复制综合分"；保证两个结论的差异可审计、可解释、可配置。
- 代价：相关度矩阵本身是主观配置，已标记为 `is_demo=True` 并在规则文档中列出，需用户后续确认。

### 取舍 6：SQLite + SQLAlchemy ORM

- 理由：单机可复现、零运维、便于打包交付与 GitHub 版本管理；ORM 便于后续迁移到 PostgreSQL。
- 代价：并发写入能力弱（本项目为单人决策系统，可接受）。

### 取舍 7：不解析自由文本推断年份 / 专业名称 / 招生人数

- 做法：陈述文本中的年份只记录为 `year_hints`（留痕），**不**写入 `applicable_years`。
- 理由：防止把"2022 届就业报告"误判为 2028 适用证据；防止编造招生事实。
- 代价：当前所有声明的 `applicable_years` 为空，必须人工核验后才可能通过年份检查。

## 4. 数据流

```
Phase3_7C Excel (只读档案)
        │  scripts/import_excel.py
        ▼
   SQLite (data/decision.db)
        │  services/decision_service.py
        ▼
   DecisionEngine (evaluate)
        │
        ├─ 硬约束引擎   -> 排除 / 历史候选 / 待核验 / 2028 资格
        ├─ 证据闸门     -> 有效 / 无效 / 未知
        ├─ 三级权重     -> 基础 + 3 情景（各自归一）
        ├─ 覆盖率       -> 各口径独立判断
        └─ 双目标       -> A 培养与职业价值 / B 一志愿报考价值
        │
        ▼
   DecisionResult (JSON，写入 decision_result 表)
```

## 5. 目录结构

```
ai-master-decision/
├── README.md
├── pyproject.toml
├── .gitignore
├── data/
│   ├── raw/          只读研究档案（原始 Excel / 回归 JSON / 报告 MD / 验证脚本）
│   ├── processed/    处理中间产物
│   └── decision.db   SQLite（可由脚本重建，不入库）
├── src/decision_system/
│   ├── models/       ORM 实体与枚举
│   ├── schemas/      Pydantic 模型
│   ├── evidence/     证据闸门 + 治理服务
│   ├── engine/       权重 / 硬约束 / 覆盖率 / 情景 / 双目标 / 门面
│   ├── importers/    Excel 导入器
│   └── services/     数据库会话 / 路径身份 / 装配层
├── tests/{unit,integration,golden}
├── docs/             architecture / decision_rules / data_dictionary / known_limitations
└── scripts/          import_excel.py / run_decision.py / describe_schema.py
```

## 6. 与 Phase 3.x 的对应关系

| Phase 3.x 位置 | Phase 4.0 对应 |
|---|---|
| 三级指标树 | `indicator` + `weight_profile` + `weight_node` |
| 3_2情景权重 | `scenario` + `scenario_multiplier` |
| 三级证据评分 | `score_record`（有效性由引擎判定，不再由 Excel 公式判定） |
| 路径（K/L/M/N/O 列） | `admission_path` + `hard_constraint_evaluation` |
| 来源登记 | `evidence_source` |
| 3_2证据映射候选 | `evidence_claim` + `claim_path_link` + `claim_indicator_link`（候选态） |
| 3_2情景比较（公式） | `engine/pipeline.py` |
| 待核问题 | `audit_log(action=import.open_question)` |
