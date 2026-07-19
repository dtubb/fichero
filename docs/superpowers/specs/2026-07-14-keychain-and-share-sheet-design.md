# Zero-Touch Pairing (iCloud Keychain) + Person-to-Person Sharing (QR / Messages / Mail)

**Date:** 2026-07-14
**Status:** RESEARCH + DESIGN — no source changes made
**Author:** design agent (Claude), for Daniel
**Brief:** *"shared keychain can add to this no? build on top of what we are doing. for another person, ideally is QR Code, or send a message via messages or email. e.g. the share system that does exist in the UX, but isn't quite working."*

Two distinct problems, deliberately kept separate:

1. **PROBLEM 1 — my own devices** (same Apple ID): zero-touch pairing via iCloud Keychain (`kSecAttrSynchronizable`), building on the existing Keychain persistence — not replacing it.
2. **PROBLEM 2 — another person**: the existing invite/share UX (QR, Messages, Mail) — what exists, what is broken, what is missing.

Every claim below is tagged: **(a)** Apple-documented, **(b)** reported developer experience / platform behavior not in a single citable doc page, **(c)** my inference. All code references were verified against `~/code/fichero` at `main` = `3053dfa54` (2026-07-14). Note: the jcodemunch index was 4 days stale (2026-07-10), so verification was done by reading files on disk at HEAD.

---

## Executive summary

- **The single biggest "isn't quite working" bug is one missing plist entry.** The app mints `fichero://pair?payload=…` and `fichero://invite?token=…` links, offers Copy and ShareLink buttons for them, and has complete `onOpenURL` receive paths on both platforms — but **no `CFBundleURLTypes`/`CFBundleURLSchemes` declaration exists anywhere** (verified: source `fichero/fichero/Info.plist`, `project.pbxproj`, and the built Release `Fichero.app/Contents/Info.plist` — zero hits). The OS therefore never routes a tapped `fichero://` link to Fichero. #2399 ("Pair via a tappable link") is CLOSED but the feature is dead on arrival. **Registering the scheme is a two-line plist fix and unblocks most of Problem 2.**
- **For Problem 1, syncing the device token itself would kill per-device revocation. Do not do it.** The viable design — and the one recommended here — is a **synced bootstrap ("enrollment secret")**: a long-lived, revocable, owner-scoped secret synced via iCloud Keychain that each new device exchanges for **its own** per-device token through the existing `/api/pair`-style exchange. Per-device revocation survives intact.
- **#3772 (pairing doesn't survive relaunch) is probably NOT the missing `kSecAttrAccessible` alone** — the platform default (`WhenUnlocked`) does survive a normal relaunch (a). Set the attribute explicitly anyway (it is required groundwork for Problem 1), and run the four-value diagnostic from the issue before assuming the cause.

---

## Part 0 — Verified current state (code, `file:line`)

### 0.1 What is persisted on a successful pair

`RemoteClientPairing.persistPairedHost` (`fichero/fichero/Services/RemoteClientPairing.swift:166-187`) persists five things:

| What | Where it goes | Code |
|---|---|---|
| Device token | **Keychain** (generic password) | `:172` → `EngineConfig.persistAuthToken` (`Services/EngineConfig.swift:932-934`) → `AuthTokenMiddleware.persistRemoteToken` |
| SPKI pin | **UserDefaults** (not Keychain) | `:173` → `RemoteCertificatePinning.persistSPKIPin` (`fichero-api-client/Sources/FicheroAPIClient/RemoteCertificatePinning.swift:85-89`) |
| Token expiry | UserDefaults (via `DeviceTokenRenewal.storeExpiry`, #3096) | `:175` |
| Host URL | UserDefaults (`EngineConfig.userDefaultsKey`) | `:176` |
| Library path | UserDefaults (`RemoteAccessConfig.pairedLibraryPathKey`) | `:182-186` |

Plus the failover endpoint store is reset to the new host (`:180-181`, #3098).

### 0.2 The Keychain write path and its missing attributes (#3772)

`AuthTokenMiddleware.persistRemoteToken` (`fichero/fichero-api-client/Sources/FicheroAPIClient/AuthTokenMiddleware.swift:251-275`) writes via `SecItemAdd`/`SecItemUpdate` using the query built at `:311-317`:

```swift
[
    kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: remoteTokenKeychainService,   // "app.fichero.fichero.remote-device-token" (:27)
    kSecAttrAccount as String: remoteTokenKeychainAccount(hostString:)  // "remote-device-token|<normalized host>" (:185-187)
]
```

**Verified by repo-wide grep (zero hits in any non-worktree Swift file):**
- No `kSecAttrAccessible` anywhere → iOS applies the default, `kSecAttrAccessibleWhenUnlocked` (a — see §1.4).
- No `kSecAttrSynchronizable` anywhere → nothing syncs today.
- No `kSecUseDataProtectionKeychain` anywhere → on macOS these items land in the **legacy file-based keychain**, not the iOS-style data-protection keychain (a — see §1.5). On iOS the key is irrelevant (always behaves as `true`) (a).

The multi-user **session token** path (`persistSessionToken`, `:328-334` query, `:338-362` write) has the identical shape and the identical gaps. Any fix must cover both (fix-then-sweep).

**On #3772 specifically** (pairing gone after iPhone/iPad relaunch): Apple documents the default `WhenUnlocked` as *"Items with this setting are only accessible when the device is unlocked"* — accessible-when-unlocked items **do survive relaunch**; they are only unreadable while the device is locked (a, citation §A.2). So the missing attribute alone explains a failure **only if** the app runs and reads the token before first unlock / while locked (background launch, quick relaunch after reboot) (c). The issue's diagnostic remains the right move: after relaunch, check which of the four persisted values is gone —
1. token unreadable but host+pin present → Keychain accessibility/data-protection problem;
2. token present but host rewritten → `EngineConfig` candidate-ordering (`Services/EngineConfig.swift:93-98` iOS branch, `:104-140` ordering) or a failed host validation dropping `savedRemote` (`:126-134`) (c);
3. everything present but still unpaired → connection failure, see #3342 (open loopback-rebind cascade).

One more candidate the issue doesn't list (c): **Keychain items survive app reinstall on iOS; UserDefaults do not** (b). A reinstall (or a restore that carries keychain but not defaults, e.g. unencrypted-backup asymmetries) yields an orphaned token with no host — which presents exactly as "unpaired". Worth checking whether Daniel's repro involves reinstall/restore rather than plain relaunch.

**Regardless of which cause wins: set `kSecAttrAccessible` explicitly** (issue #3772's own recommendation, and required groundwork for Part 1). Note the migration subtlety: changing accessibility on an *existing* item requires `SecItemUpdate` with the new `kSecAttrAccessible` in the attributes dict (or delete+re-add); merely adding it to future `SecItemAdd` calls leaves old items untouched (b).

### 0.3 Bonjour discovery on iOS (already works)

- The Mac engine is advertised as `_fichero._tcp`; the iOS app declares it (`fichero/fichero/Info.plist:27-29` `NSBonjourServices`) and has the local-network usage string (`project.pbxproj:4643`).
- Companion-first onboarding (#3102, CLOSED): `RemoteConnectionSetupView` (`fichero/fichero/FicheroApp_iOS.swift:265-299`) leads with Macs discovered via `BonjourDiscoveryService` (`:276`). The in-code comment states the current trust model precisely: *"Discovery only finds the Mac — the QR still carries the pair code + SPKI pin, so tapping a host routes into the scanner"* (`:270-274`).

So the phone can already *find* the Mac; what it cannot do is *authenticate* to it without the QR. That is exactly the gap Problem 1 fills.

### 0.4 The QR / pairing-link payload and the engine exchange

- Payload struct `PairingQRCodePayload` (`Services/EngineConfig.swift:734-750`): `{v, api_url, pair_code, expires_at, spki, library_path}` — the SPKI pin travels **inside** the payload.
- Invite-link form (#2399): `fichero://pair?payload=<base64 JSON>` — built by `RemoteClientPairing.inviteLinkString(from:)` (`Services/RemoteClientPairing.swift:77-86`), parsed by `pairingFields(fromInviteOrPayload:)` (`:66-75`), which accepts either the link or the raw QR JSON.
- Engine (`fichero-engine/src/fichero/api/routes/pairing.py`):
  - `PAIRING_CODE_TTL = timedelta(minutes=10)` (`:28`); codes are held **in-memory** (`_PAIRING_CODES`), minted by an authenticated owner over secure transport (`create_pairing_code`, `:391-421`).
  - `pair_device` (`:424-470`): strictly **one-time** (`record.used` + popped, `:459-460`), rate-limited, mints a per-device token via `app_db.create_device` (`fichero-engine/src/fichero/app_db.py:1611-1627`, default **TTL 90 days**), stored **hashed** (`accounts.hash_token`).
  - Renewal endpoint `POST /api/pair/devices/renew` (`:484-499`, #3096), rate-limited; device list/revoke endpoints exist (`/devices`).
- Mac UI: the pairing card in `PairingCardView.swift` now names its blocker honestly and offers the cure (`pairingBlocker` `:183-206`, `resolve(_:)` `:211-234` — the #3769/#3776 fix), shows the QR (`qrCodeImage` `:149-172`), the **selectable pairing link** (#3774, `:492-511`), **Copy Pairing Link**, and a **`ShareLink`** (`:513-522`) with the honest warning *"This link lets a device connect to your library — share only with people you trust"* (`:526`).

### 0.5 The invite system for people (accounts) — endpoints + UI

**Engine** (`fichero-engine/src/fichero/api/routes/auth_accounts.py`):
- `INVITE_TTL = timedelta(minutes=15)`; `SESSION_TTL = timedelta(days=30)` (`:28-31`).
- `POST /api/auth/invites` (`create_invite`, `:475-508`): owner/bootstrap-gated, rate-limited by IP, rejects duplicate usernames/pending invites, stores the token **hashed**, returns `invite_token` + `redemption_url`.
- `_invite_redemption_url` (`:374-375`): **`fichero://invite?token=<url-encoded>`** — note it carries **no host and no SPKI pin**.
- `POST /api/auth/invites/redeem` (`:511-556`): rate-limited; checks revoked / already-consumed / expired (single-use); invitee sets their own password; mints a session token; `consume_invite`.
- `POST /api/auth/invites/{id}/revoke` (`:559-572`) and `GET /api/auth/invites` (list pending) — full revocation surface exists.

**Swift UI:**
- Owner side: `InviteAccountSection` (`Views/Settings/LibraryAccess/InviteAccountSection.swift`, #3157) — mint form, pending-invite list with Revoke, and `InviteLinkSheet` (`:133-206`) showing QR + selectable link + **Copy Link**. **No `ShareLink`** — there is no "send via Messages/Mail" affordance here, only copy (`:174-186`).
- Invitee side: `SessionStore.inviteToken(from:)` parses the deep link (`Models/SessionStore.swift:181-189`); `beginInviteRedemption`/`redeemInvite` (`:194-213`) drive the set-password gate in `AuthGateView` (`Views/Shell/Auth/AuthGateView.swift:21,252`). **`redeemInvite` calls the *currently configured* client** (`SessionStore.swift:213`) — i.e. redemption presumes the app is already connected to the right engine.
- Deep-link receive paths exist on **both** platforms: macOS `handleOpenURL` (`FicheroApp.swift:314`, `:123-131`) and iOS `onOpenURL` (`FicheroApp_iOS.swift:117-131`), which also routes `fichero://pair` links into a `PairingIncomingLinkSheet` (`:124-133`).

**Library-role sharing** (#3149): `ShareLibrarySheet` (`Views/Sidebar/Sharing/ShareLibrarySheet.swift`) grants a per-library role via the audited `acl.set` action and shows the returned `share_url` with Copy + **`ShareLink` "Send…"** (`:114-131`). But `_build_share_url` (`fichero-engine/src/fichero/api/routes/authz.py:262-273`) returns a **bare engine HTTPS URL** (engine root or `/api/documents/{id}`) — an API endpoint, not an app link: opening it in a browser yields a 401 JSON, and it carries nothing that would connect a recipient's app. There is also `ShareSettingsView` (`Views/Settings/LibraryAccess/ShareSettingsView.swift`, macOS Sharing settings pane) which fronts the same hosting/pairing/authz state.

### 0.6 The missing piece — `fichero://` is not registered with the OS

Verified exhaustively:
- `grep -rn "CFBundleURLTypes\|CFBundleURLSchemes"` across `*.plist`, `*.pbxproj`, `*.xcconfig`, `*.swift` → **zero hits** (the only "fichero" strings in `Info.plist` are the `.fichero` **document type** UTI, `Info.plist:56,61`).
- The built Release app (`fichero/build/xcode/Products/Release/Fichero.app/Contents/Info.plist`) → no URL types.
- The target uses `GENERATE_INFOPLIST_FILE = YES` + `INFOPLIST_FILE = fichero/Info.plist` (`project.pbxproj:4636-4637`), and no `INFOPLIST_KEY_*` injects URL types.

**Consequence (c, but mechanically certain):** no `fichero://` link can ever launch or be delivered to the app by the OS — not from Messages, not from Mail, not from Safari, not from `open` — on either platform. The QR path works because the scanner reads the payload inside the app; "Enter Link Manually" works because it is pasted text (`FicheroApp_iOS.swift:397-399,551-554`). Every *tappable* path is dead. This is the precise shape of Daniel's *"share system that does exist in the UX, but isn't quite working."*

### 0.7 Related open issues

- **#3772** pairing doesn't survive relaunch (OPEN) — §0.2.
- **#3769** QR silently disappears from Settings (OPEN) — the blocker-card fix is present in code (§0.4); issue likely closeable after Daniel confirms on his machine.
- **#3776** toggles → one-action setup (OPEN, blocked on engine-refusal P0).
- **#3342** sharing rebinds engine off loopback (OPEN, in-progress) — can masquerade as any pairing failure.
- **#3290** iOS device-client security pass (OPEN) — Keychain accessibility work belongs to its scope.
- **#2399** tappable pair link (CLOSED — but see §0.6: shipped without scheme registration).

---

## Part 1 — Zero-touch pairing for Daniel's own devices (iCloud Keychain)

### 1.1 How `kSecAttrSynchronizable` actually behaves — all (a), citations §A.1

From the `kSecAttrSynchronizable` documentation, verbatim where it matters:

- **What it does:** the attribute "indicates whether the item in question is synchronized to other devices through iCloud." Set `true` on add; queries must also pass it (or `kSecAttrSynchronizableAny`) to see synced items.
- **What syncs:** "Starting in iOS 14, macOS 11, and watchOS 7, the keychain synchronizes passwords, certificates, and cryptographic keys. Earlier OS versions synchronize only passwords." A `kSecClassGenericPassword` item (what Fichero uses) is fine.
- **Deletion/updates propagate:** "Updating or deleting items using the kSecAttrSynchronizable key affects all copies of the item, not just the one on your local device."
- **Accessibility constraint:** items "may not also specify a kSecAttrAccessible value that is incompatible with syncing (namely, those whose names end with `ThisDeviceOnly`)." → the brief's note is confirmed: **`…ThisDeviceOnly` cannot sync.**
- **No SecAccessControl:** synchronizable items "cannot specify SecAccessControl-based access control" — no biometry-gated synced items.
- **macOS behaves like iOS:** "A keychain item created in macOS with this attribute behaves like an iOS keychain item. For example, you share the item between apps using Access Groups instead of Access Control Lists."
- **No persistent references** to synchronizable items; retrieval only via `kSecReturnAttributes`/`kSecReturnData`.
- **tvOS never syncs** (irrelevant to Fichero today).
- **Size/class constraints:** the doc page imposes no explicit size limit for generic passwords; keychain items are meant for small secrets (b — keep the payload to a few hundred bytes, which the design below does).

**When it syncs (latency):** Apple does not document a sync SLA. Reported experience (b): propagation is usually seconds-to-a-couple-of-minutes when both devices are on-network and unlocked, but it can lag, and there is **no notification API** for "a synced item arrived" — you poll on foreground/appear. Also (a, prerequisite): the user must be signed into iCloud with iCloud Keychain enabled on **both** devices; if not, `SecItemAdd` with `synchronizable=true` still succeeds **locally** — the item simply never leaves the device (b). Advanced Data Protection does not change any of this; iCloud Keychain is end-to-end encrypted in all configurations (a, §A.5).

### 1.2 THE HARD QUESTION — does per-device revocation survive?

**If the device token itself syncs: NO, and this is a real security regression.** Today every device holds its own token; the engine tracks devices individually (`app_db.create_device`, hashed tokens, per-device expiry + revoke endpoints, `pairing.py:474+`). Syncing the token collapses N device identities into one shared credential:

- Revoking "the iPhone" revokes the iPad and every future device — or worse, revoking *a device row* server-side while the token it shared with others lives on creates ghost-auth confusion.
- The audit trail (device_label per device, #1848's one-audited-action-layer world) degrades to one anonymous blob.
- The 90-day expiry + renewal machinery (#3096) becomes a shared-fate single point.

**⚠️ SECURITY CALL-OUT, LOUDLY: Option A ("just sync the token") is cheap to build and quietly destroys per-device revocation. This document rejects it. Only Daniel can overrule that, and he should not.**

**The bootstrap design (Option B) is viable — design follows.** The synced item is not a credential the API accepts; it is a **pairing grant** each device redeems for its own token. Per-device revocation survives untouched because devices still individually hit the mint path.

### 1.3 Design: synced enrollment secret → per-device token minting

**Iterates on what exists; replaces nothing.** The QR flow, the manual-link flow, `/api/pair`, `persistPairedHost`, device list/revoke/renew — all unchanged. Zero-touch is a *third way to obtain the same four fields* the QR already delivers, feeding the *same* `persistPairedHost`.

**New engine concept: enrollment secret** (name TBD; "family key" reads well in UI). Properties, mirroring the existing invite/device discipline:

- Minted by the owner (authenticated, secure transport — same gate as `create_pairing_code`, `pairing.py:395-401`).
- Stored **hashed** in the app DB (like invites and device tokens — `accounts.hash_token`), with `created_at`, `revoked` flag, and the minting user id. **Persistent** (unlike the in-memory `_PAIRING_CODES` dict, which cannot serve this role — it dies on engine restart, `pairing.py` `_PAIRING_CODES`).
- **Multi-use but single-purpose:** it can only be exchanged for a device token bound to the minting user (same user-binding the pair code enforces, `pairing.py:445-452`). It grants nothing else; it is not an API credential.
- **Long-lived, revocable, rotatable:** "Reset automatic pairing" mints a new one and revokes the old; every enrollment is rate-limited and audited, and the Mac surfaces "«Daniel's iPhone» connected automatically" (never a silent join).
- New endpoint, e.g. `POST /api/pair/enroll` `{enroll_secret, device_name}` → verifies hash + not-revoked → `app_db.create_device` → returns the **same `PairResponse`** as `/api/pair` (per-device token, 90-day TTL, renewal applies). DB change = one table ⇒ idempotent migration per the migrations policy.

**What syncs (the Keychain item):** one `kSecClassGenericPassword` item, value = JSON payload deliberately shaped like `PairingQRCodePayload` (`EngineConfig.swift:734-750`) minus the one-time code:

```json
{ "v": 1, "api_url": "https://mac.tailXXXX.ts.net", "spki": "sha256/…",
  "enroll_secret": "…", "library_path": "/…", "host_name": "Daniel's Mac Studio" }
```

- `kSecAttrSynchronizable = true`, `kSecAttrAccessible = kSecAttrAccessibleAfterFirstUnlock` (§1.4), `kSecUseDataProtectionKeychain = true` (§1.5).
- Service e.g. `app.fichero.fichero.zero-touch`, account = normalized engine identity (reusing `normalizedRemoteHostString`, `AuthTokenMiddleware.swift:189-209`) so multiple Macs each get their own item.
- **The SPKI pin rides inside the synced payload** — this elegantly solves pin distribution for own-devices: the pin arrives through an Apple end-to-end-encrypted channel (a, §A.5), strictly better than the current UserDefaults-after-QR path, and no TOFU is involved.

**Mac side (writes):** when hosting is enabled and the pairing card is healthy (exactly the existing `pairingBlocker == nil` state, `PairingCardView.swift:183-206`), the Mac mints/refreshes the enrollment secret and writes the synced item. Rotation rewrites it; disabling sharing deletes it (deletion propagates to all devices — (a), §1.1).

**iPhone/iPad side (reads):** in `RemoteConnectionSetupView` (`FicheroApp_iOS.swift:265+`), on appear and on Bonjour discovery:
1. Query the synced item (`kSecAttrSynchronizableAny` not needed — query with `synchronizable=true`).
2. If a payload matches a discovered host (or is simply present), show the discovered-Mac row as **"Connect to Daniel's Mac"** — one tap, or even auto-proceed (Daniel's call, Q4).
3. Exchange: `POST /api/pair/enroll` with a device name (`RemoteClientPairing.defaultDeviceName()`, `RemoteClientPairing.swift:52-59`), TLS validated against the synced pin.
4. Feed the result to the **existing** `persistPairedHost` — from here on the device is indistinguishable from a QR-paired one (renewal, revocation, failover, everything).

**Why this is safe (security analysis, honest):**
- Trust boundary = "devices signed into Daniel's Apple ID that have Fichero installed." That is precisely the population Daniel wants zero-touch for. iCloud Keychain is end-to-end encrypted; Apple cannot read it (a, §A.5).
- Blast radius of a leaked enrollment secret < blast radius of a leaked device token: it can only mint auditable, individually-revocable device identities on a host that is rate-limiting and logging enrollments, and it is itself revocable in one action. (c)
- It weakens nothing existing: QR remains, pinning remains, tokens remain per-device, loopback/serve transport invariants (#2124, connection-transport-invariants) are untouched.
- Residual risk to state plainly: **anyone who can unlock any of Daniel's iCloud devices can enroll a new device.** That is inherent to the "own devices" premise; the mitigations are the join notification + the device list + one-tap rotation. (c)

### 1.4 The right `kSecAttrAccessible` for the synced item (and for the existing tokens)

- Default when unset: `kSecAttrAccessibleWhenUnlocked` — "This is the default accessibility when you don't otherwise specify a setting" (a, §A.2).
- **Recommendation: `kSecAttrAccessibleAfterFirstUnlock`** for the synced payload *and* the existing device/session token items. Apple: "After the first unlock, the data remains accessible until the next restart. This is recommended for items that need to be accessed by background applications" (a, §A.3). Fichero's iOS app has background-flavored moments (capture-queue flush on reconnect, `FicheroApp_iOS.swift:138-145`; #3290 plans foreground/background renewal) where a `WhenUnlocked` read can fail and cascade into "I guess we're unpaired."
- `…ThisDeviceOnly` variants are ruled out for the synced item (cannot sync, (a)) and undesirable for the token items (they'd break encrypted-backup migration).
- `SecAccessControl`/biometry cannot be combined with sync (a, §1.1) — do not gate the synced item on Face ID.

### 1.5 Keychain access groups / app groups — what is actually needed

Verified state: **no keychain-access-groups entitlement anywhere** (`Fichero.entitlements` is an empty dict; `FicheroAppStore.entitlements` has sandbox/network/bookmarks only). Mac and iOS builds share **one bundle id** `app.fichero.fichero` (sole `PRODUCT_BUNDLE_IDENTIFIER` besides tests, `project.pbxproj`).

- **App ↔ app across devices (the sync case): no new entitlement needed.** Every app always belongs to its private access group `TEAMID.app.fichero.fichero` (a, §A.4), and since macOS and iOS builds share team + bundle id, the synced item lands in the same group on both. Keychain Sharing capability is only for *different* apps sharing items — not applicable.
- **Engine: needs nothing.** The Python engine never reads the client keychain — it verifies hashes in the app DB (`accounts.hash_token`) and hands the Mac app its bootstrap via the `.api-key` file (`AuthTokenMiddleware.swift:8-15`). No app-group plumbing required. (Verified: the only Mac-app↔engine secret channel is that file.)
- **The one real requirement is macOS `kSecUseDataProtectionKeychain`.** Synchronizable items on macOS *are* iOS-style items (a, §1.1); Apple recommends setting `kSecUseDataProtectionKeychain = true` "for all keychain operations" (a, §A.6). Today Fichero sets it nowhere, so existing macOS items (remote tokens for the Option-launch remote-client path) live in the legacy keychain. Adding the key changes where macOS looks ⇒ **needs a one-time read-legacy→write-new migration** for those items, or they silently "disappear" (b/c). iOS is unaffected. Caveat (b): on macOS the data-protection keychain requires a signed app with an application-identifier — fine for Xcode-run/Dev ID/MAS builds; a bare unsigned binary would get `errSecMissingEntitlement`.

### 1.6 Failure modes — degrade to QR, never break

| Condition | Behavior |
|---|---|
| iCloud Keychain off / not signed in (either device) | Synced item never arrives. The setup screen simply shows what it shows today (discovered Macs → scanner, #2347/#3102). **One** quiet status line on the discovered-host row — "Automatic pairing unavailable — scan the code on your Mac" — and only when we can cheaply infer it. No toggle, no error wall (dead-simple-UX rule: this is a decision, not a switch). |
| Sync latency (item not here *yet*) | Re-query on appear/foreground; if absent, the QR flow is right there. Never spin waiting on iCloud. |
| Synced payload present but host unreachable / stale (Mac renamed, pin rotated) | Enrollment fails closed (pin mismatch or 401) → fall to QR; a *successful* re-pair via QR should refresh the synced payload from the Mac side on next card refresh. |
| Enrollment secret revoked | Engine 401s; device shows the same "pair again" UX as a revoked device token (#3290's renewal/revocation UX work). |
| tvOS/visionOS | Out of scope (tvOS never syncs, (a)). |

**Hard rule preserved:** every degradation lands on the existing, working QR path. Zero-touch is additive sugar; its absence is never an error state.

### 1.7 What changes, what does not

**Unchanged:** `/api/pair`, pairing codes, QR + manual link, `persistPairedHost`, SPKI pinning, per-device tokens + 90-day TTL + renewal + revocation, loopback/`tailscale serve` transport, multi-user authz.
**Added:** explicit `kSecAttrAccessible` (+`kSecUseDataProtectionKeychain` + macOS migration) on existing token writes (#3772/#3290 groundwork); one engine table + `POST /api/pair/enroll`; one synced keychain item write/rotate/delete on the Mac; one read + one-tap connect on iOS.

---

## Part 2 — Sharing with another person (QR / Messages / Mail)

### 2.1 What exists today (all verified, §0.4–0.6)

Three distinct share surfaces, each real, each partially wired:

1. **Device-pairing link** `fichero://pair?payload=…` — QR + selectable link + Copy + `ShareLink` on the Mac card; scanner + manual paste + (dead) tap-to-open on iOS. One-time code, 10-min TTL, pin included.
2. **Account invite** `fichero://invite?token=…` — owner mints (QR + Copy, **no ShareLink**); recipient redeems by setting a password. Single-use, 15-min TTL, revocable, hashed at rest, rate-limited. Redemption requires the app to already be connected to the engine (`SessionStore.swift:213`).
3. **Library-role share** — `ShareLibrarySheet` grants a role via audited `acl.set` and offers `ShareLink` on a `share_url` that is a **bare engine API URL** carrying no credential and no app routing (`authz.py:262-273`).

### 2.2 What is broken (ranked)

1. **`fichero://` scheme unregistered (§0.6).** Every "send a link" affordance in the app produces a link the recipient cannot tap. This retroactively hollows out CLOSED #2399 and #3153/#3157's link half. *Fix: add `CFBundleURLTypes` (scheme `fichero`, role Viewer, name `app.fichero.fichero`) to `fichero/fichero/Info.plist`. Two lines of plist; the receive code is already waiting on both platforms.*
2. **Custom schemes are second-class in messaging channels (b).** Mail and Messages reliably auto-link `https://`, not arbitrary schemes; a `fichero://…` string frequently renders as plain text (recipient must select-and-copy), and any *web* intermediary (webmail, Slack, etc.) will refuse it. Registering the scheme fixes tap-on-device, not linkification. The durable fix is a **universal link** domain (§2.4).
3. **Account-invite links can't stand alone.** `fichero://invite?token=…` carries no host and no pin; redemption uses the current client (`SessionStore.swift:213`). Works for re-inviting someone already paired; **cannot onboard a fresh person with a fresh install** — they'd need the pairing link *and* the invite link, in the right order, within 15 minutes. Nothing in the UX explains that today. (c on the UX consequence; the code facts are verified.)
4. **`share_url` is not a share link.** A human receiving `https://mac.ts.net/api/documents/abc` gets a 401 JSON page. The `ShareLink` "Send…" on `ShareLibrarySheet:126` sends a URL that helps no one who wasn't already fully set up. (c on severity; verified content.)
5. **15-minute invite TTL vs asynchronous channels.** For a co-present QR, 15 min is generous. Over email — a channel where delivery+read latency routinely exceeds it — most invites will be dead before they are opened. (c)
6. Minor: `InviteAccountSection` has Copy but no `ShareLink`; inconsistent with the pairing card.

### 2.3 What is missing

A **single person-to-person invite artifact** that a stranger-to-the-system can consume: today "add a person" is three separate grants (account invite + device pairing + library role) minted in three UI places, with only the QR-savvy path actually connective.

### 2.4 Design: the share flow (QR / Messages / Mail)

**Step 1 — register the scheme (now).** Unblocks tap-to-open on devices with Fichero installed. No security change: parsing is already defensive (`pairingFields(fromInviteOrPayload:)` validates URL shape, base64, JSON, pin format, and rejects localhost/insecure transports, `RemoteClientPairing.swift:88-104`; invite parser tolerates junk, `SessionStorePhaseTests.swift:104-107`). One new consideration once registered (c): **any** app/webpage can now attempt to open `fichero://` URLs — both handlers must keep treating incoming links as untrusted input and must never auto-execute a pair/redeem without showing the user what is about to happen. The iOS `PairingIncomingLinkSheet` (confirm-before-pair, `FicheroApp_iOS.swift:127-133`) is the right shape; **macOS `handleOpenURL` currently ignores `fichero://pair` entirely** (`FicheroApp.swift:123-146` handles invite then falls through to library-file opening) — the Option-launch remote-client Mac should get the same sheet (sibling sweep).

**Step 2 — one combined invite ("Invite to library"), the product-level fix for #2.3.** Mint in one place (ShareLibrarySheet is the natural home; InviteAccountSection folds in): owner picks person + role → engine mints, atomically: account invite (existing) + pairing material, returned as a **v2 payload** = `PairingQRCodePayload` shape + `invite_token`:

```json
{ "v": 2, "api_url": "…", "spki": "sha256/…", "pair_code": "…", "expires_at": "…",
  "library_path": "…", "invite_token": "…" }
```

Recipient flow (app installed): tap/scan → confirm sheet ("Join Daniel's library 'Marshall Diaries' as Editor?") → pair (device token, pinned TLS) → redeem invite (set password) → library opens with the granted role. One artifact, one flow, and — engine decision to make explicit — `redeem` staying separate from `pair` preserves the existing separation of device identity vs user identity; both tokens end up device-held per the existing storage paths.

**Step 3 — Messages / Mail transport.** With the scheme registered, `ShareLink(item: URL)` on the combined link is already the native share sheet → Messages/Mail/AirDrop. Add `SharePreview` (title "Join «library» on Fichero", app icon) so the Messages bubble is legible. Add the missing `ShareLink` to the invite sheet. **AirDrop deserves a call-out to Daniel:** it is co-present like QR but tappable, and works today with zero extra infrastructure once the scheme is registered.

**Step 4 (deferred, Daniel's call) — universal links.** `https://fichero.app/join#<base64 payload>` with an AASA file; fragment (`#`) keeps the payload out of server logs on the fallback web hit (b). Gives: reliable linkification everywhere, a graceful not-installed landing page, and survives webmail. Costs: a domain + hosted AASA + associated-domains entitlement (which the MAS sandbox permits). The `fichero://` scheme stays as the offline/QR-encoded form.

### 2.5 Security analysis: invite-in-an-inbox vs co-present QR — explicit, per the brief

**What is in the artifact (both QR and link, identical payload — the Mac card already says so, `PairingCardView.swift:484-491`):** engine URL (reveals a `.ts.net` hostname — modest info leak, the tailnet still gates reachability), the SPKI pin (public-key material, not secret), a **one-time pairing code** (secret until used/expired), and in v2 an **invite token** (secret, single-use, hashed at rest).

| Property | QR (co-present) | Messages (iMessage) | Email |
|---|---|---|---|
| Channel confidentiality | Line of sight only; nothing transits a network | E2E-encrypted in transit (b); durable on both devices + iCloud backups | Often TLS hop-by-hop, **not** E2E; durable in inboxes, servers, forwards |
| Artifact lifetime | Seconds on screen; regenerated per card refresh | Persists in thread | **Persists indefinitely; forwardable; searchable** |
| Who can redeem | Someone physically present | Whoever holds the thread | Whoever ever obtains the message |
| MITM on first connect | Pin delivered out-of-band of the network path — strong | Pin and secrets share one channel: whoever can read/alter the message gets both, so the pin defends only against *network* attackers, not channel attackers (c — important honesty) | Same, worse channel |

**Why the design is still acceptable to offer (c, with the mitigations that make it so — all but one already built):** the secrets in the artifact are (1) **single-use** — first redemption consumes them (`pairing.py:459-460`; `consume_invite`), so a lurker in the inbox finds a dead token, and a *failed* redemption by the intended recipient is a loud signal; (2) **short-lived** (10/15 min today; see Q3 for the email tension); (3) **revocable pre-redemption and post-redemption** (invite revoke; device revoke; role revoke — all exist); (4) **hashed at rest** server-side; (5) rate-limited. Add one missing mitigation: **notify the owner on redemption** ("Sofía joined as Editor from «Sofía's iPhone»") — the engine has the audit spine (#1848) for exactly this.

**⚠️ SECURITY CALL-OUT: an emailed invite is a durable secret in an uncontrolled channel — the mitigations above are what make it defensible, so none of them (single-use, TTL, revocation, hashed storage, redemption notice) may be relaxed to smooth the UX.** The single deliberate trade proposed anywhere in this document is the email-path TTL (Q3), and it goes to Daniel, not into code.

**Recommended framing in UI copy** (extends the existing honest line at `:526`): QR/AirDrop presented first ("in person"), Messages second, Mail last, each labeled with what it implies — never a scary wall, one honest sentence.

### 2.6 Recipient without Fichero installed

Custom schemes offer no fallback: a tapped `fichero://` link with no handler does nothing (iOS) or errors (macOS) (b). Until universal links exist: the *sending* UX should say what the recipient needs ("They'll need Fichero — TestFlight/App Store/DMG link") and ideally the share sheet shares a short human message containing both the get-Fichero URL and the invite link. With universal links (Step 4), the not-installed case lands on the web page: "Get Fichero, then tap your invite again" — the payload in the fragment survives untouched. Note invite TTL must accommodate an install round-trip, which feeds Q3.

---

## Part 3 — Security invariants (unchanged and non-negotiable)

1. Per-device tokens, individually revocable — **preserved by design** (the entire point of §1.2/1.3).
2. SPKI pinning on every remote connection; pin travels only inside pairing payloads or E2E-encrypted iCloud Keychain — never bare over the channel it protects against.
3. Pairing/invite secrets: single-use, short-TTL, hashed at rest, rate-limited — preserved verbatim in the combined-invite design.
4. Engine binds loopback only; `tailscale serve` (never funnel) fronts external access (#2124, #3342) — nothing here touches transport.
5. Fail closed: unknown pin, revoked secret, expired code → refuse and say why (never a silent fallback, never a blank space).
6. Secrets never in UserDefaults, never logged (existing discipline, `AuthTokenMiddleware.swift:336-337`, `FicheroApp.swift:126-127`) — extends to the enrollment secret and synced payload.
7. Tailscale is perimeter, not user-authz (#2124) — the invite/account layer stays the authorization authority.

---

## Part 4 — Questions for Daniel (each with a recommendation)

**Q1. Approve the enrollment-secret design for zero-touch (§1.3) — synced *bootstrap*, never the synced *token*?**
→ **Recommend: yes.** It is the only variant that keeps per-device revocation. If you want zero-touch without any engine change, the honest answer is: there isn't one worth having — syncing the token is the only no-backend option and it trades away revocation (§1.2). Say the word and I'll spec the endpoint + table for a worker.

**Q2. On the iPhone, when the synced credential is present and the Mac is discovered: auto-connect silently, or one-tap "Connect to Daniel's Mac"?**
→ **Recommend: one tap the first time, automatic thereafter** (per-host). First contact should be visible (a join event on a new device is worth one human glance); after that, it's the same Mac — silence is correct. Matches "dead-simple, no needless toggles": this is a policy, not a setting.

**Q3. Email invites: extend the invite TTL for the send-by-Mail path (15 min → e.g. 24 h), keeping single-use + revocation + redemption notification?**
→ **Recommend: yes, for the email path only, and only alongside the redemption notification.** This is Part 2's one real security-vs-UX trade (§2.5 call-out) and it is yours to make, not mine: 15-minute email invites will mostly arrive dead (§2.2#5), but 24 h is 96× the exposure window in the worst channel. QR/Messages paths keep the short TTL.

**Q4. Buy/point a domain for universal links (`fichero.app` or similar) so invites are tappable everywhere and the not-installed case has a landing page (§2.4 step 4)?**
→ **Recommend: yes, but sequenced after the scheme registration + combined invite ship.** The `fichero://` registration is the 90% fix for your own testing today; universal links are what make "email an invite to a colleague" actually respectable.

**Q5. Combined invite (account + pairing + role in one artifact, §2.4 step 2): fold `InviteAccountSection` into `ShareLibrarySheet` as the one place people are invited?**
→ **Recommend: yes.** Three separate grants in three panes is machinery-shaped UX (#3776's disease). One "Invite to library…" flow, with the plain-account invite surviving as the degenerate case (no library role picked).

**Q6. macOS keychain migration: adopt `kSecUseDataProtectionKeychain = true` app-wide with a one-time legacy→data-protection migration of existing remote/session tokens (§1.5)?**
→ **Recommend: yes.** Apple recommends the key unconditionally (a); it is a precondition for the Mac writing synchronizable items; and the migration is small (two keychain services, host-scoped accounts). Without the migration flag set consciously, Option-launch Mac remote clients would silently lose their tokens — that's the loud-failure rule applied to ourselves.

**Q7. #3772 sequencing: OK to land the explicit `kSecAttrAccessible(AfterFirstUnlock)` + the four-value relaunch diagnostic first, before any Part 1/Part 2 feature work?**
→ **Recommend: yes — it is the show-stopper, it is groundwork for everything above, and the diagnostic decides whether the remaining fix is keychain, host-ordering, or #3342.**

---

## Appendix A — Citations

**Apple documentation (fetched 2026-07-14 via developer.apple.com JSON endpoints):**
1. `kSecAttrSynchronizable` — https://developer.apple.com/documentation/security/ksecattrsynchronizable — sync semantics, class support (passwords/certs/keys since iOS 14/macOS 11), update/delete propagation, `ThisDeviceOnly` incompatibility, no `SecAccessControl`, no persistent references, macOS-behaves-like-iOS, tvOS never syncs.
2. Restricting keychain item accessibility — https://developer.apple.com/documentation/security/restricting-keychain-item-accessibility — full accessibility ladder; *"This is the default accessibility"* (WhenUnlocked); `ThisDeviceOnly` = no migration to other devices' backups.
3. `kSecAttrAccessibleAfterFirstUnlock` — https://developer.apple.com/documentation/security/ksecattraccessibleafterfirstunlock — *"recommended for items that need to be accessed by background applications"*; migrates via encrypted backups.
4. Sharing access to keychain items among a collection of apps — https://developer.apple.com/documentation/security/sharing-access-to-keychain-items-among-a-collection-of-apps — default private access group = team ID + bundle ID; keychain sharing = same-team apps.
5. iCloud Keychain security overview (Apple Platform Security) — https://support.apple.com/guide/security/icloud-keychain-security-overview-sec1c89c6f3b/web — end-to-end encryption of keychain sync. *(Referenced for the E2E claim; not re-fetched — flagged (a) on the strength of the Platform Security guide.)*
6. `kSecUseDataProtectionKeychain` — https://developer.apple.com/documentation/security/ksecusedataprotectionkeychain — *"highly recommended … for all keychain operations"*; macOS-only effect; synchronizable=true implies the same behavior + sync.

**Key code references (repo `~/code/fichero` @ `3053dfa54`):** `AuthTokenMiddleware.swift:27,185-187,251-275,311-317,328-362`; `RemoteClientPairing.swift:14-24,66-104,135-187`; `RemoteCertificatePinning.swift:76-118`; `EngineConfig.swift:93-140,734-773,932-934`; `PairingCardView.swift:103-234,484-544`; `InviteAccountSection.swift`; `ShareLibrarySheet.swift:114-131`; `ShareSettingsView.swift:1-60`; `SessionStore.swift:45-50,175-213`; `AuthGateView.swift:21,252`; `FicheroApp.swift:123-146,314`; `FicheroApp_iOS.swift:117-133,265-299,397-399,551-554`; `Info.plist:27-29,56,61`; `project.pbxproj:4636-4646`; engine: `pairing.py:28,391-470,484-499`; `auth_accounts.py:28-31,374-385,475-572`; `authz.py:262-273,276-328`; `app_db.py:1611-1627`.

**GitHub issues read:** #3772, #3769, #3776, #3342, #3290, #2399 (CLOSED), #3774, #3157 (CLOSED), #3153 (CLOSED), #3149 (CLOSED), #3102 (CLOSED), #2347 (CLOSED).

**Honest unknowns:** iCloud Keychain sync latency (no Apple SLA — (b) seconds-to-minutes); exact Messages/Mail linkification behavior per OS version for custom schemes ((b) — verify empirically once the scheme is registered); which #3772 candidate cause is live on Daniel's devices (needs the four-value diagnostic); whether unsigned dev-tool contexts hit `errSecMissingEntitlement` with the data-protection keychain on macOS ((b)).
