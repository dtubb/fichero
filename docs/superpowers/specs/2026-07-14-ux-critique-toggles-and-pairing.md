# UX Critique: Toggles, Pairing, and the Blank-Space Disease

**Date:** 2026-07-14
**Author:** UX-critic agent (research + critique only; no source modified)
**Trigger:** Daniel: *"why aren't they always on or off. why have so many toggles and options for the user? we need a UX critic in there to make it dead simple. not get rid of security but not show things users don't need to see."*
**Anchor bug:** #3769 — the pairing QR silently vanished from Settings (five-condition AND-gate, no fallback message).

**Principle applied throughout:** a feature should just WORK or be plainly off. A toggle is usually a decision we failed to make. Every switch is a path to a state the user can't diagnose. Security stays — the *machinery* goes. Do the secure thing automatically; don't ask.

---

## 1. The triggering bug (#3769) — anatomy of a silent failure

I read issue #3769 with `gh issue view 3769` and verified every cited gate against `main` (e44e64de7). The five gates are real and at the cited lines:

| Gate | Verified location (main) |
|---|---|
| `canHostRemoteAccess` (= `EngineConfig.engineIsLocal`) | `BackendSettingsRemoteAccessSection.swift:85,101-103,106` |
| `hostingEnabled && appState.isBackendRunning` | `:87` |
| `pairingCode` + `advertisedPairingService` | `:135,148` |
| valid SPKI pin | `:136,149` |
| valid `publicBaseURL` | `:111,119-121` |

**Important correction to the issue's framing:** on today's `main`, the card is *not* fully blank. `PairingCardView` (`BackendSettingsRemoteAccessSection.swift:341-415`) has a `statusMessage` fallback branch (`:403-410`), and `pairingStatusMessage` (`:172-202`) covers each precondition with a sentence ("Fichero is not connected on this Mac right now", "Set up secure sharing, then Fichero can show a QR code here", …). The last commit to touch this file is `85e05f7a9` (2026-07-10, "fix: restore local pairing qr pin lookup (#3391)") — so the message scaffolding predates the issue. But the disease the issue describes is still fully present, in four forms:

1. **The messages are diagnoses without cures.** "Set up secure sharing, then Fichero can show a QR code here" (`:180,188,190`) names no place and offers no button. The actual fix lives inside a disclosure literally titled **"Advanced / Debug"** (`:476`) where the user must flip "Enable pairing and remote clients" (`:477`), type a "Reachable URL" (`:481`), type a **"Certificate SPKI pin"** (`:486`) and press "Apply and Restart Engine" (`:506`). The primary path to pairing a phone runs through a debug drawer with a raw cryptographic pin field. That is the failed decision the toggle-critique is about.
2. **One headline lies for all causes.** Every fallback shows the headline "Secure sharing needs HTTPS." (`:405`) — even when the real cause is "the engine isn't running." The user reads an HTTPS error while the actual problem is a dead backend.
3. **Several failure modes still produce literal blank or wrong space.** If preconditions pass but QR *encoding* fails, `qrCodeImage` returns nil (`:160,166-168`) and the card shows a pairing code section with no image and the text "Scan this with Fichero on another device" — with nothing to scan (`:357-365`). And `pairingError` from a failed code mint replaces the status message silently (`:57`).
4. **The whole pane is itself flag-gated.** The Backend pane renders only if `featureManager.isSettingsBackendTabEnabled` (`SettingsView.swift:53,310`), whose raw default is `false` (`FeatureManager.swift:84-85`) and which is only true because `resetToV001()` sets it (`FeatureManager.swift:334`) after a release-profile bump (`releaseProfileVersion = 32`, `:33`). If the profile machinery ever fails to run, the *entire Engine→Backend pane* disappears — silently. A settings pane whose existence depends on a versioned migration counter is exactly the class of bug #3769 describes, one level up.

### 1.1 The bigger finding: there are TWO pairing surfaces, and they disagree

The Mac has **two parallel host-side pairing UIs**, both alive, both reachable from Settings, with different gating, different URLs, different messages, and different QR sizes:

| | A: Engine → Backend ("Share This Mac") | B: Library Access → Devices (ShareSettingsView) |
|---|---|---|
| File | `BackendSettingsRemoteAccessSection.swift` | `ShareSettingsView.swift` |
| Reachability | Settings → Engine & Access → Engine → *Backend segment* → scroll (`SettingsView.swift:115-116,321-322`; `BackendSettingsView.swift:45-51`) | Settings → Engine & Access → Library Access → *Devices segment* (`SettingsView.swift:117-118,362-364`) |
| URL setup | user types "Sharing address" / "Reachable URL" by hand (`:47,481`) | **auto-derives** `https://<hostname>.local:<port>` (`ShareSettingsView.swift:37-44,95-97,339-341`) |
| SPKI pin | raw editable text field in "Advanced / Debug" (`:486-489`) | loaded automatically, never shown as a field (`ShareSettingsView.swift:423-425`) |
| Bonjour | separate toggle (`:478`) | auto-enabled with sharing (`ShareSettingsView.swift:338`) |
| Enable | "Enable pairing and remote clients" + "Apply and Restart Engine" (`:477,506`) | single "On/Off" toggle that restarts the engine itself (`ShareSettingsView.swift:51-61,332-346`) |
| Devices list | its own copy (`:416-461`) | its own copy (`ShareSettingsView.swift:68-86`) |
| Client-side pairing ("connect this Mac to another") | `MacRemoteClientPairingSection` in the same pane (`BackendSettingsView.swift:38`) | absent |

They share the same `@AppStorage` keys (`RemoteAccessConfig.hostingEnabledKey` etc. — `BackendSettingsRemoteAccessSection.swift:19-21` vs `ShareSettingsView.swift:17-19`), so flipping the toggle in B changes what A shows and vice-versa. Surface B is the good one — it already embodies the "do the secure thing automatically" principle (auto URL, auto Bonjour, hidden pin, one toggle). Surface A is the older machinery that B was presumably built to replace, never removed. **Daniel looking for "the QR code in Settings" can land on either, and each has different reasons to be QR-less.** This duplication — not any single gate — is the root of "the QR vanished": there are two places it can vanish from, for two different sets of reasons.

Recommendation (design, not patch): **one pairing surface** (keep B's behavior), demote A's section to nothing — its Advanced fields move behind a single "Advanced" escape hatch *inside* B if kept at all, and `MacRemoteClientPairingSection` (join-another-Mac) stays where it is conceptually distinct (see §3). This is iterate-not-replace: B already exists and is shipped; the work is deleting A's duplicate section, not writing anything new.

## 2. Toggle audit — every user-facing switch in Settings

Scope: all of `fichero/fichero/Views/Settings/` (18 files, read in full) plus `Models/FeatureManager.swift`. Verdicts: **KEEP** (genuine preference — named user, named moment), **AUTOMATE** (we decide; direction given), **HIDE** (dev/debug only), **DELETE** (dead or duplicate). Default is AUTOMATE.

### 2.1 General (`GeneralSettingsView.swift`)

| Control | What it does | What a real user does with it | Verdict |
|---|---|---|---|
| Thumbnail Size slider (`:29`) | grid thumbnail size | drags it once to taste | **KEEP** — but it duplicates the in-view zoom control (`library.iconViewScale` exists as a separate key in the Library view); one zoom, not two |
| Font / Font Size / Line Spacing / Margins (`:34-59`, keys `editor.*`) | editor typography | a writer who wants serif at 16pt | **KEEP** the *font*; but see the duplication note below |
| "When adding files" import mode picker (`:62-66`) | link / copy / move on import | an archivist with a canonical folder chooses Link; others Copy | **KEEP** — a genuine, consequential data-ownership preference, well-explained in the caption |
| **Toggle "Auto-extract text from documents"** (`:75`) | gates ingestion text extraction | nothing good. Turning it OFF silently kills search, Reader transcripts, and every AI feature downstream — then weeks later "search is broken" | **AUTOMATE: always ON, delete the toggle.** Extraction is what the product *is* (READ layer). If a doc shouldn't be processed there should be a per-item action, not a global kill-switch |
| **Toggle "Auto-create search embeddings"** (`:76`) | gates embedding creation | same failure: off → semantic search quietly degraded, no message says why | **AUTOMATE: always ON, delete.** If the motive was CPU/battery, that's a scheduling policy (throttle in background), not a user decision |
| Reset to Defaults (`:80-89`) | resets typography+the two toggles | fine | KEEP (and it shrinks as the toggles go) |

**Duplication finding — three font-size systems:** General → Typography writes `editor.fontSize` (`GeneralSettingsView.swift:14`), while Settings → Inspector writes `ViewSettings.FontScale.editorKey` (`SettingsView.swift:228-229`, "Editor Text… separate from the Reader") and Settings → Reader writes `FontScale.readerKey` (`SettingsView.swift:188-189`). A user who wants "bigger text" now has three places, two of which claim the word *editor*. Decide which surface owns text sizing (the per-view panes, per #3681/#3682) and remove or rename the General Typography block accordingly.

### 2.2 Engine (`EngineSettingsView.swift`)

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| **Multi-user mode toggle** (`:41-44`, key `fichero.multiuser.enabled`) | desired flag; engine applies on next restart (`:88-90` doc comment; actual state read from `GET /api/auth/identity`) | Daniel, the day he adds a second person | **KEEP for now, but it's a decision half-made.** The drift text ("Restart the engine to turn multi-user on", `:92-105`) is honest but machinery-facing. Better: flipping it *does the restart* (Engine already knows how — `restartEngine()` `:107-120`), so the toggle means what it says. Long-term candidate for full automation: multi-user turns itself on when a second account or paired device exists (flag: security-relevant — see §6 Q3) |
| Restart button (`:34-38`) | stop+start engine | a recovery ritual | **HIDE** into a diagnostics context (or keep as the one repair affordance — it's the app's "turn it off and on"). At minimum it shouldn't sit beside Library as a peer of normal preferences |

### 2.3 Backend (`BackendSettingsView.swift` + the two pairing sections)

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| "Sharing address" TextField (`BackendSettingsRemoteAccessSection.swift:47`) | the public base URL, typed by hand | nobody can type a correct Tailscale HTTPS URL unaided | **DELETE from primary UI** — ShareSettingsView already auto-derives `https://<hostname>.local:8765` (`ShareSettingsView.swift:37-44`); a manual override belongs in one Advanced disclosure only |
| **Toggle "Enable pairing and remote clients"** (`:477`) | same `@AppStorage` key as the Devices tab's sharing toggle | flips a switch that also flips a switch in another pane | **DELETE** — duplicate of ShareSettingsView's toggle (§1.1) |
| **Toggle "Advertise this Mac on the local network"** (Bonjour, `:478`) | sets `FICHERO_ENABLE_BONJOUR` at engine launch (`EngineConfig.swift:588-590`) | no user knows what Bonjour is; discovery is *how the phone finds the Mac* — off means the iOS "Connect to your Mac" list stays empty forever with no explanation | **AUTOMATE: on whenever sharing is on** (ShareSettingsView already does exactly this — `:338`). Delete the toggle |
| "Reachable URL" TextField (`:481`) | manual public URL again | — | **HIDE** — one Advanced field, in one place |
| **"Certificate SPKI pin" TextField** (`:486`) | the TLS pin, *editable* | nothing — the engine generates and persists the pin automatically on every start (`EmbeddedBackendService.swift:401-412`); the field is prefilled from storage (`:322-324`) | **DELETE from UI.** This is pure machinery exposure. Editing it can only break pinning; it is never something a user supplies. (Security note: removing the *field* removes nothing from the *pinning* — the pin still rides in the QR payload, `:139-144`) |
| "Apply and Restart Engine" button (`:506`) | restart to apply hosting | an incantation | **DELETE** — the Devices tab's single toggle already restarts the engine itself (`ShareSettingsView.swift:348-379`) |
| "Reset Invite" button (`:502`) | mints a new pairing code | rotating a leaked invite | **KEEP** (one copy, in the surviving pane) — it's the only rotation affordance |
| Advanced "Engine URL" TextField (`BackendSettingsView.swift:141-166`) | points the app at an external engine | Daniel in Debug (external engine on :8765); no end user | **HIDE** — genuinely dev-only (per the Debug-external/Release-embedded split, #3042). Keep behind Advanced, or gate to dev tier |
| Statistics section (`BackendSettingsView.swift:53-89`) | doc counts, storage | glances | KEEP, but it duplicates Engine's storage stat (`EngineSettingsView.swift:50-59`) — one Engine pane should own status+stats |
| `MacRemoteClientPairingSection` "Connect This Mac to Another Fichero" (`MacRemoteClientPairingSection.swift:27-63`) | Mac-as-client pairing | a second Mac joining the household library | **KEEP the capability, fix the copy and placement.** Its first line is *"Scan the QR code shown on the host Mac."* (`:28`) — **the Mac has no QR scanner**; the only actual path is the "Manual link" disclosure (`:32`). The instruction is impossible as written. Note the Option-at-launch chooser already reuses this section (`:149-159`) — that's arguably where it belongs exclusively, not in everyday Settings |

### 2.4 Library Access → Devices (`ShareSettingsView.swift`) — the good one

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| **Sharing On/Off toggle** (`:51-61`) | THE switch: restarts engine with TLS + Bonjour + auto URL, shows QR | "I want my phone to see my library" → On | **KEEP.** This is what a decision-made feature looks like: plainly on or plainly off, secure automatically (auto-HTTPS, auto-pin, auto-Bonjour, `:95-97,338-341`) |
| "Show Details" disclosure (`:134-148`) | address / route / code | support conversations | KEEP — right pattern: details present, folded |
| Remove (device revoke) (`:79-83`) | revokes a device token | "my old phone" | KEEP — a real security affordance |

Caveats on the good pane: the status line "Applying certificate. Toggle sharing off and on if this persists." (`:181`) ships a *manual retry ritual* as UI copy — the app should retry itself; and "Preparing…" (`:183`) is a dead-end state with no action if minting fails silently. Also #3342 (open): flipping sharing ON has rebound the engine off loopback and broken *everything* — the single toggle must never be able to strand the local app (fix is engine-side loopback-always; the toggle is only safe once that invariant holds).

### 2.5 Library Access → People (`UsersSettingsView.swift`, `InviteAccountSection.swift`)

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| Toggle "Owner (can manage users and all libraries)" (`UsersSettingsView.swift:186`) | new account role | Daniel creating an account for a collaborator | **KEEP but reshape**: this is a role, not a boolean — a Role picker (Owner/Editor/Viewer) matches the ACL model that already exists (`authzRoles`, `:579`) instead of "owner: yes/no" then a separate role assignment below |
| Role pickers / Remove / Disable (`:312-331,384-391`) | ACL management | owners | KEEP — permissions are real decisions |
| Invite a Person (`InviteAccountSection.swift`) | mints `fichero://invite` link + QR | onboarding a person | KEEP — good flow. But it renders only when `isOwnerAccess && multiuserEnabled` (`UsersSettingsView.swift:169`) — in single-user mode the section is silently absent. Show it disabled with "Turn on multi-user mode to invite people" + a button (§4) |

### 2.6 Library Access → Capture (`CaptureSettingsView.swift`)

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| Per-user "Capture" toggle (`:152`) | whether that user's mobile captures are accepted, + destination library/workflow | Daniel granting his phone-capture pipeline | **KEEP** — this is a *permission* (security policy), the legitimate kind of switch. Minor: "Capture" + empty Library ("None") is a half-configured state that uploads nowhere; turning it on should demand a destination in one step |

Note: policies persist in **client-side UserDefaults** (`:118-134`), not the engine — a policy that claims to gate other devices but lives in one Mac's defaults is a decision the *engine* should own. Not a UX matter per se, but the toggle's promise exceeds its enforcement surface; worth an issue.

### 2.7 AI (`AISettingsView.swift`, `+Tabs.swift`)

| Control | What it does | Real user | Verdict |
|---|---|---|---|
| Primary Language picker (`+Tabs.swift:14-22`) | force extraction language | a researcher with Spanish archives | KEEP — concrete and explained |
| Text / Vision / Audio (/Video) provider+model pickers (`:25-59`) | per-modality defaults | someone choosing local vs cloud | KEEP the *category*, but see collapse note |
| **Eight tier pickers**: `$small/$medium/$large` + `$vision_small/$vision_medium/$vision_large`, each provider+model (`:63-125`) | workflow alias resolution | almost nobody; sixteen dropdowns of model IDs | **AUTOMATE with escape hatch.** The app knows the installed/available models; it can resolve tiers itself (local-first per the AI-infra direction). Replace with one choice — "Prefer: On-device / Mixed / Best quality" — and move per-tier pickers behind Advanced. Today this pane is a config file rendered as UI |
| Advanced: Temperature slider, Max Tokens field, Prompt Prefix (`:221-241`) | generation params | prompt tinkerers | **HIDE** (already on an Advanced tab — fine) — but "Prompt Prefix (prepended to all prompts)" is a global invisible modifier of every AI result; if it stays, results that used it should say so (AI-as-instrument: provenance) |
| Local LLM / Downloads tabs | MLX runtime provisioning, model downloads | fine | KEEP — these are actions and status, not toggles, and `LocalInferenceSettingsView` handles the disconnected state with an explicit label (`LocalInferenceSettingsView.swift:16-20`) — the right pattern |

### 2.8 FeatureManager — ~45 flags, no UI, and that's both right and wrong

`FeatureManager.swift` holds ~45 `@AppStorage` flags (`:48-150`). **None have a Settings UI** — they're set by env var, `defaults write`, or the versioned release profile (`releaseProfileVersion = 32`, `:33`; `resetToV001()` `:314-363`). Hidden machinery: correct. But three structural problems:

1. **Settings tabs are themselves feature-flagged** — `settings_general_tab`, `settings_backend_tab`, `settings_engine_tab`, `settings_share_tab`, `settings_users_tab`, `settings_capture_tab`, `settings_models_tab` (`:82-95`) gate sidebar rows and segments (`SettingsView.swift:43-71,305-355`). A Settings pane that can silently not exist is the #3769 disease at the IA level. **Verdict: DELETE all seven `settings_*_tab` flags.** Settings panes are part of the product's basic anatomy; platform (`#if canImport(AppKit)`) is the only legitimate gate. (The raw default of `settings_backend_tab` is even `false` — the Backend pane exists today only by grace of the release-profile reset, §1 point 4.)
2. **The release-profile ratchet overwrites user state.** Any bump of `releaseProfileVersion` calls `resetToV001()` (`:373-386`), which force-resets *every* flag — including ones a user (or support session) deliberately set. It's a migration tool being used as a defaults distributor. Fine for pre-1.0; flag it as tech-debt for the public release.
3. **Redundant granularity.** Ten `workflow_tools_*` booleans (`:96-115`) plus a CSV allowlist `workflow_enabled_tools` (`:116-117`) encode the same intent twice. The CSV allowlist is the one actually curated (v0.0.1 list `:34-43`); the ten booleans are mostly `false` in the release profile. Collapse to the allowlist.

The remaining product flags (workflows, chat, agents, spatial_mode, canvas_realitykit_*, …) are legitimate *staging* flags for unshipped surfaces — keep, no UI. The 4-tier gating milestone (#3344-#3349) is presumably formalizing exactly this; this audit supports that direction: **tier-gated visibility, not user toggles.**

### 2.9 Toggles outside Settings (inventory only)

For completeness (grep of `Toggle(` across `Views/`): the densest non-Settings toggle surfaces are `AIModelSelectionView` (10), `TriggerEditorFormPanel` (6), `ViewMenuCommands` (5), `ReaderToolbar` (4), `SearchFiltersPanel` (4), `DocumentInspectorArtifactsTab+KGSection` (4), `DisplayAttributesStrip` (4). View-menu and filter toggles are mostly legitimate view state (Finder-like). The KG row-display toggles (`inspector.kg.row.show*`, 4 keys) and the loupe controls (`imagePreview.loupe*` ×4 + `pdfPreview.loupe*` ×4 — two parallel key families for the same loupe concept) smell like the same duplication pattern as §2.1 and deserve their own pass when those surfaces get their Fabel review. Not expanded here — Settings was the brief.

## 3. Pairing flow redesign

### 3.1 What the user must do today (host side, happy path)

1. Mac: Settings → Engine & Access → Library Access → Devices → flip "Off/On" toggle. (Or the older path: Engine → Backend segment → Advanced/Debug → enable + URL + pin + Apply.)
2. Engine restarts with TLS; URL auto-derives; QR appears.
3. iPhone (fresh install): first-run screen auto-opens the QR scanner (`FicheroApp_iOS.swift:294-298`); scan; done.

The iOS side is already close to dead simple — auto-scanner, Bonjour list of Macs, manual-link fallback, invite deep links (`:117-134`). **The Mac side is where the pain lives**, and §1.1's duplicate surface is most of it.

### 3.2 What the QR actually carries (the security payload)

`PairingQRCodePayload` = engine URL + one-time pair code + **SPKI pin** + library path (`BackendSettingsRemoteAccessSection.swift:139-144`, validated on receipt at `RemoteClientPairing.swift:88-104`: HTTPS-only, non-localhost, pin syntax, library path required). The camera is an out-of-band channel — the pin arrives immune to network MITM. **Any replacement for the QR must deliver the pin (or equivalent channel authentication) with the same property.** (Known hole, already filed: the client persists the QR's `library_path` without server confirmation — #3273, P3. Keep that fix on the list; it's orthogonal to this redesign.)

### 3.3 The five gates, re-decided

| Gate | Today | Should be |
|---|---|---|
| `canHostRemoteAccess` (engine is local) | card silently absent / generic message | a *fact*, stated: "This Mac is connected to <host>'s library. Sharing happens on the Mac that owns the library." No action needed — there is nothing to fix |
| `isBackendRunning` | message, no action | the app *owns* the embedded engine — if sharing is on and the engine is down, show the real error + a **Start/Retry button** (reuse `connectBackend(restart:)`, the one macOS connect path per #3108) |
| `hostingEnabled` | toggle in two places | **the one switch** (Devices pane). Everything below it is automatic |
| `publicBaseURL` valid | hand-typed in pane A; auto `.local` in pane B | **auto, always** (B's behavior). If Tailscale is detected, offer the `.ts.net` route as a labeled choice ("Same network" / "Anywhere via Tailscale") — a picker with two *named routes*, not a URL text field. Manual URL survives only under Advanced |
| SPKI pin valid | editable text field in "Advanced / Debug" | **invisible, always automatic** — the engine already mints and persists it every launch (`EmbeddedBackendService.swift:401-412`). If the pin lookup fails, that's a bug to surface ("Secure certificate missing — Restart sharing" button), not a field to edit |
| pairing code minted | silent nil on failure, or "toggle off and on" | auto-mint with visible retry: "Couldn't create a pairing code: <error> [Try Again]" |

**Resulting card contract (the #3769 fix):** the pairing card is *always rendered* when the pane is open and has exactly four states — OFF (one sentence + the switch), STARTING (progress), READY (QR + Copy Invite/ShareLink + expiry), PROBLEM (named cause + one fix button). No state renders as empty. This is a state machine worth an enum in code and a launch-stress test, not five independent `guard`s scattered across computed properties.

### 3.4 Daniel's question: should the iPhone pop up a QR code?

**No — a QR on the phone is the wrong direction, and here's the concrete reason:** the QR's job is to move the *Mac's* secrets (URL + code + pin) to the phone through the camera. The phone has nothing secret to offer yet; a phone-side QR would have to be scanned *by the Mac*, and Macs have no usable scanner posture (`MacRemoteClientPairingSection.swift:28` already contains the fossil of this confusion — it tells a Mac user to "scan" with no scanner).

But the *instinct* behind the question is right: the phone can already see the Mac (Bonjour, `_fichero._tcp.` + TXT `public_url`, `FicheroApp_iOS.swift:911-999`), yet today tapping the discovered Mac merely opens the phone's scanner (`:339-349`) and the user still has to walk to the Mac, open Settings, find the pane, and get a QR on screen. The fix is to make **the Mac react**, not the phone display:

**Phase 1 — "Knock to pair" (recommended; no new cryptography):**
1. Phone taps "Daniel's MacBook" in the discovered list.
2. Phone sends an unauthenticated, rate-limited `POST /api/pairing/knock {deviceName}` to the advertised URL (TOFU TLS — the knock carries no secrets and grants nothing).
3. The Mac app (which already heartbeats its engine) surfaces a dialog *wherever the user is*: **"'Daniel's iPhone' wants to connect to this library. [Show Pairing Code] [Ignore]"** — clicking Show presents the existing QR full-screen/sheet, no Settings navigation at all.
4. Phone's scanner is already open (it opened on tap); scan; paired.

Security properties are *identical* to today: the pin still travels only via the camera; the knock is a doorbell, not a key. Bonjour's TXT record stays untrusted (it already is — discovery "only finds the Mac", `:582-584`). The engine needs one new endpoint (rate-limited, no data returned) and the Mac app one dialog + a "present QR" sheet that is independent of Settings.

**Phase 2 — scan-free numeric comparison (only if Daniel wants camera-free pairing):** after a knock, both screens display a 6-digit code derived from the engine's certificate SPKI + a session nonce; the user confirms the codes match; the phone then persists the pin it saw over TLS. This is Bluetooth-style numeric comparison — **it is only as strong as the user actually comparing the digits.** It trades a hard guarantee (camera channel) for a human check. My recommendation: don't build it; the QR is one scan and the scanner is already auto-open. If built anyway, it must be *in addition to* the QR, and the comparison code must bind to the certificate (not be a bearer code), or it silently becomes MITM-able. Flagging loudly per the brief: **this is the one place where "simpler" can quietly cost security.**

### 3.5 Mac-as-client and invite links — two verified gaps

- **`fichero://pair` links do not open on macOS.** iOS handles them (`FicheroApp_iOS.swift:124-125` → `PairingIncomingLinkSheet`); the macOS `handleOpenURL` handles invite-account tokens and library URLs only (`FicheroApp.swift:116-139`) — a pairing link falls through to "open as library". Yet the host UI offers ShareLink/Copy Invite precisely so the link can be sent to another device (`BackendSettingsRemoteAccessSection.swift:380-386`). A second Mac must paste the link into a "Manual link" disclosure that *tells it to scan instead* (`MacRemoteClientPairingSection.swift:28-34`). Fix: route `fichero://pair` in `handleOpenURL` to the same pairing confirm sheet iOS uses.
- **The URL-scheme claim should be verified at build time** — I confirmed handler code, not the `CFBundleURLTypes` registration for macOS; worth checking `fichero` scheme is registered for the Mac target when fixing the above.

### 3.6 What "dead simple" looks like end to end

> **Mac:** Settings → Sharing → one switch: *"Share this library with your other devices."* Card shows QR or names the one problem with one button.
> **iPhone:** open app → it lists your Mac → tap it → Mac asks "Show pairing code?" → scan → done.
> **Second Mac:** open the invite link someone sent you → confirm → done.

Everything else — TLS, pins, Bonjour, URLs, engine restarts, tokens, renewal (#3096), failover endpoints (#3098) — already works automatically and should never be seen.

## 4. Blank-space inventory — everywhere the UI silently shows nothing

Verified instances where a failed/false precondition renders *nothing* (or something misleading), ranked by harm. Rule to adopt: **a gated affordance is never removed — it is disabled with the reason and, where possible, the fix.**

| # | Where | What vanishes / misleads | Cite |
|---|---|---|---|
| 1 | Pairing card, QR-encode failure | pairing section renders with "Scan this…" text but **no image** if `qrCodeImage` nils (encode/CIFilter failure) | `BackendSettingsRemoteAccessSection.swift:357-365,147-170` |
| 2 | Pairing card, all-fallback headline | every failure shows "Secure sharing needs HTTPS." even when the cause is engine-down or sharing-off | `:403-410` vs `:172-202` |
| 3 | Settings sidebar rows | **Engine**, **Library Access**, **General**, **MCP**, **Integrations** rows disappear entirely when their feature flags are off — a Settings pane that can silently not exist | `SettingsView.swift:43-48,53-61,65-67` |
| 4 | Invite a Person | absent unless owner **and** multi-user on; single-user Daniel never learns invites exist or what enables them | `UsersSettingsView.swift:169` |
| 5 | ShareSettingsView devices list | "Connected Devices" section only exists when non-empty — no "No devices yet" state (pane A has one, `:434-440`; pane B doesn't) | `ShareSettingsView.swift:68` |
| 6 | ShareSettingsView terminal states | "Preparing…" with no action if minting stalls; "Toggle sharing off and on if this persists" as the retry mechanism | `:181-183` |
| 7 | Mac client pairing copy | "Scan the QR code shown on the host Mac" — impossible instruction; no scanner exists on macOS; actual path hidden in "Manual link" disclosure | `MacRemoteClientPairingSection.swift:28-34` |
| 8 | `fichero://pair` on macOS | opening a pairing invite link does nothing pairing-related (falls into open-as-library) | `FicheroApp.swift:116-139` |
| 9 | Menu commands | New Comparison/Chain/Chat/Workflow/Schedule menu items silently absent per flag — consistent with staged features, but combined with zero UI for flags, a user can't discover *why* | `FicheroApp.swift:425-450` |
| 10 | Pane A pairing error swallows status | `pairingError` replaces the status message slot (`statusMessage: pairingStatusMessage ?? pairingError`) — an error can mask the "what to do next" text | `BackendSettingsRemoteAccessSection.swift:57` |

Counter-examples already in the codebase worth copying (the pattern exists, it's just unevenly applied): `AISettingsView`'s "Backend not connected" label (`AISettingsView.swift:48-54`), `UsersSettingsView`/`BackupsView`'s `ContentUnavailableView`s with reasons (`UsersSettingsView.swift:24-29`, `BackupsView.swift:90-101`), and `SettingsGroupContainer`'s selection-clamping so a hidden segment "never shows blank" (`SettingsView.swift:262-269`).

## 5. What Settings should even contain

Settings is for **preferences** — durable choices about how *you* want the app to behave. Not plumbing (how the app achieves it), not status (what's happening now), not actions (do a thing once). Proposed target IA, building on the existing #3679 sidebar — everything below exists today; this is consolidation, not construction:

**Stays, as-is:**
- **Views** (Library / Preview / Reader / Inspector) — genuine per-surface preferences (#3680). Absorb General's typography block here (§2.1 duplication).
- **AI** — Language + per-modality provider/model + Local LLM/Downloads. Tier pickers collapse behind Advanced (§2.7).
- **General** — thumbnail size, import mode. (Shrinks: ingestion toggles deleted per §2.1.)
- **History**, **Backups** — these are actions/status rather than preferences, but they're library management with no better home; fine.

**Consolidates:**
- **Sharing** (rename of Library Access; one pane): the sharing switch + QR card (the *only* copy), Connected Devices, People (accounts/roles/invites), Capture permissions. This is "who and what can reach my library" — one coherent question.
- **Engine**: status, storage, multi-user switch, Restart. Backend's duplicate stats and *both* pairing sections leave this pane (§1.1, §2.3). What remains is small enough that Engine and Backend stop being two segments.

**Leaves user-visible Settings entirely:**
- SPKI pin field, Reachable URL field, Bonjour toggle, "Apply and Restart Engine" (§2.3) — automatic.
- Engine URL override — dev-tier Advanced only.
- Feature flags — never had UI; keep it that way; tier-gating (#3344-#3349) is the mechanism.

Litmus test for anything new: *"Would a historian using Fichero for her archive change this twice?"* If not twice, it's a decision, not a preference.

## 6. Questions for Daniel (with recommendations)

1. **Kill the duplicate pairing surface?** Engine → Backend contains a full second copy of sharing/pairing ("Share This Mac" + Advanced/Debug + its own device list) alongside Library Access → Devices. **Recommendation: yes — Devices (ShareSettingsView) becomes the only host-side pairing UI; the Backend copy is deleted, with "Reset Invite" and a manual-URL override migrated into a single Advanced disclosure there.** This is the highest-leverage single change in this document.

2. **Knock-to-pair (§3.4 Phase 1)?** Phone taps discovered Mac → Mac pops "Show pairing code?" → QR appears without touching Settings. Same security, one new rate-limited endpoint + one dialog. **Recommendation: yes, after the #3769 card-contract fix and #3342 loopback fix land — it depends on both.**

3. **Should multi-user mode self-enable?** Automating it (on when a 2nd account or paired device exists) removes a toggle but changes the security posture of an existing library without an explicit act. **Recommendation: keep the explicit switch, but make flipping it perform the engine restart itself (§2.2); revisit automation only when pairing implies accounts (per the #2021/#2022 accounts-for-people direction).** This is the one toggle where "ask the user" is arguably the *secure* default.

4. **Delete the ingestion toggles (auto-extract / auto-embeddings)?** Always-on is the product's premise; the toggles only manufacture broken-search states. **Recommendation: delete both; if resource pressure was the motive, throttle in the engine instead.** Cost if I'm wrong: someone with a gigantic link-only archive wants import-without-processing — if that user exists, it's an *import-time choice* (next to Link/Copy/Move), not a global switch.

5. **Collapse the eight AI tier pickers?** Replace `$small/$medium/$large` (+vision) provider/model pairs with one "Prefer: On-device / Mixed / Best quality" choice, tier detail under Advanced. **Recommendation: yes — it also serves the local-first AI-infra direction (#2056).**

6. **Delete the seven `settings_*_tab` feature flags?** They make Settings panes conditionally exist (the Backend pane exists today only via the release-profile reset). **Recommendation: yes — platform `#if` is the only legitimate gate on a Settings pane; fold this into the 4-tier gating milestone (#3344-#3349).**

7. **Numeric-comparison (scan-free) pairing — build or not?** **Recommendation: not** — it's weaker than the QR unless users reliably compare digits, and the scanner already auto-opens. Documented in §3.4 Phase 2 so the trade-off is on record if reachability-without-camera ever forces it.

---

### What I could not determine (honesty section)

- **Which gate is false on Daniel's machine right now** (#3769's open forensic question). Static reading can't tell whether his current state is sharing-off, URL-invalid, or the #3342 loopback rebind cascade (whose symptom list — "no pairing QR" — matches exactly). #3342 is open and `status:in-progress`; I'd check it first.
- Whether the `fichero` URL scheme is registered in the macOS target's Info.plist (`CFBundleURLTypes`) — I verified handler code only (§3.5).
- Runtime behavior of any flow — no builds/launches were run (build lock owned elsewhere; per brief).
- Whether `FICHERO_ENABLE_BONJOUR`'s engine-side advertisement includes the TXT `public_url` the iOS discovery reads — the Swift side consumes it (`FicheroApp_iOS.swift:975-982`); the engine-side emitter is in fichero-engine, which I did not audit.

### Sources

- Issues read via `gh`: #3769, #3342, #3273, #3391 (title), #3679/#3680 (closed), milestone "Engine - Onboarding, Connection & Pairing" listing.
- Files read in full: all 18 `Views/Settings/*.swift`, `Models/FeatureManager.swift`, `Services/RemoteClientPairing.swift`, `FicheroApp_iOS.swift`, `SettingsView.swift`, plus targeted reads of `EmbeddedBackendService.swift:340-480`, `EngineConfig.swift:505-594`, `FicheroApp.swift` (root scene + `handleOpenURL`).
- All citations are against `main` @ `e44e64de7` (2026-07-14).
