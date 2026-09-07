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


def test_prep_uses_structured_match_plan_with_legacy_fallback():
    javascript = (DOCS / "app.js").read_text()
    html = (DOCS / "index.html").read_text()
    stylesheet = (DOCS / "style.css").read_text()

    assert "function renderMatchPlan" in javascript
    assert "plan.tactics.length === 3" in javascript
    assert "generated_game_plan" in javascript
    assert 'id="prep-plan"' in html
    assert ".plan-tactics" in stylesheet
    assert ".plan-focus" in stylesheet


def test_profile_screen_collects_durable_context():
    javascript = (DOCS / "app.js").read_text()
    html = (DOCS / "index.html").read_text()

    assert 'id="screen-profile"' in html
    assert 'name="level"' in html
    assert 'name="experience"' in html
    assert 'name="playing_style"' in html
    assert 'name="strengths"' in html
    assert 'name="medical_context"' in html
    assert 'apiFetch("/api/profile"' in javascript
    assert 'method: "PUT"' in javascript


def test_match_score_uses_scrollable_set_wheels():
    javascript = (DOCS / "app.js").read_text()
    html = (DOCS / "index.html").read_text()
    stylesheet = (DOCS / "style.css").read_text()

    assert 'id="set-score-rows"' in html
    assert 'id="add-set-button"' in html
    assert 'id="remove-set-button"' in html
    assert "function createScoreWheel" in javascript
    assert "scroll-snap-type: y mandatory" in stylesheet
    assert ".score-wheel-option.is-selected" in stylesheet


def test_changeover_uses_two_fast_multiselect_dictionaries():
    javascript = (DOCS / "app.js").read_text()
    stylesheet = (DOCS / "style.css").read_text()

    assert "const SELF_ISSUES" in javascript
    assert "const OPPONENT_ACTIONS" in javascript
    assert 'name="score_state"' in javascript
    assert 'name="set_stage"' in javascript
    assert 'id="event-comment"' in javascript
    assert "querySelector('button[type=\"submit\"]')" in javascript
    assert "TOPICS" not in javascript
    assert ".observation-chip" in stylesheet
    assert "min-height: 52px" in stylesheet


def test_review_and_prep_expose_opponent_memory():
    javascript = (DOCS / "app.js").read_text()
    html = (DOCS / "index.html").read_text()

    assert 'name="own_errors"' in javascript
    assert 'name="emotional_state"' in javascript
    assert 'name="opponent_what_worked"' in javascript
    assert 'name="opponent_errors"' in javascript
    assert 'name="advice_changed_play"' in javascript
    assert 'id="opponent-card"' in html
    assert "/api/opponents/history" in javascript


def test_completed_match_can_be_deleted_from_history_with_confirmation():
    javascript = (DOCS / "app.js").read_text()
    stylesheet = (DOCS / "style.css").read_text()

    assert "function deleteMatchFromHistory" in javascript
    assert "window.confirm" in javascript
    assert 'method: "DELETE"' in javascript
    assert "/permanent" in javascript
    assert "Удалить матч из истории" in javascript
    assert ".history-actions" in stylesheet
