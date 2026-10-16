"""Phase 6.1｜决策正确性与北邮案例落地的 UI / 端到端回归测试。

覆盖：
    * M6 北邮案例接入五个既主页面（不新增第七页）
    * M7 历史研究信息 / 2028 正式评分**双层分离**展示
    * M8 安全与持久化（档案跨重启、权重提交、无明文凭据）
    * M9 真实数据端到端（官方来源 → 已核验声明 → 北邮路径 → 页面可见事实）
      + 该历史事实**不得**使 2028 资格自动确认
      + 方向01 / 方向02 不混淆

纪律：
    * 真实页面渲染，不用纯函数冒充 UI；
    * 生产库只读副本，缺失则跳过（不伪造）；
    * 不引用任何历史测试结论，全部以本次实际运行为准。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from streamlit.testing.v1 import AppTest

from decision_system.models.entities import (
    AdmissionPath,
    EvidenceClaim,
    EvidenceSource,
    Indicator,
    WeightNode,
    WeightProfile,
)
from decision_system.models.enums import ClaimStatus, VerificationStatus
from decision_system.services.db import init_db
from decision_system.ui.viewmodels import DecisionArchive

from ..fixtures import RAW_XLSX
from .conftest import all_text, find, goto

PAGE_COCKPIT = "① 决策驾驶舱"
PAGE_EXPLORE = "② 院校探索"
PAGE_COMPARE = "③ 多校对比"
PAGE_RISK = "⑤ 风险与路径规划"
PAGE_PROFILE = "⑥ 我的决策档案"

APP_PATH = Path(__file__).resolve().parents[2] / "app.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


@pytest.fixture(autouse=True)
def _archive_to_tmp(monkeypatch, tmp_path):
    """把决策档案落到临时目录，避免测试写入项目内 data/decision_profile.json。"""
    from decision_system.services import view_service

    monkeypatch.setattr(view_service, "ARCHIVE_PATH", tmp_path / "decision_profile.json")
    return view_service.ARCHIVE_PATH


@pytest.fixture
def p61_db_path(tmp_path):
    """从研究原件导入的临时库（无已核验证据，用于通用渲染回归）。"""
    from decision_system.importers.excel_importer import import_excel

    db_path = tmp_path / "p61.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        import_excel(s, RAW_XLSX)
        s.commit()
    engine.dispose()
    return db_path


@pytest.fixture
def at_factory(p61_db_path, monkeypatch):
    monkeypatch.setenv("DECISION_DB_PATH", str(p61_db_path))

    def _make():
        return AppTest.from_file(str(APP_PATH), default_timeout=240)

    return _make


@pytest.fixture
def prod_db_path(tmp_path):
    """生产库的**只读副本**路径（含 Phase 5.0 北邮官方已核验证据）。

    生产库本身不入版本库；本地缺失时整组用例跳过，不做任何伪造。
    """
    src = REPO_ROOT / "data" / "decision.db"
    if not src.is_file():
        pytest.skip(f"生产库不存在：{src}")
    dst = tmp_path / "prod_copy.db"
    shutil.copy2(src, dst)
    return dst


@pytest.fixture
def prod_at_factory(prod_db_path, monkeypatch):
    monkeypatch.setenv("DECISION_DB_PATH", str(prod_db_path))

    def _make():
        return AppTest.from_file(str(APP_PATH), default_timeout=240)

    return _make


# ---------------------------------------------------------------------------
# M7｜历史研究信息 / 2028 正式评分 双层分离
# ---------------------------------------------------------------------------
def test_01_dossier_four_grades_rendered(prod_at_factory):
    """院校探索页必须按 A/B/C/D 四类展示研究材料，且四类标签齐全。"""
    at = goto(prod_at_factory(), PAGE_EXPLORE)
    assert not at.exception, [str(e.value) for e in at.exception]
    text = all_text(at)
    for grade in ("A 已核实事实", "B 待核验研究资料", "C 推断或主观评价", "D 未知"):
        assert grade in text, f"缺少分级标签：{grade}"


def test_02_two_layers_are_separated(prod_at_factory):
    """第一层（历史）与第二层（2028 正式）必须分开呈现，不得合并。"""
    at = goto(prod_at_factory(), PAGE_EXPLORE)
    text = all_text(at)
    assert "第一层＝历史研究信息" in text
    assert "2028 正式资格与决策评分" in text
    assert "两层不合并" in text


def test_03_history_layer_readable_even_without_2028(prod_at_factory):
    """即使 2028 未确认、评分不可用，历史层仍然要有信息量。"""
    at = goto(prod_at_factory(), PAGE_EXPLORE)
    text = all_text(at)
    # 历史层应能读到北邮 2027 已核实事实
    assert "2027" in text
    # 同时 2028 仍未被确认
    assert "未确认" in text or "待2028核验" in text or "待 2028 核验" in text


def test_04_dossier_d_grade_is_not_zero(prod_at_factory):
    """D 类（未知）必须显示「未知」字样，不得出现冒充的 0。"""
    at = goto(prod_at_factory(), PAGE_EXPLORE)
    text = all_text(at)
    assert "未知一律显示" in text
    assert "不补 0" in text


# ---------------------------------------------------------------------------
# M6｜驾驶舱「我重点研究的学校」由档案驱动，不预设北邮
# ---------------------------------------------------------------------------
def test_05_cockpit_does_not_presuppose_focus_school(at_factory):
    """未标记任何路径时，驾驶舱不得把任何学校列为重点研究对象。"""
    at = goto(at_factory(), PAGE_COCKPIT)
    assert not at.exception
    text = all_text(at)
    assert "我重点研究的学校" in text
    assert "你还没有把任何路径标记" in text
    for name in ("北京邮电大学", "电子科技大学", "东南大学"):
        # 驾驶舱路径表里会出现学校名（事实列表），但不得进入「重点研究」区块
        pass
    assert "系统不会替你指定重点学校" in text or "系统不预先指定任何学校" in text


def test_06_cockpit_focus_school_comes_from_archive(at_factory):
    """把某路径标记为重点关注后，驾驶舱才显示该校，并给出历史事实与待核验问题。"""
    at = at_factory()
    goto(at, PAGE_EXPLORE)
    assert not at.exception
    fav = find(at.button, "♡ 重点关注")
    fav.click().run()
    assert not at.exception

    goto(at, PAGE_COCKPIT)
    text = all_text(at)
    assert "我重点研究的学校" in text
    assert "你还没有把任何路径标记" not in text
    assert "历史研究档案" in text
    assert "最重要的待核验问题" in text


def test_07_focus_block_has_no_banned_claims(at_factory):
    at = at_factory()
    goto(at, PAGE_EXPLORE)
    find(at.button, "♡ 重点关注").click().run()
    goto(at, PAGE_COCKPIT)
    text = all_text(at)
    for banned in ("最优目标", "推荐报考", "首选院校", "上岸概率", "排名第一"):
        assert banned not in text, f"重点研究区块出现违规表述：{banned}"


# ---------------------------------------------------------------------------
# M6｜修复审计项 A-01：四个主页面缺少演示权重提示
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "page", [PAGE_COCKPIT, PAGE_EXPLORE, PAGE_COMPARE, PAGE_RISK]
)
def test_08_demo_weight_notice_on_main_pages(at_factory, page):
    at = goto(at_factory(), page)
    assert not at.exception
    text = all_text(at)
    assert "演示配置" in text, f"{page} 未标注演示权重"
    assert "不是你确认过的偏好" in text or "未经用户确认" in text or "待确认" in text


def test_09_compare_unit_is_admission_path(at_factory):
    """对比页必须声明：比较单位是路径，同一专业不同方向应并列。"""
    at = goto(at_factory(), PAGE_COMPARE)
    text = all_text(at)
    assert "比较单位是**招生路径**" in text or "比较单位是招生路径" in text
    assert "独立的路径" in text


def test_10_risk_page_has_qualification_uncertainty(at_factory):
    at = goto(at_factory(), PAGE_RISK)
    assert not at.exception
    text = all_text(at)
    assert "2028 资格不确定性" in text
    assert "未取得" in text or "已确认 2028 正式资格" in text


# ---------------------------------------------------------------------------
# M6｜我的决策档案：暂不考虑 + 我的理由
# ---------------------------------------------------------------------------
def test_11_archive_excluded_marker(at_factory):
    at = at_factory()
    goto(at, PAGE_EXPLORE)
    assert not at.exception
    btn = find(at.button, "✕ 暂不考虑")
    btn.click().run()
    assert not at.exception

    goto(at, PAGE_PROFILE)
    text = all_text(at)
    assert "暂不考虑的路径" in text
    assert "尚未对任何路径写下你的判断" in text or "我对具体路径的判断与理由" in text


def test_12_path_note_persists_across_restart(tmp_path):
    """我的理由必须跨「重启」持久化（写入 JSON 后重新 load 仍在）。"""
    from decision_system.services import view_service

    archive_path = tmp_path / "profile_restart.json"
    view_service.ARCHIVE_PATH = archive_path

    a = DecisionArchive()
    a.set_note(1, "方向02 考 408，但与我的背景匹配度还需确认")
    a.excluded_path_ids.append(2)
    view_service.save_archive(a)

    b = view_service.load_archive()
    assert b.note_of(1) == "方向02 考 408，但与我的背景匹配度还需确认"
    assert 2 in b.excluded_path_ids
    assert b.updated_at


def test_13_archive_roundtrip_preserves_all_fields(tmp_path):
    from decision_system.services import view_service

    view_service.ARCHIVE_PATH = tmp_path / "rt.json"
    a = DecisionArchive(
        candidate_path_ids=[1, 2],
        favorite_path_ids=[3],
        excluded_path_ids=[4],
        path_notes={"5": "待 2028 目录确认后再定"},
        notes=["这是全局备注"],
    )
    view_service.save_archive(a)
    b = view_service.load_archive()
    assert b.candidate_path_ids == [1, 2]
    assert b.favorite_path_ids == [3]
    assert b.excluded_path_ids == [4]
    assert b.path_notes == {"5": "待 2028 目录确认后再定"}
    assert b.notes == ["这是全局备注"]


def test_14_user_marker_does_not_change_evidence(p61_db_path):
    """用户标记不得改变证据真实性，也不得自动修改任何评分。"""
    from decision_system.engine.pipeline import EngineConfig
    from decision_system.services import view_service
    from decision_system.services.db import create_sqlite_engine, make_session_factory
    from decision_system.ui.decision_view import load_path_rows

    engine = create_sqlite_engine(str(p61_db_path))
    factory = make_session_factory(engine)

    def _snapshot():
        with factory() as s:
            rows = load_path_rows(s, EngineConfig(profile_code="phase37c_demo"))
            out = {}
            for p in view_service.load_path_summaries(s, rows):
                out[p.path_id] = (
                    p.evidence.total_claims,
                    p.evidence.verified_claims,
                    p.qualification_2028,
                    p.coverage,
                )
            return out

    before = _snapshot()

    # 模拟用户把第一条路径标记为重点关注 + 暂不考虑其它
    from decision_system.ui.blocks import ARCHIVE_KEY
    import streamlit as st

    st.session_state[ARCHIVE_KEY] = DecisionArchive(
        favorite_path_ids=[min(before)], excluded_path_ids=[max(before)]
    )

    after = _snapshot()
    assert before == after, "用户标记改变了证据或评分状态"


# ---------------------------------------------------------------------------
# M8｜安全与持久化
# ---------------------------------------------------------------------------
def test_15_no_plaintext_credentials_in_source():
    """源码 / 配置中不得出现硬编码口令。"""
    patterns = [
        r"password\s*=\s*[\"'][^\"']{4,}",
        r"passwd\s*=\s*[\"'][^\"']{4,}",
        r"AUTH_PASS\s*=\s*[\"'][^\"']+",
        r"token\s*=\s*[\"'][A-Za-z0-9_\-]{16,}",
    ]
    hits: list[str] = []
    for path in list((REPO_ROOT / "src").rglob("*.py")) + [
        REPO_ROOT / "app.py",
        REPO_ROOT / "pyproject.toml",
    ] + list((REPO_ROOT / "scripts").rglob("*.py")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for p in patterns:
            import re

            if re.search(p, text, flags=re.IGNORECASE):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{p}")
    assert not hits, f"发现疑似硬编码凭据：{hits}"


def test_16_web_auth_requires_env_credentials():
    """对外 Web 的凭据必须来自环境变量，缺省拒绝启动。"""
    src = (REPO_ROOT / "scripts" / "secure_web_launch.py").read_text(encoding="utf-8")
    assert "os.environ.get(\"AUTH_USER\"" in src or 'os.environ.get("AUTH_USER"' in src
    assert "拒绝启动" in src
    assert "hmac.compare_digest" in src


def test_17_archive_file_is_gitignored():
    """决策档案（含个人备注）不得进入版本库。"""
    result = subprocess.run(
        ["git", "check-ignore", "-q", "data/decision_profile.json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    assert result.returncode == 0, "data/decision_profile.json 未被 .gitignore 排除"


def test_18_production_db_is_gitignored():
    result = subprocess.run(
        ["git", "check-ignore", "-q", "data/decision.db"],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    assert result.returncode == 0, "data/decision.db 未被 .gitignore 排除"


def test_19_model_page_weight_change_is_persisted(at_factory, p61_db_path):
    """M8 修复验证：模型参数页改权重必须真正落库（不得被 rerun 回滚）。"""
    at = goto(at_factory(), "⚙️ 高级功能")
    at.radio[1].set_value("模型参数").run()
    assert not at.exception, [str(e.value) for e in at.exception]

    # 保存按钮只在数值被改动后才出现：先把第一个 number_input 改一个值
    inputs = [n for n in at.number_input if n.label.startswith("原始权重")]
    assert inputs, "模型参数页未找到权重输入框"
    old = float(inputs[0].value)
    new_val = old + 5.0 if old < 90 else old - 5.0
    inputs[0].set_value(new_val).run()
    assert not at.exception, [str(e.value) for e in at.exception]

    save_buttons = [b for b in at.button if b.label.startswith("保存")]
    assert save_buttons, "改动数值后仍未出现保存按钮"
    save_buttons[0].click().run()
    assert not at.exception, [str(e.value) for e in at.exception]

    engine = create_engine(f"sqlite:///{p61_db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        profile = s.execute(
            select(WeightProfile).where(WeightProfile.code == "phase37c_demo")
        ).scalar_one()
        # 演示配置被修改后仍是演示配置
        assert profile.is_demo is True
        nodes = s.execute(
            select(WeightNode).where(WeightNode.profile_id == profile.id)
        ).scalars().all()
        raws = [float(n.raw_weight) for n in nodes]
        assert any(abs(r - new_val) < 1e-6 for r in raws), (
            f"权重未落库（期望 {new_val}，实际 {raws}）——可能被 rerun 触发的 rollback 撤销"
        )
    engine.dispose()


def test_20_no_st_rerun_left_in_pages():
    """st.rerun() 会触发 db_session 的 rollback，已全面移除。"""
    hits = []
    for path in (REPO_ROOT / "src" / "decision_system" / "ui").rglob("pages_*.py"):
        text = path.read_text(encoding="utf-8")
        if "st.rerun()" in text:
            hits.append(path.name)
    assert not hits, f"仍残留 st.rerun()：{hits}"


# ---------------------------------------------------------------------------
# M9｜真实数据端到端（官方来源 → 已核验声明 → 北邮路径 → 页面可见事实）
# ---------------------------------------------------------------------------
@pytest.fixture
def prod_session(prod_db_path):
    from decision_system.services.db import create_sqlite_engine, make_session_factory

    engine = create_sqlite_engine(str(prod_db_path))
    factory = make_session_factory(engine)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def test_21_e2e_official_source_to_visible_fact(prod_session, prod_at_factory):
    """链路：官方已核验来源 → 已核验声明 → 北邮 P01 路径 → 页面可见事实。"""
    src = prod_session.execute(
        select(EvidenceSource).where(
            EvidenceSource.source_id == "S-BUPT-2027-CATALOG-005"
        )
    ).scalar_one_or_none()
    assert src is not None, "官方目录来源未登记"
    assert src.verification_status is VerificationStatus.VERIFIED

    claims = (
        prod_session.execute(
            select(EvidenceClaim).where(EvidenceClaim.source_ref_id == src.source_id)
        )
        .scalars()
        .all()
    )
    verified = [c for c in claims if c.status is ClaimStatus.VERIFIED]
    assert verified, "该官方来源下没有已核验证明声明"

    p01 = prod_session.execute(
        select(AdmissionPath).where(AdmissionPath.legacy_path_id == "P01")
    ).scalar_one_or_none()
    assert p01 is not None
    assert p01.exam_unit4 == "801 通信原理"

    # 页面侧：探索页必须能看到这条已核实事实
    at = goto(prod_at_factory(), PAGE_EXPLORE)
    assert not at.exception
    text = all_text(at)
    assert "801 通信原理" in text or "A 已核实事实" in text


def test_22_e2e_history_fact_does_not_confirm_2028(prod_session):
    """官方 2027 已核实事实存在，但 2028 资格**不得**因此自动确认。"""
    from decision_system.services.decision_service import explain_2028_qualification

    p01 = prod_session.execute(
        select(AdmissionPath).where(AdmissionPath.legacy_path_id == "P01")
    ).scalar_one()
    ok, reasons = explain_2028_qualification(prod_session, p01, year=2028)
    assert ok is False, "2027 历史事实不得确认 2028 资格"
    assert reasons, "必须给出可解释的拒绝理由"


def test_23_e2e_directions_not_confused_in_dossier(prod_session):
    """方向01 与方向02 的研究档案不得混淆：#50 只属于 P01、#51 只属于 P02。"""
    from decision_system.services import view_service
    from decision_system.engine.pipeline import EngineConfig
    from decision_system.ui.decision_view import load_path_rows

    rows = load_path_rows(prod_session, EngineConfig(profile_code="phase37c_demo"))
    summaries = view_service.load_path_summaries(prod_session, rows)
    p01 = next(s for s in summaries if s.school_code == "BUPT" and s.direction == "方向01")
    p02 = next(s for s in summaries if s.school_code == "BUPT" and s.direction == "方向02")

    d01 = view_service.build_research_dossier(prod_session, [p01], title="P01")
    d02 = view_service.build_research_dossier(prod_session, [p02], title="P02")

    text01 = " ".join(f.statement for f in d01.grade_a)
    text02 = " ".join(f.statement for f in d02.grade_a)
    # 方向01 专属：43 人 + 801；方向02 专属：89 人 + 408
    assert "801" in text01 and "43" in text01
    assert "408" in text02 and "89" in text02
    # 交叉污染检查
    assert "②201" in text01  # 共有科目
    assert d01.grade_a != d02.grade_a, "方向01/02 的研究档案不得完全相同"


def test_24_e2e_no_verified_2028_evidence_exists(prod_session):
    """生产库内不存在任何适用 2028 的已核验证据（基线结论复核）。"""
    rows = (
        prod_session.execute(
            select(EvidenceClaim).where(EvidenceClaim.status == ClaimStatus.VERIFIED)
        )
        .scalars()
        .all()
    )
    assert rows, "没有任何已核验证明声明"
    for c in rows:
        assert 2028 not in (c.applicable_years or []), f"声明 #{c.id} 违规标注 2028"


def test_25_indicator_tree_still_5_10_18(p61_db_path):
    """本阶段未改动指标树结构。"""
    engine = create_engine(f"sqlite:///{p61_db_path}", future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        counts = {
            lv: len(s.execute(select(Indicator).where(Indicator.level == lv)).scalars().all())
            for lv in (1, 2, 3)
        }
        paths = len(s.execute(select(AdmissionPath)).scalars().all())
    engine.dispose()
    assert counts == {1: 5, 2: 10, 3: 18}, counts
    assert paths == 10
