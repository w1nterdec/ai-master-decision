from __future__ import annotations

import json

import pytest

from decision_system.services import view_service
from decision_system.ui.viewmodels import DecisionArchive


def test_failed_atomic_write_keeps_existing_archive(tmp_path, monkeypatch):
    path = tmp_path / "archive.json"
    monkeypatch.setattr(view_service, "ARCHIVE_PATH", path)
    view_service.save_archive(DecisionArchive(notes=["原始备注"]))
    original = path.read_bytes()

    def fail(*args):
        raise OSError("simulated write failure")

    monkeypatch.setattr(view_service.os, "replace", fail)
    with pytest.raises(OSError):
        view_service.save_archive(DecisionArchive(notes=["新备注"]))
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]
    assert json.loads(original)["notes"] == ["原始备注"]
