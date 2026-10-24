from __future__ import annotations

import importlib.util
import io
import subprocess
import tomllib
import zipfile
from pathlib import Path

from decision_system.ui.viewmodels import EXAMPLE_BACKGROUND, USER_CONFIRMED_BACKGROUND

ROOT = Path(__file__).resolve().parents[2]


def checker():
    spec = importlib.util.spec_from_file_location(
        "release_secrets", ROOT / "scripts" / "check_secrets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mit_metadata_and_third_party_boundary_are_shipped():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["license"] == "MIT"
    assert set(metadata["project"]["license-files"]) == {"LICENSE", "NOTICE"}
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "does not grant rights to third-party content" in (
        ROOT / "NOTICE"
    ).read_text(encoding="utf-8")
    assert "LICENSE NOTICE" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_public_default_is_example_and_legacy_import_remains_compatible():
    assert USER_CONFIRMED_BACKGROUND is EXAMPLE_BACKGROUND
    text = repr(EXAMPLE_BACKGROUND)
    assert "示例" in text
    assert "信息与计算科学" not in text and "不强制上海" not in text


def test_deleted_secret_is_found_in_history_without_printing_value(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True
        )

    git("init")
    git("config", "user.name", "Example")
    git("config", "user.email", "example@users.noreply.github.com")
    token = "ghp_" + "a" * 36
    path = tmp_path / "temporary.txt"
    path.write_text(token, encoding="utf-8")
    git("add", "temporary.txt")
    git("commit", "-m", "first")
    path.unlink()
    git("add", "-u")
    git("commit", "-m", "remove")
    hits, scanned, _ = checker().scan_history(tmp_path)
    assert scanned > 0 and any("github-token" in hit for hit in hits)
    assert token not in repr(hits)


def test_spreadsheet_xml_is_scanned_for_secrets():
    raw = io.BytesIO()
    token = "ghp_" + "b" * 36
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", f"<text>{token}</text>")
    hits, skipped = checker().inspect_blob(raw.getvalue(), "sample.xlsx")
    assert not skipped
    assert any("sharedStrings.xml" in hit and "github-token" in hit for hit in hits)
    assert token not in repr(hits)


def test_private_state_is_rejected_but_env_example_is_allowed():
    check = checker()
    for name in (
        ".env",
        ".env.production",
        "data/local.db",
        "other/decision_profile.json",
    ):
        assert check.is_private_file(name)
    assert not check.is_private_file(".env.example")
    assert not check.is_private_file("data/school_research_consolidated.json")
