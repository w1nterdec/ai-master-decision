# Phase 4.1 数据库兼容性说明

结论：**Phase 4.1 未修改任何既有表结构，未迁移/删除任何既有数据，Phase 4.0 的 24 张表全部保持兼容。**

## 1. 结构层面

- 表数量：Phase 4.0 = 24 张；Phase 4.1 = **24 张**（未新增、未删除、未改列）。
- ORM 实体文件 `src/decision_system/models/entities.py` 在 Phase 4.1 **零改动**。
- 枚举文件 `models/enums.py` 在 Phase 4.1 **零改动**（不改变落库字面量）。
- 因此 `sqlalchemy` 的 `Base.metadata.create_all()` 对既有库是幂等的：已有表不会被重建。

## 2. 数据层面

Phase 4.1 只是新增了**写入通道**，不修改既有行：

| 可能被写入的表 | 写入来源 | 对既有数据的影响 |
|---|---|---|
| `evidence_source` | 用户在【证据管理】登记新来源 | 仅 INSERT 新行；既有 84 行不被修改（`register_source_strict` 遇重复 source_id 直接拒绝，不做 upsert） |
| `evidence_claim` | 用户登记事实声明 | 仅 INSERT；既有 48 行不变 |
| `claim_path_link` / `claim_indicator_link` | 证据关联 | 仅 INSERT（唯一约束已存在则复用） |
| `claim_conflict` | 标记冲突 | 仅 INSERT；被标记声明改为「来源冲突」状态，**旧事实不被覆盖** |
| `audit_log` | 所有写操作 | 仅 INSERT；审计只增不改 |
| `weight_profile` / `weight_node` | 派生用户配置、调整权重、恢复默认 | 可 INSERT 新配置版本；演示配置 `phase37c_demo` 在「派生」与「恢复」流程中**不被改动** |
| `score_record` | — | **Phase 4.1 不写入评分**（页面无评分录入入口，保持 180 格全空） |
| `admission_record` / `mentor` / `research_resource` | — | **不写入**（无自动补数据） |

## 3. 与 Excel 导入的相互影响

- 导入器 `importers/excel_importer.py` 未改动，按 `batch_key = sha256(file)[:16]@profile_code` 与实体自然键幂等。
- 若用户手工登记了与 Excel 中同名的 `source_id`，下次导入时该来源会被识别为「已存在」而跳过（不会覆盖用户填写的本体信息）。
- 反过来，重新导入 Excel **不会**覆盖用户在界面上的核验结论（`verification_status` 不由导入器提升）。

## 4. 备份与回滚建议

- `data/decision.db` 为单文件 SQLite，直接复制即可备份。
- 回滚到 Phase 4.1 之前的状态：删除 Phase 4.1 期间新增的行（`audit_log` 中以 `source.register` /
  `claim.register` / `profile.*` 等动作标识）即可，结构无需回滚。
- 如需完全重建：`python scripts/import_excel.py` 会在空库上重建全部基础数据（幂等，可重复执行）。

## 5. 已验证

- 正式库 `data/decision.db` 在全部 149 项测试执行前后记录数一致（24 表；school=5、admission_path=10、
  evidence_source=84、evidence_claim=48、score_record=180、audit_log=44），**测试未污染正式库**。
- UI 测试通过环境变量 `DECISION_DB_PATH` 指向 `tmp_path` 临时库，不使用正式库。
