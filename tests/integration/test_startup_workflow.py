from __future__ import annotations

import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launcher(monkeypatch):
    for key in (
        "DECISION_DB_PATH",
        "DECISION_ARCHIVE_PATH",
        "STREAMLIT_SERVER_PORT",
        "STREAMLIT_SERVER_ADDRESS",
    ):
        monkeypatch.delenv(key, raising=False)
    spec = importlib.util.spec_from_file_location(
        "test_launcher", ROOT / "scripts" / "start.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_initialization_is_isolated_and_replayable(
    launcher, tmp_path, monkeypatch
):
    formal = tmp_path / "formal.db"
    formal.write_bytes(b"preserve formal data")
    monkeypatch.setenv("DECISION_DB_PATH", str(formal))
    demo = tmp_path / "demo"
    args = [
        "--demo",
        "--demo-dir",
        str(demo),
        "--env-file",
        str(tmp_path / "missing.env"),
        "--prepare-only",
    ]
    assert launcher.main(args) == 0
    assert launcher.main(args) == 0
    assert formal.read_bytes() == b"preserve formal data"
    with sqlite3.connect(demo / "decision.db") as conn:
        assert conn.execute("SELECT count(*) FROM school").fetchone()[0] == 5
        assert conn.execute("SELECT count(*) FROM admission_path").fetchone()[0] == 10
    assert not (demo / "decision_profile.json").exists()


def test_environment_beats_dotenv_and_child_gets_resolved_paths(
    launcher, tmp_path, monkeypatch
):
    env_file = tmp_path / "sample.env"
    env_file.write_text(
        "DECISION_DB_PATH=must-not-win.db\nSTREAMLIT_SERVER_PORT=8510\n",
        encoding="utf-8",
    )
    db = tmp_path / "chosen.db"
    monkeypatch.setenv("DECISION_DB_PATH", str(db))
    monkeypatch.setenv("DECISION_ARCHIVE_PATH", str(tmp_path / "archive.json"))
    seen = {}

    def run(command, *, cwd, env):
        seen.update(command=command, cwd=cwd, env=env)
        return 0

    monkeypatch.setattr(launcher.subprocess, "call", run)
    assert launcher.main(["--env-file", str(env_file), "--port", "8512"]) == 0
    assert seen["env"]["DECISION_DB_PATH"] == str(db)
    assert seen["cwd"] == ROOT
    assert "8512" in seen["command"]
    assert not (ROOT / "must-not-win.db").exists()


def test_invalid_port_does_not_prepare_data(launcher, tmp_path):
    assert (
        launcher.main(["--demo", "--demo-dir", str(tmp_path / "unused"), "--port", "0"])
        == 1
    )
    assert not (tmp_path / "unused").exists()


def test_database_uri_is_rejected_without_echoing_credentials(
    launcher, tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv(
        "DECISION_DB_PATH", "postgresql://" + "person:privatevalue" + "@host/db"
    )
    assert (
        launcher.main(["--prepare-only", "--env-file", str(tmp_path / "missing.env")])
        == 1
    )
    captured = capsys.readouterr()
    assert "privatevalue" not in captured.err
    assert "PostgreSQL" in captured.err
