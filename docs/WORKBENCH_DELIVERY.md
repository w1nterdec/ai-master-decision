# 工作台改进与公开发布交付

> 更新于 2026-10-24。本文包含当前关键文件全文；许可、公开示例和数据权利说明已按最新版本同步。

## 1. 改进方案

先阅读仓库，保留决策引擎和规则；降低首次启动门槛，提供独立演示、新手引导、个人条件与带理由的人工备考分层，展示真实功能状态和解释。自动分层、R7、多用户隔离继续明确列为未完成。公开发布阶段补齐 MIT、第三方权利边界、隐私与贡献说明，通过 PR 和质量检查同步未提交改进。

## 2. 新增与修改文件

修改：
- `.dockerignore`
- `.github/workflows/quality.yml`
- `.gitignore`
- `Dockerfile`
- `README.md`
- `app.py`
- `compose.yaml`
- `docs/2028_AI_MASTER_DECISION_REPORT.md`
- `docs/BUPT_DECISION_CASE.md`
- `pyproject.toml`
- `src/decision_system/services/decision_policy.py`
- `src/decision_system/services/view_service.py`
- `src/decision_system/ui/blocks.py`
- `src/decision_system/ui/pages_cockpit.py`
- `src/decision_system/ui/pages_explore.py`
- `src/decision_system/ui/pages_paths.py`
- `src/decision_system/ui/pages_profile.py`
- `src/decision_system/ui/pages_result.py`
- `src/decision_system/ui/pages_risk.py`
- `src/decision_system/ui/pages_tree.py`
- `src/decision_system/ui/viewmodels.py`

新增：
- `.env.example`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `PRIVACY.md`
- `SECURITY.md`
- `data/README.md`
- `docs/DATA_PROVENANCE.md`
- `docs/ENGINEERING_NOTES.md`
- `docs/GETTING_STARTED.md`
- `docs/PUBLIC_RELEASE.md`
- `docs/WORKBENCH_DELIVERY.md`
- `scripts/check_secrets.py`
- `scripts/smoke_app.py`
- `scripts/start.py`
- `src/decision_system/ui/onboarding.py`
- `tests/integration/test_startup_workflow.py`
- `tests/ui/test_onboarding_workflow.py`
- `tests/unit/test_personal_planning.py`
- `tests/unit/test_public_release.py`
- `tests/unit/test_secret_checks.py`

## 3. 关键文件完整内容

### README.md

````markdown
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
````

### .env.example

````dotenv
# 本地运行不需要 API Key、token 或数据库口令。
# 可复制为 .env；只有 scripts/start.py 自动读取它，真实进程环境变量优先。
# 相对路径由启动器按仓库根目录解析。--demo 使用独立目录并覆盖下面两个路径。
DECISION_DB_PATH=data/decision.db
DECISION_ARCHIVE_PATH=data/decision_profile.json

# 默认只允许本机访问；端口被占用时可改成 8503，或传 --port 8503。
STREAMLIT_SERVER_ADDRESS=127.0.0.1
STREAMLIT_SERVER_PORT=8501

# 以下仅供独立的 secure_web_launch.py 代理使用；普通本地启动无需设置。
# 该代理不会自动读取 .env，需要显式注入环境变量；缺少凭据时拒绝启动。
# AUTH_USER=
# AUTH_PASS=
# PROXY_PORT=3000
# STREAMLIT_PORT=8502
# SESSION_TTL=604800
````

### scripts/start.py

````python
#!/usr/bin/env python3
"""Prepare data and launch the workbench; --demo isolates personal state."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def resolve_path(value: str | Path) -> Path:
    if "://" in str(value):
        raise ValueError("这里仅接受本地文件或目录路径，PostgreSQL 后端尚未接入。")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def prepare(args: argparse.Namespace) -> dict[str, str]:
    load_dotenv(resolve_path(args.env_file), override=False, interpolate=False)
    env = dict(os.environ)
    if args.demo:
        folder = resolve_path(args.demo_dir)
        db, archive = folder / "decision.db", folder / "decision_profile.json"
    else:
        db = resolve_path(env.get("DECISION_DB_PATH", "data/decision.db"))
        archive = resolve_path(
            env.get("DECISION_ARCHIVE_PATH", "data/decision_profile.json")
        )
    if db == archive:
        raise ValueError("数据库与个人档案必须使用不同的文件路径。")
    from bootstrap import bootstrap

    bootstrap(db, projection=False)
    archive.parent.mkdir(parents=True, exist_ok=True)
    env.update(DECISION_DB_PATH=str(db), DECISION_ARCHIVE_PATH=str(archive))
    return env


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="使用独立演示数据库和档案")
    parser.add_argument(
        "--demo-dir", default="data/demo", help="演示状态目录（可重复使用）"
    )
    parser.add_argument(
        "--env-file", default=".env", help="可选环境文件，不覆盖已有环境变量"
    )
    parser.add_argument(
        "--prepare-only", action="store_true", help="只初始化，不启动服务"
    )
    parser.add_argument("--host", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, help="监听端口，默认 8501")
    args = parser.parse_args(argv)
    # Validate configuration before writing data.
    load_dotenv(resolve_path(args.env_file), override=False, interpolate=False)
    try:
        port = (
            args.port
            if args.port is not None
            else int(os.environ.get("STREAMLIT_SERVER_PORT", "8501"))
        )
        if not 1 <= port <= 65535:
            raise ValueError("端口必须在 1–65535 范围内。")
        host = args.host or os.environ.get("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")
        env = prepare(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[FAIL] 启动准备失败：{exc}", file=sys.stderr)
        return 1
    print(
        "[OK] 独立演示已就绪（已归档历史研究，非虚构招生样本）。"
        if args.demo
        else "[OK] 工作台数据已就绪。"
    )
    print("[OK] 未修改原始研究或核心规则；个人条件与人工分层请到“我的决策档案”填写。")
    if args.prepare_only:
        return 0
    print(f"[OPEN] http://{host}:{port}")
    try:
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(ROOT / "app.py"),
                "--server.address",
                host,
                "--server.port",
                str(port),
                "--server.headless=true",
            ],
            cwd=ROOT,
            env=env,
        )
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
````

### src/decision_system/ui/onboarding.py

````python
"""User-facing feature inventory and first-run guidance; no decision calculations."""

from __future__ import annotations

import streamlit as st

FEATURES = (
    ("① 决策驾驶舱", "可用", "查看当前状态、优先缺口和关注路径的解释。"),
    ("② 院校探索", "可用", "筛选具体路径，查看来源、历史资料和风险，加入对比。"),
    ("③ 多校对比", "可用", "最多四条路径并列比较；评分取决于有效证据。"),
    ("④ 动态决策树", "可用", "调整相对权重、观察情景、派生和确认自己的偏好。"),
    (
        "⑤ 风险与路径规划",
        "部分可用",
        "缺口与准备事项可用；R7 调剂算法、直接就业评分尚未实现。",
    ),
    ("⑥ 我的决策档案", "可用", "记录个人条件、人工备考分层、关注、理由并导出。"),
    (
        "⑦ 择校结果总览",
        "历史研究意见",
        "查看原案例人工分析；不是针对新用户自动生成的结论。",
    ),
    ("⑧ 研究资料库", "可用", "检索全部底稿映射，按主题筛选并导出、回查原件。"),
    (
        "⚙️ 高级功能",
        "管理入口",
        "五个子页：证据管理、路径查看、模型参数、决策分析、系统状态。",
    ),
)


def navigate(page: str) -> None:
    st.session_state["nav_page"] = page


def render() -> None:
    with st.expander("新手入门与功能状态", expanded=False):
        st.markdown(
            "**第一次使用：看资料 → 记个人条件 → 比路径 → 核验证据 → 看解释与缺口。**"
        )
        st.caption(
            "这是证据化择校决策系统，不会自动抓取高校官网，也不会自动产出冲稳保。人工分层只是你的备考假设。"
        )
        c1, c2 = st.columns(2)
        c1.button(
            "先浏览研究样本",
            on_click=navigate,
            args=("⑧ 研究资料库",),
            key="onboard_research",
            width="stretch",
        )
        c2.button(
            "填写个人条件与备考分层",
            on_click=navigate,
            args=("⑥ 我的决策档案",),
            key="onboard_profile",
            width="stretch",
        )
        for name, status, purpose in FEATURES:
            st.markdown(f"**{name} · {status}**：{purpose}")
        st.markdown(
            "**高级功能状态**：证据登记/关联/人工核验、权重管理、分析和状态查看可用；路径维护目前只读，新增路径通过原始 Excel 导入。评分录入尚无独立网页表单。"
        )
        st.markdown(
            "**术语速查**：证据闸门＝检查来源、年份、路径是否匹配；覆盖率＝有有效证据支持的权重占比，不是录取把握；三级权重＝先大类再细项；情景＝换一种重视程度观察结论；phase＝开发历史标记。"
        )
        st.caption(
            "首次安装：python scripts/start.py --demo。缺少正式数据时可先看研究资料库，不要降低覆盖率门槛来制造评分。"
        )
````

### src/decision_system/ui/pages_profile.py

````python
"""页面六｜我的决策档案。

职责：沉淀「我自己的判断过程」，可导出为 Markdown 复盘。
纪律：
    * 档案只存**用户标记与备注**，不改数据库结构（独立 JSON 文件）；
    * 演示权重与用户确认偏好**分开显示**，不混淆；
    * 导出内容同样不含录取概率、不含院校排名。
"""

from __future__ import annotations

import datetime as _dt
from typing import Sequence

import streamlit as st

from decision_system.ui.theme import data_table
from sqlalchemy import select

from decision_system.models.entities import WeightProfile
from decision_system.services import view_service
from decision_system.ui.blocks import (
    get_archive,
    path_label,
    persist_archive,
    render_disclaimer,
)
from decision_system.ui.formatting import pct, render_status
from decision_system.ui.viewmodels import (
    EXAMPLE_BACKGROUND,
    PathSummary,
)


def _profile_rows(session) -> list[dict[str, str]]:
    profiles = (
        session.execute(select(WeightProfile).order_by(WeightProfile.id))
        .scalars()
        .all()
    )
    return [
        {
            "配置代码": p.code,
            "名称": p.name,
            "性质": "用户确认偏好" if not p.is_demo else "演示配置（待确认）",
        }
        for p in profiles
    ]


def _build_markdown(
    summaries: Sequence[PathSummary],
    archive,
    profile_rows,
    *,
    profile_code: str,
) -> str:
    by_id = {p.path_id: p for p in summaries}
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# 我的决策档案（2028 AI 硕士动态择校）")
    lines.append("")
    lines.append(f"> 导出时间：{now}　|　当前权重配置：`{profile_code}`")
    lines.append(">")
    lines.append("> 本档案**不含录取概率**，也**不构成院校排名**。")
    lines.append("")

    lines.append("## 一、决策前提（本人录入，仅作上下文）")
    lines.append("")
    if not archive.personal_conditions:
        lines.append("尚未录入个人条件；原始案例背景不代表当前使用者。")
    for k, v in archive.personal_conditions.items():
        lines.append(f"- **{k}**：{v}")
    lines.append("> 个人条件仅作记录，不自动改写引擎约束、权重或原案例政策。")
    lines.append("")

    lines.append("## 二、候选路径")
    lines.append("")
    if archive.candidate_path_ids:
        for pid in archive.candidate_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
            if p is not None:
                lines.append(
                    f"  - 2028 资格：{p.qualification_2028}　|　硬约束：{p.eligibility}　|　"
                    f"有效覆盖率：{pct(p.coverage)}　|　证据：{p.evidence.state}"
                )
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三、关注路径")
    lines.append("")
    if archive.favorite_path_ids:
        for pid in archive.favorite_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三·补、暂不考虑的路径")
    lines.append("")
    if archive.excluded_path_ids:
        for pid in archive.excluded_path_ids:
            p = by_id.get(pid)
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid} 已不在库中）'}")
            note = archive.note_of(pid)
            if note:
                lines.append(f"  - 我的理由：{note}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 三·补二、我对具体路径的判断与理由")
    lines.append("")
    if archive.path_notes:
        for pid, note in archive.path_notes.items():
            p = by_id.get(int(pid)) if str(pid).isdigit() else None
            lines.append(f"- {path_label(p) if p else f'（路径 #{pid}）'}：{note}")
    else:
        lines.append("- （暂无）")
    lines.append("")
    lines.append(
        "> 以上理由为用户自己的判断，**不改变任何证据的真实性，也不自动修改任何评分**。"
    )
    lines.append("")

    lines.append("## 四、权重配置状态")
    lines.append("")
    for r in profile_rows:
        lines.append(f"- `{r['配置代码']}`：{r['名称']}　（{r['性质']}）")
    lines.append("")
    lines.append(
        "> 演示配置仅代表示例权重结构；未点击「确认为我的正式偏好」之前，"
        "不得视为用户真实偏好。"
    )
    lines.append("")

    lines.append("## 五、我的备注")
    lines.append("")
    if archive.notes:
        for i, n in enumerate(archive.notes, 1):
            lines.append(f"{i}. {n}")
    else:
        lines.append("- （暂无）")
    lines.append("")

    lines.append("## 六、当前结论状态")
    lines.append("")
    confirmed = [p for p in summaries if p.qualification_is_confirmed]
    comparable = [
        p
        for p in summaries
        if p.decision is not None
        and str(p.decision.base.status).startswith("可比较")
        and p.decision.base.weighted_score is not None
    ]
    lines.append(f"- 在库路径：{len(summaries)} 条")
    lines.append(f"- 已确认 2028 正式资格：{len(confirmed)} 条")
    lines.append(f"- 当前可比较路径：{len(comparable)} 条")
    lines.append("")
    lines.append(
        "> 可比较路径为 0 是当前证据状态下的**正确结果**："
        "本地快照可能缺少已核验的 2028 资料或有效评分，系统不会强行给出排序。"
    )
    lines.extend(
        [
            "",
            "## 七、个人备考分层（人工假设）",
            "",
            "> 冲稳保为本人记录，非系统推荐；保不代表保证录取，不参与评分或资格判定。",
        ]
    )
    for pid, tier in archive.planning_tiers.items():
        path = by_id.get(int(pid))
        lines.append(
            f"- {path_label(path) if path else f'路径 #{pid}'}：{tier}；理由：{archive.note_of(int(pid))}"
        )
    if not archive.planning_tiers:
        lines.append("- 尚未进行人工分层。")
    lines.append("")
    return "\n".join(lines)


def render(session, rows, *, profile_code: str) -> None:
    st.subheader("我的决策档案")
    summaries = view_service.load_path_summaries(session, rows)
    archive = get_archive()
    by_id = {p.path_id: p for p in summaries}

    st.caption(
        f"档案文件：`{view_service.ARCHIVE_PATH}`"
        "　|　仅保存你的标记与备注，**不修改数据库结构**。"
    )

    st.markdown("### 我的个人条件")
    st.info(
        "个人条件用于记录与复盘，不会自动改写引擎硬约束、偏好权重或原案例政策。修改权重请到动态决策树；路径资格仍须逐条核验。"
    )
    with st.form("personal_conditions_form"):
        conditions = {}
        for field_name in (
            "本科专业",
            "目标方向",
            "意向城市",
            "可接受专业代码",
            "预算与其他限制",
        ):
            conditions[field_name] = st.text_input(
                field_name,
                value=archive.personal_conditions.get(field_name, ""),
                max_chars=1000,
                key=f"personal_{field_name}",
            )
        if st.form_submit_button("保存个人条件"):
            archive.personal_conditions = {
                k: v.strip() for k, v in conditions.items() if v.strip()
            }
            persist_archive()
            st.success("个人条件已保存，仅作决策上下文。")
    with st.expander("示例背景（仅供参照，不代表新用户）", expanded=False):
        for k, v in EXAMPLE_BACKGROUND:
            st.markdown(f"- **{k}**：{v}")

    st.markdown("### 个人备考分层（人工记录）")
    st.caption(
        "当前没有自动冲稳保算法。你可按已读证据记录自己的备考假设；“保”不代表保证录取。所有标签都不参与资格判定或评分。"
    )
    if summaries:
        pid = st.selectbox(
            "选择要记录分层的路径",
            list(by_id),
            format_func=lambda value: path_label(by_id[value]),
            key="planning_path",
        )
        tiers = ["未分层", "冲", "稳", "保"]
        with st.form(f"planning_form_{pid}"):
            tier = st.selectbox(
                "个人备考分层",
                tiers,
                index=tiers.index(archive.planning_tiers.get(str(pid), "未分层")),
                key=f"planning_tier_{pid}",
            )
            reason = st.text_area(
                "分层理由与待核验前提",
                value=archive.note_of(pid),
                max_chars=5000,
                key=f"planning_reason_{pid}",
            )
            if st.form_submit_button("保存人工分层"):
                try:
                    archive.set_planning_tier(pid, tier, reason)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    persist_archive()
                    st.success("已保存人工假设，未改变任何引擎结论。")
    else:
        st.info("暂无招生路径。可用 python scripts/start.py --demo 启动独立演示。")

    st.markdown("### 候选路径")
    if archive.candidate_path_ids:
        for pid in list(archive.candidate_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_c_{pid}"):
                archive.candidate_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无候选。可在「院校探索」中加入。")

    st.markdown("### 重点关注路径")
    if archive.favorite_path_ids:
        for pid in list(archive.favorite_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_f_{pid}"):
                archive.favorite_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无重点关注。可在「院校探索」中加入。")

    st.markdown("### 暂不考虑的路径")
    if archive.excluded_path_ids:
        for pid in list(archive.excluded_path_ids):
            p = by_id.get(pid)
            name = path_label(p) if p else f"（路径 #{pid} 已不在库中）"
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"- {name}")
            if c2.button("移除", key=f"prof_del_x_{pid}"):
                archive.excluded_path_ids.remove(pid)
                persist_archive()
    else:
        st.caption("暂无「暂不考虑」的路径。")
    st.caption(
        "标记只表达**你自己的判断**，不会改变证据真实性，也不会自动修改任何评分。"
    )

    st.markdown("### 我对具体路径的判断与理由")
    if archive.path_notes:
        for pid, note in list(archive.path_notes.items()):
            p = by_id.get(int(pid)) if str(pid).isdigit() else None
            name = path_label(p) if p else f"（路径 #{pid}）"
            st.markdown(f"- **{name}**：{note}")
    else:
        st.caption("尚未对任何路径写下你的判断。可在「院校探索」的路径详情中填写。")

    st.markdown("### 权重配置状态")
    profile_rows = _profile_rows(session)
    data_table(profile_rows, hide_index=True, width="stretch")
    st.caption("演示配置 ≠ 你的偏好。确认动作在「动态决策树 → 配置管理」中完成。")

    st.markdown("### 备注")
    note = st.text_area("新增一条备注", key="prof_note", height=80)
    if st.button("保存备注", key="prof_note_save"):
        if note.strip():
            archive.notes.append(note.strip())
            persist_archive()
            st.success("已保存。")
    if archive.notes:
        for i, n in enumerate(archive.notes, 1):
            st.markdown(f"{i}. {n}")
        if st.button("清空备注", key="prof_note_clear"):
            archive.notes = []
            persist_archive()

    st.markdown("### 导出")
    md = _build_markdown(summaries, archive, profile_rows, profile_code=profile_code)
    st.download_button(
        "下载决策档案（Markdown）",
        data=md,
        file_name="我的决策档案.md",
        mime="text/markdown",
        width="stretch",
    )
    with st.expander("预览导出内容", expanded=False):
        st.code(md, language="markdown")

    st.caption(f"上次更新：{archive.updated_at or '（尚未保存）'}")
    render_disclaimer()
````

### LICENSE

````text
MIT License

Copyright (c) 2026 ai-master-decision contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
````

### NOTICE

````text
ai-master-decision
Copyright (c) 2026 ai-master-decision contributors

Original project source code and original documentation are licensed under MIT.
Third-party dependencies retain their own licenses.

The MIT license does not grant rights to third-party content reproduced or
referenced in data/raw/, data/school_research_consolidated.json, research
reports, or screenshots. University notices, archived web text, attributed
excerpts, and third-party material within compiled research retain the rights
and terms of their respective owners. A publicly accessible source is not,
by itself, permission to redistribute that source.

No blanket open-data license is asserted for the research dataset. Check
data/README.md and docs/DATA_PROVENANCE.md before reusing or redistributing it.
No university affiliation or endorsement is implied.
````

### PRIVACY.md

````markdown
# 公开仓库与个人数据

## 页面中的背景属于示例

默认背景是从历史研究案例抽象的示例场景，不表示当前使用者的专业、城市倾向、预算或考研安排。历史研究报告只解释原案例，不会从你输入的条件自动生成相同结论。

个人条件、冲稳保标签和备注由使用者自行输入，只作个人上下文，不自动修改引擎资格或评分。示例背景中不预置真实姓名、联系方式或具体家庭信息。

## 保存位置与共享边界

- `.env` 保存可选本地配置，不应进入版本库。
- SQLite 默认位于 `data/decision.db`；个人档案默认是 `data/decision_profile.json`。
- 独立演示默认使用 `data/demo/`；这些路径均被 Git 忽略。
- 应用不自动抓取官网，也没有接入 LLM API；项目配置关闭 Streamlit 使用统计。GitHub、依赖下载和主动打开的官方链接仍由各服务处理。
- 一个服务实例共享同一套服务器档案，没有账户和按用户隔离能力。把服务开放给他人可能使对方看到或修改同一档案，公开源码不会自动公开你本机的服务或被忽略的本地文件。

导出的 Markdown、CSV、错误日志、截图可能包含个人条件、机器路径或研究内容；分享前自行检查。自定义数据库/档案路径可能位于默认忽略范围之外，应额外配置忽略规则。

## Git 历史不能靠改当前文件撤回

已公开的历史提交含有原案例背景和非 noreply 作者邮箱。新提交使用 GitHub 隐私邮箱，当前页面改成示例表述，但这不删除历史信息。本次不强制改写提交或标签；他人的 fork、克隆、缓存也不会随新提交撤回。

若需要进一步移除历史个人信息，应单独制定影响分支、标签、PR 和协作者的历史清理方案。涉及凭据时先撤销或轮换凭据，不能仅删除文本。

## 提交前检查

运行 `python scripts/check_secrets.py --history`，并人工检查截图、二进制原件和个人化内容。扫描器只覆盖指定模式，不提供“完全不存在隐私或密钥”的保证。避免在公开 Issue 或日志中粘贴个人档案、token 或完整环境文件。
````

## 4. 启动与验证

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts/start.py --demo
```

```bash
python scripts/check_secrets.py --history
python scripts/check_data.py
python scripts/smoke_app.py
python -m ruff check .
python -m pytest
```

此前工作台改进的本地全量回归为 328 项通过；公开发布补齐额外增加许可、示例兼容、历史密钥、表格扫描和私密文件名测试，最终结果以本 PR 的当前 CI 检查为准。数据一致性、静态检查、模式扫描和依赖检查均需通过。容器需验证构建、健康接口和实际页面渲染，不能用旧版 CI 的成功替代本轮验收。

核心引擎和 `docs/decision_rules.md` 无 diff。新提交使用 GitHub noreply 邮箱；历史邮箱和已公开副本未被撤回。

## 5. 后续迭代与边界

- 补齐网页评分录入和独立偏好确认，再将个人条件按明确规则接入硬约束。
- 定义并验证自动冲稳保和 R7，不把人工备考标签当成引擎推荐。
- 多人服务需要身份隔离、PostgreSQL 和档案并发控制，不是只换连接串。
- MIT 只许可项目原创代码和原创文档；第三方材料仍需逐项核对源站条款或取得许可，当前没有整套研究数据的统一开放授权。
- 当前界面使用泛化示例；过去阶段报告可能保留原案例措辞。清理公开历史须单独规划，不能靠改当前文件撤回 fork、克隆或缓存。
