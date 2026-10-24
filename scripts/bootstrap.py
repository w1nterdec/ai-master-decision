#!/usr/bin/env python3
"""Rebuild a complete installation from tracked research files, idempotently."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from decision_system.importers.excel_importer import import_excel
from decision_system.services.db import (
    create_sqlite_engine,
    init_db,
    make_session_factory,
)
from export_consolidated import DEFAULT_EXCEL, DEFAULT_OUT, export
import migrate_bupt_phase5_0 as migration


def bootstrap(db_path: Path, *, projection: bool = True) -> dict:
    engine = create_sqlite_engine(db_path)
    init_db(engine)
    try:
        with make_session_factory(engine)() as session:
            report = import_excel(session, Path(DEFAULT_EXCEL))
            session.commit()
    finally:
        engine.dispose()
    old = migration.DB_PATH, migration.BACKUP_PATH
    migration.DB_PATH = db_path
    migration.BACKUP_PATH = (
        db_path.parent / "backup" / f"{db_path.name}.before-official-evidence"
    )
    try:
        migrated = migration.run(apply=True)
    finally:
        migration.DB_PATH, migration.BACKUP_PATH = old
    if migrated["warnings"]:
        raise RuntimeError(f"官方历史资料关联不完整：{migrated['warnings']}")
    if projection:
        export(DEFAULT_EXCEL, DEFAULT_OUT)
    return {"imported": report.to_dict(), "migration": migrated}


def main() -> None:
    # Windows redirected stdout may default to cp1252 even when all input files are UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("DECISION_DB_PATH", ROOT / "data" / "decision.db")),
    )
    parser.add_argument("--skip-projection", action="store_true")
    args = parser.parse_args()
    result = bootstrap(args.db, projection=not args.skip_projection)
    print(f"[OK] 数据初始化完成：{args.db}")
    print(
        f"[OK] 历史来源 {len(result['migration']['sources'])} 条；不确认任何 2028 招生资格"
    )


if __name__ == "__main__":
    main()
