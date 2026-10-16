#!/usr/bin/env python3
"""对数据库中的全部路径执行独立决策评估，并输出 JSON / Markdown 报告。

用法：
    python scripts/run_decision.py --db data/decision.db --out reports/decision_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from decision_system.engine.pipeline import EngineConfig  # noqa: E402
from decision_system.models.entities import AdmissionPath  # noqa: E402
from decision_system.services.db import create_sqlite_engine, init_db  # noqa: E402
from decision_system.services.decision_service import (  # noqa: E402
    build_engine,
    path_context_from_db,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="运行独立决策引擎")
    parser.add_argument("--db", default=str(ROOT / "data" / "decision.db"))
    parser.add_argument("--out", default=str(ROOT / "reports" / "decision_report.json"))
    parser.add_argument("--threshold", type=float, default=0.8)
    parser.add_argument("--year", type=int, default=2028)
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"[FAIL] 数据库不存在：{db_path}（请先运行 scripts/import_excel.py）", file=sys.stderr)
        return 1

    engine = create_sqlite_engine(db_path)
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with factory() as session:
        paths = session.execute(select(AdmissionPath)).scalars().all()
        dec_engine = build_engine(session, EngineConfig(
            coverage_threshold=args.threshold, evaluation_year=args.year
        ))
        results = [
            dec_engine.evaluate(path_context_from_db(session, p)).to_dict() for p in paths
        ]

    payload = {
        "engine_version": "0.4.0",
        "evaluation_year": args.year,
        "coverage_threshold": args.threshold,
        "disclaimer": "输出不含录取概率，不构成录取预测或院校排名",
        "paths": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 已评估 {len(results)} 条路径 -> {out}")
    for r in results:
        hc = r["hard_constraint"]
        print(
            f"  {r['label'][:28]:<30} 准入={hc['eligibility']:<4} "
            f"2028={hc['qualification_2028']:<12} "
            f"基础覆盖={r['base']['weight_coverage']:.3f} 状态={r['base']['status']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
