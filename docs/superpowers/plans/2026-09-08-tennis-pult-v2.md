# Tennis Pult v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the approved Pult redesign, preserving existing matches and legacy clients.

**Architecture:** Keep the static vanilla PWA and Flask/Supabase. Add a versioned API implementation, transactional database RPCs for durable operations and preparation updates, and read models for complete history/dossiers. No production migration runs before backup and verification.

**Tech Stack:** Python, Flask, PostgreSQL/Supabase, vanilla JavaScript, CSS, pytest.

## Handoff audit

The v2 functional spec is byte-identical to the approved spec. Use `Tennis App Pult v2.dc.html` for visuals; the bundled README and `Tennis App 1c.dc.html` are v1 references. Do not copy demo data, mixed-name dossier records, fake drafts/statuses, click-only wheel simulation, or inactive month controls. Correct small targets and dark accent contrast while retaining the visual language.

## Task 1: Data safety and versioned operations

Files: `supabase/migrations/20260908_pult_v2.sql`, `db.py`, `pult.py`, `tests/test_pult.py`.

- [x] Add tests for contract validation, retries, immutable preparation, new-set semantics and statistics.
- [x] Add nullable fields and RLS-protected operation/cache/context tables; transactional claim/commit with lease fencing, revision checks and atomic preparation replacement.
- [x] Add DB methods and versioned route dispatch without removing legacy APIs.
- [x] Run targeted pytest and SQL migration checks on disposable PostgreSQL if available.

## Task 2: AI and history

Files: `pult.py`, `gpt.py`, `db.py`, `tests/test_pult.py`, `tests/test_gpt.py`.

- [x] Implement optional review fields, independent app-helpful metric, source-backed cached dossiers covering all records.
- [x] Add paginated match/opponent reads and full-period stats; preserve exact login identities.
- [x] Verify source validation, old data fallbacks, unknown outcomes and datasets over old limits.

## Task 3: PWA

Files: `docs/index.html`, `docs/app.js`, `docs/style.css`, `docs/manifest.json`, `tests/test_frontend.py`.

- [x] Implement the visual shell and all approved screens using real data, accessible controls and themes.
- [x] Preserve preparation/review/event/finish drafts and operation identities through errors and reopening.
- [x] Implement score wheels, persistent action footer, complete history, dossier search and deferred review.
- [x] Update behavior checks and run JavaScript syntax/DOM verification.

## Task 4: Verification and delivery

Files: `tests/`, `docs/superpowers/plans/2026-09-08-tennis-pult-v2.md`, `CLAUDE.md`, deployment notes.

- [x] Run `python3 -m pytest -q`, `python3 -m py_compile app.py db.py gpt.py pult.py`, `node --check docs/app.js`.
- [x] Inspect real PWA in browser with a local fixture API; exercise preparation, new set, finish, deferred review, history, drafts/errors and both themes.
- [x] Document backup-first rollout and verification of old records. Do not claim deployed or migrated without actual evidence.
- [x] Review diff and commit verified implementation; deliver outcome and any environment-specific rollout limitation.

## Verification evidence — 2026-09-08

- Python: 74 tests passed. Node: 10 tests passed (9 interface behavior checks and an actual PGlite migration/transaction scenario).
- Additive SQL applied twice to disposable legacy records: all original IDs and column values preserved. Verified revision conflicts, immutable started prep, legacy style snapshots, idempotent retries, lease fencing and restricted RPC access.
- Browser at localhost with disposable memory API: preparation, replacement within the same match, start, changeover, new set, wheel finish, deferred review from journal, dossier source links, light/dark themes, 320 px layout, persisted preparation/observation drafts after reload.
- Browser check found and fixed missing OPTIONS routes for preparation update and poor selected-chip contrast in dark mode. UI checks cover lost responses, connection changes, all 700 characters of advice and legacy plan text. AI dossier test covers all 31 original sources across batching and lease renewal.
- Actual iPhone keyboard, real OpenAI responses, VPN/Railway connectivity and production-data copy migration remain release-environment checks. No production migration or deployment was performed.
- Rollout: `docs/deployment/pult-v2.md`. Backup + restored-copy verification are mandatory before production migration. Destructive Oura migration excluded.
- Package-lock download was declined; direct test dependency versions are pinned in package.json, and verification used previously installed temporary dependencies. No application build dependencies were introduced.
