#!/usr/bin/env python3
"""Excel -> SQLite 导入脚本（可重复执行，幂等）。

用法：
    python scripts/import_excel.py --excel data/raw/Phase3_7C_情景覆盖率门槛修复版.xlsx \
        --db data/decision.db --report reports/import_report.json

    # 仅重复导入（校验幂等）
    python scripts/import_excel.py --excel <same-file> --db <same-db> --replay-check

退出码：
    0 成功；1 失败（参数错误 / 文件缺失 / 导入异常）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from decision_system.importers.excel_importer import import_excel  # noqa: E402
from decision_system.services.db import create_sqlite_engine, init_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入 Phase 3.7C Excel 到 SQLite")
    parser.add_argument(
        "--excel",
        default=str(ROOT / "data" / "raw" / "Phase3_7C_情景覆盖率门槛修复版.xlsx"),
        help="Phase 3.7C Excel 路径（只读研究档案）",
    )
    parser.add_argument("--db", default=str(ROOT / "data" / "decision.db"), help="SQLite 路径")
    parser.add_argument("--report", default=str(ROOT / "reports" / "import_report.json"))
    parser.add_argument("--target-year", type=int, default=2028)
    parser.add_argument(
        "--replay-check",
        action="store_true",
        help="重复导入并断言不产生新记录（幂等性校验）",
    )
    args = parser.parse_args(argv)

    excel_path = Path(args.excel)
    if not excel_path.is_file():
        print(f"[FAIL] Excel 文件不存在：{excel_path}", file=sys.stderr)
        return 1

    engine = create_sqlite_engine(args.db)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    reports = []
    rounds = 2 if args.replay_check else 1
    with factory() as session:
        for i in range(rounds):
            report = import_excel(session, excel_path, target_year=args.target_year)
            session.commit()
            reports.append(report)
            print(f"[RUN {i + 1}] " + "-" * 60)
            print(report.as_text())

    if args.replay_check:
        first, second = reports[0], reports[1]
        new_inserts = {k: v for k, v in second.inserted.items() if v}
        if new_inserts:
            print("[FAIL] 重复导入产生了新记录，幂等性不成立：", new_inserts, file=sys.stderr)
            return 1
        print("[OK] 幂等性校验通过：重复导入未产生任何新记录")

    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[OK] 导入报告已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
