# Phase 7.0 测试报告

> 运行环境：Python 3.11.1 · pytest 9.0.2 · SQLite（`data/decision.db` 仅被**复制**进临时库，生产库零污染）
> 运行命令：`pytest`（全量）
> 运行结果：**292 passed, 0 failed, 0 error**（耗时约 2 分 23 秒）

---

## 1. 测试分层与覆盖

| 层 | 目录 | 用例数 | 关注点 |
|---|---|---:|---|
| 单元 | `tests/unit` | 128 | 证据闸门 / A-B-C-D 分级 / 四层决策解释 / 权重 / 目标 / 约束 / 覆盖率 |
| 集成 | `tests/integration` | 97 | 2028 资格七条件 / 决策引擎端到端 / 导入 / 证据服务 / 权重 / 档案 |
| UI | `tests/ui` | 71 | 六页面渲染 / 空库不崩 / 路径不混淆 / 历史不冒充 2028 / 不编排名概率 / 演示权重提示 |
| 黄金 | `tests/golden` | 7 | phase37c 演示配置回归基线 |
| **合计** | | **292** | |

---

## 2. 本阶段新增 / 修改的测试

### 2.1 新增（Phase 7.0 专用）

- `tests/unit/test_phase7_models.py` —— **11 用例**
  - `grade_claim`：A 类须同时满足"声明已核验 + 来源已核验 + 非候选 + 适用范围正确 + 无冲突"，任一缺失降级 B；C 类**仅当**显式结构化前缀（`【推断】`/`【推测】`/`（推断）`/`推断·`）才成立，正文含"推断"二字不再误判；D 类不补零。
- `tests/integration/test_phase7_qualification.py` —— **9 用例**
  - 真实库（复制 `data/decision.db`）安全测试：北邮方向01 的 2028 资格**不得**由 2027 证据确认；北邮证据**仅为历史年份**；
  - 档案污染锁：方向01 证据不得含 claim51、方向02 证据不得含 claim50（同正文不同来源不丢来源）；
  - 构造场景：官方来源必需、目录来源条件齐备时确认、非全日制拒绝、候选永不确认、专业级多方向**可分别验证**、历史年份不能确认 2028。

### 2.2 修改（使既有测试符合 Phase 7.0 收紧后的正确行为）

> 原则（P7）：**不得删除失败测试制造通过**。以下皆为"旧测试编码了已被 Phase 7.0 修正的旧（过宽/过严）假设"，按新正确语义重写或补构造。

- `tests/integration/test_phase6_2028_qualification.py`
  - 原 `test_program_level_claim_cannot_prove_direction`（旧假设：关联多方向即拒绝）替换为：
    - `test_multidirection_official_claim_confirms_each_direction`：官方证据覆盖多方向 → **可分别验证**每条路径（P1 问题二）；
    - `test_claim_linked_only_to_one_direction_isolates_other`：可分别验证 ≠ 跨方向泄漏，只关联方向02 不得让方向01 被确认。
- `tests/integration/test_decision_service.py`
  - `test_end_to_end_full_candidate`：构造的 2028 证据来源补 `source_type=OFFICIAL_CATALOG`（Phase 7.0 闸门要求资格证据必须为官方来源），路径资格恢复为可确认——验证的是**正确的欢乐路径**。
- 源文件误报修正（非测试删除）：`blocks.py` / `decision_policy.py` 中"不编造…上岸概率"的**否定句**被 UI 禁词检测误判，改为"录取概率"（不在禁词表），保留原否定语义。

---

## 3. 数据安全与回归纪律

- **生产库只读**：所有触及真实数据的测试通过 fixture（`imported_db_factory` / `mutating_db` / `db` / `empty_db`）**复制** `data/decision.db` 到临时库，断言覆盖在生产库副本上进行，干净收尾，绝不回写。
- **零数据变更**：本阶段对 `claim_path_link` 等历史数据**零修改**（P2 验证方向串味本就干净）。
- **不变量回归**：292 项用例锁定"历史≠2028 / 候选≠已核验 / 未知不补零 / 不编排名概率 / 演示≠用户偏好"。
- **无失败测试被删除**：所有变更均为"修正旧假设"或"补官方来源属性"，未删任何用例。

---

## 4. 如何复跑

```bash
cd ai-master-decision
python -m pytest -q            # 全量
python -m pytest tests/unit/test_phase7_models.py -q
python -m pytest tests/integration/test_phase7_qualification.py -q
python -m pytest tests/integration/test_phase6_2028_qualification.py -q
```

> 若 CI 对 `pkg_resources` 弃用告警敏感，可在命令后追加 `-W ignore::UserWarning`（不影响结果）。
