from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_bootstrap_handles_western_windows_stdout(tmp_path):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "bootstrap.py"),
            "--db",
            str(tmp_path / "local.db"),
            "--skip-projection",
        ],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        cwd=root,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "数据初始化完成" in result.stdout.decode("utf-8")
