# Sharing & Pairing — Consolidated Plan

**Date:** 2026-07-21
**Status:** DESIGN + AUDIT — grounded against code and issues; no engine source modified (the
`feature/research-and-hygiene` branch is actively reorganizing `fichero-engine/src/fichero/*`
security modules into `fichero-engine/src/fichero/security/`, per
`docs/design/engine-package-reorg.md` — that work is out of scope here).
**Verified against:** worktree checkout of `main`, jCodemunch index `local/fichero-29aa4eed`
(48,532 symbols, 2,107 files), plus `git log --all` for the reorg branch state, and `gh issue
list --milestone ... --state all` for all seven milestones below.

## How this doc relates to prior design docs

Two design docs already exist in `docs/superpowers/specs/` from 2026-07-14 (one week before this
audit):

- `2026-07-14-sharing-always-on-design.md` — a deep, code-cited design proposing that both
  sharing *and* multi-user become permanently ON, with the empty share-set as the only closed
  door.
- `2026-07-14-ux-critique-toggles-and-pairing.md` — a toggle-by-toggle UX audit of Settings,
  recommending automation of most switches and consolidation of the two duplicate pairing
  surfaces.

**Both are still valuable references** — most of their concrete recommendations shipped (see
milestone #263 below: 15 of 17 issues closed in the week since). But one central recommendation
was **not adopted**: the 07-14 doc's step 5 ("the flip") proposed making `multiuser_enabled()`
return `True` unconditionally. Current code does the opposite. `fichero-engine/src/fichero/multiuser.py`
today reads:

```python
def multiuser_enabled(env: Mapping[str, str] | None = None) -> bool:
    """...Multi-user auth is **explicit opt-in only**. A fresh single-user local
    launch must never silently enable multi-user because account rows happen
    to exist (the ``__paired_device_owner__`` phantom, #3331)...
    # ponytail: no _has_account_rows() fallback — account rows are a side
    # effect, not intent. Multi-user stays OFF until explicitly turned on.
    return False
```

This matches the standing HARD constraint (`MEMORY.md`: "Two toggles: sharing + multiuser" —
Settings exposes only sharing on/off + multiuser on/off, both explicit). **This consolidated plan
treats the two-toggle model as settled and authoritative**, and flags the 07-14 doc's "always-on"
recommendation as superseded. Everything else in that doc (owner-account unification, the
one-action share, transport invariants, bootstrap-as-local-root) is still accurate and mostly
built — see per-milestone tables below.

---

## Milestone summaries and issue triage

Status legend: **BUILT** (verified closed + code confirms), **ACTIONABLE** (open, no design
blocker, safe to schedule), **DESIGN-BLOCKED** (open, explicitly needs a design/human decision
before code), **TRACKING** (EPIC/summary issue, not itself implementable), **MIS-FILED** (open
issue in this milestone that isn't actually sharing/pairing work).

### #263 — Sharing & Pairing — Dead-Simple UX (15 closed / 2 open)

One paragraph: this is the "dead-simple UX" execution milestone that the 07-14 UX critique fed
directly into — kill the duplicate pairing surface, make "share this library" one action, replace
the SPKI text field with automatic minting, fix the vanishing-QR bug, add zero-touch enrollment
for the owner's own devices, and give Settings the ability to edit/delete accounts. Verified: 15
of 17 issues are closed, matching the critique's recommendations almost issue-for-issue. This
milestone is **effectively done**.

| # | Title | Status | Note |
|---|---|---|---|
| 3859 | DELETE /api/users/{id} missing | BUILT | closed |
| 3858 | PATCH /api/users/{id} can't edit display_name | BUILT | closed |
| 3813 | Share link is loopback URL | BUILT | closed |
| 3811 | "turn on sharing" = one action | BUILT | closed — matches design §7 |
| 3791 | Universal links: fichero.app + AASA on static hosting | ACTIONABLE | no server-side dependency; can proceed anytime |
| 3790 | Email invites: 24h TTL, single-use, revocable | BUILT | closed |
| 3789 | Zero-touch pairing via synced enrollment secret | BUILT | closed |
| 3788 | fichero:// URL scheme unregistered | BUILT | closed |
| 3787 | Add/edit/delete users in Settings | BUILT | closed |
| 3779 | P0: engine refuses connections when nothing shared | BUILT | closed — `test_unpaired_remote_request_is_denied_with_empty_device_set` |
| 3778 | iOS-initiated numeric pairing | DESIGN-BLOCKED | title says "BLOCKED on the SPKI question"; 07-14 critique §3.4 Phase 2 explicitly recommends **not building** this (weaker than QR unless users reliably compare digits) — recommend closing as won't-fix unless Daniel overrides |
| 3777 | Duplicate pairing surface killed | BUILT | closed |
| 3776 | Sharing + multi-user stay toggles, one-action setup | BUILT | closed — confirms two-toggle model in code |
| 3775 | Folder-share affordance misleading | BUILT | closed |
| 3774 | Copyable pairing link (not QR-only) | BUILT | closed |
| 3772 | Pairing doesn't survive relaunch (iOS) | BUILT | closed |
| 3769 | Pairing QR silently disappears | BUILT | closed — the anchor bug of the UX critique |

### #133 — Engine - Sharing - Accounts, Multi-user & Libraries (7 closed / 11 open)

One paragraph: the account/authz substrate — owner resolution, ACL status reporting, actor
attribution. Verified: the owner-unification fix from the 07-14 design doc's §5.2 landed
(`56f98dde6 "fix: unify paired device owner identity (#263)"`, and `pairing.py:199` now calls a
shared `ensure_owner_account(app_db)`). Several open issues here are genuine security hygiene
(actor forgery, toggle desync); several others are **not sharing/pairing work at all** — they
appear mis-filed into this milestone (chat merge failures, reader UI, spatial zoom).

| # | Title | Status | Note |
|---|---|---|---|
| 3343 | Create Owner Account UX | BUILT | closed |
| 3335 | ACL/authz status returns "Server error" when multiuser OFF | ACTIONABLE | small diagnosis-quality bug, low risk |
| 3287 | "No accounts" shown to non-owners (401 swallowed) | BUILT | closed |
| 3286 | Single-user pairing auto-creates owner row | BUILT | closed |
| 3285 | actions/invoke exposes ignored 'actor' body field | ACTIONABLE | matches "prefer raise over silent fallback" standing rule — delete the footgun |
| 3284 | P1: multi-user toggle desync can run hosted engine with authz disabled | ACTIONABLE | real security risk; touches `multiuser.py` — sequence after reorg merge |
| 3277 | Fabel Review Summary — Accounts, Multi-user & Sharing | TRACKING | meta-issue; this consolidated plan effectively supersedes/answers it — recommend closing with a pointer to this doc |
| 3129 | HELD(perimeter): actor_from_request() falls back to "system" | DESIGN-BLOCKED | explicitly HELD, references #2023; do not touch without Daniel |
| 2500 | iPhone merge fails ("operation couldn't be completed") | MIS-FILED | chat/KG bug, not sharing |
| 2484 | Fullscreen reader thumbnail filmstrip | MIS-FILED | Reader View feature, not sharing |
| 2391 | Spatial RealityKit zoom/xpos-ypos bug | MIS-FILED | Library View - Spatial bug, not sharing |
| 2054 | Owner shared-libraries view (which libs shared, with whom) | DESIGN-BLOCKED | tagged `needs-design`; genuinely useful once the sharing model settles — worth designing next |
| 2029 | Multi-writer concurrency + presence | DESIGN-BLOCKED | tagged `needs-design`; explicitly "design pass" only |
| 2021 | EPIC: Multi-user, permissions & remote lab collaboration | TRACKING | parent epic for this whole milestone cluster |
| 1867 | Share button (library/entity/doc) | BUILT | closed |
| 1202 | KG entity inspector prose biography | MIS-FILED | Inspector View - Knowledge feature, not sharing |
| 971 | Cross-page paragraph NER | MIS-FILED | ingestion/NER bug, not sharing |

### #96 — Engine - Sharing - Device Pairing (37 closed / 5 open)

One paragraph: this is the most heavily built milestone in the cluster — SPKI pinning, Bonjour
discovery-as-hint, per-device tokens, tailnet fallback in the QR payload, device-token
renewal/expiry UX, adversarial pairing tests (code replay, rate-limit isolation), and remote
change-stream propagation are all shipped and verified in code (`remote_access_tls.py`,
`discovery.py`, `bind_host.py`, `pairing.py`). What remains is mostly hardening and iOS-side
polish.

| # | Title | Status | Note |
|---|---|---|---|
| 3375 | Pairing hardening: mTLS, UDS, iCloud identity sync | DESIGN-BLOCKED | tagged `needs-design`; note the UDS transport bind already landed separately (`89ae0fb85` "additive UDS transport bind (Lane E)") — re-scope against that before designing |
| 3374 | SPKI pin mismatch recovery + re-pin flow | ACTIONABLE | Swift-side; no reorg dependency |
| 3373 | Device tokens in Keychain with renewal/reset UX | ACTIONABLE | Swift-side; no reorg dependency |
| 3372 | QR/deep-link handshake must confirm library path before persisting | ACTIONABLE | this is the known #3273 hole the 07-14 critique flagged (client persists QR's `library_path` without server confirmation) |
| 3371 | Discover Mac-hosted engine candidates on iOS/iPad | ACTIONABLE | Swift-side; Bonjour consumption already exists client-side per `FicheroApp_iOS.swift` — verify scope before starting, may be partially done |
| ...37 closed | SPKI pinning, tailnet transport, Keychain-owner separation, adversarial pairing tests, cross-device sync, etc. | BUILT | verified in code: `remote_access_tls.py`, `pairing.py:322-410` (rate-limited codes), `bind_host.py` |

### #231 — Engine - Sharing - Discovery (0 issues)

**Empty milestone.** The discovery capability it names is fully built (`discovery.py` — Bonjour
advertisement, TXT record intentionally carries no SPKI trust anchor per the module docstring:
*"Bonjour only helps clients find a running engine on the local network. It is not
authorization"*), but all discovery-related issues were filed under milestones #96 (pairing) or
#74 (remote) instead. Recommend closing #231 or explicitly re-scoping it to hold future
discovery-specific work (e.g., #3371) so discovery has one home.

### #218 — Engine - Sharing - Multi-Library (2 closed / 6 open)

One paragraph: this is the "each library owns its own connection" axis of the engine-ownership
model (`MEMORY.md`: "app owns one engine PROCESS; each LIBRARY owns its CONNECTION — not XOR").
The core mechanism (#2573, per-library host on `LibraryReference`) is still open and is the
highest-leverage item in this milestone — everything else (sidebar showing where a library lives,
TestFlight build, iPad/Vision Pro clients) either depends on it or is peripheral.

| # | Title | Status | Note |
|---|---|---|---|
| 2666 | iPhone has no way to open document preview/reader | ACTIONABLE | real regression bug, only loosely multi-library-related |
| 2665 | iPad EXC_BAD_ACCESS crash blocking launch | BUILT | closed |
| 2574 | Sidebar shows where each library lives (local vs remote) | BUILT | closed |
| 2573 | Multi-engine: per-library host on LibraryReference | ACTIONABLE | **core of the two-axis model** — connect to own + remote engines per library; sequence after reorg merge (touches connection/auth plumbing) |
| 2570 | TestFlight (internal) build | ACTIONABLE | release logistics, no design blocker |
| 2096 | EPIC: iOS/iPad client connecting to Mac-hosted engine | TRACKING | parent epic |
| 1160 | Vision Pro + iPad: read/annotate/notes | DESIGN-BLOCKED | tagged `needs-design` |
| 968 | iPad/iPhone client via Tailscale | BUILT-MOSTLY | most of the underlying tailnet transport (advertise `.ts.net`, failover LAN→tailnet) shipped under #74; recommend re-verifying against current state and closing or narrowing |

### #74 — Engine - Sharing - Remote & Self-Hosting (16 closed / 2 open)

One paragraph: this milestone is **essentially complete**. Tailnet transport detection, Bonjour
advertisement, self-signed TLS + SPKI exposure, the loopback+`tailscale serve` model
(`docs/contributor/remote-backend-tailscale.md`, verified current and accurate against
`bind_host.py`), the platform abstraction layer, and the AppKit-to-SwiftUI audit are all closed
and confirmed in code. Only generic "someday" web-client work remains open.

| # | Title | Status | Note |
|---|---|---|---|
| 1182 | Platform expansion: web UI + iOS/iPad sharing FastAPI backend | DESIGN-BLOCKED | no active design; genuine product-priority fork (see Decisions below) |
| 1094 | Web client calling the engine | DESIGN-BLOCKED | same fork as 1182 |
| ...16 closed | Tailnet detection, Bonjour+TLS LAN listener, platform abstraction, AppKit audit, remote iOS/iPad target, no-local-paths audit | BUILT | verified: `docs/contributor/remote-backend-tailscale.md` matches `bind_host.py` current behavior exactly (loopback default, explicit-ack escape hatch, `tailscale serve` not funnel) |

### #205 — Engine - Sharing - Settings (0 issues)

**Empty milestone.** The settings-surface consolidation this milestone would have owned
(one Sharing pane, deleting the duplicate Engine→Backend pairing UI, deleting the seven
`settings_*_tab` feature flags) happened instead under #263 (3776, 3777) and is already
partly reflected in code: `FeatureManager.swift` still defines all seven
`settings_*_tab` flags, but `settings_backend_tab` now defaults **false** (confirmed at
`FeatureManager.swift:357`), matching the critique's recommendation to retire the duplicate
pane. The flags themselves are not yet deleted (critique recommendation "DELETE all seven"
is not fully executed — they still exist, just defaulted off). Recommend closing #205 and
filing one small ACTIONABLE issue to finish deleting the flags, or folding it into #263.

---

## Architecture: one model, five surfaces

All seven milestones are facets of a single account/access model, not seven independent
subsystems. Grounded in verified code:

1. **Accounts are people, not devices.** `users` table + `is_owner` flag is the root of trust.
   One canonical owner account (post `56f98dde6` unification — the `owner` /
   `__paired_device_owner__` duplicate-owner bug is fixed). A `LibraryRole` row per (user,
   library) is the grant unit — **whole libraries only**, no folder-level sharing (verified: 3775
   closed as "not a bug: folder sharing does not exist").
2. **Devices are credentials scoped to a user, not to a library.** `devices` table stores
   per-device tokens (hashed at rest, expiring, revocable — `models.py`). Pairing a device grants
   *that person's* existing roles; it does not itself grant access — the `LibraryRole` does. This
   is why "share with my other iPhone" only needs a pairing step (the role rows are already
   mine), while "share with Ana" needs an account + a role + a device.
3. **Discovery is an unauthenticated hint layer, never a trust source.** `discovery.py`'s own
   module docstring states this; the Bonjour TXT record's `spki` field is deliberately blank
   (`_txt_properties()`) — SPKI provenance comes only from the QR/link payload or explicit
   confirmation, never from the network advertisement. This is fully built and matches the HARD
   constraint verbatim.
4. **Transport is orthogonal to authorization, and binds fail-closed by default.** `bind_host.py`
   defaults to `127.0.0.1`; any non-loopback bind (LAN direct or otherwise) requires the explicit
   `FICHERO_ALLOW_NON_LOOPBACK_BIND=I_UNDERSTAND_SHARED_SECRET_RISK` acknowledgement. The
   documented supported remote path is loopback + `tailscale serve` (never funnel) — verified
   current and accurate in `docs/contributor/remote-backend-tailscale.md`. **Open tension** (see
   Decisions #1): the shipped one-action "Share this library" toggle auto-supplies that
   acknowledgement env for same-network LAN sharing (per the 07-14 design's Flag 1) — this was
   flagged for Daniel a week ago and this audit could not confirm it was resolved. It should be
   resolved explicitly, not left as an accident of what shipped.
5. **The engine has two independent ownership axes** (`MEMORY.md`, verified consistent with
   `#218`'s open #2573): the app supervises exactly one engine *process* (embedded, local); each
   *library* independently owns its *connection* — local-embedded or remote-hosted. These are not
   mutually exclusive. #2573 (per-library host on `LibraryReference`) is the one piece of this
   axis still unbuilt; everything else in the cluster (accounts, pairing, discovery, remote
   transport) is connection-agnostic plumbing this axis will consume once it lands.

The two Settings toggles (`sharing` on/off, `multiuser` on/off — both explicit, per current
`multiuser.py` and the HARD "two toggles" constraint) are the only user-facing controls over this
entire model. Everything else — SPKI pins, transport selection details, device-token renewal,
Bonjour — is automatic machinery behind those two switches, per the 07-14 UX critique's
"AUTOMATE by default" verdict, which is now mostly executed (#263 closed count confirms it).

---

## Ordered implementation sequence

**Hard sequencing constraint:** `feature/research-and-hygiene` (#2566) is mid-flight, moving
`accounts.py`, `multiuser.py`, `bind_host.py`, `remote_access_tls.py`, `security_scoped_access.py`,
`discovery.py`, `remote_backend.py` (and 5 more) into `fichero-engine/src/fichero/security/`, with
identity-preserving import shims. It changes file *locations*, not behavior (route count verified
unchanged: 360 before/after). Any engine-side sharing/pairing work that touches these modules
should land **after** that branch merges to `main`, to avoid rebasing security-module edits across
a mass file move. Swift-side and purely-additive work (new files, no edits to the moved modules)
can proceed in parallel.

1. **Merge `feature/research-and-hygiene` (#2566) to `main`.** Blocking prerequisite for
   everything engine-side below.
2. **In parallel with step 1 (Swift-only, no engine dependency):**
   - #3374 SPKI pin mismatch recovery/re-pin flow
   - #3373 device tokens in Keychain with renewal/reset UX
   - #3372 QR/deep-link library-path confirmation (client-side check; server already returns the
     library path, this closes the trust gap)
   - #3371 discover Mac-hosted engine candidates on iOS (verify against existing
     `FicheroApp_iOS.swift` Bonjour consumption first — may be partially done)
   - #2666 iPhone document preview/reader access (regression fix, disjoint files)
   - #3791 universal links / AASA (static hosting, zero engine dependency)
3. **After step 1 merges, engine-side hygiene (small, safe):**
   - #3335 ACL/authz status 500 when multiuser OFF
   - #3285 remove ignored `actor` body field from actions/invoke
   - #3284 multi-user toggle desync (security-relevant; needs a real fix + adversarial test, not
     just a UI tweak)
4. **After step 3, the core multi-library mechanism:**
   - #2573 per-library host on `LibraryReference` — this is the one piece of the two-axis
     ownership model still missing; unblocks #218's remaining open issues and gives multi-engine
     support a real foundation
5. **Housekeeping, any time (no code dependency):**
   - Close or re-scope the two empty milestones (#231 Discovery, #205 Settings) — fold into #96
     and #263 respectively, or explicitly re-home future discovery/settings-surface issues there
   - Close #3277 (Fabel Review Summary) pointing at this doc
   - Re-verify and close #968 (iPad/iPhone via Tailscale) against current shipped state
6. **Design-gated, needs a decision or a design pass before any code:**
   - #2054 owner shared-libraries view (needs-design)
   - #2029 multi-writer concurrency + presence (needs-design)
   - #3375 pairing hardening / mTLS / UDS / iCloud identity (needs-design; re-scope against the
     already-shipped UDS transport bind first)
   - #1160 Vision Pro / iPad annotation clients (needs-design)
   - #1182 / #1094 web client (blocked on the product-priority decision below)
   - #3129 actor_from_request fallback (explicitly HELD per standing rule — do not touch without
     Daniel)
   - #3778 numeric pairing (recommend closing as won't-fix per the 07-14 critique's own
     recommendation, unless Daniel wants it reopened)

---

## Decisions Daniel must make

The two-toggle model, transport invariants, account-not-device identity, and owner-as-permanent-
local-root are all already settled by existing HARD constraints and verified in shipped code —
they are **not** re-litigated here. These are the genuine remaining forks:

1. **Which transport does the one-action "Share this library" toggle actually bless?**
   `EngineConfig.swift` auto-supplies the non-loopback bind risk-acknowledgement for the
   auto-derived `https://<hostname>.local` LAN address (per the 07-14 design doc's Flag 1) — this
   audit could not confirm from static code whether Daniel later ruled on this. **Recommendation:**
   offer two named routes in the share sheet ("On your network" = LAN direct-bind as shipped,
   "Anywhere, via Tailscale" = the documented loopback+`tailscale serve` path) rather than picking
   one exclusively — matches the 07-14 doc's own recommendation and requires no new engine
   mechanism, only a UI choice.
2. **Does an AI/agent caller (#1847's "the model is a user") get an account auto-provisioned on
   first use, or only when explicitly added as a person?** Not settled anywhere in code or
   constraints. **Recommendation:** explicit add only — an instrument's account should appear in
   People *by Daniel's act*, same as any other person; auto-provisioning is a decision made
   silently, which conflicts with the AI-integrity "instrument, not interlocutor" north star.
3. **Per-library connection selection UX for #2573** (multi-engine/per-library host): auto-detect
   via Bonjour + fall back to manual entry, or manual-only? **Recommendation:** auto-detect with
   manual override — consistent with how host-side pairing already auto-derives its address
   (`ShareSettingsView.swift`) rather than requiring typed URLs.
4. **Web client priority (#1182/#1094).** Both are open with no active design and no committed
   date; the whole rest of the cluster (accounts, pairing, discovery, remote transport) is
   web-client-agnostic groundwork already in place. **Recommendation:** keep in backlog behind
   #2573 (multi-library) and Mac/iOS polish — a web client is a new client surface, not a gap in
   the sharing model itself, and nothing else in this cluster blocks on it.
5. **Housekeeping for the two empty milestones** (#231 Discovery, #205 Settings): keep as
   standing homes for future discovery/settings-surface issues, or close them now and re-file
   anything future under #96/#263? **Recommendation:** close both now — an empty milestone with
   no clear intake point tends to accumulate mis-filed issues (as #133 already shows with five
   clearly-unrelated open issues); re-open if a genuinely discovery- or settings-specific
   workstream starts.

---

## What this audit could not verify

- Whether Daniel already ruled on Decision #1 (transport choice) in conversation not reflected in
  code or committed docs — worth a direct check before scheduling any share-sheet UI work.
- Runtime behavior — this was a static/code-index audit only (no engine started, no app built),
  consistent with the constraint against editing engine code during the active reorg.
- The exact current state of `FicheroApp_iOS.swift`'s Bonjour-candidate-discovery relative to
  #3371's scope — the critique doc describes it as already fairly complete; #3371 may be near-done
  or may cover a specific remaining gap. Needs a fresh read before scheduling.

## Decisions (Daniel, 2026-07-21)
- **Share-toggle transport = BOTH, as named routes.** The one-action share offers LAN direct-bind AND loopback+Tailscale-serve; user picks per share. Engine still binds 127.0.0.1 + `tailscale serve` only (never funnel); Tailscale = perimeter, not authz.
- **Per-library connection (#2573) = auto-detect (Bonjour) + manual host override.**
- **Agent/MCP accounts (#1847) = Xcode-style consent prompt:** connect → prompt → approve auto-provisions/uses the account; "don't ask again" remembers FOR THE SESSION; relaunch re-prompts.
- Empty milestones #231 (Discovery) + #205 (Settings): recommend closing (capability built elsewhere).
