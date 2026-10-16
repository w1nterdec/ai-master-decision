"""Phase 3.7C Excel -> SQLite 迁移导入器（Task D）。

行为准则：
    1. 读取路径与指标，保留原始字段（raw_row 全量留痕）。
    2. 保留原始来源信息；引用但未登记的 source_id 记为「未登记」，**不得**视为已核验。
    3. 不确定字段一律标记待核验，不擅自补全未知值。
    4. 不生成模拟招生事实（人数、录取概率、科目年份一律不推断）。
    5. 不把演示权重当成用户最终偏好（WeightProfile.is_demo=True）。
    6. 不把历史招生路径当作 2028 已确认路径（qualification 由引擎判定，默认为未确认）。
    7. 幂等：以 batch_key(=文件 sha256) + 各实体自然键做 get_or_create，重复导入不产生重复记录。
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from decision_system.models.entities import (
    AdmissionPath,
    AdmissionYear,
    AuditLog,
    ClaimConflict,
    ClaimIndicatorLink,
    ClaimPathLink,
    College,
    EvidenceClaim,
    EvidenceSource,
    ImportBatch,
    Indicator,
    Program,
    Scenario,
    ScenarioMultiplier,
    School,
    ScoreRecord,
    WeightNode,
    WeightProfile,
)
from decision_system.models.enums import (
    Accessibility,
    AdmissionMethod,
    ClaimStatus,
    EvidenceLevel,
    PathKind,
    Qualification2028,
    ScoreValidity,
    SourceType,
    StudyMode,
    TriState,
    Verification2028,
    VerificationStatus,
)
from decision_system.services.path_identity import build_path_key

# ---------------------------------------------------------------------------
# 常量与映射（来源：Phase 3.x 研究成果；未知项保持 None，不做推断）
# ---------------------------------------------------------------------------
SCHOOL_CODE_MAP = {
    "北京邮电大学": "BUPT",
    "电子科技大学": "UESTC",
    "东南大学": "SEU",
    "合肥工业大学": "HFUT",
    "西南交通大学": "SWJTU",
}

REGION_MAP = {
    "北京邮电大学": "华北",
    "电子科技大学": "西南",
    "东南大学": "华东",
    "合肥工业大学": "华东",
    "西南交通大学": "西南",
}

DEFAULT_PROFILE_CODE = "phase37c_demo"
DEFAULT_EVALUATION_YEAR = 2028

SCENARIO_COLUMNS = {"career": 5, "admission": 6, "research": 7}  # E / F / G
SCENARIO_NAMES = {
    "career": "职业发展优先",
    "admission": "报考可行性优先",
    "research": "科研培养优先",
}

_YEAR_HINT_RE = re.compile(r"(20\d{2})\s*(?:届|年)")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return value


def _map_tristate(value: Any) -> TriState:
    text = str(_clean(value) or "").strip()
    if text in ("是", "Y", "y", "yes", "符合"):
        return TriState.YES
    if text in ("否", "N", "n", "no", "不符合"):
        return TriState.NO
    return TriState.UNKNOWN


def _map_study_mode(value: Any) -> StudyMode:
    text = str(_clean(value) or "")
    if "全日制" in text and "非全" not in text:
        return StudyMode.FULL_TIME
    if "非全" in text:
        return StudyMode.PART_TIME
    return StudyMode.UNKNOWN


def _map_evidence_level(value: Any) -> EvidenceLevel:
    text = str(_clean(value) or "").upper()
    return {"S1": EvidenceLevel.S1, "S2": EvidenceLevel.S2,
            "S3": EvidenceLevel.S3, "S4": EvidenceLevel.S4}.get(text, EvidenceLevel.UNKNOWN)


def _map_accessibility(value: Any) -> Accessibility:
    text = str(_clean(value) or "").upper()
    return {"P1": Accessibility.P1, "P2": Accessibility.P2,
            "P3": Accessibility.P3, "P4": Accessibility.P4}.get(
        text, Accessibility.NA if not text else Accessibility.NA
    )


def _map_verification_2028(value: Any) -> Verification2028:
    text = str(_clean(value) or "")
    if "已核验2028" in text or text == "已核验":
        return Verification2028.VERIFIED
    if "2028" in text:
        return Verification2028.PENDING
    return Verification2028.UNKNOWN


def _map_source_verification(value: Any) -> VerificationStatus:
    text = str(_clean(value) or "")
    mapping = {
        "已核验": VerificationStatus.VERIFIED,
        "待核验": VerificationStatus.PENDING,
        "来源冲突": VerificationStatus.CONFLICT,
        "已失效": VerificationStatus.INVALID,
        "无法核验": VerificationStatus.UNVERIFIABLE,
        "未登记": VerificationStatus.UNREGISTERED,
    }
    return mapping.get(text, VerificationStatus.PENDING)


def _map_source_type(value: Any) -> SourceType:
    text = str(_clean(value) or "")
    for st in SourceType:
        if st.value in text:
            return st
    return SourceType.UNKNOWN


def _extract_year_hints(text: str | None) -> list[int]:
    if not text:
        return []
    return sorted({int(m) for m in _YEAR_HINT_RE.findall(text)})


# ---------------------------------------------------------------------------
# 导入报告
# ---------------------------------------------------------------------------
@dataclass
class ImportReport:
    batch_key: str
    source_file: str
    file_sha256: str
    imported_at: str
    replayed: bool = False

    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    pending_verification: int = 0
    conflicts: int = 0
    unregistered_source_ids: list[str] = field(default_factory=list)
    open_questions: int = 0
    anomalies: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def bump(self, bucket: dict[str, int], key: str, n: int = 1) -> None:
        bucket[key] = bucket.get(key, 0) + n

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_key": self.batch_key,
            "source_file": self.source_file,
            "file_sha256": self.file_sha256,
            "imported_at": self.imported_at,
            "replayed_same_version": self.replayed,
            "inserted": dict(sorted(self.inserted.items())),
            "skipped": dict(sorted(self.skipped.items())),
            "pending_verification": self.pending_verification,
            "conflicts": self.conflicts,
            "unregistered_source_count": len(self.unregistered_source_ids),
            "unregistered_source_ids_sample": self.unregistered_source_ids[:30],
            "open_questions": self.open_questions,
            "anomalies": self.anomalies,
            "notes": self.notes,
        }

    def as_text(self) -> str:
        d = self.to_dict()
        lines = [
            "=== Phase 3.7C Excel 导入报告 ===",
            f"文件: {d['source_file']}",
            f"SHA256: {d['file_sha256'][:32]}...",
            f"批次: {d['batch_key']}   导入时间: {d['imported_at']}",
            f"同版本重复导入: {'是（幂等跳过）' if d['replayed_same_version'] else '否'}",
            "",
            "[成功导入数量]",
        ]
        for k, v in d["inserted"].items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append("[跳过数量（已存在/幂等）]")
        for k, v in d["skipped"].items():
            lines.append(f"  {k}: {v}")
        lines.append("")
        lines.append(
            f"[待核验数量] {d['pending_verification']}    "
            f"[冲突数量] {d['conflicts']}    "
            f"[未登记来源] {d['unregistered_source_count']}    "
            f"[待核问题] {d['open_questions']}"
        )
        lines.append("")
        lines.append("[数据异常]")
        lines.extend(f"  - {a}" for a in d["anomalies"] or ["  无"])
        lines.append("")
        lines.append("[说明]")
        lines.extend(f"  - {n}" for n in d["notes"])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 导入器
# ---------------------------------------------------------------------------
class ExcelImporter:
    def __init__(
        self,
        session: Session,
        *,
        target_year: int = DEFAULT_EVALUATION_YEAR,
        profile_code: str = DEFAULT_PROFILE_CODE,
        actor: str = "import_excel",
    ) -> None:
        self.session = session
        self.target_year = target_year
        self.profile_code = profile_code
        self.actor = actor
        self.report: ImportReport | None = None
        self._school_cache: dict[str, School] = {}
        self._college_cache: dict[tuple[int, str], College] = {}
        self._program_cache: dict[tuple[int, str], Program] = {}
        self._indicator_cache: dict[str, Indicator] = {}
        self._path_cache: dict[str, AdmissionPath] = {}
        self._source_cache: dict[str, EvidenceSource] = {}

    # ---------- 入口 ----------
    def run(self, xlsx_path: str | Path) -> ImportReport:
        path = Path(xlsx_path)
        if not path.is_file():
            raise FileNotFoundError(f"Excel 文件不存在：{path}")
        sha = _sha256(path)
        batch_key = f"{sha[:16]}@{self.profile_code}"

        existing = (
            self.session.execute(
                select(ImportBatch).where(ImportBatch.batch_key == batch_key)
            )
            .scalar_one_or_none()
        )
        report = ImportReport(
            batch_key=batch_key,
            source_file=str(path),
            file_sha256=sha,
            imported_at=_now().isoformat(timespec="seconds"),
            replayed=existing is not None,
        )
        self.report = report

        if existing is not None:
            report.notes.append("检测到同版本已导入，仍逐实体执行幂等 upsert 校验（不应产生重复记录）")

        wb = load_workbook(path, data_only=False, read_only=False)

        self._import_indicators(wb)
        self._import_weight_profile(wb)
        self._import_scenarios(wb)
        self._import_sources(wb)
        self._import_paths(wb)
        self._import_score_matrix(wb)
        self._import_claims(wb)
        self._import_open_questions(wb)

        report.notes.extend(
            [
                "默认权重标记为演示配置（is_demo=True），不得冒充用户最终偏好",
                "历史招生路径一律不以 2028 已确认资格导入；资格由硬约束引擎独立判定",
                "候选证据映射导入为 ClaimStatus.CANDIDATE，不会自动升级为已核验",
                "评分矩阵全部保持未知（未评分），不以缺失补零",
            ]
        )

        self.session.flush()
        if existing is None:
            self.session.add(
                ImportBatch(
                    batch_key=batch_key,
                    source_file=str(path),
                    file_sha256=sha,
                    report=report.to_dict(),
                )
            )
        else:
            existing.report = report.to_dict()
        self._audit("import.batch", batch_key, report.to_dict())
        self.session.flush()
        return report

    # ---------- 指标 ----------
    def _import_indicators(self, wb) -> None:
        ws = wb["三级指标树"]
        report = self.report
        idx = 0
        for r in range(2, 20):
            l1, l2, l3 = _clean(ws.cell(r, 1).value), _clean(ws.cell(r, 2).value), _clean(ws.cell(r, 3).value)
            if not (l1 and l2 and l3):
                report.anomalies.append(f"三级指标树 第{r}行缺少层级名称，已跳过")
                continue
            anchor = _clean(ws.cell(r, 8).value)
            c1, c2, c3 = f"L1-{l1}", f"L2-{l1}|{l2}", f"L3-{l1}|{l2}|{l3}"
            for code, name, level, parent in ((c1, l1, 1, None), (c2, l2, 2, c1), (c3, l3, 3, c2)):
                if code in self._indicator_cache:
                    continue
                row = (
                    self.session.execute(select(Indicator).where(Indicator.code == code))
                    .scalar_one_or_none()
                )
                if row is None:
                    row = Indicator(
                        code=code, level=level, name=name, parent_code=parent,
                        sort_order=idx, scoring_anchor=anchor if level == 3 else None,
                    )
                    self.session.add(row)
                    self.session.flush()
                    self.bump_inserted("indicator")
                else:
                    self.bump_skipped("indicator")
                self._indicator_cache[code] = row
            idx += 1

    # ---------- 权重 ----------
    def _import_weight_profile(self, wb) -> None:
        ws = wb["三级指标树"]
        report = self.report
        # 一级权重：L(12) 一级类别 / M(13) 权重(%)
        l1_weights: dict[str, float] = {}
        for r in range(2, 7):
            name, w = _clean(ws.cell(r, 12).value), _clean(ws.cell(r, 13).value)
            if name and w is not None:
                l1_weights[str(name)] = float(w)
        # 二级组内权重
        l2_weights: dict[str, float] = {}
        for r in range(9, 19):
            name, w = _clean(ws.cell(r, 12).value), _clean(ws.cell(r, 13).value)
            if name and w is not None:
                l2_weights[str(name)] = float(w)
        if not l1_weights or not l2_weights:
            report.anomalies.append("未能读取一级/二级权重参数列（M 列），权重配置未导入")
            return

        profile = (
            self.session.execute(
                select(WeightProfile).where(WeightProfile.code == self.profile_code)
            )
            .scalar_one_or_none()
        )
        if profile is None:
            profile = WeightProfile(
                code=self.profile_code,
                name="Phase 3.7C 演示权重（来源：三级指标树 M 列）",
                is_demo=True,
                description="演示配置，不是用户最终偏好；修改后自动重算三级全局权重",
            )
            self.session.add(profile)
            self.session.flush()
            self.bump_inserted("weight_profile")
        else:
            self.bump_skipped("weight_profile")

        existing_nodes: set[int] = {wn.indicator_id for wn in profile.nodes}
        pending = 0
        for r in range(2, 20):
            l1, l2, l3 = _clean(ws.cell(r, 1).value), _clean(ws.cell(r, 2).value), _clean(ws.cell(r, 3).value)
            w3 = _clean(ws.cell(r, 6).value)
            if not (l1 and l2 and l3) or w3 is None:
                continue
            w1 = l1_weights.get(str(l1))
            w2 = l2_weights.get(str(l2))
            if w1 is None or w2 is None:
                report.anomalies.append(f"第{r}行指标 {l1}/{l2} 缺少一级或二级权重，标记为待核验")
                pending += 1
                w1 = w1 if w1 is not None else 0.0
                w2 = w2 if w2 is not None else 0.0
            triples = (
                (f"L1-{l1}", 1, w1),
                (f"L2-{l1}|{l2}", 2, w2),
                (f"L3-{l1}|{l2}|{l3}", 3, float(w3)),
            )
            for code, level, w in triples:
                ind = self._indicator_cache.get(code)
                if ind is None:
                    continue
                if ind.id in existing_nodes:
                    self.bump_skipped("weight_node")
                    continue
                self.session.add(
                    WeightNode(profile_id=profile.id, indicator_id=ind.id, level=level, raw_weight=float(w))
                )
                existing_nodes.add(ind.id)
                self.bump_inserted("weight_node")
        self.session.flush()
        report.pending_verification += pending

    # ---------- 情景 ----------
    def _import_scenarios(self, wb) -> None:
        ws = wb["3_2情景权重"]
        report = self.report
        seen_l1: dict[str, str] = {}
        for r in range(2, 20):
            l1 = _clean(ws.cell(r, 1).value)
            if l1:
                seen_l1[f"L1-{l1}"] = str(l1)

        for code, col in SCENARIO_COLUMNS.items():
            scenario = (
                self.session.execute(select(Scenario).where(Scenario.code == code))
                .scalar_one_or_none()
            )
            if scenario is None:
                scenario = Scenario(
                    code=code, name=SCENARIO_NAMES[code], is_demo=True,
                    description="倍率为情景假设，不代表事实；情景权重独立归一化",
                )
                self.session.add(scenario)
                self.session.flush()
                self.bump_inserted("scenario")
            else:
                self.bump_skipped("scenario")
            existing = {m.target_code for m in scenario.multipliers}
            for r in range(2, 20):
                l1 = _clean(ws.cell(r, 1).value)
                mult = _clean(ws.cell(r, col).value)
                if not l1 or mult is None:
                    continue
                target = f"L1-{l1}"
                if target in existing:
                    self.bump_skipped("scenario_multiplier")
                    continue
                try:
                    value = float(mult)
                except (TypeError, ValueError):
                    report.anomalies.append(f"情景 {code} 第{r}行倍率非数值：{mult!r}")
                    continue
                self.session.add(
                    ScenarioMultiplier(scenario_id=scenario.id, target_code=target, multiplier=value)
                )
                existing.add(target)
                self.bump_inserted("scenario_multiplier")
        self.session.flush()

    # ---------- 来源登记 ----------
    def _import_sources(self, wb) -> None:
        ws = wb["来源登记"]
        report = self.report
        for r in range(2, ws.max_row + 1):
            sid = _clean(ws.cell(r, 1).value)
            if not sid:
                continue
            status = _map_source_verification(ws.cell(r, 4).value)
            src = self._get_or_create_source(
                source_id=str(sid),
                title=str(_clean(ws.cell(r, 2).value) or f"（未命名来源）{sid}"),
                source_type=_map_source_type(ws.cell(r, 3).value),
                verification_status=status,
                verification_note=_clean(ws.cell(r, 5).value),
                is_placeholder=True,  # 登记表首行为占位登记
            )
            if status is not VerificationStatus.VERIFIED:
                report.pending_verification += 1

    # ---------- 路径 ----------
    def _import_paths(self, wb) -> None:
        ws = wb["路径"]
        report = self.report
        years = {self.target_year}
        for r in range(2, ws.max_row + 1):
            legacy_id = _clean(ws.cell(r, 1).value)
            school_name = _clean(ws.cell(r, 2).value)
            college_code = _clean(ws.cell(r, 3).value)
            program_code = _clean(ws.cell(r, 4).value)
            if not (legacy_id and school_name and college_code and program_code):
                report.anomalies.append(f"路径表 第{r}行缺少必要字段，已跳过")
                continue

            school = self._get_or_create_school(str(school_name))
            college = self._get_or_create_college(school, str(college_code))
            program = self._get_or_create_program(college, str(program_code))

            study_mode = _map_study_mode(ws.cell(r, 5).value)
            direction = _clean(ws.cell(r, 6).value)
            path_key = build_path_key(
                school_code=school.code,
                college_code=str(college_code),
                program_code=str(program_code),
                admission_year=self.target_year,
                study_mode=study_mode,
                direction=direction,
                admission_method=AdmissionMethod.UNIFIED_EXAM,
                path_kind=PathKind.FIRST_CHOICE,
            )
            path = (
                self.session.execute(select(AdmissionPath).where(AdmissionPath.path_key == path_key))
                .scalar_one_or_none()
            )
            if path is None:
                path = AdmissionPath(
                    path_key=path_key,
                    legacy_path_id=str(legacy_id),
                    school_id=school.id,
                    college_id=college.id,
                    program_id=program.id,
                    admission_year=self.target_year,
                    study_mode=study_mode,
                    admission_method=AdmissionMethod.UNIFIED_EXAM,
                    path_kind=PathKind.FIRST_CHOICE,
                    direction=str(direction) if direction else None,
                    exam_unit4=str(_clean(ws.cell(r, 7).value) or None),
                    training_location=str(_clean(ws.cell(r, 8).value) or None),
                    full_time_ok=_map_tristate(ws.cell(r, 11).value),
                    program_code_acceptable=_map_tristate(ws.cell(r, 12).value),
                    other_constraints_ok=_map_tristate(ws.cell(r, 13).value),
                    verification_2028=_map_verification_2028(ws.cell(r, 9).value),
                    key_risk=str(_clean(ws.cell(r, 10).value) or None),
                    notes=(
                        "历史数据来源为 2026/2027 年度材料；"
                        f"导入口径目标年份={self.target_year}，2028 存在性未经核验"
                    ),
                )
                self.session.add(path)
                self.session.flush()
                self.bump_inserted("admission_path")
            else:
                self.bump_skipped("admission_path")
            self._path_cache[str(legacy_id)] = path
            self._path_cache[path_key] = path

            if path.verification_2028 is not Verification2028.VERIFIED:
                report.pending_verification += 1
            for field_name, value in (
                ("full_time_ok", path.full_time_ok),
                ("program_code_acceptable", path.program_code_acceptable),
                ("other_constraints_ok", path.other_constraints_ok),
            ):
                if value is TriState.UNKNOWN:
                    report.pending_verification += 1
            if path.exam_unit4 and "待核" in str(path.exam_unit4):
                report.pending_verification += 1
            if "冲突" in str(path.key_risk or ""):
                report.conflicts += 1
                self._audit(
                    "import.risk_conflict",
                    path.path_key,
                    {"key_risk": path.key_risk, "note": "关键风险登记为冲突，保留记录不自动合并"},
                )

        for y in sorted(years):
            row = (
                self.session.execute(select(AdmissionYear).where(AdmissionYear.year == y))
                .scalar_one_or_none()
            )
            if row is None:
                self.session.add(
                    AdmissionYear(
                        year=y, catalog_published=False,
                        note=f"{y} 年招生目录未发布/未核验；导入时不得推断为已确认",
                    )
                )
                self.bump_inserted("admission_year")
            else:
                self.bump_skipped("admission_year")
        self.session.flush()

    # ---------- 评分矩阵 ----------
    def _import_score_matrix(self, wb) -> None:
        ws = wb["三级证据评分"]
        report = self.report
        for r in range(2, ws.max_row + 1):
            legacy_id = _clean(ws.cell(r, 1).value)
            l1, l2, l3 = _clean(ws.cell(r, 2).value), _clean(ws.cell(r, 3).value), _clean(ws.cell(r, 4).value)
            if not (legacy_id and l1 and l2 and l3):
                continue
            path = self._path_cache.get(str(legacy_id))
            if path is None:
                report.anomalies.append(f"三级证据评分 第{r}行的路径 {legacy_id} 未导入，已跳过")
                continue
            code = f"L3-{l1}|{l2}|{l3}"
            ind = self._indicator_cache.get(code)
            if ind is None:
                report.anomalies.append(f"三级证据评分 第{r}行指标 {code} 不存在，已跳过")
                continue
            raw_score = _clean(ws.cell(r, 5).value)
            source_ref = _clean(ws.cell(r, 6).value)
            fact_type = _clean(ws.cell(r, 7).value)
            exists = (
                self.session.execute(
                    select(ScoreRecord).where(
                        ScoreRecord.path_id == path.id,
                        ScoreRecord.indicator_id == ind.id,
                        ScoreRecord.evaluation_year == self.target_year,
                    )
                )
                .scalar_one_or_none()
            )
            if exists is not None:
                self.bump_skipped("score_record")
                continue
            score_int: int | None = None
            if isinstance(raw_score, (int, float)) and not isinstance(raw_score, bool):
                score_int = int(raw_score)
            elif isinstance(raw_score, str) and raw_score.strip().isdigit():
                score_int = int(raw_score.strip())
            self.session.add(
                ScoreRecord(
                    path_id=path.id,
                    indicator_id=ind.id,
                    evaluation_year=self.target_year,
                    raw_score=score_int,
                    source_ref_id=str(source_ref) if source_ref else None,
                    fact_type=str(fact_type) if fact_type else None,
                    validity=ScoreValidity.UNKNOWN if score_int is None else ScoreValidity.UNKNOWN,
                    note="导入自 Excel；评分有效性由证据闸门独立判定，导入阶段一律未知",
                )
            )
            self.bump_inserted("score_record")
            if score_int is None:
                report.pending_verification += 1
        self.session.flush()

    # ---------- 证据映射候选 ----------
    def _import_claims(self, wb) -> None:
        ws = wb["3_2证据映射候选"]
        report = self.report
        unregistered: set[str] = set()
        for r in range(2, ws.max_row + 1):
            legacy_id = _clean(ws.cell(r, 1).value)
            indicator_name = _clean(ws.cell(r, 5).value)
            statement = _clean(ws.cell(r, 8).value)
            raw_sources = _clean(ws.cell(r, 9).value)
            if not (legacy_id and indicator_name and statement):
                report.anomalies.append(f"证据映射候选 第{r}行缺少路径/指标/陈述，已跳过")
                continue
            path = self._path_cache.get(str(legacy_id))
            if path is None:
                report.anomalies.append(f"证据映射候选 第{r}行路径 {legacy_id} 未导入，已跳过")
                continue
            ind = self._indicator_by_name(str(indicator_name))
            if ind is None:
                report.anomalies.append(f"证据映射候选 第{r}行指标 {indicator_name} 未匹配到三级指标，已跳过")
                continue

            status_text = str(_clean(ws.cell(r, 12).value) or "")
            limitation = str(_clean(ws.cell(r, 13).value) or "")
            is_conflict = ("冲突" in status_text) or ("冲突" in limitation)
            claim_status = ClaimStatus.CONFLICT if is_conflict else ClaimStatus.CANDIDATE

            source_ids = [
                s.strip() for s in str(raw_sources or "").replace("；", ";").split(";") if s.strip()
            ]
            if not source_ids:
                report.anomalies.append(f"证据映射候选 第{r}行缺少来源ID，已跳过")
                continue

            year_hints = _extract_year_hints(str(statement))
            raw_row = {
                "excel_row": r,
                "legacy_path_id": str(legacy_id),
                "school": _clean(ws.cell(r, 2).value),
                "college": _clean(ws.cell(r, 3).value),
                "program": _clean(ws.cell(r, 4).value),
                "indicator": str(indicator_name),
                "stage": _clean(ws.cell(r, 6).value),
                "topic": _clean(ws.cell(r, 7).value),
                "source_ids": source_ids,
                "evidence_level": _clean(ws.cell(r, 10).value),
                "accessibility": _clean(ws.cell(r, 11).value),
                "excel_verification_status": status_text,
                "match_limitation": limitation,
                "scoring_status": _clean(ws.cell(r, 14).value),
                "year_hints": year_hints,
            }

            primary_source_id = source_ids[0]
            source = self._get_or_create_source(
                source_id=primary_source_id,
                title=f"（引用自 Phase 3.2 候选映射）{primary_source_id}",
                source_type=SourceType.UNKNOWN,
                verification_status=VerificationStatus.UNREGISTERED,
                verification_note=(
                    "该 source_id 仅在证据映射候选中被引用，来源本体（标题/机构/URL/时间）未登记，"
                    "不得进入正式评分"
                ),
                is_placeholder=False,
                referenced_only=True,
            )
            if source.verification_status is not VerificationStatus.VERIFIED:
                unregistered.add(primary_source_id)
                report.pending_verification += 1

            claim = (
                self.session.execute(
                    select(EvidenceClaim).where(
                        EvidenceClaim.source_id_fk == source.id,
                        EvidenceClaim.statement == str(statement),
                    )
                )
                .scalar_one_or_none()
            )
            if claim is None:
                claim = EvidenceClaim(
                    source_id_fk=source.id,
                    source_ref_id=primary_source_id,
                    statement=str(statement),
                    topic=str(_clean(ws.cell(r, 7).value) or None),
                    stage=str(_clean(ws.cell(r, 6).value) or None),
                    school_code=path.school.code if path.school else None,
                    college_code=path.college.college_code if path.college else None,
                    program_code=path.program.program_code if path.program else None,
                    applicable_years=[],  # 不做年份推断；留待人工核验
                    evidence_level=_map_evidence_level(ws.cell(r, 10).value),
                    accessibility=_map_accessibility(ws.cell(r, 11).value),
                    status=claim_status,
                    is_candidate=True,
                    match_limitation=limitation or None,
                    raw_row={**raw_row, "variants": [raw_row]},
                )
                self.session.add(claim)
                self.session.flush()
                self.bump_inserted("evidence_claim")
            else:
                # 同一（来源, 陈述）被映射到多个指标：保留全部原始行，避免留痕丢失
                base = dict(claim.raw_row or {})
                variants = list(base.get("variants") or [base])
                if raw_row not in variants:
                    variants.append(raw_row)
                claim.raw_row = {**base, "variants": variants}
                self.bump_skipped("evidence_claim")

            self._link(claim, path, ind)

            if is_conflict:
                conflict_desc = limitation or f"导入时检测到冲突：{status_text}"
                conflict = (
                    self.session.execute(
                        select(ClaimConflict).where(
                            ClaimConflict.claim_id == claim.id,
                            ClaimConflict.description == conflict_desc,
                        )
                    )
                    .scalar_one_or_none()
                )
                if conflict is None:
                    self.session.add(
                        ClaimConflict(
                            claim_id=claim.id,
                            description=conflict_desc,
                            resolved=False,
                        )
                    )
                    report.conflicts += 1
                    self.bump_inserted("claim_conflict")
                else:
                    self.bump_skipped("claim_conflict")

            for extra_id in source_ids[1:]:
                extra = self._get_or_create_source(
                    source_id=extra_id,
                    title=f"（引用自 Phase 3.2 候选映射）{extra_id}",
                    source_type=SourceType.UNKNOWN,
                    verification_status=VerificationStatus.UNREGISTERED,
                    verification_note="候选映射附加引用，来源本体未登记",
                    is_placeholder=False,
                    referenced_only=True,
                )
                unregistered.add(extra_id)
        self.session.flush()
        report.unregistered_source_ids = sorted(unregistered)

    # ---------- 待核问题 ----------
    def _import_open_questions(self, wb) -> None:
        if "待核问题" not in wb.sheetnames:
            return
        ws = wb["待核问题"]
        for r in range(2, ws.max_row + 1):
            content = _clean(ws.cell(r, 3).value)
            if not content:
                continue
            self.report.open_questions += 1
            self._audit(
                "import.open_question",
                str(_clean(ws.cell(r, 2).value) or ""),
                {
                    "priority": _clean(ws.cell(r, 1).value),
                    "content": str(content),
                    "impact": _clean(ws.cell(r, 4).value),
                    "status": _clean(ws.cell(r, 5).value),
                },
            )
            if "冲突" in str(_clean(ws.cell(r, 5).value) or ""):
                self.report.conflicts += 1
                self._audit(
                    "import.conflict_note",
                    str(_clean(ws.cell(r, 2).value) or ""),
                    {"content": str(content), "note": "登记为未解决冲突，不得自动合并"},
                )

    # ---------- 工具 ----------
    def _link(self, claim: EvidenceClaim, path: AdmissionPath, indicator: Indicator) -> None:
        link = (
            self.session.execute(
                select(ClaimPathLink).where(
                    ClaimPathLink.claim_id == claim.id, ClaimPathLink.path_id == path.id
                )
            )
            .scalar_one_or_none()
        )
        if link is None:
            self.session.add(ClaimPathLink(claim_id=claim.id, path_id=path.id, applicable=True))
            self.bump_inserted("claim_path_link")
        else:
            self.bump_skipped("claim_path_link")

        ilink = (
            self.session.execute(
                select(ClaimIndicatorLink).where(
                    ClaimIndicatorLink.claim_id == claim.id,
                    ClaimIndicatorLink.indicator_id == indicator.id,
                )
            )
            .scalar_one_or_none()
        )
        if ilink is None:
            self.session.add(
                ClaimIndicatorLink(claim_id=claim.id, indicator_id=indicator.id, supports=True)
            )
            self.bump_inserted("claim_indicator_link")
        else:
            self.bump_skipped("claim_indicator_link")

    def _indicator_by_name(self, name: str) -> Indicator | None:
        for code, ind in self._indicator_cache.items():
            if code.startswith("L3-") and ind.name == name:
                return ind
        row = (
            self.session.execute(
                select(Indicator).where(Indicator.level == 3, Indicator.name == name)
            )
            .scalars()
            .all()
        )
        return row[0] if row else None

    def _get_or_create_school(self, name: str) -> School:
        if name in self._school_cache:
            return self._school_cache[name]
        code = SCHOOL_CODE_MAP.get(name) or f"SCH-{hashlib.sha1(name.encode('utf-8')).hexdigest()[:6].upper()}"
        school = (
            self.session.execute(select(School).where(School.code == code)).scalar_one_or_none()
        )
        if school is None:
            school = School(code=code, name=name, region=REGION_MAP.get(name))
            self.session.add(school)
            self.session.flush()
            self.bump_inserted("school")
            if name not in SCHOOL_CODE_MAP:
                self.report.anomalies.append(f"学校 {name} 无既定代码映射，已生成稳定代号 {code}")
        else:
            self.bump_skipped("school")
        self._school_cache[name] = school
        return school

    def _get_or_create_college(self, school: School, college_code: str) -> College:
        key = (school.id, college_code)
        if key in self._college_cache:
            return self._college_cache[key]
        college = (
            self.session.execute(
                select(College).where(
                    College.school_id == school.id, College.college_code == college_code
                )
            )
            .scalar_one_or_none()
        )
        if college is None:
            college = College(school_id=school.id, college_code=college_code)
            self.session.add(college)
            self.session.flush()
            self.bump_inserted("college")
        else:
            self.bump_skipped("college")
        self._college_cache[key] = college
        return college

    def _get_or_create_program(self, college: College, program_code: str) -> Program:
        key = (college.id, program_code)
        if key in self._program_cache:
            return self._program_cache[key]
        program = (
            self.session.execute(
                select(Program).where(
                    Program.college_id == college.id, Program.program_code == program_code
                )
            )
            .scalar_one_or_none()
        )
        if program is None:
            program = Program(college_id=college.id, program_code=program_code)
            self.session.add(program)
            self.session.flush()
            self.bump_inserted("program")
        else:
            self.bump_skipped("program")
        self._program_cache[key] = program
        return program

    def _get_or_create_source(
        self,
        *,
        source_id: str,
        title: str,
        source_type: SourceType,
        verification_status: VerificationStatus,
        verification_note: str | None,
        is_placeholder: bool,
        referenced_only: bool = False,
    ) -> EvidenceSource:
        if source_id in self._source_cache:
            return self._source_cache[source_id]
        source = (
            self.session.execute(
                select(EvidenceSource).where(EvidenceSource.source_id == source_id)
            )
            .scalar_one_or_none()
        )
        if source is None:
            source = EvidenceSource(
                source_id=source_id,
                title=title,
                source_type=source_type,
                verification_status=verification_status,
                verification_note=verification_note,
                is_placeholder=is_placeholder,
                retrieved_at=_now(),
            )
            self.session.add(source)
            self.session.flush()
            self.bump_inserted("evidence_source")
            if referenced_only:
                self.bump_inserted("evidence_source_referenced_only")
        else:
            self.bump_skipped("evidence_source")
        self._source_cache[source_id] = source
        return source

    def bump_inserted(self, key: str, n: int = 1) -> None:
        assert self.report is not None
        self.report.bump(self.report.inserted, key, n)

    def bump_skipped(self, key: str, n: int = 1) -> None:
        assert self.report is not None
        self.report.bump(self.report.skipped, key, n)

    def _audit(self, action: str, entity_id: str, detail: dict[str, Any]) -> None:
        self.session.add(
            AuditLog(actor=self.actor, action=action, entity_type="ImportBatch",
                     entity_id=entity_id, detail=detail)
        )


def import_excel(
    session: Session, xlsx_path: str | Path, *, target_year: int = DEFAULT_EVALUATION_YEAR
) -> ImportReport:
    """便捷入口。"""
    return ExcelImporter(session, target_year=target_year).run(xlsx_path)
