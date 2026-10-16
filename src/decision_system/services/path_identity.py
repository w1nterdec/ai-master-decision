"""招生路径身份（path_key）生成与解析。

**禁止**使用「学校名称 + 专业代码」作为唯一标识。
一条路径的身份 = 学校码 + 学院码 + 专业码 + 学习方式 + 方向 + 招生年份 + 招生方式 + 路径角色。
因此：不同年份、不同学院、一志愿与调剂都会得到不同的 path_key，互不覆盖。
"""

from __future__ import annotations

import re

from decision_system.models.enums import AdmissionMethod, PathKind, StudyMode

SEP = "|"


def _norm(value: object) -> str:
    if value is None:
        return "NA"
    if isinstance(value, StudyMode) or isinstance(value, AdmissionMethod) or isinstance(value, PathKind):
        text = str(value.value)
    else:
        text = str(value)
    text = text.strip()
    return text or "NA"


def build_path_key(
    *,
    school_code: str,
    college_code: str,
    program_code: str,
    admission_year: int,
    study_mode: object,
    direction: object,
    admission_method: object,
    path_kind: object = PathKind.FIRST_CHOICE,
) -> str:
    parts = [
        _norm(school_code),
        _norm(college_code),
        _norm(program_code),
        _norm(study_mode),
        _norm(direction),
        str(int(admission_year)),
        _norm(admission_method),
        _norm(path_kind),
    ]
    key = SEP.join(parts)
    return re.sub(r"\s+", "", key)


def parse_path_key(path_key: str) -> dict[str, str]:
    parts = path_key.split(SEP)
    if len(parts) != 8:
        raise ValueError(f"path_key 结构非法（应为 8 段）：{path_key}")
    keys = [
        "school_code",
        "college_code",
        "program_code",
        "study_mode",
        "direction",
        "admission_year",
        "admission_method",
        "path_kind",
    ]
    return dict(zip(keys, parts))
