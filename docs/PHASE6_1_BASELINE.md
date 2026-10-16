# Phase 6.1｜开发基线

采集时间：2026-10-16　|　采集人：本轮开发会话（**全部为本次实际执行结果，未引用历史报告**）

---

## 1. 版本与分支

| 项 | 值 |
|---|---|
| 仓库 | `w1nterdec/ai-master-decision`（**Private**，default_branch = `main`） |
| 当前分支 | `feature/phase6-decision-ui` |
| 分支 HEAD | `d7d9480` feat(phase6): 决策产品化重构 |
| 基线来源 | `cc30730`（Phase 5.2 归档提交） |
| 工作区 | 干净（`git status` 无输出） |
| PR | **#1 open，未合并**，head=`feature/phase6-decision-ui`，base=`main`，1 commit，19 files，+3185 / −33 |
| Python | 3.11.1 |
| 关键依赖 | streamlit 1.66.0 / SQLAlchemy 2.1.4 / pandas 3.0.0 / pytest 9.0.2 |

## 2. 本次测试实际结果（M1 起点）

```
$ python3 -m pytest
225 passed in 113.86s (0:01:53)
```

测试文件分布（`--collect-only`，本次实际统计）：

| 目录 | 用例数 |
|---|---|
| tests/unit | 87 |
| tests/integration | 45 |
| tests/ui | 93 |
| **合计** | **225** |

> 说明：本数字为**本轮 M1 实际运行**结果，非引用 Phase 6.0 报告。

## 3. 数据库状态（生产库 `data/decision.db`）

MD5：`3ab1fa51d9bb54d66dd9f9e7f2565363`
副本 `data/web_public_snapshot.db` 同 MD5（**本阶段未做任何写入**）

| 表 | 行数 | 说明 |
|---|---:|---|
| school | 5 | BUPT / UESTC / SEU / HFUT / SWJTU |
| college | 9 | |
| program | 9 | |
| admission_path | 10 | P01–P10，全部 `admission_year=2028`、`path_kind=一志愿` |
| indicator | 33 | 一级 5 / 二级 10 / 三级 18 |
| weight_profile | 1 | `phase37c_demo`，**is_demo=True** |
| weight_node | 33 | |
| scenario | 3 | career / admission / research，全部 is_demo=True |
| scenario_multiplier | 15 | |
| evidence_source | 87 | 已核验 2 / 待核验 1 / **未登记 84** |
| evidence_claim | 56 | 已核验 6 / 待核验 2 / **候选映射 48** |
| claim_path_link | 71 | |
| claim_indicator_link | 193 | |
| claim_conflict | 0 | 当前无冲突登记 |
| score_record | 180 | **全部 `validity=未知`，有效评分 0** |
| admission_record | 0 | 三种名额口径均无记录 |
| mentor | 0 | |
| research_resource | 0 | |
| decision_result | 0 | |
| hard_constraint_evaluation | 0 | |
| audit_log | 100 | |

### 3.1 已核验来源（仅 2 个，均为 2027）

| id | source_id | 标题 | 类型 | 发布 | 适用年份 |
|---|---|---|---|---|---|
| 85 | `S-BUPT-2027-CATALOG-005` | 2027年人工智能学院硕士专业目录（北邮研招网） | 官方招生目录 | 2026-10-04 | **[2027]** |
| 86 | `S-BUPT-2027-EXAMADJ` | 北邮 2027 年硕士研究生招生考试初试科目调整公告 | 官方公告 | 2026-06-09 | **[2027]** |

### 3.2 已核验声明（仅 6 条，全部适用 2027）

| id | 来源 | topic | 适用年份 | 路径关联 |
|---|---|---|---|---|
| 49 | 85 | 招生名额（目录计划口径） | 2027 | P01、P02 |
| 50 | 85 | 方向01 考试科目与名额 | 2027 | **P01** |
| 51 | 85 | 方向02 考试科目与名额 | 2027 | **P02** |
| 52 | 85 | 名额口径（含推免原注） | 2027 | P01、P02 |
| 53 | 85 | 导师信息可得性 | 2027 | P01、P02 |
| 54 | 86 | 初试科目调整（2027） | 2027 | P01、P02 |

指标关联（`supports=1` 才算支持）：

| 声明 | 关联指标 |
|---|---|
| 49 | 全日制统考路径明确性、名额口径可靠性 |
| 50 | 全日制统考路径明确性、名额口径可靠性、初复试科目稳定性 |
| 51 | 全日制统考路径明确性、名额口径可靠性、初复试科目稳定性 |
| 52 | 名额口径可靠性 |
| 53 | 导师招生路径证据（**supports=0**） |
| 54 | 初复试科目稳定性 |

**关键结论**：当前库内**不存在任何适用 2028 的已核验证据**，
因此 2028 招生资格必须全部为「未确认」——这是正确结果，不是故障。

## 4. 已知待修问题（本阶段要处理）

| # | 问题 | 位置 |
|---|---|---|
| 1 | 资格判定仍依赖文本关键词（招生目录/招生名额/全日制/统考），可被无关声明触发 | `decision_service._claim_supports_qualification` |
| 2 | 资格判定**未校验证据适用范围**（学校/学院/专业/学习方式/方向） | `decision_service._has_verified_2028_evidence` |
| 3 | 资格判定**未校验方向粒度**（专业级声明会同时"证明"方向01与方向02） | 同上 |
| 4 | 资格判定**未校验未解决冲突** | 同上 |
| 5 | V4.0 五维仅做展示映射，未审计计算语义一致性 | `ui/viewmodels.py`、`engine/*` |
| 6 | 历史（2026/2027）资料未转化为可阅读的院校优劣 | 展示层 |
| 7 | 用户无法在未设置权重前理解"北邮为什么值得考虑" | 页面层 |

## 5. 本阶段硬约束

- 不新增学校、不新增 Agent、不大规模爬取、不重设计数据库；
- 不擅自重写决策算法（`engine/` 只审计不改）；
- 不伪造评分、不编造录取概率/报录比；
- 生产库禁止破坏性写入（本阶段只读 + 仅在临时库写）。
