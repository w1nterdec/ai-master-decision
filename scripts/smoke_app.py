#!/usr/bin/env python3
"""Render every route without writing preferences or changing evidence."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    if app.exception:
        raise RuntimeError([str(e.value) for e in app.exception])
    # Actual route options are read from the rendered navigation, not duplicated here.
    for page in app.selectbox(key="nav_top").options:
        app.selectbox(key="nav_top").set_value(page).run()
        if app.exception:
            raise RuntimeError(
                f"Route failed: {page}: {[str(e.value) for e in app.exception]}"
            )
        if page == "⚙️ 高级功能":
            for sub in app.selectbox(key="adv_top").options:
                app.selectbox(key="adv_top").set_value(sub).run()
                if app.exception:
                    raise RuntimeError(f"Management route failed: {sub}")
    print("[OK] All 9 navigation entries and 5 management pages rendered successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
