"""Read-only research projection. Research rows never grant eligibility or scores."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "data" / "school_research_consolidated.json"


class CatalogError(ValueError):
    """The projection is missing, corrupt, or internally inconsistent."""


@dataclass(frozen=True)
class ResearchCatalog:
    data: dict[str, Any]
    digest: str

    @property
    def paths(self) -> list[dict]:
        return self.data["paths"]

    @property
    def records(self) -> list[dict]:
        return self.data["research_flat"]

    @property
    def themes(self) -> list[str]:
        return sorted({r["theme"] for r in self.records if r.get("theme")})

    def for_path(self, legacy_id: str | None) -> list[dict]:
        return [r for r in self.records if r["path_id"] == legacy_id]

    def search(
        self,
        *,
        query: str = "",
        path_ids: Iterable[str] | None = None,
        theme: str | None = None,
        grade: str | None = None,
    ) -> list[dict]:
        ids = None if path_ids is None else set(path_ids)
        terms = query.casefold().split()
        return [
            r
            for r in self.records
            if (ids is None or r["path_id"] in ids)
            and (theme is None or r.get("theme") == theme)
            and (grade is None or r.get("grade") == grade)
            and all(
                t in " ".join(str(v or "") for v in r.values()).casefold()
                for t in terms
            )
        ]


def load_catalog(path: Path = CATALOG_PATH) -> ResearchCatalog:
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise CatalogError(
            "研究数据无法读取，请运行 python scripts/bootstrap.py 重建。"
        ) from exc
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("paths"), list)
        or not isinstance(data.get("research_flat"), list)
    ):
        raise CatalogError("研究数据结构不完整。")
    paths, records = data["paths"], data["research_flat"]
    if not paths or any(not isinstance(p, dict) or not p.get("path_id") for p in paths):
        raise CatalogError("路径身份缺失。")
    ids = [p["path_id"] for p in paths]
    if len(ids) != len(set(ids)):
        raise CatalogError("路径编号重复，无法安全关联研究资料。")
    if any(
        not isinstance(r, dict) or r.get("path_id") not in ids or not r.get("statement")
        for r in records
    ):
        raise CatalogError("存在无正文或未关联路径的研究资料。")
    grouped = data.get("research_by_path")
    if not isinstance(grouped, dict) or any(
        not isinstance(v, list) for v in grouped.values()
    ):
        raise CatalogError("研究资料索引缺失。")
    canonical = lambda rows: Counter(
        json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows
    )
    if canonical(records) != canonical(
        r for values in grouped.values() for r in values
    ):
        raise CatalogError("研究资料索引与正文不一致，请重建数据。")
    for pid, values in grouped.items():
        if pid not in ids or any(r.get("path_id") != pid for r in values):
            raise CatalogError("研究资料被关联到错误路径。")
    return ResearchCatalog(data, hashlib.sha256(raw).hexdigest())


def csv_export(records: Iterable[dict]) -> bytes:
    """UTF-8 BOM for Excel; neutralize spreadsheet formulas in untrusted research text."""
    fields = [
        "record_id",
        "path_id",
        "school",
        "college",
        "program",
        "theme",
        "indicator",
        "statement",
        "grade",
        "source_id",
        "verify_status",
        "match_limit",
        "source_sheet",
        "source_row",
    ]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        safe = {}
        for key in fields:
            value = str(record.get(key) or "")
            safe[key] = (
                "'" + value
                if value.lstrip().startswith(("=", "+", "-", "@"))
                else value
            )
        writer.writerow(safe)
    return out.getvalue().encode("utf-8-sig")
