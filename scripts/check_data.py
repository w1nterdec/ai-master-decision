#!/usr/bin/env python3
"""Fail CI if tracked JSON drifts from the complete tracked workbook projection."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from decision_system.services.research_catalog import load_catalog
from export_consolidated import DEFAULT_EXCEL, export


def main() -> None:
    catalog = load_catalog()
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / "projection.json"
        export(DEFAULT_EXCEL, str(target))
        if catalog.data != json.loads(target.read_text(encoding="utf-8")):
            raise SystemExit(
                "[FAIL] Research projection differs from Excel. Run scripts/export_consolidated.py."
            )
    print(
        f"[OK] {len(catalog.paths)} paths / {len(catalog.records)} research mappings; projection matches workbook"
    )


if __name__ == "__main__":
    main()
