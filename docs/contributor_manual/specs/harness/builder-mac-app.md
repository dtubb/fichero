# The builder as a sandboxed Mac app — Design Spec (#6345)

> Milestone: builder-mac-app
> Manual: TBD — the contributor manual's "Running the builder" page must say how to install the app, grant it the
> one folder it works in, read the console, and answer an alert; no user-manual section, this is a contributor tool.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code makes them pass.
> **Status: DRAFT — awaiting the owner's approval (#6345: the spec is written by the spec writer and approved by the
> owner before any build; nothing here is built from a DRAFT).** Extends `harness/dev-workflows.md` (the builder, its
> ladder, its console `dev-workflows.run.loop-status`, its jail `dev-workflows.run.jail-home` and the sandbox paragraph
> that already says the shipped sandbox is chosen by test); nothing here replaces a verb, a rung or a journal row.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired · **[GAP]** intended, never built.

## Intent (the design)

Once the builder is solid it becomes a Mac app like Fichero itself: signed, sandboxed by entitlements, installable on any
Mac (a friend's included) from the website, with the console as its window. What the owner observes: one app in the Dock
that shows the lanes, the queue, the ladder's rungs per batch, graphs of progress over time, real token counts and the cost
so far, and alerts explained in plain words; the worker runs inside the app's sandbox, not as a second Unix user. The
engine of the app is the builder as it stands (`fichero-builder/fichero_builder`, stdlib Python, the journal, the rules
file); the app is a shell over it exactly as Fichero's app is a shell over its engine (`engine-startup-lifecycle.md`): the
Swift side owns the window, the sandbox and the process; the Python side owns every decision.

## Prior art (reuse, do not invent)

- **Fichero's own shell** (`harness/engine-startup-lifecycle.md`): a Swift app that spawns an embedded Python engine
  through Briefcase, waits for readiness and shows its state. The builder app is the same pattern with a different
  engine, so the launcher, the readiness probe, the embedded-Python packaging and the Sparkle feed are reused, not
  written again.
- **App Sandbox and inherited sandboxes** (Apple): a child process started by a sandboxed app inherits the app's
  container and entitlements (`com.apple.security.inherit`); a security-scoped bookmark grants the one folder the owner
  picks (the worktree root) across launches. `dev-workflows.md` already decides the mechanism by test (a signed
  launcher with App Sandbox inherited, raw Seatbelt with a maintained profile, Apple `container`): this spec takes the
  winner of that test and adds nothing beside it.
- **The console** (`dev-workflows.run.loop-status`, Step 2.26 of `dev-workflows.md`): the page the app shows is the
  console's page in a web view first; a native view replaces a card only when the page cannot do it (the graphs may be
  the page's own, drawn from `/api/status` history).

## Behaviors

### A. The app and its sandbox

- `builder-app.one-app-one-folder` [GAP] (#6345) — the app is installed like any Mac app and asks once for the one folder
  it works in (the worktree root, a security-scoped bookmark); every worktree, jail home and state file lives under that
  folder or the app's container; the app reads nothing else, and the owner's `~/.ssh`, `~/.config/gh` and `~/.claude` are
  not reachable from inside (today's `[jail].deny_read` list becomes an entitlement, not a probe). Acceptance: a worker
  inside the app that reads `~/.ssh/id_ed25519` is refused by the sandbox, the refusal a `jail` row; the owner picks a
  folder and the bookmark survives a relaunch.
- `builder-app.worker-inherits-the-sandbox` [GAP] (#6345) — the worker (Claude Code or Pi in a pane) is a child of the
  app with the inherited sandbox; the separate Unix user (`[jail].user`) is gone; the policy hook stays, since a
  sandbox says which files, and the hook says which commands. Acceptance: the same policy-hook tests pass with the
  worker a child of the app; `id -u` inside the worker is the owner's; a write outside the folder is refused by the
  sandbox and journalled.
- `builder-app.signed-and-updated-like-fichero` [GAP] (#6345) — the app is signed and notarized by the release lane that
  signs Fichero, ships as a DMG on the website beside Fichero and updates through the same Sparkle feed mechanism with
  its own feed; the embedded Python is Briefcase's, the builder's stdlib-only rule keeping the bundle small. Acceptance:
  the release lane's DMG smoke opens the app, the console appears, and a Sparkle check against the feed finds the
  version; the bundle has no dependency the builder does not import.
- `builder-app.build-merge-push-stay-outside` [GAP] (#6345) — as `dev-workflows.md` says for the sandbox, build, merge
  and push stay outside the worker's sandbox: the app runs them itself (the owner's keychain, the owner's gh login) and
  the worker only asks through the existing verbs. Acceptance: a worker's `git push` is refused by the hook as today; the
  app's land step pushes with the owner's credentials and writes the `landed` row.

### B. The console as the window

- `builder-app.console-is-the-window` [GAP] (#6345) — the app's window is the console page (`dev-workflows.run.loop-status`,
  the phone layout and read-only tailnet view of Step 2.26 included) in a web view bound to the app's own loopback
  server; the token is the app's, never typed. Acceptance: the window shows the same page as `builder status` in a
  browser; an action from the window writes the same `console` row.
- `builder-app.progress-over-time` [GAP] (#6345; owner's first requirement) — graphs over time, from the journal alone:
  landings a day, items in flight, rework rounds per landed batch, tokens and cost a day per role and model (the ledger
  of `dev-workflows.ledger.*`), the ladder's wall time per rung; each graph a time series the page draws, with the range
  (today, 7 days, 30 days) chosen once. Acceptance: a fixture journal of 30 days gives each graph its points; a day with
  no row is a gap, not a zero.
- `builder-app.real-token-counts` [GAP] (#6345; owner: actual counts, not estimates) — every token figure shown is a count
  read from a transcript or a provider's answer (`session.py`'s usage parsing; the ledger's rows), flagged `billed` or
  `equivalent` as the ledger flags it, and the page says "no count" where none was recorded rather than estimating from
  bytes. Acceptance: a lane whose transcript carries usage shows the count and its flag; a lane without shows "no count";
  no figure on the page is derived from a byte length.
- `builder-app.rungs-shown-visually` [GAP] (#6345) — a batch is shown as the ladder it climbs: the rungs of the rules
  file in order (ready, diff bound, red on base, guards, contract current, since-guards, build, review, land), each green,
  red, running or not yet, with the time it took and a link to its log; a refusal names its rung. Acceptance: a fixture
  batch red at the guards rung shows the first four rungs green, the fifth red with the first line of the failure, and the
  rest grey.
- `builder-app.alerts-in-plain-words` [GAP] (#6345; owner: the person answering may not know which to pick) — each alert
  action carries one sentence of what it does and when to pick it: send back (the worker reworks with the finding), retry
  (the same step runs again unchanged, for a flake), park (set aside, nothing runs, the issue stays open), approve (the
  refusal is overridden for this step and the override is journalled), adopt (the work is already on the base, Step
  2.28); the recommended one is first when the harness knows (a review finding recommends send back). Acceptance: every
  action button in a fixture alert has its sentence; an alert with a review finding lists send back first.
- `builder-app.landed-means-origin-integration` [GAP] (#6345; owner's rule) — the word "landed" on any card, graph or row
  means on `origin/integration` and nothing else: a local land branch, a pushed lane branch or a `done` snapshot is "ready
  to land", "queued" or "reviewing", never "landed". Acceptance: a fixture with a land branch ahead of origin shows the
  batch as "ready to land" until the push; the landings graph counts only rows whose sha is on origin/integration.

### C. The harness answers its own alerts

- `builder-app.send-back-by-the-harness` [GAP] (#6345 "also"; tracked separately by the manager) — an alert class that
  is answered "send back" nearly always (a review NOT READY with named findings, a presubmit red with a lint's exact
  line) is sent back by the harness itself after the rule names it, journalled as the harness's answer; only approve and
  question alerts wait for a person. Acceptance: a NOT READY review alert is sent back with no person and the row names
  the rule; an `ask-owner` alert waits.

## Build order

Nothing below is built until the owner approves this spec (the header flips to APPROVED by the owner's hand; the
manager does not approve this one, 2026-11-08). The order is written so the owner can read what comes first; no issue
is filed from it and no lane takes a step from it while the header says DRAFT.

### Stage 0 — Decide the sandbox (no app yet)

#### Step 0.1 — The sandbox test from dev-workflows.md decides the mechanism (#6345)
- Behaviours: `builder-app.worker-inherits-the-sandbox`
- Tests: fichero-builder/tests/test_pi_policy_extension.py, test_sandbox_mechanism.py (not yet written)
- Depends on: none
- Size: M

The existing paragraph in `dev-workflows.md` already orders this: a signed launcher with App Sandbox inherited, raw
Seatbelt with a maintained profile, Apple `container`, each tried with Pi and Claude Code on one real item; the one
that passes the jail tests and runs the worker is the mechanism. Nothing else in this spec starts before it is known.

- test (to write): `test_sandbox_mechanism.py` in fichero-builder/tests/ (the worker as a child of a sandboxed launcher:
  a read of a denied path refused and journalled; a write outside the folder refused; the hook's refusals unchanged)

### Stage 1 — The console says what the owner asked

#### Step 1.1 — Rungs, plain-word alerts, "landed" means origin/integration (#6345)
- Behaviours: `builder-app.rungs-shown-visually`, `builder-app.alerts-in-plain-words`, `builder-app.landed-means-origin-integration`
- Tests: fichero-builder/tests/test_status_page.py, test_console_rungs.py (not yet written)
- Depends on: none
- Size: M

These three are console page changes and land in the browser console long before any app exists; the app shows the
same page. Each is a card the page already has, told more.

- test (to write): `test_console_rungs.py` in fichero-builder/tests/ (the ladder rendered per batch from a fixture
  journal; each action's sentence present; a land-branch batch shown as ready to land until origin has it)

#### Step 1.2 — Graphs over time and real token counts (#6345)
- Behaviours: `builder-app.progress-over-time`, `builder-app.real-token-counts`
- Tests: fichero-builder/tests/test_status_page.py, test_console_graphs.py (not yet written)
- Depends on: 1.1
- Size: M

The series come from the journal and the ledger (`dev-workflows.ledger.*`, Steps 2.17 and 2.24 of `dev-workflows.md`);
no new store. The counts are the ledger's, flagged as it flags them.

- test (to write): `test_console_graphs.py` in fichero-builder/tests/ (30 fixture days give each series its points with
  gaps; a lane without usage shows "no count"; no figure derived from bytes)

#### Step 1.3 — The harness sends back what is nearly always sent back (#6345)
- Behaviours: `builder-app.send-back-by-the-harness`
- Tests: fichero-builder/tests/test_loop.py, test_auto_send_back.py (not yet written)
- Depends on: 1.1
- Size: S

- test (to write): `test_auto_send_back.py` in fichero-builder/tests/ (a NOT READY review alert sent back by rule with the
  row naming it; an ask-owner alert waits)

### Stage 2 — The app

#### Step 2.1 — The shell: one folder, the inherited sandbox, the console as the window (#6345)
- Behaviours: `builder-app.one-app-one-folder`, `builder-app.console-is-the-window`, `builder-app.build-merge-push-stay-outside`
- Tests: fichero/Tests/Unit/general/Views/Settings/CloudCapsSettingsTests.swift, BuilderAppShellTests.swift (not yet written)
- Depends on: 0.1, 1.2
- Size: L

Fichero's launcher and readiness probe reused for a second engine; the bookmark for the folder; the web view on the
loopback console. The Swift test file cited beside the planned one is the Settings test the shell's folder picker is
modelled on, not a test of this step.

- test (to write): `BuilderAppShellTests.swift` in fichero/Tests/Unit/general/Views/ (the folder bookmark survives a
  relaunch; the console loads from the app's server with the app's token; a worker's push refused, the app's land step
  pushes)

#### Step 2.2 — Signed, notarized, on the website, updated (#6345)
- Behaviours: `builder-app.signed-and-updated-like-fichero`
- Tests: fichero-builder/tests/test_build_verb.py, test_builder_app_release.py (not yet written)
- Depends on: 2.1
- Size: M

- test (to write): `test_builder_app_release.py` in fichero-builder/tests/ (the release lane's DMG smoke opens the app;
  the Sparkle feed carries the version; the bundle imports nothing outside the stdlib and the builder)

## Open questions for the owner

- QUESTION (owner): does the app run the worker's model session itself (Claude Code signed in inside the sandbox, which
  needs the login to live in the container) or does it drive the owner's existing Claude Code install outside it? The
  default taken here is inside, since "runs on a friend's Mac" needs the whole thing in the bundle; the owner may veto.
- QUESTION (owner): one app for builder and console, or the console alone first as a small app that watches a builder
  run from the command line? The default taken here is one app, built after Stage 1 has put everything the owner asked
  for into the page.
