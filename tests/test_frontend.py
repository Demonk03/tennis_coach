import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_manifest_icons_exist_and_are_png():
    manifest = json.loads((DOCS / "manifest.json").read_text())

    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    for icon in manifest["icons"]:
        path = DOCS / icon["src"]
        assert path.exists()
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_javascript_id_selectors_exist_in_html():
    html = (DOCS / "index.html").read_text()
    javascript = (DOCS / "app.js").read_text()
    html_ids = set(re.findall(r'id="([^"]+)"', html))
    html_ids.update(re.findall(r'id="([^"]+)"', javascript))
    referenced_ids = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', javascript))

    assert referenced_ids - html_ids == set()


def test_frontend_config_does_not_contain_secret():
    config = (DOCS / "config.js").read_text()

    assert "API_KEY" not in config
    assert "Bearer" not in config



def test_pult_screens_and_assets_are_present():
    html = (DOCS / "index.html").read_text()
    css = (DOCS / "style.css").read_text()
    for screen in ("prep", "plan", "match", "observation", "advice", "finish", "review", "history", "details", "dossier", "profile", "settings", "error"):
        assert f'id="screen-{screen}"' in html
    assert "support.js" not in html
    assert "prefers-reduced-motion" in css
    assert "scroll-snap-type: y mandatory" in css
    assert 'data-theme="dark"' in css


def test_ui_behavior_suite_exists():
    # Behavior is exercised in Node's jsdom suite, not through fragile source substrings.
    assert (ROOT / "tests" / "pult-ui.test.cjs").is_file()
