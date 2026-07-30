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


def test_match_history_exposes_result_and_set_winner_styles():
    javascript = (DOCS / "app.js").read_text()
    stylesheet = (DOCS / "style.css").read_text()

    assert 'badge.textContent = "W"' in javascript
    assert 'badge.textContent = "L"' in javascript
    assert 'set.self > set.opponent ? "strong"' in javascript
    assert 'set.opponent > set.self ? "strong"' in javascript
    assert ".match-list-item.result-win" in stylesheet
    assert ".match-list-item.result-loss" in stylesheet
