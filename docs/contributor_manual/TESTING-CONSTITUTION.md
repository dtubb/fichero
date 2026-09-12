# Testing Constitution

> Status: RATIFIED 2026-09-08. Governs *why and what we test*.
> **Durable principles only.** Today's bugs, waves, and scan numbers live in GitHub
> issues, never here (see "Where the specifics live"). The *how* lives in
> `docs/contributor_manual/TESTING.md`.
>
> **The Fichero creative director** is the design authority named throughout — the role
> that owns product/design intent and ratifies specs, whoever fills it.

## Preamble

Fichero is **not** short on testing machinery: a 9-layer pyramid, ~90 `check_*.py`
guardrails with known-gap allowlists, a spec-first `xfail(strict=True)` mechanism, a
shared fixture library, a coverage ratchet, platform canaries. Yet the same *classes*
of regression keep landing. That is a **discipline** gap, not a machinery gap:

1. We test *what the code does*, not *what it should do* — a test can be green while
   the behavior is wrong.
2. **Cross-surface invariants** ("these N places must agree") and **capability
   availability** ("shown iff runnable") aren't pinned as invariants.
3. The **feature gate** is both a capability switch and an accidental error source.
4. **Workflow behavior** (node-config completeness, node idempotence) isn't a tested layer.

This constitution sets the principles that close that gap.

## Design-led testing (the primary mode)

Tests defend a **design** — how a surface should look and behave — not whatever the
code currently does. The design is the source of truth; the test enforces it; the code
makes the test pass.

- **The Fichero creative director owns intent.** A worker may draft the behavioral spec, but it is
  not real until the creative director approves it. Tests are written to the approved
  design, never reverse-engineered from the implementation.
- **The design leads the UI too.** Unit + store + UX tests pin the design's states and
  interactions; the RenderPreview / preview-driven loop is the cheap design-led check
  before an XCUITest.
- **A design change is a spec change is a test change** — same PR, in that order. A
  test that no longer matches the intended design is corrected, never silently deleted.
- **"It compiles / the graph runs" is not the bar.** The bar is "it does what the
  design says," pinned by a test a future change will trip.

## Articles

**1. Spec before test before fix.** Behavior changes and bug fixes begin with a
one-line behavioral spec (what the user should *observe*), then a test, then the code.
An unfixable-yet defect lands its test first as a strict-xfail in
`known_specification_failures.txt`; the fix is "this line now passes, so delete it."

**2. A regression becomes a guardrail.** A fix isn't done until a test or guardrail
exists that *would have caught it*, at the cheapest layer that can fail on it.

**3. Cross-surface invariants are tested as invariants.** When one truth must appear in
N surfaces, test that *the surfaces agree*, once — not each surface ad hoc.

**4. Availability tells the truth.** A provider / runtime / model is shown available or
enabled **iff** it is actually installed and runnable. No surface advertises a
capability the engine can't perform. **"Runnable" means resource-safe:** a model that
crashes the machine, exhausts memory, or is too large to load is NOT available.
Availability is tested by actually *running* the model under load — not just checking
registration — and **fan-out/parallelism is bounded** so running models never peg or
crash the machine (it stays useful) and never burst a provider into rate-limit/quota
failures. The real provider error (bad key vs rate-limit vs out-of-credits vs too-large)
is surfaced, never flattened to one generic message.

**5. The gate is the contract.** A rule not in the gate is a suggestion. Specs that
matter get a guardrail or test in `scripts/gate`; known gaps are explicit allowlists,
never silent skips.

**6. Feature-gating is a capability switch, not an error source.** Gate only what
genuinely varies by tier; a gated-off capability degrades cleanly and testably, never
surfaces as a bug. Warrants a one-time audit of what should never be gated.

**7. Workflows are behavior, and behavior is tested.** Node **config completeness**
(required fields present + editable), node **idempotence** (a deterministic node isn't
re-run redundantly), and provider **routing** — asserted, not just "the graph ran."

**8. Cheapest layer that catches it wins.** Push each test to the lowest layer that can
fail on the defect; reserve XCUITest for the few true end-to-end flows.

**9. Coverage ratchets; debt is visible.** Coverage only goes up; gaps are filed as
Test Coverage debt and drained deliberately, never silently skipped. Debt doesn't
hard-block merges.

**10. AI workers get a crisp brief.** Every test dispatch names the **layer**, the
**behavioral spec**, the **invariant/regression** it pins, and the **fixture**. The
adversarial pass (error paths, boundaries) is required; vanity coverage is not.

**11. Complete across the stack, or not shipped.** A capability is wired end-to-end —
backend ↔ UX ↔ tracked ↔ tested — or it isn't shipped. No orphaned code, in any shape:
*code with no caller* (dead code); *backend without UX* (an endpoint nothing surfaces);
*UX without backing* (a control with nothing behind it, or untracked); *declared but
not embedded* (a provider/model registered but not actually bundled + runnable — the
build must contain what it advertises, asserted by a packaging test). Completeness has
**depth too**: when we integrate a tool we expose and test its real capability set, not
one narrow slice — each provider gets a capability audit (what it CAN do vs what we
EXPOSE vs what we TEST), gaps filed as issues. (Contract guardrails already assert
slices of this — `check_crud_completeness`, `check_endpoint_coverage_matrix`,
`check_action_surface_matrix`, `check_emit_change_coverage` — extend them. Dead-code
detection must account for dynamic registration the import graph can't see.)

## Operating rules (ratified)

- **Design-led loop:** worker drafts spec → **creative director approves intent** → worker
  writes tests → code. Pinning test in the same PR.
- **Interleave, don't freeze:** every new/touched feature ships its spec + tests.
- **Workers by feature** (a capability across all its layers), not by layer; claim each
  issue (`/claim-task`) so lanes don't collide.
- **Hard-gate = invariants + availability** (Articles 3, 4). Every other new test is
  tracked coverage debt (Article 9); debt doesn't block merges.
- **UX coverage is a broad goal**, but only after the deterministic in-process engine
  harness lands — broad UX on spawned-uvicorn+TLS is too slow/flaky.
- **Lifecycle + cleanup** (AGENTS.md → Worker Orchestration): issue under a milestone →
  worktree → integrate + build-verify → **close the issue → remove the worktree + delete
  its branch**. No merged worktrees left to rot.

## Where the specifics live (so this doc stays durable)

The constitution holds principles. **Current state lives in GitHub issues, not here:**

- **Regression corpus** (the concrete bugs, each → a pinning test) → the umbrella issue
  and its children.
- **Per-provider capability work** (Kraken, MLX, spaCy, …) → one issue each.
- **Coverage-gap scans, "which wave next", dated decisions** → the tracking issue / a
  handoff — they change weekly and would rot the constitution.
- **Per-capability behavioral specs** → `docs/contributor_manual/specs/<area>.md`, cited by the
  tests' docstrings.
- **Which tests to write for a surface (the checklist so you don't have to remember)** →
  `docs/contributor_manual/TEST-TEMPLATE.md` — the per-surface leg matrix (pure rule · availability
  · backend · MCP · CLI · **click-around XCUITest** · iPad/iOS · load) with a fill-in-the-blank
  skeleton per leg, grounded in the real harnesses. Paste its matrix into a spec's *Test
  matrix* section. The click-around leg is the weakest — treat its skeleton as non-optional
  for any surface a user touches, and list the accessibility identifiers it needs in the spec.
- **Which DOCS to write for a feature (same idea, for readers)** → `docs/contributor_manual/DOC-TEMPLATE.md`
  — the per-feature documentation matrix (user manual + screenshot · developer docs · MCP tool
  description · CLI `--help` · reference). A feature is met by four kinds of reader who never
  read each other's docs; the matrix says which it owes. Paste it into the spec's
  *Documentation matrix* section, next to the Test matrix.

A bug is a line in an issue; a lesson from it is (maybe) a line in this doc.

## Grounded in what exists (do not reinvent)

`docs/contributor_manual/TESTING.md` · `known_specification_failures.txt` · `scripts/check_*.py`
+ known-gap allowlists · `scripts/check_coverage_ratchet.py` · `fichero/Tests/plans/` +
platform canaries · `test-fixtures/` + resolvers · `scripts/verify_all.sh --fast` · the
manager post-feature loop.
