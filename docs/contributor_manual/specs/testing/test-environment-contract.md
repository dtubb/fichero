# Test Environment Contract — config parity with briefcase + per feature-gate

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it.
> **Status: DRAFT — awaiting approval.** First spec authored from `_TEMPLATE.md`.
> Tags: [OK] built · [MISSING] not built · [PARTIAL] exists / not enforced.

## Intent (the design)

A test must run the engine in a configuration that matches what the **briefcase** (the
packaged, shipped engine) runs — *except* for a small, explicit, reviewed set of test-only
overrides. Today they can silently diverge: the briefcase loads a `.env` via
`python-dotenv`, while the UI harness sets env inline (`FICHERO_FORCE_UDS_PATH`,
`FICHERO_UITEST_HOME`, `FICHERO_ALL_FEATURES=1`, `FICHERO_SKIP_EMBEDDINGS_PREWARM=1`).
Two failure modes follow: (1) a test passes on config the shipped app never uses; (2) the
shipped app breaks on config no test covered. And because the harness forces
`FICHERO_ALL_FEATURES=1`, **no UI test exercises the real release feature gate.**

## Behaviors

### A. One config base, explicit overrides
- `testenv.base-shared` [MISSING] — the engine config the briefcase ships (its `.env`
  base) and the test engine config derive from ONE source, not two hand-maintained lists.
- `testenv.overrides-allowlisted` [MISSING] — every test-only env override lives in ONE
  reviewed allowlist with a reason, e.g.:
  - `FICHERO_UITEST_HOME` / `_LIBRARY` / `_OPEN_DOCUMENT` — point the engine at the seeded
    disposable library (isolation).
  - `FICHERO_FORCE_UDS_PATH` — dev fast-loop socket.
  - `FICHERO_SKIP_EMBEDDINGS_PREWARM=1` — skip the model download a fresh-home engine can't
    serve (a UI plan testing embeddings unsets it).
  Anything set in a test but NOT in this allowlist is a drift bug.
- `testenv.parity-guardrail` [MISSING] — a `check_*.py` that fails when the test engine
  sets an env var the briefcase doesn't know, unless it's in the allowlist; and warns when
  the briefcase relies on a var no test ever sets.

### B. Per feature-gate coverage
- `testenv.gate-source` [OK] — `features.yaml` is the tier source (dev/alpha/beta/release),
  with `check_features_freshness`.
- `testenv.test-each-gate` [MISSING] — the suite runs under the REAL tiers, not only
  `ALL_FEATURES=1`: at minimum a **release**-gate run (what users get) plus the
  all-features dev run. A feature that works dev-on but is broken/hidden at release is a
  bug the current setup can't see.
- `testenv.gate-availability` — for each tier, the capability-availability tests assert the
  surfaces that tier SHOULD expose are reachable, and the ones it shouldn't are absent.

### C. Model / data locations
- `testenv.model-cache` [PARTIAL] — `MODELS_BASE = server_state_dir()/models`. A fresh test
  home has none, so an embeddings test must point at a shared cached model (offline) or
  seed it — otherwise it downloads/hangs (the prewarm bug). Define one cached location the
  briefcase and an embeddings-testing engine both use.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (py) | y | the prewarm gate + any parity/override rule | `fichero-server/tests/unit/api/test_prewarm_gate.py` (done) + parity rule test |
| Guardrail (py) | y | test/briefcase env parity + allowlist | `scripts/check_test_env_parity.py` (new) |
| Backend (pytest) | y | engine honors the gate/env | startup/config tests |
| Click-around (XCUITest) | y | the suite runs under the release gate, not only ALL_FEATURES | a release-tier UI plan |
| Load | n | — | — |

Hard-gate: the parity guardrail (no undocumented test/prod divergence) + at least one
release-gate UI run.

## Accessibility identifiers
n/a (infrastructure spec).

## Open questions for the creative director
- Where does the shared engine `.env` base live, and does the test harness read it +
  layer the allowlisted overrides (vs. re-listing env in Swift)?
- Which tiers get a full UI run vs. a smoke run (release always; beta on release branches;
  dev every push)?
- Model cache: one committed/seeded fixture model for embeddings tests, or point tests at
  the developer's real `~/.cache` (fast but not hermetic)?
