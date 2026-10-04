# Test Environment Contract — config parity with briefcase + per feature-gate

> Milestone: test-environment-contract
> Manual: docs/contributor_manual/guide/11-testing.md
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it.
> **Status: DRAFT — awaiting approval.** First spec authored from `_TEMPLATE.md`.
> Tags: [OK] built · [MISSING] not built · [PARTIAL] exists / not enforced.

## Intent (the design)

A test must run the engine in a configuration that matches what the **briefcase** (the
packaged, shipped engine) runs — *except* for a small, explicit, reviewed set of test-only
overrides. Today they can silently diverge: the briefcase loads a `.env` via
`python-dotenv`, while the UI harness sets env inline (`FICHERO_FORCE_UDS_PATH`,
`FICHERO_UITEST_HOME`, `FICHERO_ALL_FEATURES=1`; `FICHERO_SKIP_EMBEDDINGS_PREWARM=1` is gone
since #5283, when the engine stopped loading the embedding model at startup).
Two failure modes follow: (1) a test passes on config the shipped app never uses; (2) the
shipped app breaks on config no test covered. And because the harness forces
`FICHERO_ALL_FEATURES=1`, **no UI test exercises the real release feature gate.**

## Behaviors

### A. One config base, explicit overrides
- `testenv.base-shared` [MISSING] (#4784) — the engine config the briefcase ships (its `.env`
  base) and the test engine config derive from ONE source, not two hand-maintained lists.
- `testenv.overrides-allowlisted` [MISSING] (#4785) — every test-only env override lives in ONE
  reviewed allowlist with a reason, e.g.:
  - `FICHERO_UITEST_HOME` / `_LIBRARY` / `_OPEN_DOCUMENT` — point the engine at the seeded
    disposable library (isolation).
  - `FICHERO_FORCE_UDS_PATH` — dev fast-loop socket.
  Anything set in a test but NOT in this allowlist is a drift bug.
- `testenv.parity-guardrail` [MISSING] (#4645, #4786) — a `check_*.py` that fails when the test engine
  sets an env var the briefcase doesn't know, unless it's in the allowlist; and warns when
  the briefcase relies on a var no test ever sets.

### B. Per feature-gate coverage
- `testenv.gate-source` [OK] — `features.yaml` is the tier source (dev/alpha/beta/release),
  with `check_features_freshness`. Pinned:
  `test_check_features_freshness.py::test_repo_is_currently_fresh` (the real repo's generated
  tier artifacts match `features.yaml` today),
  `::test_self_check_catches_injected_drift` (the guardrail actually detects drift, not a
  vacuous pass).
- `testenv.test-each-gate` [MISSING] (#4787) — the suite runs under the REAL tiers, not only
  `ALL_FEATURES=1`: at minimum a **release**-gate run (what users get) plus the
  all-features dev run. A feature that works dev-on but is broken/hidden at release is a
  bug the current setup can't see.
- `testenv.gate-availability` — for each tier, the capability-availability tests assert the
  surfaces that tier SHOULD expose are reachable, and the ones it shouldn't are absent.

### C. Model / data locations
- `testenv.model-cache` [PARTIAL] (#4788) — `MODELS_BASE = server_state_dir()/models`. A fresh test
  home has none, so an embeddings test must point at a shared cached model (offline) or
  seed it — otherwise it downloads/hangs (the prewarm bug). Define one cached location the
  briefcase and an embeddings-testing engine both use.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | any parity/override rule (the prewarm gate it once held went with the prewarm, #5283) | parity rule test |
| Guardrail (py) | y | test/briefcase env parity + allowlist | `scripts/check_test_env_parity.py` (new) |
| Backend (pytest) | y | engine honors the gate/env | startup/config tests |
| Click-around (XCUITest) | y | the suite runs under the release gate, not only ALL_FEATURES | a release-tier UI plan |
| Load | n | — | — |

Hard-gate: the parity guardrail (no undocumented test/prod divergence) + at least one
release-gate UI run.

## Accessibility identifiers
n/a (infrastructure spec).

## Open questions for the creative director
- **Answered** (design lead 2026-10-04, applying the spec's lean): One shared base file, with the harness layering only the allowlisted overrides. Where does the shared engine `.env` base live, and does the test harness read it +
  layer the allowlisted overrides (vs. re-listing env in Swift)?
- **Answered** (design lead 2026-10-04, applying the spec's lean): Release always runs the full UI suite, beta on release branches, and dev runs a smoke run on every push. Which tiers get a full UI run vs. a smoke run (release always; beta on release branches;
  dev every push)?
- **Answered** (design lead 2026-10-04, by the existing design): Tests use the developer's cached model offline and skip with a logged reason when it is missing (#5188, `fichero-server/tests/conftest.py`). Model cache: one committed/seeded fixture model for embeddings tests, or point tests at
  the developer's real `~/.cache` (fast but not hermetic)?

## Triaged from the backlog (2026-10-04)
- `testenv.one-mcp-test-tree` — **[GAP]** (#4480) fichero-mcp is tested from one tree only; the stale copy under fichero-server/tests/unit/mcp is removed or made the same suite (it still exists).
- `testenv.no-defaults-leak` — **[GAP]** (#4234, #4103, #4578) tests never create UserDefaults suites in the shipping app container, and a sweep removes the ~180 test.purge.* plists.
- `testenv.full-suite-completes` — **[GAP]** (#5249, #4039) a full engine pytest run finishes without a hang (the perf test is bounded, not skipped) and without shared-app middleware errors at setup.
- `testenv.no-modal-in-hosted-tests` — **[GAP]** (#4270) a hosted unit test never raises a user-visible save panel or alert; save paths are pointed at a temp directory.
- `testenv.no-real-files-touched` — **[GAP]** (#4537) tests running in the app container never write real container files (e.g. .api-key) without save/restore; a sweep and guardrail cover the class.
- `testenv.expect-message-is-comment` — **[GAP]** (#4698) a guardrail fails before a build when a Swift Testing #expect/Issue.record message is a concatenation or String variable.
- `testenv.load-insensitive-unit-tests` — **[GAP]** (#4793) WebKit-backed ReaderTranscriptWrapTests and ServiceHostReconfigurationTests:78 do not fail the gate under machine load.
- `testenv.engine-leg-fits-footprint` — **[GAP]** (#4916) the gate's engine leg completes under the 4096 MB footprint ceiling (scripts/gate GATE_FOOTPRINT_MB) by sharding the engine suite across processes.
- `testenv.transport-error-tests-use-stubs` — **[GAP]** (#4207) twelve service suites that assert transport error mapping use a stub transport, not real DNS/network.
- `testenv.guardrails-fail-on-stale-baseline` — **[GAP]** (#3339) every scripts/check_*.py returns nonzero when a KNOWN_VIOLATIONS or baseline entry is stale (check_native_controls.py and check_feature_flags.py warn and return 0).
- `testenv.export-route-tests-order-independent` — **[BROKEN]** (#5309) test_routes_export's MarkdownFolderExport and EleventySiteExport tests mount their routes whatever ran before them (an earlier module reloading fichero_server.api.main must not unmount export routes).
- `testenv.tests-never-write-the-real-registry` **[BROKEN]** (#5266): no test adds a library to the person's real engine registry: UI tests open their seed and untitled libraries through an engine with its own temporary home, a guard fails a run that adds to the real registry, and an explicit, reported prune removes entries whose package no longer exists.
- `testenv.unit-suite-runs-in-minutes` **[BROKEN]** (#5294): the Python unit suite finishes in minutes on a quiet machine, as it once did (5 min 53 s), not hours: the FastAPI app is built once per auth posture and reused rather than reloaded twice per test (16 files do it today), and the suite's slowest tests are listed with --durations so a regression shows.
- `testenv.apple-vision-fixture-tests-read-the-page` **[BROKEN]** (#5378): the palaeography fixture's three Apple Vision tests read the gold page and score a real CER, not ~1.0; when Vision cannot run (a locked session, the runner's context) they skip and say why instead of failing.
- `testenv.unit-tests-order-independent` **[BROKEN]** (#5407): every engine unit test passes in a combined run as it does alone: no earlier test leaves a module cache, env var, supplied key, reloaded app or old jobs-table schema behind, and waits are event-driven rather than on background queues. Today test_star_yields_directories_like_rglob, test_nothing_is_persisted, the query-ratchet task-list test and the Gemini two-pass test fail only in combined runs.

## Future (ideas, not scheduled)
- (#4425) Design principle: what must not be forgotten lives in the gate, advice lives in skills.
