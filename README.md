# AI 硕士证据化择校决策工作台

面向 AI、LLM、Agent、具身智能相关硕士的择校研究：检索材料、比较具体招生路径、记录个人条件和判断，再核对结论依据与缺口。

**本项目是证据化择校决策系统，不是自动抓取官网数据的择校搜索引擎。** 不输出录取概率；没有自动“冲稳保”算法。人工备考分层只是用户自己的假设，不代表保证录取。

## 适用人群与技术栈

适合愿意核对来源、比较学校/学院/专业/方向、希望保留判断过程的考生或个人研究者。当前规则与历史报告源于“2028 年、只考一次、AI 方向”的原始案例，并不是适用于所有考生的通用政策。

Python 3.11+、Streamlit、SQLAlchemy、Pydantic、SQLite、pandas、openpyxl；启动器用 python-dotenv 读取可选配置。开发检查用 pytest 与 Ruff。无需 API Key。

## 5 分钟快速开始

在仓库根目录执行。首次依赖下载耗时取决于网络。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe scripts/start.py --demo
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/start.py --demo
```

打开 <http://127.0.0.1:8501>，展开“新手入门与功能状态”。先看研究资料库，再到我的决策档案填写条件。停止服务按 Ctrl+C。

`--demo` 从已入库原件初始化 **5 校、10 条路径、207 条逐路径研究映射**，默认写入 `data/demo/` 的独立数据库和档案，不需要自己找 Excel，也不会改动默认个人档案。它是历史研究演示，启动后 2028 资格未确认、没有有效评分是预期状态。重复启动不会清空数据。

端口占用用 `--port 8503`；只准备数据用 `--prepare-only`。使用默认工作空间则执行 `python scripts/start.py`，不要加 `--demo`。

## 配置与数据准备

没有必须手填的环境变量。可复制 `.env.example` 为 `.env` 后编辑，**只有 `scripts/start.py` 自动读取 `.env`**；真实进程环境变量优先，命令行端口/地址优先于环境变量。

- `DECISION_DB_PATH`：本地 SQLite 文件，默认 `data/decision.db`，不是 PostgreSQL URL。
- `DECISION_ARCHIVE_PATH`：个人档案 JSON，默认 `data/decision_profile.json`。
- `STREAMLIT_SERVER_ADDRESS` / `STREAMLIT_SERVER_PORT`：默认 `127.0.0.1` / `8501`。
- `--demo` 覆盖上述数据库和档案路径，默认使用 `data/demo/`。

直接运行 `streamlit run app.py` 时，需要先执行 `python scripts/bootstrap.py`；该初始化脚本不自动读取 `.env`，可显式传 `--db`。研究资料库和结果总览只读 JSON，其余页面需要数据库。

原始研究在 `data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx`；JSON 是它的完整投影。更新原件后运行 `python scripts/bootstrap.py` 和 `python scripts/check_data.py`。新增院校/路径须编辑 Excel 后导入，网页的“数据维护”目前只读。不要手改派生 JSON。

207 条是逐路径映射，不是 207 个独立官方来源。来源编号、表名、行号和适用限制可回查；来源层级 S1–S4 不等于已核验。资料不会自动联网更新。

## 一次完整的使用流程

1. **录入个人条件**：在“我的决策档案”填写本科专业、目标方向、城市、可接受专业代码、预算与限制。保存后进入个人 JSON 和 Markdown 导出。这些条件目前只作上下文，不自动改写引擎硬约束或原案例政策。
2. **找研究对象**：在院校探索筛选具体路径，查看原文、资格、考试科目及风险，加入候选/关注或对比。比较单位包含学院与方向。
3. **录入学校证据**：高级功能 → 证据管理 → 来源登记，填写机构、原文 URL/文件标识、适用年份；在证据关联页登记声明，关联具体路径和指标；在人工核验页核对原件并记录依据、操作者。登记来源不会自动核验声明。
4. **设置偏好**：动态决策树中从当前配置派生用户版本，在“当前偏好配置”切换，调整并明确确认。高级功能的模型参数也可管理版本。三级权重是由大类到细项的相对重视程度；情景只改变重视程度，不改变事实。
5. **看懂结果**：院校探索展开“看懂当前结论：依据、缺口与风险”；驾驶舱查看关注路径的四层解释。低覆盖率、未确认资格、来源冲突都可能阻断判断；缺失项不补零，默认覆盖率门槛仍为 80%。
6. **记录冲稳保**：在档案选择路径、人工选择冲/稳/保，并填写理由与待核验前提。没有理由不能保存。“保”只是个人备考标签。系统目前不能从个人成绩、复试线等自动生成该分层，也不能替你证明风险可控。

评分录入尚无独立网页表单，补齐来源本身不等于补齐有效评分；自动量化输出取决于完整输入与严格闸门。当前原件不足以产生正式自动推荐。详细操作与术语见 [新手指南](docs/GETTING_STARTED.md)。

## 9 个导航入口与完成状态

实际为 **8 个业务页面 + 1 个高级功能入口**，不是 9 个独立算法。

1. **决策驾驶舱｜可用**：总体状态、缺口、关注路径和四层解释。
2. **院校探索｜可用**：筛选、资料、资格、解释、候选/关注与加入对比。
3. **多校对比｜可用**：最多四条路径的事实、主题原文、覆盖率及研究导出。
4. **动态决策树｜可用**：权重树、偏好版本、零权重提示、情景与修改审计。
5. **风险与路径规划｜部分可用**：缺口与准备事项可用；R7 调剂推荐算法、直接就业评分尚未实现。
6. **我的决策档案｜可用**：个人条件、人工冲稳保、理由、标记及 Markdown 导出。
7. **择校结果总览｜历史人工意见**：展示原案例研究分组与分析，不会根据新用户条件自动重算。
8. **研究资料库｜可用**：全文检索、学校/路径/主题/层级筛选、CSV 和原件下载。
9. **高级功能｜管理入口**：含下面五个子页。

高级功能：**证据管理**提供登记、关联、人工核验与缺口；**数据维护·招生路径**只读查看；**模型参数**管理权重与版本；**决策分析**查看引擎输出和缺失项；**系统状态**显示在库统计。无网页路径编辑器和独立评分录入表单。

手机与桌面共用以上功能；窄屏默认完整字段卡片，“阅读设置”可切回可搜索、排序、下载的交互表格。

## Docker / Compose

```bash
docker compose config --quiet
docker compose up --build -d
```

默认本机 <http://127.0.0.1:8501>，宿主机端口可用 `.env` 的 `STREAMLIT_SERVER_PORT` 改动，容器内仍为 8501。非 root 运行，启动前幂等初始化；`decision-state` 卷保存 SQLite 和档案。`docker compose down` 保留数据；`down -v` 会删除卷中状态。

容器声明依赖、原件、JSON、主题、启动命令和健康检查齐全。CI 同时检查 HTTP 健康与容器内真实页面渲染，健康接口正常本身不代表全部页面正常。Docker daemon 需要运行。数据不会同步到另一台独立实例。

需要电脑关机后手机仍可访问，可按 [持续服务器部署指南](docs/SERVER_DEPLOYMENT.md) 使用云服务器和域名。新增 `compose.server.yaml` 与 `deploy/Caddyfile` 提供 HTTPS、入口密码、数据持久化和自动重启；先复制 `deploy/server.env.example` 为服务器的 `.env` 并填写域名和密码哈希。该配置单独使用，只公开 80/443，不公开应用端口；所有获准访问者仍共用一份档案。

## 目录结构

```text
app.py                       应用入口
src/decision_system/
  engine/                    核心规则与计算，本轮不改
  evidence/                  来源与声明治理
  services/                  导入、查询与持久化服务
  ui/                        页面、档案模型与共享跨端组件
scripts/start.py             一条命令准备与启动
scripts/bootstrap.py         幂等导入、历史证据迁移、JSON 投影
scripts/check_data.py        原件与 JSON 一致性
scripts/check_secrets.py     可入库文本的敏感模式检查
scripts/smoke_app.py         9 个入口与 5 个管理页渲染检查
data/raw/                    已入库历史原件
data/demo/                   独立演示状态，不入库
docs/                        规则、指南、研究报告和工程说明
tests/                       单元、集成、黄金与 UI 回归
```

## 验证

```bash
python -m pip install -e ".[dev]"
python scripts/start.py --demo --prepare-only
python scripts/check_data.py
python scripts/check_secrets.py
python -m ruff check .
python -m pytest
```

测试使用临时数据库和档案。`python scripts/smoke_app.py` 可另行验证当前配置下所有页面；从 `.env` 启动的服务与独立烟测进程的环境需保持一致。CI 覆盖 Linux/Python 3.11、Windows/Python 3.12 和 Docker。

## 已知限制与后续规划

- 仍为五校历史快照；2028 正式资格需对应官方资料核验，不是实时招生状态。
- 原始案例背景和全局政策仍影响既有解释；个人条件录入未自动接入约束计算。用户版本与“已确认偏好”目前也没有独立审批状态。
- 量化评分、结构化导师/资源/名额未完整补齐；无独立网页评分录入。R7 和自动冲稳保明确未完成。
- 单实例对应个人档案，没有多用户身份、权限隔离、并发档案合并。SQLite 可用于个人、低频写入；多人同时写入或跨实例服务应考虑 PostgreSQL，同时迁移档案存储和身份体系，不能只换连接串。
- 原创代码与原创文档采用 [MIT](LICENSE)；第三方原文、研究汇编中的外部内容、截图引用保留原权利，详见 [NOTICE](NOTICE) 和 [资料使用边界](data/README.md)。没有对研究数据授予统一开放许可。

后续依次推进：评分录入闭环与独立偏好确认 → 可配置个人硬约束 → 经验证的分层规则及 R7 → 账户隔离、数据库迁移与部署运维。完整风险、敏感检查范围和协议建议见 [工程说明](docs/ENGINEERING_NOTES.md)。

核心规范：[决策规则](docs/decision_rules.md)。历史背景：[产品审查](docs/PRODUCT_REVIEW.md)、[原案例研究结论](docs/2028_AI_MASTER_DECISION_REPORT.md)。

## 公开发布、隐私与贡献

默认背景已泛化为示例，不代表当前使用者。个人档案和配置不应提交；已公开历史中的作者邮箱及原案例内容不会因当前版本更新而撤回，见 [隐私说明](PRIVACY.md)。发布前可运行 `python scripts/check_secrets.py --history`，覆盖版本化文本和分支/标签的可达历史；模式扫描不能代替人工核对。

第三方内容的来源和未确认许可见 [数据来源清单](docs/DATA_PROVENANCE.md)。欢迎按 [贡献指南](CONTRIBUTING.md) 提交改进；安全问题请按 [安全报告说明](SECURITY.md) 处理。`PHASE*`、历史验收报告记录过去阶段，其旧状态和措辞不代表当前版本或当前用户。
