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
