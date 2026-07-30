# Sharing Always-On — Design for Daniel's Sharing Model

**Date:** 2026-07-14
**Status:** DRAFT for Daniel — research + design only; no source was modified
**Trees cited:** engine/Swift code from `~/code/fichero-worktrees/integrate` at `3b8d49b85` (content-identical to `origin/main` at `074f0cf15` — the extra merge is the same commit). Issues read live via `gh issue view`.
**Milestone:** #263 "Sharing & Pairing — Dead-Simple UX" — #3769, #3772, #3774, #3775, #3776, #3777, #3778, #3779.
**Prior art built on (not re-derived):** `docs/superpowers/specs/2026-07-14-ux-critique-toggles-and-pairing.md` (the toggle audit and pairing-flow redesign; its Swift citations were spot-checked and hold).

## The target model (Daniel, authoritative — this is the destination, not a proposal)

- Sharing capability: **always ON**. Multi-user: **always ON**.
- Default **state**: one user, nothing shared.
- Nothing shared → the backend **refuses the connection**. The empty share-set IS the closed door.
- **No** "enable sharing" toggle. **No** "enable multi-user" toggle.
- Sharing is **whole libraries only** — not folders (Daniel, 2026-07-14: *"just whole libraries"*).
- "Share this library" is **one action** that does its own setup.
- Keep: share, multi-user, add/edit/remove users.
- One "off" escape hatch, under Advanced, off by default.
- Never a dead control, never a silent no-op, never a blank space.
- **Security is not weakened**: SPKI pinning, loopback-only bind, per-device tokens, short-lived pair codes, fail-closed transport all stay. We remove user-facing machinery, not protection.

## Contents

1. [What has already landed](#1-what-has-already-landed-dont-redo-it)
2. [Ground truth: how the closed door works today](#2-ground-truth-how-the-closed-door-works-today)
3. [The central problem: multi-user always-on vs direct actions](#3-the-central-problem-multi-user-always-on-vs-direct-actions)
4. [Action-context caller table](#4-action-context-caller-table)
5. [The owner-actor design](#5-the-owner-actor-design)
6. [Migration: existing libraries and the first user](#6-migration-existing-libraries-and-the-first-user)
7. ["Share this library" as ONE action](#7-share-this-library-as-one-action)
8. [What replaces the start_backend.sh switches](#8-what-replaces-the-start_backendsh-switches)
9. ["Nothing shared", defined precisely](#9-nothing-shared-defined-precisely)
10. [Ordering: shippable, gateable steps](#10-ordering-shippable-gateable-steps)
11. [Security invariants — preserved, and two loud flags](#11-security-invariants--preserved-and-two-loud-flags)
12. [What I could not determine](#12-what-i-could-not-determine)
13. [Questions for Daniel](#13-questions-for-daniel-each-with-a-recommendation)

---

## 1. What has already landed (don't redo it)

Since the milestone opened this morning, four commits already implement pieces of this design. Any worker picking up the issues must build on these, not re-do them:

| Commit | What it did | Issue |
|---|---|---|
| `c2a5c8d81` | `test_unpaired_remote_request_is_denied_with_empty_device_set` — the P0 proof that an empty device set denies remote requests (`fichero-server/tests/unit/test_api_auth.py:63`) | #3779 |
| `1132b4b47` | Deleted the "Certificate SPKI pin" **text field** (the input, not the protection) | #3776 part 1 |
| `170a6e681` | `pairingStatusMessage` → typed `PairingBlocker` enum: each blocker carries its own headline + fix button (`engineNotRunning → [Start Engine]`, `sharingNotStarted → [Start Sharing]`, `pinNotDerived → [Prepare Certificate]`, `addressMissing` — honest no-button) | #3776/#3769 |
| `3b8d49b85` | `test_multiuser_denies_unresolved_direct_action_actor` — locks the deny boundary this design must now *move through deliberately* (`fichero-server/tests/unit/test_multiuser.py:52-56`) | #263 |

So: **#3779's engine-side verification is DONE and test-locked.** The pairing card's blank-space disease has its first fix. What remains is the structural work: the actor problem (§3–§5), the one-action share (§7), the switch deletion (§8), and the UI consolidation (#3776 rest, #3777).

## 2. Ground truth: how the closed door works today

Established and verified — this section is the foundation everything else stands on.

### 2.1 The engine is structurally fail-closed for remote callers

The auth middleware (`fichero-server/src/fichero_server/api/auth.py:617-728`) admits exactly four credential shapes:

1. **Session token** (multi-user only): hash-matched against the sessions table (`auth.py:411-432`).
2. **Device token**: hash-matched against the devices table — `app_db.get_device_by_token_hash(token_hash)`; with an **empty device set no row can match** → `(None, None, "missing or invalid Authorization header")` → 401 (`auth.py:437-441`). The deny is the *absence of a credential*, not a flag being false. Proved by `test_unpaired_remote_request_is_denied_with_empty_device_set` (`tests/unit/test_api_auth.py:63`).
3. **Bootstrap shared secret**: accepted **only from direct loopback** (`auth.py:653-664` single-user; `auth.py:667-677` multi-user explicitly returns 401 "bootstrap auth is loopback only" for non-loopback). Loopback detection distrusts forwarding headers (`auth.py:459-471`).
4. **Nothing valid** → 401/403; non-loopback with no device token in single-user mode → `403 loopback only` (`auth.py:653-656`).

**Therefore deleting the UI toggles cannot open a hole.** The toggles govern whether *hosting transport* is even provisioned; the *authorization* boundary is credential rows, and it holds even with hosting up.

### 2.2 Transport is separately fail-closed

- The engine binds `127.0.0.1` by default; non-loopback bind requires the explicit risk-acknowledgement env (`FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK`, `fichero-server/src/fichero_server/bind_host.py:16-20,47-56`).
- Remote pairing refuses non-HTTPS and refuses to run without a configured SPKI pin (`fichero-server/src/fichero_server/api/routes/auth/pairing.py:357-369`); direct loopback pairing is exempt (`:359-360`) — the local Mac pairing its own phone over the QR channel.
- Bonjour is advertisement only, "not authorization" by design (`fichero-server/src/fichero_server/discovery.py:3-5`).

### 2.3 But "always on" is contradicted by three switch layers

1. **Engine gate:** `multiuser_enabled()` defaults **off**; turns on only via `FICHERO_MULTIUSER` env or the persisted `multiuser.enabled` app-db setting (`fichero-server/src/fichero_server/multiuser.py:15-39`). No engine code writes that setting (grep: zero `set_setting(MULTIUSER_SETTING_KEY…)` sites) — in practice the env var, derived at launch, is the gate.
2. **Launcher switches:** `fichero-server/scripts/start_backend.sh:43-65` reads macOS `defaults` (`fichero.remote_access.enabled`, `fichero.multiuser.enabled`, …); `:114-121` makes `FICHERO_MULTIUSER` **default to 1 only when a public URL is configured**, else 0 — multi-user is coupled to hosting.
3. **App switches:** the Mac app passes `FICHERO_MULTIUSER: EngineConfig.multiuserEnabled ? "1" : "0"` at embedded launch (`fichero/Services/EngineConfig.swift:580`), and `multiuserEnabled` defaults **false** with an explicit comment saying why: *"Defaulting ON spawns the backend with FICHERO_MULTIUSER=1, whose fail-closed ACL choke-point then 401/403s the app's own requests so no library loads"* (`EngineConfig.swift:178-186`).

That comment is the whole story: **multi-user always-on is blocked by the actor problem**, not by any security need for a toggle. Solve §3 and every one of these switches becomes deletable.

## 3. The central problem: multi-user always-on vs direct actions

With `FICHERO_MULTIUSER=1`, every authorization check runs `authz._allowed()` (`fichero-server/src/fichero_server/authz.py:235-253`):

```
resolve_user(user) is None            → deny        (authz.py:245-248)
no LibraryRole row for (user, lib)    → deny        (authz.py:251-253)
```

`resolve_user` returns `None` for `None`, empty strings, the literal `"system"`, and any string that is not a user id/username in the accounts table (`authz.py:56-75`). So any `ActionContext` whose `actor` is `"system"`, `"workflow"`, `"ui"`, etc. is **denied at the registry choke point** (`fichero-server/src/fichero_server/actions/registry.py:186-190`) — proved by `test_multiuser_denies_unresolved_direct_action_actor` (`tests/unit/test_multiuser.py:52-56`).

There is exactly one escape valve: `ActionContext.is_bootstrap` (`registry.py:55,186`) — contexts built by the `action_context` FastAPI dependency carry the middleware's `bootstrap_auth` flag (`auth.py:534-547`), and the read/write route guards return early for bootstrap (`fichero-server/src/fichero_server/api/main.py:1149-1150,1180-1181`). So the local Mac app mostly *works* under multi-user — but it works **anonymously**: in the multi-user branch the bootstrap path sets `request.state.user = None` (`auth.py:676`), `actor_from_request` degrades to `"system"` (`auth.py:474-489`), and every audit row loses attribution (`registry.py:198-207`). Meanwhile everything that does **not** ride an HTTP request with the bootstrap flag — workflows, internal fallbacks, future agents — is dead.

The fix is not to weaken the deny. The deny is correct. The fix is to make **every direct action resolve a real user** — which is also exactly Daniel's #1847 direction (an AI model is a real user account with a role, acting via audited tools).

## 4. Action-context caller table

Every path that reaches the authz choke points, what actor it carries today, what happens under multi-user, and what it should resolve to. (Grep basis: all `ActionContext(` constructors, all `assert_can_read/write`, `ensure_owner_role`, `require_owner`, `_require_owner_or_bootstrap` call sites.)

| # | Caller | Actor today | Under `FICHERO_MULTIUSER=1` today | Should resolve to |
|---|---|---|---|---|
| 1 | **Mac app / local UI** — loopback + bootstrap secret | `request.state.user = None` → actor `"system"`; `is_bootstrap=True` (`auth.py:676,534-547`) | Works via bootstrap bypass, but **audits say "system"**; `ensure_owner_role(None,…)` no-ops so new libraries get **no owner row** | **The owner account.** Reuse `_resolve_single_user_owner()` (`auth.py:550-581`) in the multi-user bootstrap branch too — see §5 |
| 2 | **Remote device, session token** | Real `AccountUser` (`auth.py:692-697`) | Works | Unchanged |
| 3 | **Remote device, device token** | Real `AccountUser` via `device.user_id` (`auth.py:707-726`, `models.py:1103-1115`) | Works | Unchanged |
| 4 | **CLI** (`fichero` command) | Bearer = the per-launch bootstrap shared secret (`fichero-cli/src/fichero_cli/client.py:5,282`) → same as row 1 | Same as row 1 (loopback-only, anonymous) | **The owner account** — the CLI is the owner at their own keyboard. Falls out of the row-1 fix automatically. If CLI-as-another-user is ever wanted, that's a session login (`#2022` notes auth is CLI-only today), not a new mechanism |
| 5 | **Routes with per-route `action_context` dependency** (citations, claims, entities, references, artifacts, sources, bibliography, library_links, actions_registry, library_registry — all build ctx via `Depends(action_context)` / `actor_from_request`) | Whatever the request resolved (rows 1–3) | Follows rows 1–3 | Unchanged mechanism; fixed by row 1 |
| 6 | **Defensive fallbacks** `ActionContext(actor="system")` when the dependency "isn't an ActionContext" (`fichero-server/src/fichero_server/api/routes/claim_links.py:165,218,236`) | `"system"`, `is_bootstrap=False` | **Denied** if ever reached | **Delete the fallbacks.** The dependency always returns an `ActionContext`; a silently-substituted anonymous context is precisely the "silent fallback masks bugs" class (#2430 lesson). Raise instead |
| 7 | **Workflows** (`fichero-server/src/fichero_server/workflows/tools/merge_dedup_only.py:172`, `organize_same_documents.py:90`) | `actor="workflow"` | **Denied** (`resolve_user("workflow") → None`) | **The initiating user**, threaded from the request that started the workflow run; keep `run_id` for the "via workflow" provenance already designed into the audit (`registry.py:47-48,205`). A workflow is never its own principal — someone pressed Run |
| 8 | **Chat/AI agent tools** (`fichero-server/src/fichero_server/actions/chat_tools.py:185-194`) | `actor` is a parameter; the #1847 wiring comment says how it will be connected; **no production caller yet** (grep found none) | Denied unless the passed actor is a real account | **A real user account with a role** — Daniel's #1847 model, verbatim. The AI signs in as itself; its role rows scope what it may touch; audits attribute it honestly (AI-as-instrument requires exactly this) |
| 9 | **Registry default** `ActionContext.actor = "system"` (`registry.py:51`) | anonymous | Denied wherever defaulted | After rows 6–8 are fixed, make `actor` **required** (no default) so a new caller cannot compile/run anonymously by accident |
| 10 | **Read guards** `assert_library_read_authorized` / write twin (`api/main.py:1140-1199`) | `request.state.user` | Bootstrap bypasses (`:1149-1150`); users need role rows | Unchanged mechanism; legacy-library role backfill covers the role-row gap (§6) |
| 11 | **Owner-gated admin routes** (`_require_owner_or_bootstrap`: accounts, providers, provider_keys, settings, mcp_servers, kg curation — `fichero-server/src/fichero_server/api/routes/auth/accounts.py:…`) | bootstrap **or** session owner | Works | Unchanged — this helper already implements "local Mac = owner" for admin surfaces |
| 12 | **Search visibility filters** (`fichero-server/src/fichero_server/api/routes/search.py:57,92,108,130`) | bootstrap bypass or per-user `can_read` | Works | Unchanged |
| 13 | **Pairing routes** (`pairing.py:179-186 _pairing_user`) | single-user: synthesizes/returns an owner account; multi-user: requires session owner or bootstrap | Works | Unchanged in mechanism, but see §5 on the **two competing owner accounts** it can create |

**Summary:** rows 2, 3, 5, 10–13 already behave correctly. The entire "central problem" reduces to: (a) make loopback-bootstrap resolve the owner account under multi-user (rows 1, 4), (b) thread the initiating user through workflows and future agent calls (rows 7, 8), and (c) delete the anonymous fallbacks and the anonymous default (rows 6, 9). No authorization rule changes; only *who the caller is* gets fixed.

## 5. The owner-actor design

### 5.1 What already exists (build on it — iterate, never replace)

- `_resolve_single_user_owner()` (`auth.py:550-581`): returns the single active `is_owner` account, **creating** `username="owner"` keyed to the bootstrap token if none exists. Already called in the single-user bootstrap branch (`auth.py:663`).
- `_single_user_pairing_owner()` (`pairing.py:193-211`): the pairing route's own owner-creation path, username `__paired_device_owner__` (`pairing.py:79`).
- `ensure_owner_role()` (`authz.py:171-193`): writes the first owner LibraryRole for a library — called on library open/create (`api/main.py:1136`, `api/routes/library.py:131`).
- `_bootstrap_legacy_library_owner()` (`api/main.py:1088-1137`): backfills owner role rows for pre-multi-user libraries on first trusted owner access — including the loopback-bootstrap-with-exactly-one-owner case (`:1124-1131`).

### 5.2 The design (small, mostly already-written)

1. **One line of truth:** in the multi-user bootstrap branch, replace `request.state.user = None` (`auth.py:676`) with `request.state.user = _resolve_single_user_owner()` — the exact mirror of the single-user branch two screens up (`auth.py:663`). Loopback + bootstrap secret = the Mac's owner, in both modes. This single change fixes rows 1 and 4 of the table: audits attribute the owner, `ensure_owner_role` fires on library creation, the legacy backfill's session path applies, and `actor_from_request` stops degrading to `"system"`.
2. **Unify the two owner-creation paths.** `"owner"` (auth.py:568) and `"__paired_device_owner__"` (pairing.py:79) can BOTH exist as `is_owner=True` rows, and both resolvers then pick `owners[0]` / `active_owners[0]` (`auth.py:561-562,574-575`; `pairing.py` `_owner_for_pairing`) — order-dependent identity. Fix: one canonical constant + one `ensure_owner_account()` helper in `accounts.py`/`auth.py` that both call; a small idempotent migration folds `__paired_device_owner__` into the canonical row **iff both exist** (re-point `device.user_id`, `library_roles.user_id`, deactivate the duplicate). This is a real data migration → `db_migrations.py`, idempotent ALTER/backfill discipline per the standing rule.
3. **Thread the initiating user into workflows.** Workflow run state already carries `task_id` into `run_id` (`organize_same_documents.py:92`); add the requesting actor at the same place the run is created (the route that starts the run has `request.state.user`), persist it on the run/task record, and build `ActionContext(actor=<that user>, run_id=…)` in the tools. Delete the `"workflow"` literals.
4. **Agent/MCP callers = accounts** (#1847). `chat_tools.dispatch` already takes `actor` as a parameter (`chat_tools.py:185-194`) — the contract is right; the wiring rule is: the value must be a real account (the model's account), never a role-name string.
5. **Keep `is_bootstrap` as the local-trust bypass — explicitly documented.** Even with the owner resolved, the bootstrap bypass (`registry.py:186`, `main.py:1149,1180`) means the local Mac app is never locked out by ACL misconfiguration (e.g., a library whose only owner row points at a deactivated account). That is the correct availability property for "your own Mac, your own data." It should be stated in code comments as a decision, not left as an accident. (Tightening it later — bootstrap acts as owner but still passes through `_allowed` — is possible once the owner row is guaranteed, but is **not** required by Daniel's model and risks lockouts; recommend keeping the bypass.)

### 5.3 Is there a migration problem? (asked directly by the brief)

**Mostly no, by construction — the lazy-bootstrap pattern already handles it:**
- *No user rows at all:* the first authenticated loopback request creates the owner account (`auth.py:563-573`). Nothing is created at install time; nothing strands.
- *Existing libraries with no role rows:* `_bootstrap_legacy_library_owner` backfills owner on first access (`api/main.py:1088-1137`), and the bootstrap bypass keeps everything readable even before that fires.
- *The genuinely broken case:* **two competing owner accounts** (§5.2 item 2) — that's the one real migration, and it's small and idempotent.
- *Marshall Diaries discipline applies:* the owner-unification touches `users`, `devices`, `library_roles` in the app DB — idempotent migration in `db_migrations.py`, never destructive, full backend suite as the gate (targeted `-k` runs skip the guardrail tests).

## 6. Migration: existing libraries and the first user

Concrete sequence for a Mac upgrading from today's build to always-on multi-user, with nothing shared:

1. App update launches engine with no `FICHERO_MULTIUSER` coupling (§8); `multiuser_enabled()` now returns True (final step of §10).
2. First loopback request → bootstrap secret verified → `ensure_owner_account()` returns-or-creates the canonical owner → `request.state.user` = owner.
3. First open of each existing library → `_bootstrap_legacy_library_owner` writes the owner `LibraryRole` (`api/main.py:1136`).
4. Devices table: empty (nothing was ever paired) → every remote request 401s exactly as the #3779 test proves. **State after upgrade = "one user, nothing shared" with zero user-visible steps.**
5. If devices WERE paired before the upgrade (single-user pairing attached them to the synthesized owner — `pairing.py:193-211`): they keep working, now attributed to the canonical owner after the §5.2 unification. No re-pairing. (#3772's iOS-side persistence bug is orthogonal and stays its own issue.)

## 7. "Share this library" as ONE action

### 7.1 What sharing a library *is*, in data (whole libraries only)

Three rows, all existing schema — **no new tables**:
- an **account** for the person (exists: `users`, invites — `UsersSettingsView`/`InviteAccountSection`, engine `auth_accounts.py`),
- a **LibraryRole** (user, library-path, owner/editor/viewer) (`models.py:1118+`, `authz.set_role` `authz.py:110-125`) — *this is the whole-library grant; per-target ACL overrides (`set_override`) exist but stay out of the primary UX, matching "just whole libraries"*,
- a **device credential** for each of their devices (`models.py:1103-1115` — app-wide, user-scoped, deliberately not library-scoped; the library scoping is the role row).

"Share this library with Ana as Viewer" = ensure account (invite) + `set_role(viewer)` + Ana pairs a device. Unshare = `remove_role` (+ optionally revoke devices). Sharing with **your own other devices** is the degenerate case: role rows already yours; only the device pairing is needed — which is why pairing alone must feel like the whole flow there.

### 7.2 The preconditions the one action must perform ITSELF

Enumerated against today's chain (the #3769 five-gate disease). For each: can the app do it automatically, and if not, the honest message + button.

| # | Precondition | Automatic? | How / honest fallback |
|---|---|---|---|
| 1 | Engine running | **Yes** | App owns the embedded engine; `applySharing()` already stops/starts it (`fichero/Views/Settings/Sharing/ShareSettingsView.swift:348-379`). Failure → the landed `PairingBlocker.engineNotRunning` card with **[Start Engine]** (`170a6e681`). Debug external-engine mode can't restart what it doesn't own — say so: "Fichero is using an external engine; restart it with sharing enabled" (this is dev-only per the Debug-external/Release-embedded split, #3042) |
| 2 | TLS material + SPKI pin | **Yes, fully** | Engine mints and persists cert+pin at launch (`prepare_remote_access_tls`, invoked by both launch paths — `start_backend.sh:88-113`, `EmbeddedBackendService` per critique §3.3); the pin is never typed (field already deleted, `1132b4b47`). Derivation failure → `PairingBlocker.pinNotDerived` + **[Prepare Certificate]** (landed) |
| 3 | A reachable address | **Same-network: yes.** Off-network: **no — and honesty is required** | Same network: auto-derive `https://<hostname>.local:8765` (`ShareSettingsView.swift:37-44`, already built). Off-network requires Tailscale (`tailscale serve`, #2124) — the app can *detect* Tailscale and offer the `.ts.net` route as a **named choice** ("On your network" / "Anywhere, via Tailscale"), but cannot conjure connectivity: honest message "To share beyond your network, Fichero uses Tailscale" + **[Set Up]** / link. Never a URL text field on the primary path (manual override survives only under Advanced). ⚠️ See §11 flag 1 — which transport is blessed is Daniel's call |
| 4 | Engine restarted with hosting env | **Yes** | `applySharing()` already does the restart transparently (`ShareSettingsView.swift:332-346`); "Apply and Restart Engine" as a *user job* is deleted (#3776 table) |
| 5 | Bonjour advertising | **Yes** | Auto-on with sharing (`ShareSettingsView.swift:338`); it is discovery, not authorization (`discovery.py:3-5`). Toggle deleted |
| 6 | Pair code minted | **Yes** | `POST /api/pairing/code` (`pairing.py:394+`), short-TTL, rate-limited (`pairing.py:322-347`). Mint failure → visible retry ("Couldn't create a pairing code: <error> [Try Again]") — never a blank QR slot |
| 7 | Payload delivered to the other device | **Yes** | QR **and** the copyable/sendable link carrying the identical payload (URL + pair code + expiry + SPKI pin + library path) — #3774; iOS "Enter Link Manually" already parses it (`FicheroApp_iOS.swift:396-403`, from #2350). Simulator has no camera → the link is the only path there |
| 8 | Person + role for *this* library | **Yes, within the flow** | For "my other device": nothing to do (owner). For another person: the share sheet IS the invite — pick person (or "Invite…" minting the existing `fichero://invite`) + role (Viewer/Editor); acceptance writes the `LibraryRole` via existing `set_role`. The QR payload already carries `library_path` — the share action pins the grant to the library it was invoked on |
| 9 | Undo | **Yes** | Devices list with Remove (revoke, exists) + People list with role edit/remove (exists) — in the same single surface (#3777) |

**Contract:** the action never *refuses because preconditions aren't met*; it *performs* them, and when one genuinely cannot be performed (external engine; no off-network route), it names the one problem and offers the one fix. That is the landed `PairingBlocker` pattern extended to the whole flow.

### 7.3 Where it lives

One surface (#3777): **Library Access → Sharing** (ShareSettingsView's pane — the critique's "surface B", already the good one), absorbing People/accounts + Devices + the QR card; the Engine→Backend duplicate ("surface A") is deleted, with "Reset Invite" and the manual-URL override folded into ONE Advanced disclosure. Plus a **"Share…"** entry point on the library itself (sidebar context menu / File menu) that opens the same sheet — you share a thing by sharing it. #3775's folder-share confusion resolves by scoping the affordance honestly: the context-menu item appears **on libraries**, and a folder's menu shows no share item (folders are organized *inside* a shared library; if a user asks, the answer is the parent library's share sheet — never a dead control).

## 8. What replaces the start_backend.sh switches

`start_backend.sh` is the **Debug/dev external-engine launcher** (Release embeds and spawns — #3042, `EngineConfig.launchEnvironment` `EngineConfig.swift:573-591`). Today it smuggles product policy in via macOS `defaults`:

| Today (`fichero-server/scripts/start_backend.sh`) | Replacement |
|---|---|
| `:49-51` reads `fichero.remote_access.enabled` from defaults; `:69-71` uses it to gate restoring the public URL | **Delete.** Hosting is not a persisted mode; it is the presence of `FICHERO_PUBLIC_BASE_URL` in the launch env, supplied by the app when share-state requires hosting (§9). Dev override: pass the env var explicitly |
| `:57,60-65` reads `fichero.multiuser.enabled` from defaults into `FICHERO_MULTIUSER` | **Delete** once multi-user is always-on. During transition (§10 step 5), `FICHERO_MULTIUSER` remains honored by `multiuser.py` for tests; at the final step `multiuser_enabled()` returns True unconditionally and the env var becomes a no-op (keep `FICHERO_MULTIUSER=0` working **only** in pytest via the existing conftest until the test suite is migrated — the conftest autouse `FICHERO_MULTIUSER=0` and every gate-dependent test must flip in the same PR as the flip, or the suite goes red en masse) |
| `:114-121` `FICHERO_MULTIUSER` **depends on a public URL** | **Delete the coupling entirely.** Multi-user (who you are) and hosting (how you're reached) are orthogonal; the coupling is why local-only multi-user never worked |
| `:85-87` loopback TLS by default | **Keep** — this is the always-secure baseline and already right |
| `:122-177` defaults-cleanup + SPKI-pin writes into the app's defaults domain | Keep for dev parity (the Debug app reads pins from defaults), but it is dev tooling, not product |

**The product rule that replaces all of it:** the *app* computes the launch env from the share-state — `FICHERO_PUBLIC_BASE_URL`/`FICHERO_ENABLE_BONJOUR` (+ bind material) present iff hosting should be up (§9), nothing read from hidden defaults switches. `EngineConfig.launchEnvironment` already is that function (`EngineConfig.swift:573-591`); it loses its `FICHERO_MULTIUSER` line and gains "hosting iff share-state non-empty or pairing in progress".

Engine-side deletions when the flip lands: `multiuser.py`'s gate logic (module shrinks to `return True` + deprecation shim), the `multiuser_enabled()` early-returns at `authz.py:178,242` and `api/main.py:1109`, the mode-forks in `auth.py:447-450,627-664` (the single-user middleware branch collapses into the multi-user one, since both now resolve the owner on loopback bootstrap), `pairing.py:179-186`'s mode fork. Each deletion is a place the two modes can no longer diverge — that's the simplification payoff.

## 9. "Nothing shared", defined precisely (this is the security boundary)

Because the empty share-set is the closed door, "empty" must be exact. **Definition — the share-set is empty iff ALL of:**

1. **No usable device credentials:** zero rows in `devices` that are non-revoked and non-expired (`models.py:1108-1115`; checked at `auth.py:439-446`).
2. **No other people:** zero active accounts besides the canonical owner (`users.is_owner`, `app_db.py:221`), and zero active sessions for non-owner accounts.
3. **No outstanding invites/pair codes:** no unexpired invite tokens or pairing codes (pair codes are in-memory + short-TTL — `pairing.py:394-410` — so they self-empty).

**Consequences, in order of strength:**
- With (1)–(3) empty, **hosting is not even provisioned**: the app has no reason to pass `FICHERO_PUBLIC_BASE_URL`, the engine binds loopback only (`bind_host.py:16-20`), Bonjour is off. The closed door is *no door*.
- Even if hosting is up (a share was just revoked; a pair code just expired), every remote request fails auth at the credential check — the #3779-proved property. Empty set → 401 (`test_api_auth.py:63`).
- LibraryRole rows for the owner alone do **not** constitute sharing — the owner's own roles are bookkeeping, not exposure.

**The Advanced "off" escape hatch** (Daniel's one switch): a single persisted setting — proposed name `sharing.suspended`, default false — that makes the app (a) never provision hosting regardless of share-state and (b) the engine refuse **all** non-loopback requests and pairing mints even with valid device tokens outstanding (checked in the auth middleware, fail-closed: suspended → 403 before token lookup). It suspends the *radio*; it does not delete credentials, roles, or accounts — turning it back off restores exactly the prior state. Off the primary path, under Advanced, honestly labeled ("Suspend all sharing — no other device can connect until you turn this off"). It is a *state*, not a capability toggle: the capability code path stays identical.

## 10. Ordering: shippable, gateable steps

Safest first; each independently shippable, testable, and revertible. Backend steps gate on the FULL engine suite (targeted `-k` runs skip guardrail tests); every step adds edge/undo/regression tests, not happy-path only.

| Step | Change | Risk | Gate / proof |
|---|---|---|---|
| 0 ✅ | #3779 engine-refusal test; SPKI field deletion; PairingBlocker card | — | Landed (`c2a5c8d81`, `1132b4b47`, `170a6e681`, `3b8d49b85`) |
| 1 | **Owner unification (engine):** canonical `ensure_owner_account()`; idempotent migration folding `__paired_device_owner__` into it; multi-user bootstrap branch resolves the owner (`auth.py:676`) | Low — additive + one-line branch change; bootstrap bypass unchanged | Tests: dual-owner-rows migration; audit rows attribute owner under both modes; existing deny tests still pass (the deny for *unresolvable* actors must NOT loosen) |
| 2 | **Kill anonymous internal actors (engine):** thread initiating user into workflow runs; delete `ActionContext(actor="system")` fallbacks (raise instead); then make `registry.ActionContext.actor` required | Low-medium — touches workflow plumbing | Test: workflow started by owner writes owner-attributed audits under `FICHERO_MULTIUSER=1`; a context with an unresolvable actor still denies (`test_multiuser.py:52` stays green) |
| 3 | **Verify the legacy backfill under always-on (engine):** multi-library, deactivated-owner, and two-owner edge tests for `_bootstrap_legacy_library_owner` + `ensure_owner_role` | Low (test-mostly) | Full suite |
| 4 | **One-action share assembly (Swift):** single surface (#3777), Share… entry on libraries (#3775 resolution), copyable pairing link (#3774), remaining card states. No engine dependency on steps 1–3 — can proceed in parallel **on disjoint files** | Medium (UI) | Build gate + the launch-stress pattern for the card state machine; the #3772 relaunch-persistence bug fixed independently (Keychain accessibility, per issue) |
| 5 | **The flip (engine):** `multiuser_enabled()` → always True; delete mode forks (§8 list); migrate the test conftest (`FICHERO_MULTIUSER=0` autouse) and every mode-dependent test **in the same PR** | **Highest** — this is where the EngineConfig comment's failure mode ("no library loads") bites if steps 1–3 missed a caller | Full suite green REQUIRED before push (verify-suite-then-push rule); plus a manual smoke: fresh app-DB launch, existing-data launch, CLI ops, one workflow run. If any shipped adversarial security test conflicts, HOLD for Daniel (standing rule) — do not flip an auth-perimeter assertion |
| 6 | **Delete the switches:** app drops the multi-user toggle + `FICHERO_MULTIUSER` line (`EngineConfig.swift:178-186,580`); Engine→Backend duplicate surface deleted (#3776 rest, #3777); `start_backend.sh` defaults-coupling removed (§8); the seven `settings_*_tab` flags per #3776 | Low once 5 holds — UI deletion over a proven engine | Build gate; settings panes exist unconditionally |
| 7 | **Advanced "off" switch** (`sharing.suspended`, §9) — last, so it is built against the final model | Low | Adversarial tests: suspended → 403 with a *valid* device token; unsuspend restores; loopback unaffected |

Issue mapping: step 1–3 + 5 are the engine substrate #3776 is "blocked on"; step 4 = #3774/#3775/#3777 (+#3769 remainder, #3772 independently); step 6 = #3776/#3777 completion; #3778 (numeric pairing) stays **blocked on its written SPKI design** and is untouched by all of this — the QR + link remain the secure pairing paths.

## 11. Security invariants — preserved, and two loud flags

Preserved, mechanism by mechanism (nothing in this design touches them):
- **SPKI pinning** — pin minted+persisted engine-side, carried in QR/link, validated client-side; the deleted *text field* was input, not protection (`1132b4b47`).
- **Loopback-only bind by default** — `bind_host.py:16-20`; non-loopback still requires the explicit ack env.
- **Per-device tokens** — hashed at rest, expiring, revocable (`models.py:1103-1115`, `auth.py:435-456`).
- **Short-lived, rate-limited pair codes** — `pairing.py:322-347,394-410`.
- **Fail-closed transport + auth** — remote pairing refuses non-HTTPS/pinless (`pairing.py:357-369`); empty credential set denies (#3779 test); unresolvable actors deny (`test_multiuser.py:52`) and **keep denying** — we resolve real actors, we do not loosen the deny.
- **Bootstrap secret loopback-only** — in both modes (`auth.py:653-656,667-672`).

**⚠️ FLAG 1 — transport model tension (pre-existing; Daniel must rule, not a worker).** The blessed remote transport per #2124 is *loopback bind + `tailscale serve`* (never funnel; Tailscale = perimeter, not user-authz). But the shipped one-toggle share path binds the engine **directly on the LAN** — `EngineConfig.launchEnvironment` auto-supplies `FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK` + a non-loopback `FICHERO_BIND_HOST` (`EngineConfig.swift:581-582`) for the auto-derived `https://<hostname>.local:8765` (`ShareSettingsView.swift:37-44`). The risk-acknowledgement env that `bind_host.py:1-7` frames as "an explicit, risk-acknowledged escape hatch rather than the default path" is silently supplied by the app on the happy path. This is not *newly* weakened by this design — it shipped — and the exposure is bounded (TLS + pinning + device tokens still gate everything, and the bootstrap secret is never accepted non-loopback). But "the one action does its own setup" must pick its transport, so the contradiction is now load-bearing. **Do not let a worker resolve this silently.** Options in §13 Q1.

**⚠️ FLAG 2 — the bootstrap bypass becomes the permanent local root.** With multi-user always on, `is_bootstrap` (`registry.py:186`, `main.py:1149,1180`) is no longer a transitional shim; it is *the* statement that whoever controls the Mac's loopback + token file controls everything, regardless of ACLs. That is today's trust model unchanged (single-user mode is exactly this), and §5.2(5) recommends keeping it for availability. But it deserves Daniel's explicit sign-off as a permanent property, because "multi-user always on" *sounds* like ACLs always apply — and for the local bootstrap caller they deliberately do not.

Also noted, unchanged and un-traded: clipboard exposure of the copyable link (#3774's own analysis: same secrets as the on-screen QR, short-lived code — accepted there, nothing new here); knock-to-pair and numeric pairing (#3778) remain design-gated on the written SPKI answer.

## 12. What I could not determine

- **Why the EngineConfig comment says multi-user ON breaks "the app's own requests"** in *practice* — by code reading, bootstrap-authenticated route requests bypass authz (`main.py:1149`, `registry.py:186` via `action_context`) and should work anonymously. The comment (`EngineConfig.swift:178-186`) may reflect an older engine, the Debug external-engine + device-token path (which has no bootstrap flag), or breakage via the non-`action_context` callers (workflows, fallbacks). Steps 1–3 fix all candidates, and step 5's smoke test settles it empirically — but I could not run the app to observe which one bites today (no builds; build lock owned elsewhere).
- **Whether anything writes the engine-side `multiuser.enabled` app-db setting** — I found no writer in engine code; if some path writes it that I missed, step 5 must delete that writer too.
- **Runtime behavior of any flow** — everything here is static reading plus the cited tests; no engine was started, no app launched.
- **The workflow-run creation route's exact shape** for threading the actor (§5.2 item 3) — the two workflow tools' `ActionContext` sites are verified, but I did not map every runner entry point (`fichero/workflows/` is large); the implementing worker must enumerate `run` creation sites before wiring the actor through.
- **#3772's root cause** (pairing lost on iOS relaunch) — the issue's instrumentation plan stands; nothing in this design depends on its answer, but the one-action share is only credible once pairing *persists*.

## 13. Questions for Daniel (each with a recommendation)

1. **Which transport does the one-action share bless — LAN direct-bind or loopback + `tailscale serve`?** (Flag 1.) Options: (a) keep the shipped LAN direct-bind (TLS+pin+tokens; simplest same-network UX; contradicts #2124's loopback-only invariant), (b) loopback-only + `tailscale serve` always (honors #2124; requires Tailscale even for same-network sharing — real friction), (c) both as the two *named routes* ("On your network" = LAN bind, "Anywhere" = Tailscale). **Recommendation: (c)** — it matches the routes users understand, keeps #2124 as the off-network rule, and confines the risk-ack bind to the case whose exposure is the local network the user is standing on. If you choose (b), say so before step 4 — it reshapes the share sheet.
2. **Is the loopback bootstrap bypass acceptable as the permanent local root?** (Flag 2: local Mac app/CLI is never subject to per-library ACLs.) **Recommendation: yes** — it is today's trust model, it prevents self-lockout, and per-library ACLs are for *other* principals; document it in `authz.py`'s module docstring as a decision.
3. **Canonical owner account name and visibility:** unify on username `owner` (auth.py's choice), shown in People as "You (Owner)"? Any rename ripples into audits' actor strings. **Recommendation: yes, `owner`,** rendered as "You" in UI; migrate `__paired_device_owner__` into it (§5.2).
4. **Does an AI agent get its account at first use** (auto-created with Viewer role, visible in People) **or only when you explicitly add it as a user?** (#1847 says it IS a user; the question is provisioning.) **Recommendation: explicit add** — "the model is a user" means it appears in People *by your act*, exactly like a person; auto-provisioning an account for an instrument is a decision made silently.
5. **Share roles offered in the sheet:** just Viewer/Editor for others (Owner grantable only from People management)? **Recommendation: yes** — sharing hands out use, not administration; a second Owner is a deliberate People-pane act (`remove_role` already guarantees a library keeps ≥1 owner, `authz.py:128-142`).
6. **The escape hatch semantics** (§9): suspend-the-radio (keep credentials, refuse connections) rather than revoke-everything? **Recommendation: suspend** — reversible, honest, and the fail-closed check is one middleware line; a revoke-all belongs as a separate explicit "Remove all devices" button in the same Advanced disclosure.
7. **Sequencing sign-off:** engine substrate (steps 1–3) before the flip (step 5), UI assembly (step 4) in parallel on disjoint files, switches deleted last (step 6). Flip PR includes the full test-suite migration. **Recommendation: approve as ordered;** the only step with real blast radius is 5, and it is gated on everything before it plus a full green suite.
