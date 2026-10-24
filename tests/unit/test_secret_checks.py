from __future__ import annotations

import importlib.util
from pathlib import Path


def test_secret_checks_return_only_locations_and_rule_names():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_secrets.py"
    spec = importlib.util.spec_from_file_location("secret_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    token = "ghp_" + "a" * 36
    found = module.findings("safe\n" + token)
    assert found == [(2, "github-token")]
    assert token not in repr(found)
    assert module.findings("http://127.0.0.1:8501") == []
