import pytest
pw = pytest.importorskip("playwright.sync_api")   # pip install playwright && playwright install chromium; server on :8000
def test_ui_flow():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto("http://localhost:8000")
        pg.fill("#m", "PayFlow 504 timeout"); pg.press("#m", "Enter"); pg.fill("#m", "prod"); pg.press("#m", "Enter")
        pg.get_by_text("Still stuck").click(); pg.get_by_text("Submit").click()
        pg.wait_for_selector("text=Created INC"); b.close()
