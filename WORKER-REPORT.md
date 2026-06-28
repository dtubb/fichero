# Worker Report — Repo Hygiene & Structure batch

**Worker:** Claude (opus) · **Date:** 2026-06-28 · **Branch:** `lane/archdocs`
**Base:** reset to `origin/main` (`40736aab`) · **Milestone:** Repo Hygiene & Structure (#103)
**Not pushed.** 3 commits, each gated.

## Milestone triage (8 open issues)

| # | Title | Verdict |
|---|---|---|
| **#2657** | EngineHarness assumes retired `fichero-0.0.2` layout | ✅ **DONE** |
| **#2702** | Publicization: de-personalize repo | ⚠️ **PARTIAL** — did the safe mechanical path slice; corpus/email review stays for Daniel (issue left open) |
| **#2600** | Overnight review findings | ✅ closed-out — see below |
| #2705 | Archived unmerged commits from deleted branches | skip — informational capture log, no code work |
| #2594 | reorg: consolidate execution subsystem | skip — large reorg, contract-test risk (memory: reorg-hold-then-salvage) |
| #2577 | decision: top-level component layout | skip — **decision**, design-blocked |
| #2576 | fichero-mcp top-level + external MCP | skip — large refactor/feature |
| #2575 | feat: fichero-web full client | skip — feature, not hygiene |

## What I shipped

### 1. `fix(tests): EngineHarness repo discovery checkout-name agnostic` (#2657) — `51491863`
- `EngineHarness.repoRoot()` hardcoded `fichero-0.0.2/` (retired — repo renamed to
  `~/code/fichero`, 0.0.2 merged via #2652). The test bundle lives in DerivedData so
  the bundle walk-up rarely reaches the repo; it fell back to the dead
  `~/code/fichero-0.0.2` path.
- Fix (iterate-not-replace): also probe up from `#filePath`
  (`<repo>/fichero/fichero-tests/EngineHarness.swift`) → name-agnostic discovery;
  dropped the dead `fichero-0.0.2` child probe; updated the last-resort fallback to
  `~/code/fichero`.
- **Gate:** swiftlint clean (exit 0; pre-existing line-202 nesting warning unrelated).
  No xcodebuild (HARD rule — Daniel's machine).

### 2. `chore(hygiene): de-hardcode personal /Users/danieltubb paths` (#2702 slice) — `e6b16e4d`
- `test_full_book_catalogue_e2e.py`: removed the hardcoded personal iCloud
  `DEFAULT_BOOK`; the opt-in fixture path now comes solely from
  `FICHERO_FULL_BOOK_E2E_PDF` (skips cleanly when unset). Added regression test
  `test_book_path_has_no_hardcoded_default`.
- `MEMORY.md`: generalized the retired `~/code/fichero-0.0.2/.venv` `FICHERO_PYTHON_BIN`
  example to a path-agnostic instruction.
- Confirmed zero `/Users/danieltubb` left in the touched shipped files.
- **Scope note:** only the mechanical path de-hardcode. #2702's corpus-removal +
  personal-email decisions need Daniel's judgment → **issue stays open**.
- **Gate:** ruff clean; pytest `3 passed, 1 skipped`.

### 3. `test(security): direct SSRF matrix coverage for url_security guard` (#2600/#2593) — `9ad1e9cc`
- **Verified #2600's findings before acting:** the #2590 library_links read-path authz
  WARN is **already fixed on main** (all read endpoints declare `require_library_path`
  + `request_actor`); the #2593 router-independent SSRF coverage the review asked for
  **already exists** (`test_research_tools_ssrf.py`). The remaining genuine gap was the
  **canonical guard** `fichero.url_security.is_safe_url` / `is_internal_ip` — exercised
  only indirectly.
- New `test_url_security.py` (25 cases): blocked schemes, embedded credentials,
  missing scheme/hostname, loopback/private/link-local ranges, IPv6 loopback, cloud
  metadata hosts+literals, public-IP allow, `allow_userinfo` gate. IP-literal /
  known-metadata-host based → no live DNS; `asyncio.run` matches sibling convention.
  Router-independent, survives the planned #2593 router deletion.
- **Gate:** ruff clean; pytest `25 passed`.

## Gates (from this worktree)
- `ruff check fichero-engine/src/` → **All checks passed**
- `PYTHONPATH=fichero-engine/src pytest <changed>` → **28 passed, 1 skipped** (venv:
  `~/code/fichero/.venv` — this worktree has none, per the MEMORY note I just fixed)
- swiftlint (EngineHarness) → clean
- No new mutating API routes added → write-authorized-DB guardrail N/A.

## Notes / handoff
- **#2657** ready to close once Daniel runs the Swift test target (I can't — GUI-focus
  HARD rule).
- **#2702** stays open: only the path slice landed; corpus + personal-email decisions
  are Daniel's call.
- **#2600** can be closed: every finding is either [OK], already-fixed-on-main, or
  already-covered; the one real gap (url_security direct tests) is now filled.
- Not pushed.
