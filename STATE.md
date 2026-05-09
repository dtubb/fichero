# STATE.md — Fichero

## Current Focus

**Branch:** `0.0.2` — pushed `52af797b` (37 commits ahead since 2026-05-01).
Catalogue pipeline now per-page end-to-end (Phase E multi-output + Phase
C/D cleanup tools); inspector V2 has the Finder Get Info shape Daniel
asked for; Debug iteration loop down to ~5s thanks to Embed-skip on
Debug. Apple Intelligence runs locally via on-device Foundation Models.

**Goal:** Daniel runs the new Catalogue pipeline on a real folder and
confirms per-file artifacts land + KG inspector reads well, then we
move to release packaging (#658–#660).

## Open Issues (0.0.2 milestone)

**Release pipeline (Daniel-blocked):**
| # | Title | Status |
|---|---|---|
| #658 | Set up fichero-releases GitHub repo | Needs Daniel to create repo |
| #659 | Build, sign, notarize 0.0.2 DMG | Blocked on #658 + Apple notarytool creds |
| #660 | Dry-run install 0.0.2 on Daniel's machine | Blocked on #659 |
| #661 | Add Fichero download page to tubb.ca | Content writing |
| #662 | Update tubb.ca/fichero with release notes | Content writing |

**Engineering — open or deferred:**
| # | Title | Status |
|---|---|---|
| #178/#803 | Phase C: page_cleanup tool | ✅ Shipped 2026-05-04 |
| #179/#804 | Phase D: folder_cleanup tool | ✅ Shipped 2026-05-04 |
| #180/#805 | Phase E: multi-output catalogue | ✅ Shipped 2026-05-04 |
| #806 | Duplicate Apple Intelligence in model picker | ✅ Closed (dedup at startup) |
| #807 | Phantom SourceKit "Self has no member" errors | ✅ Closed (3 real lint fixes) |
| #720 | Catalogue (composable) doesn't emit combined artifact | Resolved by Phase E (multi-output) |
| #721 | Inspector shows parent's container artifacts on child page | Inspector V2 ships per-doc strict scope |
| #702 | Drag-drop folder onto PDF row | Validation matrix, not started |
| #598 | Sidebar drop routes to selected row, not cursor target | Pending |

## In Progress

- Inspector V2 Phase 2 (#156): RTF-editable panels ✓, delete ✓, AI
  display attributes (deferred), per-type artifact payloads (deferred).

## Blocked

Nothing right now. Daniel needs to test the new pipeline end to end on
a real folder before the release packaging path opens up.

## In Progress

- **LLM-stack overhaul (#872 master plan)** — 15 issues closed overnight; archive in HISTORY.md.
- Inspector V2 Phase 2 (#156) — RTF panels shipped; AI display attributes + payload types still pending.

## Blocked

- #854 Apple Intelligence proactive token budgeting — waiting on macOS SDK 26.4 release.

**Decisions logged (Daniel approved):**
- Theme C: stay on fm-bridge as canonical Apple integration.
- Theme A: do the LLMProvider Protocol refactor — long-hall worth it.

## Branch reconciliation in progress (2026-05-08)

**0.0.2 is being merged into 0.0.3 — 0.0.3 becomes canonical.**

The 0.0.3 branch (3 weeks old) shipped real UI work — Finder-style
search criteria strip (#517), library list/table/map re-enable, NNW
toolbars (#617), sidebar reorder (#602), Artifacts column (#519). All
on the *original* directory layout: `fichero-api/` + `fichero-swiftui/`.

The 0.0.2 branch did the directory rename (`cef63616` on Apr 29:
`fichero-api/` → `fichero-engine/`, `fichero-swiftui/` → `fichero/`)
*after* 0.0.3's UI work, then shipped the full LLM-stack overhaul on
the renamed paths.

Merge plan: from `~/code/fichero-0.0.3` worktree, `git merge 0.0.2`.
Git's automatic rename detection maps the directory move; expected
conflicts only on STATE.md / MEMORY.md / HISTORY.md / docs that both
branches edited.

After the merge, 0.0.3 is canonical. This 0.0.2 worktree is archived.

## Next Session — Start Here

**Latest commit on 0.0.2: `3d50df04`** (10 integration tests for the LLM
fallback chain, mocked at the network boundary, no internet calls).

### 0.0.2 milestone state

Open: 9 (was 16). Closed: 265+. Ratio 96%.

The remaining 9 are: #659–#665 (release packaging, all Daniel-blocked),
#821 (Apple Intelligence Tool calls — bigger feature, deferrable), #868
+ #872 + #873 (LLM-stack follow-ups — all doable now), #854 moved to
0.0.3 (genuinely blocked on macOS SDK 26.4).

### Highest-value next thing: #868 LLMProvider Protocol refactor

**Read first:** the implementation brief I wrote inside the issue
(GitHub comment dated 2026-05-07). It has the exact 5-commit sequence
+ file paths + risk analysis. Don't re-derive — execute.

**Quick orientation:** the foundation is already in `llm.py`:
- `AppleUnavailableError` hierarchy (~line 145)
- `_compute_timeout(config, kind, *, schema_chars=None)` (~line 1308)
- `collect_usage()` + `_record_usage()` (~line 70)
- Reasoning routing in `get_langchain_model` (~line 1850)

The refactor wraps these into provider classes; dispatchers replace the
in-line `if config.provider == "apple": ... else: ...` branches.

### Other paths

- **#873 next slice:** the 10 fallback-chain tests are scoped piece 1.
  Pieces 2/3 would be (a) a workflow-execution-runner test with mocked
  tools, (b) an end-to-end test driving the FastAPI route. Both need
  fixture-infra design choices first.
- **Live verification still pending:** restart backend on a recent commit
  and re-run Catalogue (Mixed) on Legal Case to confirm the Spanish
  locale fix works in production.
- **Cellphone-aware rule for autonomous loop:** mock all LLM calls in
  tests; never write a test that hits real provider APIs without an env
  flag (`FICHERO_INTEGRATION=1`) and `pytest.skipif` guard.

### Don't break

- AppleUnavailableError fallback works because `chat_with_fallback` /
  `chat_structured_with_fallback` catch the base class. Don't catch
  `GuardrailViolationError` specifically anywhere.
- Don't add a fourth timeout formula somewhere. Use `_compute_timeout`.
- Don't `logger.info("LLM usage ...")` directly. Use `_record_usage` so
  the contextvar collector picks it up.
- Don't add a second Apple path. fm-bridge is canonical.

### Read for context

- `docs/architecture/api/development_standards.md` — 6 contracts under
  "LLM Stack Architecture (post-#872)"
- `MEMORY.md` 2026-05-07 entries (7 durable lessons)
- HISTORY.md 2026-05-07 session summary
- GitHub issue #868 comment "Implementation brief — for fresh-context resumption"
2. **If per-file works**: move on to release pipeline #658–#660 (DMG
   build / notarize / dry-run install).
3. **If per-file doesn't land**: check engine.log for
   `page_cleanup(<key>): wrote <key>_clean on N/M descendant docs` —
   N>0 means it's working. If N=0, the records flow lost doc_ids
   again; verify catalogue.json has both `transcribe.texts → aggregate.text`
   AND `files-source.documents → aggregate.documents` (force-reseed
   defaults via Settings if not).
4. Iterate on the inspector via plain Xcode: `BuildProject` (~1.5s) +
   `open .../Fichero.app` (~5s end-to-end). Don't try SwiftUI
   previews of the Inspector — they hit the 30s app-launch timeout
   and the SPM workaround isn't worth the duplication cost.
5. New bugs Daniel files via `/bug` go to milestone 0.0.2.

## Architecture Reminders

- **Engine**: external (`./fichero-engine/scripts/start_backend.sh` or
  briefcase dev) — Debug Embed phase no longer copies the briefcase
  bundle; the Swift app probes `:8765` for 5s and uses whatever's there.
- **Auth**: token at `~/Library/Application Support/Fichero/.api-key`,
  written by `initialize_token()` on every engine start regardless of
  launch path.
- **Test 2 folder**: `7dbba674ae204be9b08dc8df5a00f6fa` (Asprilla,
  15 files); Catalogue workflow id changes per reseed — query
  `/api/workflows/` to find current.
