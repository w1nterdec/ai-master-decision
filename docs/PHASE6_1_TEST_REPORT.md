# Phase 6.1 测试报告（M9）

> 执行环境：Python 3.11.1 / streamlit 1.66.0 / SQLAlchemy 2.1.4 / pytest 9.0.2
> 分支：`feature/phase6-decision-ui`
> **本报告所有数字均为本次实际运行结果，不引用任何历史测试结论。**

---

## 1. 完整测试执行结果

```
$ python3.11 -m pytest
........................................................................ [ 26%]
........................................................................ [ 53%]
........................................................................ [ 79%]
.......................................................                  [100%]
271 passed in 142.79s (0:02:22)
```

| 阶段 | 结果 |
|---|---|
| Phase 6.1 M1 基线（本分支起点） | **225 passed in 113.86s** |
| Phase 6.1 M2 完成后 | **243 passed in 113.37s** |
| **Phase 6.1 M6/M7/M8 完成后（本次）** | **271 passed in 142.79s** |

新增 28 项（`tests/ui/test_phase6_1_decision_ui.py`），无失败、无跳过（生产库存在，端到端用例全部实跑）。

---

## 2. 新增测试明细（28 项）

### 2.1 M7｜历史研究信息 / 2028 正式评分双层分离

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 01 | `test_01_dossier_four_grades_rendered` | 页面同时出现 A/B/C/D 四类标签 | ✅ |
| 02 | `test_02_two_layers_are_separated` | 出现「第一层＝历史研究信息」「2028 正式资格与决策评分」「两层不合并」 | ✅ |
| 03 | `test_03_history_layer_readable_even_without_2028` | 2028 未确认时历史层仍可读（含 2027 事实） | ✅ |
| 04 | `test_04_dossier_d_grade_is_not_zero` | 出现「未知一律显示」「不补 0」 | ✅ |

### 2.2 M6｜重点研究学校由档案驱动

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 05 | `test_05_cockpit_does_not_presuppose_focus_school` | 未标记时驾驶舱不列任何学校为重点 | ✅ |
| 06 | `test_06_cockpit_focus_school_comes_from_archive` | 标记后才显示，且给出历史档案与待核验问题 | ✅ |
| 07 | `test_07_focus_block_has_no_banned_claims` | 重点区块无「最优目标/推荐报考/首选院校/上岸概率/排名第一」 | ✅ |
| 08 | `test_08_demo_weight_notice_on_main_pages`（4 参数） | 驾驶舱/探索/对比/风险四页均标注演示权重（**修复审计项 A-01**） | ✅ |

### 2.3 M6｜比较单位与风险页

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 09 | `test_09_compare_unit_is_admission_path` | 声明「比较单位是招生路径」「同一专业不同方向是独立的路径」 | ✅ |
| 10 | `test_10_risk_page_has_qualification_uncertainty` | 风险页出现「2028 资格不确定性」区块 | ✅ |

### 2.4 M6｜决策档案

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 11 | `test_11_archive_excluded_marker` | 「暂不考虑」标记可用并在档案页显示 | ✅ |
| 12 | `test_12_path_note_persists_across_restart` | 我的理由写盘后重新 load 仍在（跨重启） | ✅ |
| 13 | `test_13_archive_roundtrip_preserves_all_fields` | 候选/关注/暂不考虑/理由/备注全字段往返一致 | ✅ |
| 14 | `test_14_user_marker_does_not_change_evidence` | 用户标记前后证据计数、2028 资格、覆盖率**逐项相等** | ✅ |

### 2.5 M8｜安全与持久化

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 15 | `test_15_no_plaintext_credentials_in_source` | `src/`、`app.py`、`scripts/`、`pyproject.toml` 无硬编码口令 | ✅ |
| 16 | `test_16_web_auth_requires_env_credentials` | 对外 Web 凭据取自环境变量、缺省拒绝启动、常量时间比对 | ✅ |
| 17 | `test_17_archive_file_is_gitignored` | `data/decision_profile.json` 被 gitignore | ✅ |
| 18 | `test_18_production_db_is_gitignored` | `data/decision.db` 被 gitignore | ✅ |
| 19 | `test_19_model_page_weight_change_is_persisted` | 模型参数页改权重**真正落库**（修复 rerun→rollback） | ✅ |
| 20 | `test_20_no_st_rerun_left_in_pages` | 全部 `pages_*.py` 无残留 `st.rerun()` | ✅ |

### 2.6 M9｜真实数据端到端

| # | 用例 | 断言要点 | 结果 |
|---|---|---|---|
| 21 | `test_21_e2e_official_source_to_visible_fact` | 官方来源 `S-BUPT-2027-CATALOG-005`（已核验）→ 已核验声明 → P01（`exam_unit4=801 通信原理`）→ 页面可见 | ✅ |
| 22 | `test_22_e2e_history_fact_does_not_confirm_2028` | `explain_2028_qualification(P01, year=2028)` 返回 `False` 且给出理由 | ✅ |
| 23 | `test_23_e2e_directions_not_confused_in_dossier` | P01 档案含「801」「43」；P02 档案含「408」「89」；两者 A 类**不相同** | ✅ |
| 24 | `test_24_e2e_no_verified_2028_evidence_exists` | 生产库 6 条已核验声明**无一**标注 2028 | ✅ |
| 25 | `test_25_indicator_tree_still_5_10_18` | 指标树仍为 5/10/18，路径仍为 10 条（结构未改） | ✅ |

---

## 3. 端到端验证链路（实测）

```
官方来源 S-BUPT-2027-CATALOG-005（verification_status=已核验, applicable_years=[2027]）
   │
   ├─ 已核验声明 #49 #50 #52 #53   （#51 属于 P02）
   │
   ▼
招生路径 P01 = BUPT|005|085410|全日制|方向01|2028|统考|一志愿（exam_unit4=801 通信原理）
   │
   ▼
院校探索页：A 类事实可见 + 来源年份 2027 + 研究状态
   │
   ▼
2028 资格判定：explain_2028_qualification → False（理由：年份不匹配 / 无 2028 已核验证据）
```

**关键负向断言**：链路跑通**不等于** 2028 资格被确认。用例 22 与 24 分别验证了路径级与库级两个层面：

- 路径级：P01 的 2028 资格判定返回 `False`；
- 库级：6 条已核验证明声明的 `applicable_years` 全部为 `[2027]`，无一含 2028。

---

## 4. 移动端验证（390 × 844）

| 页面 | scrollWidth | clientWidth | 横向溢出 | JS 报错 |
|---|---:|---:|---:|---:|
| ① 决策驾驶舱 | 390 | 390 | **0 px** | 0 |
| ② 院校探索 | 390 | 390 | **0 px** | 0 |
| ③ 多校对比 | 390 | 390 | **0 px** | 0 |
| ⑤ 风险与路径规划 | 390 | 390 | **0 px** | 0 |
| ⑥ 我的决策档案 | 390 | 390 | **0 px** | 0 |

抓取方式：真实 Chromium + Playwright，`pageerror` 与 `console.error` 全程监听，**0 条**。
（侧边栏在移动端默认折叠，测试脚本先展开再切换页面，与真实用户操作一致。）

---

## 5. 生产库完整性

| 项 | 值 |
|---|---|
| 基线 MD5（`docs/PHASE6_1_BASELINE.md`） | `3ab1fa51d9bb54d66dd9f9e7f2565363` |
| **本次执行完整测试后 MD5** | `3ab1fa51d9bb54d66dd9f9e7f2565363` |
| 结论 | **完全一致，生产库未被任何测试写入** |

测试对生产库的使用方式是**复制到临时目录后只读使用**（`prod_db_path` fixture），遵循 M8「不得对生产库做破坏性测试」。

---

## 6. 本轮修复的两个真实缺陷（由测试暴露）

| # | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| **D-1** | 展示层常量 `VERIFIED = "已核实"` 与数据层枚举 `VERIFIED = "已核验"` 不一致，导致 `it.status == VERIFIED` 判定**恒为 False** | 已核验证据被全部误判为 B 类（待核验）；院校探索页「已核实的事实」区块**一直显示"暂无已核验声明"** —— 即使库里明明有 6 条已核实事实 | 新增 `VERIFIED_TEXTS = frozenset({"已核验","已核实"})`，三处判定改用集合；展示文案不变 |
| **D-2** | `pages_model.py` 在 `apply_weight_change`（仅 `flush`）之后调用 `st.rerun()`，抛出 `RerunException` 被 `db_session()` 的 `except` 捕获执行 `rollback` | 「高级功能 → 模型参数」页改权重：**提示"已保存"但改动被静默回滚** | 移除该 `st.rerun()`，依赖按钮点击自身的重跑；新增用例 19 验证落库 |

---

## 7. 未覆盖 / 已知限制（诚实记录）

| 项 | 说明 |
|---|---|
| 方向培养方案、导师名单 | 库内无材料，页面只能显示「未知」，测试也只能断言「不编造」 |
| 2028 目录 | 尚未发布，无可用真实数据；所有 2028 相关用例均为**负向断言**（不得确认） |
| 权重语义问题 A-02~A-13 | 已在 `docs/V4_MODEL_SEMANTIC_AUDIT.md` 登记，**本阶段按纪律未改算法**，故无对应修复测试 |
| 情景倍率改变用户偏好（A-04） | 已审计并记录，未修改引擎 |
| 生产库端到端用例 | 依赖本地 `data/decision.db`，该文件不入版本库；在其他环境缺失时相关用例会 **skip**（不伪造、不失败） |

---

## 8. 结论

1. **271 项全部通过**，无失败、无跳过，Phase 4.1 / 5.0 / 6.0 既有功能无回退。
2. 北邮案例的四级证据链（来源 → 声明 → 路径 → 页面）**端到端跑通**，且**未**因此使 2028 资格被误确认。
3. 方向01 / 方向02 在档案层与页面层均**未混淆**。
4. 未知值全程未被补零；无证据时不排名；无录取概率输出。
5. 移动端 5 个主页面零横向溢出、零 JS 报错。
6. 生产库 MD5 未变，未被测试污染。
7. 测试过程中暴露并修复了 2 个真实缺陷（D-1、D-2），二者都是**用户可见的错误行为**，不是理论问题。
