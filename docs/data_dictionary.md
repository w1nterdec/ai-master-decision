# 数据字典（Phase 4.0）

## 1. 核心概念定义

| 概念 | 定义 |
|---|---|
| School | 学校。唯一键 `code`（既定代号映射，如 BUPT / UESTC / SEU / HFUT / SWJTU）。 |
| College | 学院。唯一键 `(school_id, college_code)`。 |
| Program | 专业。唯一键 `(college_id, program_code)` —— 同一专业代码可在多个学院存在。 |
| AdmissionPath | 一条可决策的招生路径。**唯一键 `path_key`**，不使用「学校+专业代码」。 |
| AdmissionYear | 招生年度。`catalog_published=False` 表示该年度目录未发布/未核验。 |
| AdmissionRecord | 招生记录。`quota_basis` 区分「目录计划 / 复试统考计划 / 实际录取」；`admission_method` 区分统考/推免/专项计划/调剂。 |
| ResearchResource | 研究资源（平台、实验室、校企合作）。附 `accessibility`（P1–P4）与来源声明。 |
| Mentor | 导师。附研究方向与来源声明。 |
| EvidenceSource | 来源登记。`verification_status` 决定是否可进入正式评分。 |
| EvidenceClaim | 事实声明：`来源 → 支持的（路径 / 指标）事实`。 |
| Indicator | 指标树节点，`level` ∈ {1,2,3}，`code` 形如 `L3-职业发展\|AI工程就业\|岗位与实习机会`。 |
| WeightProfile | 权重配置。`is_demo=True` 表示演示配置。 |
| WeightNode | 权重节点，`raw_weight` 为**组内相对权重**。 |
| Scenario | 情景定义。 |
| ScenarioMultiplier | 情景倍率，`target_code` 可为一级或三级指标代码。 |
| ScoreRecord | （路径 × 指标 × 评价年份）评分。`raw_score=None` 表示未知。 |
| DecisionResult | 决策输出快照（JSON）。**无录取概率字段**。 |
| AuditLog | 审计日志。 |

## 2. `path_key` 结构

```
path_key = 学校码|学院码|专业码|学习方式|方向|招生年份|招生方式|路径角色
示例：BUPT|005|085410|全日制|方向01|2028|统考|一志愿
```

由 `services/path_identity.build_path_key()` 唯一生成，禁止在其它位置重复实现。

## 3. 枚举取值

| 枚举 | 取值 |
|---|---|
| VerificationStatus | 已核验 / 待核验 / 来源冲突 / 已失效 / 无法核验 / 未登记 |
| ClaimStatus | 已核验 / 候选映射 / 待核验 / 来源冲突 / 已失效 |
| SourceType | 官方招生目录 / 官方公告 / 官方网页 / PDF原件 / 就业质量报告 / 研究报告 / 访谈宣讲 / 媒体报道 / 未知 |
| EvidenceLevel | S1 / S2 / S3 / S4 / 未知 |
| Accessibility | P1 / P2 / P3 / P4 / 不适用 |
| StudyMode | 全日制 / 非全日制 / 待核 |
| AdmissionMethod | 统考 / 推免 / 专项计划 / 调剂 / 未知 |
| PathKind | 一志愿 / 调剂 / 直接就业 / 未分类 |
| TriState | 是 / 否 / 待确认 |
| PathEligibility | 排除 / 候选 / 待核验 |
| Qualification2028 | 2028正式资格已确认 / 2028资格未确认 / 未满足 |
| Verification2028 | 已核验2028 / 待2028核验 / 未知 |
| ScoreValidity | 有效 / 无效 / 未知 |
| ComparisonStatus | 可比较（非录取预测） / 证据不足 / 硬约束不符-排除 / 硬约束待确认-不可比较 |
| ObjectiveStatus | 可输出 / 待补充证据 / 暂无法判断 / 待核验 / 已排除 / 不适用 |

## 4. 评分锚点（沿用 Phase 3.x，供人工填分时参考）

| 分值 | 证据要求 | 注意 |
|---|---|---|
| 1 | 官方明确不利证据 | 不是信息缺失 |
| 2 | 可追溯的明显短板 | 必须列来源 |
| 3 | 可追溯的中性或混合证据 | 不能用作默认分 |
| 4 | 可靠的正向证据 | 区分学院与专业 |
| 5 | 直接、强且可进入的证据 | 需高强度官方支持 |
| 空白 | 未知/缺失 | 不参与分数计算 |
| 不适用 | 该路径无此维度 | 不可写 0 |

## 5. 导入结果字段说明

| 报告字段 | 含义 |
|---|---|
| `inserted` | 本次实际新增记录数（按实体类型） |
| `skipped` | 因已存在而跳过的记录数（幂等） |
| `pending_verification` | 待核验计数累加（未登记来源、未核验 2028、待确认硬约束、空评分等） |
| `conflicts` | 冲突登记数量 |
| `unregistered_source_count` | 被候选映射引用但来源本体未登记的 source_id 数量 |
| `open_questions` | 从「待核问题」表导入的未闭合问题数 |
| `anomalies` | 数据异常清单（缺字段、非数值、无法匹配等） |

<!-- AUTO_SCHEMA -->

## 数据库表结构（自动生成）

| 表名 | 用途 | 字段 |
|---|---|---|
| `admission_year` | 招生年度维度（目录是否已发布）<br>**唯一约束**: year | `id` INTEGER PK<br>`year` INTEGER NOT NULL<br>`catalog_published` BOOLEAN NOT NULL<br>`note` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `audit_log` | 审计日志 | `id` INTEGER PK<br>`at` DATETIME NOT NULL<br>`actor` VARCHAR(64) NOT NULL<br>`action` VARCHAR(128) NOT NULL<br>`entity_type` VARCHAR(64)<br>`entity_id` VARCHAR(64)<br>`detail` JSON |
| `evidence_source` | 证据来源登记（核验状态决定是否可进入评分）<br>**唯一约束**: source_id | `id` INTEGER PK<br>`source_id` VARCHAR(128) NOT NULL<br>`title` VARCHAR(512) NOT NULL<br>`publisher` VARCHAR(255)<br>`url_or_file` TEXT<br>`source_type` VARCHAR(64) NOT NULL<br>`published_at` DATE<br>`applicable_years` JSON<br>`retrieved_at` DATETIME<br>`verification_status` VARCHAR(64) NOT NULL<br>`verification_note` TEXT<br>`is_placeholder` BOOLEAN NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `import_batch` | 导入批次（幂等控制与报告留痕）<br>**唯一约束**: batch_key | `id` INTEGER PK<br>`batch_key` VARCHAR(128) NOT NULL<br>`source_file` VARCHAR(512) NOT NULL<br>`file_sha256` VARCHAR(128) NOT NULL<br>`imported_at` DATETIME NOT NULL<br>`report` JSON |
| `indicator` | 三级指标树节点（level=1/2/3）<br>**唯一约束**: code | `id` INTEGER PK<br>`code` VARCHAR(64) NOT NULL<br>`level` INTEGER NOT NULL<br>`name` VARCHAR(128) NOT NULL<br>`parent_code` VARCHAR(64)<br>`sort_order` INTEGER NOT NULL<br>`scoring_anchor` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `scenario` | 情景定义（职业/报考/科研优先）<br>**唯一约束**: code | `id` INTEGER PK<br>`code` VARCHAR(64) NOT NULL<br>`name` VARCHAR(128) NOT NULL<br>`is_demo` BOOLEAN NOT NULL<br>`description` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `school` | 学校<br>**唯一约束**: code | `id` INTEGER PK<br>`code` VARCHAR(64) NOT NULL<br>`name` VARCHAR(128) NOT NULL<br>`city` VARCHAR(64)<br>`province` VARCHAR(64)<br>`region` VARCHAR(64)<br>`note` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `weight_profile` | 权重配置（is_demo 标记演示配置）<br>**唯一约束**: code | `id` INTEGER PK<br>`code` VARCHAR(64) NOT NULL<br>`name` VARCHAR(128) NOT NULL<br>`is_demo` BOOLEAN NOT NULL<br>`description` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `college` | 学院（学校一对多）<br>**唯一约束**: school_id, college_code | `id` INTEGER PK<br>`school_id` INTEGER FK NOT NULL<br>`college_code` VARCHAR(32) NOT NULL<br>`name` VARCHAR(128)<br>`campus` VARCHAR(128)<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `evidence_claim` | 事实声明（来源支持的具体事实） | `id` INTEGER PK<br>`source_id_fk` INTEGER FK NOT NULL<br>`source_ref_id` VARCHAR(128) NOT NULL<br>`statement` TEXT NOT NULL<br>`topic` VARCHAR(128)<br>`stage` VARCHAR(64)<br>`school_code` VARCHAR(64)<br>`college_code` VARCHAR(32)<br>`program_code` VARCHAR(32)<br>`applicable_years` JSON<br>`evidence_level` VARCHAR(64) NOT NULL<br>`accessibility` VARCHAR(64) NOT NULL<br>`status` VARCHAR(64) NOT NULL<br>`is_candidate` BOOLEAN NOT NULL<br>`match_limitation` TEXT<br>`raw_row` JSON<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `scenario_multiplier` | 情景倍率（作用于一级或三级指标）<br>**唯一约束**: scenario_id, target_code | `id` INTEGER PK<br>`scenario_id` INTEGER FK NOT NULL<br>`target_code` VARCHAR(64) NOT NULL<br>`multiplier` FLOAT NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `weight_node` | 权重节点（组内相对权重）<br>**唯一约束**: profile_id, indicator_id | `id` INTEGER PK<br>`profile_id` INTEGER FK NOT NULL<br>`indicator_id` INTEGER FK NOT NULL<br>`level` INTEGER NOT NULL<br>`raw_weight` FLOAT NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `claim_conflict` | 来源冲突登记（保留冲突，不自动合并） | `id` INTEGER PK<br>`claim_id` INTEGER FK NOT NULL<br>`conflicting_claim_id` INTEGER FK<br>`description` TEXT NOT NULL<br>`detected_at` DATETIME NOT NULL<br>`resolved` BOOLEAN NOT NULL<br>`resolution_note` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `claim_indicator_link` | 事实声明 ↔ 指标 关联（是否支持该指标）<br>**唯一约束**: claim_id, indicator_id | `id` INTEGER PK<br>`claim_id` INTEGER FK NOT NULL<br>`indicator_id` INTEGER FK NOT NULL<br>`supports` BOOLEAN NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `mentor` | 导师 | `id` INTEGER PK<br>`college_id` INTEGER FK<br>`name` VARCHAR(64) NOT NULL<br>`research_direction` TEXT<br>`evidence_claim_id` INTEGER FK<br>`verification_status` VARCHAR(64) NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `program` | 专业（同一专业代码可在多个学院存在）<br>**唯一约束**: college_id, program_code | `id` INTEGER PK<br>`college_id` INTEGER FK NOT NULL<br>`program_code` VARCHAR(32) NOT NULL<br>`name` VARCHAR(128)<br>`degree_type` VARCHAR(32)<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `research_resource` | 研究资源（平台/实验室/校企合作） | `id` INTEGER PK<br>`college_id` INTEGER FK<br>`name` VARCHAR(255) NOT NULL<br>`category` VARCHAR(128)<br>`accessibility` VARCHAR(64) NOT NULL<br>`statement` TEXT<br>`evidence_claim_id` INTEGER FK<br>`verification_status` VARCHAR(64) NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `admission_path` | 招生路径（决策对象，path_key 唯一）<br>**唯一约束**: path_key | `id` INTEGER PK<br>`path_key` VARCHAR(255) NOT NULL<br>`legacy_path_id` VARCHAR(32)<br>`school_id` INTEGER FK NOT NULL<br>`college_id` INTEGER FK NOT NULL<br>`program_id` INTEGER FK NOT NULL<br>`admission_year` INTEGER NOT NULL<br>`study_mode` VARCHAR(64) NOT NULL<br>`admission_method` VARCHAR(64) NOT NULL<br>`path_kind` VARCHAR(64) NOT NULL<br>`direction` VARCHAR(128)<br>`exam_unit4` VARCHAR(128)<br>`training_location` VARCHAR(128)<br>`full_time_ok` VARCHAR(64) NOT NULL<br>`program_code_acceptable` VARCHAR(64) NOT NULL<br>`other_constraints_ok` VARCHAR(64) NOT NULL<br>`verification_2028` VARCHAR(64) NOT NULL<br>`key_risk` TEXT<br>`notes` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `admission_record` | 招生计划/实际录取记录（计划数与实际录取数分离）<br>**唯一约束**: path_id, year, admission_method, quota_basis | `id` INTEGER PK<br>`path_id` INTEGER FK NOT NULL<br>`year` INTEGER NOT NULL<br>`admission_method` VARCHAR(64) NOT NULL<br>`quota_basis` VARCHAR(64) NOT NULL<br>`planned_quota` INTEGER<br>`actual_admitted` INTEGER<br>`note` TEXT<br>`evidence_claim_id` INTEGER FK<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `claim_path_link` | 事实声明 ↔ 招生路径 关联<br>**唯一约束**: claim_id, path_id | `id` INTEGER PK<br>`claim_id` INTEGER FK NOT NULL<br>`path_id` INTEGER FK NOT NULL<br>`applicable` BOOLEAN NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `decision_result` | 决策输出快照（JSON） | `id` INTEGER PK<br>`path_id` INTEGER FK NOT NULL<br>`profile_code` VARCHAR(64) NOT NULL<br>`evaluation_year` INTEGER NOT NULL<br>`computed_at` DATETIME NOT NULL<br>`payload` JSON NOT NULL<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `hard_constraint_evaluation` | 硬约束评估留痕 | `id` INTEGER PK<br>`path_id` INTEGER FK NOT NULL<br>`evaluated_at` DATETIME NOT NULL<br>`eligibility` VARCHAR(64) NOT NULL<br>`qualification_2028` VARCHAR(64) NOT NULL<br>`reasons` JSON<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `resource_path_link` | 研究资源 ↔ 招生路径 的证据化关联<br>**唯一约束**: resource_id, path_id, claim_id | `id` INTEGER PK<br>`resource_id` INTEGER FK NOT NULL<br>`path_id` INTEGER FK NOT NULL<br>`claim_id` INTEGER FK<br>`accessible` BOOLEAN NOT NULL<br>`note` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
| `score_record` | （路径 × 指标）评分记录<br>**唯一约束**: path_id, indicator_id, evaluation_year | `id` INTEGER PK<br>`path_id` INTEGER FK NOT NULL<br>`indicator_id` INTEGER FK NOT NULL<br>`evaluation_year` INTEGER NOT NULL<br>`raw_score` INTEGER<br>`source_ref_id` VARCHAR(128)<br>`claim_id` INTEGER FK<br>`fact_type` VARCHAR(32)<br>`validity` VARCHAR(64) NOT NULL<br>`rejection_reasons` JSON<br>`note` TEXT<br>`created_at` DATETIME NOT NULL<br>`updated_at` DATETIME NOT NULL |
