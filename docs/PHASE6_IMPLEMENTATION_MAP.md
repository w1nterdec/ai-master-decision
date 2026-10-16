# Phase 6.0｜实施清单与指标映射表

基线 Commit：`cc3073083ec4458513eae6298d529da6787ecea7`
分支：`feature/phase6-decision-ui`　|　盘点日期：2026-10-16（**只此一次**）

---

## 1. V4.0 五维 → 现有指标树 映射表

现有库内一级维度与千问 V4.0 命名**不一致**。按任务书 1.2：**只建映射，不覆盖既有指标**。

| V4.0 一级维度 | 现有库内一级 | 对应关系 | 说明 |
|---|---|---|---|
| 05 长期职业发展与衔接 | `L1-职业发展` | 1:1 | 二级：AI工程就业、长期成长 |
| 04 考研可行性与失败风险 | `L1-报考可行性` | 1:1 | 二级：招生路径、考试风险 |
| 03 院校、专业与科研平台 | `L1-研究培养` | 1:1 | 二级：科研匹配、培养可进入 |
| 01 地域与 AI 产业生态 | `L1-地域生态` | 1:1 | 二级：产业机会、生活适配 |
| 02 家庭条件与地理关系 | `L1-成本安排` + `L2-地域生态\|生活适配` | **1:2 拆分** | V4.0 的"家庭条件"→ `成本安排`（经济成本/培养安排）；"地理关系"→ `地域生态\|生活适配\|地域与气候` |

映射常量落在 `src/decision_system/ui/viewmodels.py` 的 `V4_DIMENSION_MAP`，页面按 V4.0 顺序展示，
**数据库指标 code / name / 层级一律不改**。

三级指标共 18 个，全部保留原义。数据状态按 `ScoreRecord.validity` 判定（当前 180 条全部「未知」）。

---

## 2. 可复用组件（不重写）

| 组件 | 位置 | 复用于 |
|---|---|---|
| `PathRow` / `load_path_rows` / `filter_path_rows` / `missing_indicators` | `ui/decision_view.py` | 驾驶舱、院校探索、对比、风险 |
| `build_engine` / `path_context_from_db` / `build_weight_tree` / `load_scenarios` | `services/decision_service.py` | 全部页面（唯一决策入口） |
| `StrictEvidenceGate` | `evidence/gate.py` | 不改，仍严格 |
| `WeightTree`（组内/全局归一、预览） | `engine/weights.py` | 动态决策树 |
| `update_weight` / `weight_change_history` | `services/weight_service.py` | 权重调整与变化记录 |
| `clone_profile` / `restore_from_base` / `confirm_as_user_preference` | `services/profile_service.py` | 权重保存/恢复/确认 |
| `scenario_weights` | `engine/scenarios.py` | 情景切换 |
| `status_kind` / `render_status` / `show_value` / `quota_text` | `ui/formatting.py` | 全站状态文案 |
| `pages_evidence` / `pages_model` / `pages_overview` / `pages_paths` / `pages_analysis` | `ui/` | **原样保留**，挂到「高级功能」 |
| `db_session` / `resolve_db_path` | `ui/db_access.py` | 不变 |

## 3. 必须修改

| 文件 | 改动 |
|---|---|
| `app.py` | 导航重组：6 主页面 + 高级功能（证据管理/数据维护/模型参数/系统状态）；默认首页=决策驾驶舱；标题与副标题；隐藏内部细节 |
| `src/decision_system/services/decision_service.py` | **M4**：修复 `_has_verified_2028_evidence()` 的路径适用性 / 来源年份边界（见第 6 节） |

## 4. 需要新增

| 文件 | 职责 |
|---|---|
| `src/decision_system/ui/viewmodels.py` | M2 只读 ViewModel：`SchoolSummary` / `PathSummary` / `EvidenceSummary` / `ComparisonSummary` / `RiskSummary` + `V4_DIMENSION_MAP`。**不建业务实体** |
| `src/decision_system/services/view_service.py` | 少量只读查询函数（学校聚合、路径证据摘要、对比矩阵、缺口排序、档案读写） |
| `src/decision_system/ui/pages_cockpit.py` | 页面一 决策驾驶舱 |
| `src/decision_system/ui/pages_explore.py` | 页面二 院校探索 |
| `src/decision_system/ui/pages_compare.py` | 页面三 多校对比 |
| `src/decision_system/ui/pages_tree.py` | 页面四 动态决策树 |
| `src/decision_system/ui/pages_risk.py` | 页面五 风险与路径规划 |
| `src/decision_system/ui/pages_profile.py` | 页面六 我的决策档案（含 Markdown 导出） |
| `src/decision_system/ui/blocks.py` | 六页面共享渲染块（路径事实 / 资格 / 名额 / 证据 / 缺口 / 候选动作），避免各页重复实现 |
| `data/decision_profile.json` | 决策档案轻量持久化（独立配置文件，不动数据库结构；**已加入 .gitignore**） |

### 4.1 新增测试

| 文件 | 覆盖 |
|---|---|
| `tests/integration/test_phase6_2028_qualification.py` | M4 边界回归：关联适用性 / 来源年份边界 / 资格相关性 / 候选·待核验·未核验来源·空年份·历史年份 |
| `tests/ui/test_phase6_decision_ui.py` | 六页面渲染、空库、无虚假排名、无预设最优、历史不冒充 2028、未知不补零、路径身份不混淆、权重持久化、档案导出 |
| `tests/unit/test_phase6_viewmodels.py` | V4.0 维度顺序、未知常量非 0、对比永不宣布赢家、档案往返序列化 |

## 5. 不需要修改

`models/`、`engine/`（除调用）、`evidence/`、`importers/`、`scripts/` 迁移脚本、
`tests/` 既有用例（只新增）、数据库结构（**不改表、不改字段**）。

## 6. M4 待修复：`_has_verified_2028_evidence()` 误判风险

现状（3 处可导致把历史/无关声明误判为 2028 资格）：

1. **未校验 `ClaimPathLink.applicable`** —— 关联被标为不适用仍计入；
2. **未校验来源年份边界** —— 只要求声明 `applicable_years` 含 2028，未要求**来源**的 `applicable_years` 也含 2028；
3. **未校验声明是否支持"招生资格"** —— 任何 2028 已核验声明（如"考试科目"）都会让资格成立。

修复（最小范围）：
- 加入 `link.applicable` 判定；
- 加入来源 `applicable_years` 含评估年份的判定（空则视为不限年份，保持既有行为）；
- 加入"资格相关"判定：声明须关联到招生资格相关指标（`L1-报考可行性` 下指标）或 `topic/stage` 命中资格关键词，
  否则不作为资格证据。
- 增加回归测试：`tests/integration/test_phase6_2028_qualification.py`。

## 7. 数据口径纪律（全站统一）

- 历史事实（2026/2027）单独展示，**不冒充 2028**；
- 2028 继续走 `StrictEvidenceGate`，年份不匹配即拒；
- 未知 ≠ 0：`None` 一律显示「暂无数据 / 待核验 / 证据不足 / 无法判断」；
- 不输出录取概率；证据不足不排名、不画排名图；
- 名额口径（目录计划 / 统考计划 / 实际录取）分列展示，不混用。
