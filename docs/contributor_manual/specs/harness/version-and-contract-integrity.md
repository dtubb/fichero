# Version and Contract Integrity — Design Spec (#5046)

> Milestone: version-and-contract-integrity
> Manual: contributor-facing. The one user-visible consequence — a connection refused or
> flagged because two machines disagree about the contract — belongs to
> `transport/` alongside the pairing surfaces.

> Design-led (Testing Constitution). **Status: DRAFT — awaiting approval.**
> Tags: **[OK]** built and tested · **[PARTIAL]** built, partly proven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the rule (needs an issue).

## Intent (the design)

There is **one truth about what version this is**, and everything that claims a version
either derives from it or is checked against it. A version that can drift silently is not a
version; it is a decoration that happens to be right for a while.

Three places can disagree today, and all three did:

- **The code** (`fichero-server/pyproject.toml`) says what the engine is.
- **The contract** (`openapi.json` `info.version`) says what the wire looks like.
- **The pair of machines actually talking** — an app and an engine, which on a remote
  connection are two different builds from two different days.

On 2026-09-26 the code said `2026.9.20`, the contract said `2026.9.8`, and `v2026.09.20`
had shipped six days earlier. Nothing noticed, because nothing was looking.

**The failure was not the guard. It was the response to the guard.** The environment drifted,
the regeneration correctly refused, and the refusal was worked around by hand-editing the one
field it complained about. Every downstream check stayed green, because each was asking a
narrower question than "is this still true".

So this spec is as much about *how a refusal must be answered* as about what is checked.

## Behaviours

### `contract.version-tracks-code` — the contract never lags the code **[BROKEN]** (#5046)

The committed `openapi.json` `info.version` matches `pyproject.toml`. A release cannot ship
with a stale contract.

Today nothing asserts this. `check_openapi_version_regression.py` (#4199) prevents the version
going **backwards** — a real and separate property — but a contract frozen four releases behind
never regresses, so it passes forever.

The check must FAIL when it cannot read either input, never pass vacuously, and ship with a
`--self-test` that synthesises a stale contract and asserts it is caught (AGENTS.md rule 0).

### `contract.never-hand-edited` — a generated file is regenerated, never patched **[BROKEN]** (#5046)

AGENTS.md rule 3 already forbids editing generated files. The rule needed strengthening
because the tempting violation is not rewriting the document — it is `sed`-ing a single field
so a guard stops complaining, which does not feel like editing the file.

It matters more than it looks: `sync_openapi_schema.sh` regenerates all three `openapi.json`
copies, the contract fixtures and the CLI surface **together**. Patching one desynchronises the
rest while the shadow-type, typed-field and client-parity guardrails all still report green.

**A refusal to regenerate means the environment is wrong.** The canonical venv is
editable-installed against the main checkout and drifts. Point the script at a venv holding a
current install (`FICHERO_PYTHON_BIN=...`) rather than editing its output (#5043).

### `contract.runtime-compatibility` — both ends verify they agree **[GAP]** (#5047)

An app and an engine confirm at connect time that they share a contract, and say so plainly
when they do not.

`/api/health` already returns `backend_version`. That is the **app** version, and it is the
wrong thing to compare: two builds can share a contract, and one build can change it. Wire
compatibility is decided by the **contract**, which nothing currently reports and nothing
compares.

- The engine reports the served schema's `info.version` plus a hash of the document, computed
  once at startup — not per request; the document is large.
- The client carries the contract identity it was generated from, baked in at build time so the
  two cannot be skewed by hand.
- Compared on connect and after pairing. Same version with a different hash is its own defect —
  one version published twice with different content — and must be loud.

Whether a mismatch refuses or warns is a **ruling, not an assumption**. Refusing is safest and
matches rule 0; warning is kinder during a staged rollout where a user cannot upgrade both
machines at once. The embedded engine always matches its app, so this only bites remote
connections — which is exactly where two builds from different days are normal.

### `lane.preflight-deterministic` — a lane verifies its ground before working **[GAP]** (#5048)

A worker or manager lane confirms its environment before doing work, and refuses loudly rather
than discovering the problem hours later through a confusing symptom.

Everything that cost time on 2026-09-26 was an unverified assumption about the environment, not
a mistake in reasoning: a revoked token, a closed Xcode reported as a broken server, sixty stale
`LaunchServices` registrations behind a `HOST NEVER STARTED`, a drifted venv behind a refused
regeneration. Each was cheap to check and expensive to diagnose.

The preflight answers, deterministically and in one place: the right worktree and branch; a venv
that can actually run the sync; whether the contract matches the code; whether the Swift test
path is available at all; and whether stale processes or registrations will sabotage a test host.

It **reports** rather than repairs. Repair is a decision — reinstalling an editable package
changes the contract version, which is a release decision, not housekeeping.

## Test matrix

Spec-led: each behaviour is pinned by a test that names it, and asserts the BEHAVIOUR rather
than the implementation.

| Behaviour | Test asserts |
|---|---|
| `contract.version-tracks-code` | a contract behind `pyproject.toml` FAILS; a matching one passes; an unreadable input FAILS rather than passing |
| `contract.never-hand-edited` | regenerating produces byte-identical output to the committed contract; a patched single field is detected |
| `contract.runtime-compatibility` | matching contracts connect; a version mismatch is surfaced naming both sides; same-version/different-hash is caught; an unreadable identity fails loudly |
| `lane.preflight-deterministic` | each condition is detected on a synthesised broken environment; a healthy environment passes; the check never reports success on input it could not read |

A guard that can return an empty set and satisfy an empty expectation is worse than no guard.
This was live on the same day: three field-coverage tests used `Mirror`, which sees only stored
properties, and went blind the moment `swift-openapi-generator` moved a schema to copy-on-write
storage. They now read the contract instead, and a companion test asserts the reader actually
sees known fields — so "blind" and "satisfied" cannot look alike.

## Open questions for the design lead

1. Does a runtime contract mismatch **refuse** a remote connection, or warn and proceed?
2. Should `info.version` track `pyproject.toml` exactly, or only at release boundaries?
3. Should the lane preflight ever repair (`pip install -e`), or always only report?
