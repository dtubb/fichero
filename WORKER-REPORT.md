# Worker Report — AI Backend Hardening (milestone #90)

Author: Claude (commits authored as Claude, co-authored Daniel Tubb). **Not pushed.**
Branch base: `9eb8a6ce` (origin/main). Date: 2026-06-28.

## Milestone selection (auto-advance)

- **#92 Programmatic Guardrails** — only EPIC #2271 open (skipped). Drained of actionable non-EPIC work.
- Auto-advanced by soonest-due. The soonest-due milestones are Swift/SwiftUI/EPIC/design-heavy and
  not gateable in this ruff+pytest / swiftlint-only lane: **#82 Test Coverage** (Swift unit/XCUITest
  only — needs Xcode), **#70 API Surface** (Swift-client conversions + QA), **#77/#74/#64/#62** (Swift
  / large EPIC / roadmap). I picked the soonest milestone with **lane-actionable backend-Python**
  work: **#90 AI Backend Hardening → #2507** (silent-fallback sweep) — fully gateable and matching
  Daniel's hard "prefer-raise-over-silent-fallback" principle.

## Issue worked: #2507 — replace silent fallbacks with raised/logged errors

The sweep, done honestly, found the **high-risk write paths are already hardened**:
- The #2430 exemplar (`llm_base.py` / `vision_base.py` save → reroute-to-parent) is fixed (returns
  None + logs; never substitutes the parent doc) and already covered by
  `test_save_artifact_page_child_resolution.py`.
- An AST sweep of the whole engine found **5** silent broad `except Exception` swallows inside
  write-named functions. Reviewing each: `browser_save` (×2) and `_ingest_one` **surface the error**
  (into the response payload / result tuple) — not silent; the 2 scheduler ones were genuine silent
  swallows. So a blanket sweep would have been over-reach (Daniel: "blanket sweep is wrong").

Two focused, safe slices:

### Commit 1 — `fix(#2507): scheduler stops silently swallowing all remove_job errors`
`update_schedule` / `delete_schedule` wrapped `self._scheduler.remove_job(...)` in
`except Exception: pass`, masking ANY APScheduler failure as a no-op. `remove_job` raises
`JobLookupError` when the job is simply absent (the only expected case for idempotent
re-register/delete). Narrowed both catches to `JobLookupError` so a genuine scheduler error now
surfaces. `fichero-engine/src/fichero/workflows/scheduler.py`.

### Commit 2 — `test(guardrail): ban pure-silent broad swallows in write paths (#2507)`
The issue asks for "a lightweight guard/lint where feasible." Added
`scripts/check_silent_write_swallow.py` — AST scan flagging an `except Exception:` whose body is
purely silent (only `pass`/`continue`/`break`/`...`/bare-return/`return None` — no log, no raise, no
error-payload return) inside a write-named function. Deliberately narrow: narrow excepts,
log-warn-and-skip, error-payload returns, and read functions are all accepted, so it won't over-reach.
Baseline CLEAN (0) after Commit 1, so it permanently guards against reintroducing the class.
Auto-discovered by `verify_all.sh`. + `test_check_silent_write_swallow.py` (8 tests: planted-violation
RED, all legit patterns GREEN).

## Gate results (this worktree)
- `ruff check fichero-engine/src/fichero/workflows/scheduler.py` → All checks passed.
- `ruff check scripts/check_silent_write_swallow.py` + the test → All checks passed.
- `pytest -k schedul` → **33 passed, 1 xfailed**.
- `pytest test_check_silent_write_swallow.py` → **8 passed**.
- `python3 scripts/check_silent_write_swallow.py` → exit 0 (0 violations, empty baseline).
- Did **not** push.

## Not done / flagged
- No #2430-style corruption bugs remain to fix; the regression is already test-covered. A blanket
  except-Exception ban was deliberately NOT done (220 silent handlers engine-wide, most legitimate —
  ImportError/JSONDecodeError/Timeout/CancelledError). The guard is scoped to the dangerous subset
  (broad + pure-silent + write-path).
- `#2507` also has a **frontend** half (surface underlying errors in Swift, #2500) — Swift/build work,
  out of this lane.
- `#2615` (embedded Apple FM + MLX models) — large feature with Swift/build parts; not taken.
