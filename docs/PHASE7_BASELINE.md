# Phase 7.0 基线记录（执行前）

> 建立时间：2026-10-17，分支 `feature/phase6-decision-ui`，基线提交 `f4797d3eac1ebe67a4038bc5503d21628c526209`。

## 1. 远端 / 本地一致性
- 本地 HEAD：`f4797d3eac1ebe67a4038bc5503d21628c526209`（与远端、PR #1 head 一致，已于上一阶段核验）。
- 工作区：干净（无未提交修改）。
- 后续改动将通过本阶段提交追加到该分支并推送，远端 HEAD 将更新。

## 2. 工作区与敏感文件
- `data/decision.db`、`data/decision_system.db`、`data/web_public_snapshot.db`、`data/backup/`、`reports/xlsx_*.json`、`__pycache__/`、`egg-info/`、`.pytest_cache/` 均被 `.gitignore` 排除。
- 本阶段对生产库的**唯一**数据改动：修正两条 `claim_path_link`（claim 50/51 本就各只关联一个方向，脚本为空操作，零风险）。

## 3. 架构与关键文件（已读）
- 资格判定：`src/decision_system/services/decision_service.py`（`explain_2028_qualification` / `_evaluate_claim_for_qualification`，Phase 6.1 七条件重写版）。
- 展示模型：`src/decision_system/ui/viewmodels.py`（`grade_claim`、A/B/C/D）。
- 只读服务：`src/decision_system/services/view_service.py`（`build_research_dossier` / `build_evidence_summary`）。
- 引擎：`engine/weights.py`、`engine/scenarios.py`、`engine/objectives.py`、`engine/pipeline.py`（保持兼容，本阶段不改其数值内核）。
- 审计基准：`docs/V4_MODEL_SEMANTIC_AUDIT.md`（A-01~A-13）。

## 4. 现有测试
- 单元 `tests/unit/`（weights / evidence_gate / coverage / constraints / objectives / pipeline / phase6_viewmodels）。
- 集成 `tests/integration/`（import / decision_service / weight_service / evidence_service / profile_service / phase5_0 / phase6_2028）。
- UI `tests/ui/`（streamlit_app / phase5_0 / phase6 / phase6_1）。
- 本阶段新增：`tests/unit/test_phase7_models.py`、`tests/integration/test_phase7_qualification.py`。

## 5. 数据库与研究资料现状（已核验）
- 学校 5 所：BUPT / UESTC / SEU / HFUT / SWJTU；路径 10 条（北邮含方向01、方向02 两条）。
- 已核验来源 2 个（均为 2027 北邮官方：招生目录、初试科目调整公告）；待核验官方网页 1 个；未登记来源 84 个（占位）。
- 已核验声明 6 条（id 49–54，全部适用 2027，关联北邮 085410 方向01/02）；候选映射 48 条；待核验 2 条。
- `admission_record` 为空（无结构化名额）；`score_record` 180 条全部"未知"。
- Phase 2A/2B/2C/2D 原始独立文件在工作区不存在（与 Phase 6.1 库存一致）；可用真实资料仅为上述北邮 2027 官方快照。

## 6. 本阶段目标（节选自任务书）
P1 资格判定修复 → P2 A/B/C/D 与档案污染 → P3 V4.0 四层决策模型 → P4 研究资料整合 → P5 五校案例 → P6 UI 实用化 → P7 严格测试 → P8 文档与提交推送。验收以六项决策问题（Q1–Q6）为准，不以页面/代码/测试数量为准。
