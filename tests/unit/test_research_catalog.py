from __future__ import annotations

import copy
import csv
import io
import json

import pytest

from decision_system.services.research_catalog import (
    CatalogError,
    csv_export,
    load_catalog,
)
from decision_system.ui.theme import table_cards


def test_complete_research_projection():
    catalog = load_catalog()
    assert len(catalog.paths) == 10
    assert len(catalog.records) == 207
    assert len({r["record_id"] for r in catalog.records}) == 207
    assert all(
        r["source_row"] >= 2 and r["source_sheet"] == "3_2证据映射候选"
        for r in catalog.records
    )


def test_search_intersects_filters_and_preserves_scope():
    catalog = load_catalog()
    results = catalog.search(path_ids=["P02"], query="具身", grade="S2")
    assert results
    assert all(r["path_id"] == "P02" and r["grade"] == "S2" for r in results)
    assert not catalog.search(path_ids=[])
    assert not catalog.search(query="不存在的主题xyz")


def test_search_multiple_terms_and_case_insensitive():
    catalog = load_catalog()
    assert catalog.search(query="AI") == catalog.search(query="ai")
    results = catalog.search(query="具身 导师")
    assert results
    assert all("具身" in str(r) and "导师" in str(r) for r in results)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_path", "dangling_record", "wrong_index", "index_missing_row"],
)
def test_rejects_inconsistent_catalog(tmp_path, mutation):
    data = copy.deepcopy(load_catalog().data)
    if mutation == "duplicate_path":
        data["paths"].append(data["paths"][0])
    elif mutation == "dangling_record":
        data["research_flat"][0]["path_id"] = "OTHER"
    elif mutation == "wrong_index":
        data["research_by_path"]["OTHER"] = data["research_by_path"].pop("P01")
    else:
        data["research_by_path"]["P01"].pop()
    path = tmp_path / "research.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(path)


def test_catalog_updates_without_process_restart(tmp_path):
    data = load_catalog().data
    path = tmp_path / "research.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    first = load_catalog(path).digest
    data["source_year_note"] = "Updated source note"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert load_catalog(path).digest != first


def test_csv_export_preserves_unicode_and_blocks_formula_injection():
    raw = csv_export(
        [{"statement": "  =HYPERLINK(1)", "source_id": "@test", "school": "东南大学"}]
    )
    row = next(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert row["statement"].startswith("'")
    assert row["source_id"].startswith("'")
    assert row["school"] == "东南大学"


def test_mobile_cards_escape_all_research_text_and_keep_columns():
    cards = table_cards(
        [
            {
                "学院": "人工智能",
                "原文": '<script>alert("x")</script>',
                "未知名额": "暂无数据",
            }
        ]
    )
    assert "<script>" not in cards
    assert "&lt;script&gt;" in cards
    assert "未知名额" in cards and "暂无数据" in cards and "人工智能" in cards
