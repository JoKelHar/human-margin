# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 João Harrison
"""Visual check for the budget page: every form field is 44px tall with the design
token border, at desktop (1280) and phone (390) widths. Copy tests alone missed a
regression where switching inputs to type=text dropped the type-scoped CSS, so this
renders the real page in a browser and asserts the computed box. Screenshots are
saved to tests/artifacts/. Skipped when Playwright or its browser is unavailable."""

from __future__ import annotations

from pathlib import Path

import pytest

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "web" / "budget.html").as_uri()
ARTIFACTS = ROOT / "tests" / "artifacts"
FIELD_BORDER_LIGHT = "rgb(220, 220, 215)"      # --line2 in light mode (#DCDCD7)
WIDTHS = {"desktop": 1280, "phone": 390}


def _check_at(page, name: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900 if width > 800 else 844})
    page.goto(PAGE)
    page.wait_for_selector("#form .field")
    page.evaluate("document.querySelectorAll('details').forEach(function(d){ d.open = true; });")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ARTIFACTS / f"budget-{name}-{width}.png"), full_page=True)

    boxes = page.eval_on_selector_all(
        "#form .field",
        """els => els
            .filter(el => el.offsetParent !== null)          // visible only
            .map(el => {
              const cs = getComputedStyle(el);
              return { id: el.id || el.tagName.toLowerCase(),
                       h: Math.round(el.getBoundingClientRect().height),
                       border: cs.borderTopColor, radius: cs.borderTopLeftRadius };
            })""")
    assert boxes, f"{name}: no visible form fields found"
    for b in boxes:
        assert b["h"] == 44, f"{name} {width}px: field '{b['id']}' is {b['h']}px tall, want 44"
        assert b["border"] == FIELD_BORDER_LIGHT, \
            f"{name} {width}px: field '{b['id']}' border {b['border']}, want {FIELD_BORDER_LIGHT}"
        assert b["radius"] == "10px", f"{name} {width}px: field '{b['id']}' radius {b['radius']}"


def test_budget_page_fields_are_styled_at_desktop_and_phone():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(color_scheme="light")
            for name, width in WIDTHS.items():
                _check_at(page, name, width)
            browser.close()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "executable doesn't exist" in msg or "playwright install" in msg or "browsertype" in msg:
            pytest.skip(f"Playwright browser unavailable: {exc}")
        raise
