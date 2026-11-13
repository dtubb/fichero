# Signing in from iOS and from your own devices — Design Spec (→ #6568)

> Milestone: Sharing & Pairing — Dead-Simple UX
> Manual: TBD — "Opening your library on your iPhone or iPad" (which switch to turn on, what each one trusts, how to remove a device).
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-11-12** (every [GAP] names its `(not yet written)` test, so
> `check_specs_have_tests` guards it; APPROVED waits for the owner's answers to the open questions and the manual section).
> Written from the owner's direction of 2026-11-12 (paraphrased, never quoted) and the rulings already in
> `library-sharing.md`, `multiuser-always-on.md` and `source/sharing-two-macs.md`; code read on integration at c01d822e91.
> Tags: **[OK]** built and seen working · **[PARTIAL]** built, unproven or incomplete · **[GAP]** not built.
> Secrets (tokens, keys, codes) appear nowhere in this file.

## Intent

A scholar's own iPhone or iPad opens the library on their Mac with nothing typed: no code, no password, no address. Each way
of getting there is a **switch the owner turns on in Settings › Sharing on the Mac**, never a default forced on them, and each
switch says in its own words what it trusts. Another person's device still signs in as that person. Every device, whichever
way it arrived, gets its own session the Mac can revoke, and nothing is ever reachable beyond the Mac's tailnet or local network.

## The rulings this rests on

- **With Multi-user on, sharing a Mac is its Tailscale address plus an account** (owner 2026-11-12, #6568): Add Device shows
  `https://<mac>.<tailnet>.ts.net:<port>` with Copy and the words "sign in with your account"; pairing links and codes stay only
  for Multi-user off and for plain `.local` / IP addresses (which still need the pinned link or the shown key fingerprint,
  `sharing.people.sign-in-without-a-code`). A `.ts.net` address has Tailscale's public certificate, so no pin.
- **Only the Mac's own app, over the engine's Unix socket, may turn Multi-user on or off or set the owner's password**
  (owner ruling 2026-11-12, #6565): the switch and the password are never reachable from a paired device, the TCP listener,
  the CLI or MCP. The same rule governs the Allow button of method 2 below.
- Every remote connection is a device with its own revocable credential bound to a person (`sharing.device-acts-as-its-binding`,
  `sharing.revoke`, `sharing.revoke-cascades`); with Multi-user off that person is the owner.
- Transport invariants are unchanged: HTTPS always; `.local` pinned by SPKI, `.ts.net` by system trust; `tailscale serve`, never
  `funnel`; the Mac's own app dials its engine over the Unix socket (`transport-http-uds.md`).
- **How a device reaches the Mac (owner 2026-11-12):** on the local network, Bonjour; from any other network, Tailscale.
  There is no Apple-provided way to reach a running engine on a Mac from another network: Back to My Mac is gone, and
  CloudKit syncs data, not a live connection. Every method below rides on those two routes and adds no third.

## Prior art (adopt, don't invent)

- **iCloud Keychain shared items** (`kSecAttrSynchronizable`, a keychain access group shared across the Mac and iOS apps): how
  Apple's own apps let a person's devices find each other's secrets without a step. The owner key already lives this way
  (`fichero/fichero/Services/Auth/OwnerKeyStore.swift`, `multiuser-always-on.md` "Keychain access group"). Method 1 reuses it.
- **Tailscale node approval, Signal linked devices, AirPods/HomePod proximity set-up**: the new device asks, a trusted one
  approves. Method 2 is this, with the Mac's own window as the trusted side.
- **Passkeys / WebAuthn** (W3C, AuthenticationServices on Apple): per-account public key, challenge-response, Face ID/Touch ID,
  synced by iCloud Keychain. Bound to a relying-party id proven by associated domains, which is why `multiuser-always-on.md`
  kept them for the web client; method 3 names the open question instead of pretending a `.ts.net` host is a domain we own.
- **Password AutoFill and the Passwords app** (`textContentType`, associated domains for credential autofill): method 4.

## Behaviours

### A. Ground rules (all methods)

- `signin.methods-are-options` — **[GAP]** (#6568; owner ruling 2026-11-12) Settings › Sharing lists each way a device may
  sign in as its own switch with one grey line under it saying what it trusts: *Your own devices sign in by themselves*
  (off), *Approve new devices on this Mac* (on when Sharing is on), *Passkeys* (off, and absent until built), and the two
  fallbacks that need no switch (the Add Device QR, username and password). A switch's words are part of this spec, not
  decoration; nothing is turned on by an update. Acceptance: a fresh install with Sharing on has exactly *Approve* on.
  *Test:* `SignInOptionsSwitchesTests.swift` (the defaults, the captions) (not yet written).
- `signin.every-device-gets-its-own-session` — **[GAP]** (#6568) whichever method a device arrives by, the engine records it
  as its own device row, named by the device, bound to one person, with the METHOD recorded (`enrolled`, `approved`,
  `passkey`, `code`, `password`), and mints it its own credential; no method shares one token between devices, and a method's
  switch going off never ends the sessions it already made (revoke does). Acceptance: two iPhones by method 1 are two rows.
  *Test:* `test_every_method_makes_its_own_device_to_spec.py` (not yet written).
- `signin.only-the-macs-own-app-decides` — **[GAP]** (#6568; ruling #6565) the switches of this spec, the Allow/Deny of
  method 2 and the Multi-user switch itself are accepted only from the Mac's own app over the Unix socket (the peer-stamped
  request, `multiuser.first-connection-asks-the-person`); the TCP listener, a paired device, a `.ts.net` caller, the CLI and
  MCP are refused 403 in words. Acceptance: a paired owner device cannot allow another device.
  *Test:* `test_only_the_mac_app_decides_sign_in_options_to_spec.py` (not yet written).
- `signin.nothing-beyond-the-tailnet-or-lan` — **[GAP]** (#6568) no method opens a listener, a relay or a forward beyond what
  Sharing already binds (`sharing.listener`, `sharing.tailscale-serve`): the Keychain item of method 1 names only the Mac's
  tailnet and `.local` addresses, method 2 answers only on those listeners, and nothing ever uses `tailscale funnel` or a
  public relay. Acceptance: a guard fails any `funnel` or public-host string in the engine.
  *Test:* `test_sign_in_methods_bind_nothing_new_to_spec.py` (not yet written).
- `signin.revoke-from-the-mac` — **[GAP]** (#6568) Settings › Sharing › Devices lists every device from every method with its
  method in grey ("iPhone · signed in by itself", "iPad · approved here 12 Nov"), and `−` revokes it; a revoked device is
  refused at once and its streams end (`sharing.revoke-closes-the-stream`). Revoking a device never revokes the method.
  Acceptance: revoke one of two self-enrolled iPhones; the other keeps working.
  *Test:* `test_revoke_names_the_method_to_spec.py`, `DevicesListMethodWordsTests.swift` (not yet written).
- `signin.multiuser-off-still-works` — **[GAP]** (#6568) with Multi-user off: methods 1 and 2 bind the device to the owner
  (the only person); method 3 and "address + account" are not offered (no accounts to sign into) and their switches say so in
  one grey line; the QR and code stay. With Multi-user on: methods 1 and 2 bind to the OWNER'S account only (they are the
  owner's own devices; another person's device uses an account); method 3 is per account. Acceptance: the same iPhone enrols
  under both states and is the owner in both. *Test:* `test_methods_under_multiuser_off_to_spec.py` (not yet written).

### B. Method 1 — your own devices sign in by themselves (off by default)

- `signin.own.mac-writes-the-keychain-item` — **[GAP]** (#6568) with the switch on, the Mac writes ONE synchronizable Keychain
  item (`kSecAttrSynchronizable`, the shared access group, `AfterFirstUnlock`, no user-presence prompt) holding: the engine id,
  the Mac's name, its addresses (`.ts.net` first, then `.local` with its SPKI pin), and a per-enrollment secret the engine
  minted for this purpose and stores only as a hash (`POST /api/pair/enroll` already exchanges such a secret for a device
  token; nothing mints it today, `library-sharing.md` `sharing.synced-device-pairs-by-host-code`). The item is rewritten
  whenever an address changes and deleted when the switch goes off. Never the owner key, never a session.
  Acceptance: the item's payload has those fields and nothing else. *Test:* `OwnDevicesKeychainItemTests.swift` (the shape),
  `test_enrollment_secret_is_minted_hashed_and_revoked_to_spec.py` (not yet written).
- `signin.own.ios-finds-it-and-connects` — **[GAP]** (#6568) an iPhone or iPad on the same Apple ID, with iCloud Keychain on,
  finds the item on launch (and on foreground), shows the Mac by name under "Your Macs", dials its addresses in turn
  (`sharing.client-tries-every-address`), redeems the enrollment secret for ITS OWN device token (`/api/pair/enroll`, named
  "Daniel's iPhone") and opens the library; nothing is typed. With no item it shows the other methods. A device enrols once
  (its token is kept in its own Keychain, not synced); it never re-enrols while its token works.
  Acceptance: a fresh iPhone opens the library with zero taps past the row. *Test:* `OwnDevicesConnectTests.swift` with a
  fake Keychain reader, `test_enroll_makes_one_device_per_redeem_to_spec.py` (not yet written).
- `signin.own.setting-says-the-trade-off` — **[GAP]** (#6568) the switch's caption says, in plain words, that any device
  signed into this Apple ID can open this Mac's libraries without asking, so it should stay off on a shared Apple ID; the
  words are pinned by test. Acceptance: the caption names the Apple ID trade-off. *Test:* `SignInOptionsSwitchesTests.swift`
  (not yet written).
- `signin.own.off-ends-enrolment-not-devices` — **[GAP]** (#6568) turning the switch off deletes the item and retires the
  enrollment secret (a later redeem is refused as a bad code, learning nothing); devices already enrolled keep their own
  sessions until revoked, and the Devices list says which came this way. Turning it on again mints a NEW secret.
  Acceptance: off, then a redeem of the old secret is 401. *Test:* `test_enrollment_off_retires_the_secret_to_spec.py`
  (not yet written).
- `signin.own.secret-is-rate-limited-and-rotates` — **[GAP]** (#6568) the enrollment secret is 32 random bytes, redeemed only
  over TLS to the Mac's own listeners, rate-limited like `POST /api/pair` (`PAIRING_RATE_LIMIT`), rotated by the Mac every 30
  days (the item is rewritten; enrolled devices are untouched) and on every revoke of a self-enrolled device. Acceptance: a
  revoke changes the secret. *Test:* `test_enrollment_secret_rotates_to_spec.py` (not yet written).

### C. Method 2 — tap the Mac, approve on the Mac (on by default when Sharing is on)

- `signin.approve.ios-lists-macs` — **[GAP]** (#6568; builds on `sharing.ios-discovers-host`, `sharing.settings.ios-host-pick`)
  the iPhone's Connect screen lists Macs it can see: Bonjour (`_fichero._tcp`, `fichero/fichero/Services/Connectivity/NearbyHosts.swift`)
  and Tailscale names it has used before or that the Keychain item names; a `.ts.net` host only in this device's own tailnet
  (`sharing.mac-finds-host`'s rule). Each row says the address it will use. Acceptance: a Mac on the LAN appears within 5 s.
  *Test:* `HostChoicesTests.swift` (the iOS rows) (not yet written).
- `signin.approve.tap-asks-the-mac` — **[GAP]** (#6568) tapping a Mac sends `POST /api/pair/requests {device_name, public_key}`
  over the Mac's TLS listener, unauthenticated, rate-limited, at most 3 pending per address and 20 in all, each living 2
  minutes; the phone shows "Waiting for <Mac> to allow this iPhone…" with Cancel, and polls the request's state. The request
  carries the device's own fresh P-256 public key (`multiuser.client-gets-its-own-credential`'s shape), never a password.
  Acceptance: the fourth pending request from one address is 429 in words. *Test:*
  `test_pair_request_is_capped_and_expires_to_spec.py`, `ApproveOnMacWaitingTests.swift` (not yet written).
- `signin.approve.mac-shows-allow` — **[GAP]** (#6568) the Mac's own app shows, in its own window (a sheet on the front window,
  and a notification that opens it), "Allow <device name> to open your libraries?" with the address it came from, Allow and
  Deny; the answer goes to the engine over the Unix socket only (`signin.only-the-macs-own-app-decides`). Nothing is shown on
  a paired device. Acceptance: an answer over TCP is 403. *Test:* `test_approve_only_over_uds_to_spec.py`,
  `AllowDeviceSheetTests.swift` (not yet written).
- `signin.approve.allow-enrols-the-device` — **[GAP]** (#6568) on Allow the engine registers the request's public key as that
  device's credential, bound to the owner (Multi-user off or on; another person uses an account), and the phone's next poll
  gets its session and opens the library; Deny, expiry and Cancel each answer the phone the same "not allowed" in words and
  leave nothing behind. Acceptance: Allow then the phone lists the library; Deny then 401. *Test:*
  `test_allow_registers_the_key_deny_leaves_nothing_to_spec.py` (not yet written).
- `signin.approve.default-and-unlock` — **[GAP]** (#6568; open question 3) the switch is on whenever Sharing is on, and off
  with it; a request that arrives while the Mac's screen is locked waits (the sheet shows at unlock within the 2 minutes) or
  is shown on the lock screen, as the owner rules. Acceptance: Sharing off, the route is 404. *Test:*
  `test_requests_route_follows_sharing_to_spec.py` (not yet written).

### D. Method 3 — passkeys for people's accounts (off until built and proven)

- `signin.passkey.offered-after-first-password` — **[GAP]** (#6568) after a person's first password sign-in from an iPhone,
  iPad or Mac, the app offers once "Save a passkey for <Mac>?" (Not Now is remembered per device); a passkey is made with
  AuthenticationServices and registered with the engine against that account. Acceptance: the offer appears once.
  *Test:* `PasskeyOfferTests.swift` (not yet written).
- `signin.passkey.engine-is-the-relying-party` — **[GAP]** (#6568) the engine implements WebAuthn registration and assertion
  (a `credentials` row of kind `passkey`: credential id, public key, sign count, account; challenge single-use, 60 s, bound to
  the engine id as the key challenge is, `multiuser.signature-is-bound-to-this-engine`); a passkey assertion yields a device
  session like any other. Acceptance: a replayed assertion is refused. *Test:* `test_passkey_register_and_assert_to_spec.py`
  (not yet written).
- `signin.passkey.rp-id-is-decided-first` — **[GAP]** (#6568; open question 2) a passkey is bound to a relying-party id the
  platform verifies by associated domains; a `.ts.net` host is Tailscale's domain and a `.local` name is nobody's. The
  options, for the owner: (a) a static RP id on a domain we own (`tubb.ca`, the AASA already served, `sharing.ios-link-opened-from-messages`),
  with every engine a sub-origin of it, which makes one passkey per account per engine; (b) wait for platform support for
  non-domain relying parties. Nothing is built, and the switch is absent, until this is ruled. Acceptance: n/a (a decision).
  *Test:* n/a (a decision; recorded here so nobody builds ahead of it).
- `signin.passkey.face-id-sign-in` — **[GAP]** (#6568) with a passkey saved, that account's later sign-ins on that device are
  Face ID / Touch ID, no password; a lost device is a revoke of its sessions and of the passkey from the Mac. Acceptance:
  second sign-in asks for nothing but biometrics. *Test:* `PasskeySignInTests.swift` with a fake authorization controller
  (not yet written).

### E. The fallbacks (always there)

- `signin.qr-stays-the-fallback` — **[PARTIAL]** (#6568; exists: `sharing.settings.add-device-sheet`, `sharing.ios.nearby-tap-pairs-with-that-mac`)
  Add Device's QR and code stay for Multi-user off and plain local addresses; with Multi-user on the sheet shows the tailnet
  address and "sign in with your account" instead (#6568). Not built: the Multi-user-on words.
  *Test:* `AddDeviceSheetModelTests.swift` (exists; the Multi-user-on words not yet written).
- `signin.password-comes-last` — **[PARTIAL]** (#6568; order ruled in `multiuser.password-comes-last`; sign-in route built,
  `sharing.people.sign-in-without-a-code`) the iOS sign-in screen offers, in order: your own Macs (method 1), nearby Macs to
  approve (method 2), a passkey (method 3), the QR, and last a username and password; the password fields use
  `textContentType` username/password so the Passwords app offers to save them. Not built: the order and the AutoFill hints.
  *Test:* `SignInOptionsOrderTests.swift` (not yet written).

### F. Failed sign-ins

Today the engine only throttles: `LOGIN_RATE_LIMIT` 5 tries per `LOGIN_RATE_WINDOW` of 1 minute, per account and per IP, in
memory (`fichero-server/src/fichero_server/api/routes/auth/accounts.py`), 429 with `Retry-After`; a restart resets it and there
is no lockout.

- `signin.failures.escalating-backoff-persists` — **[GAP]** (#6568; owner 2026-11-12) after the window's 5 failures, an account
  backs off in steps, 1 min, 5 min, 15 min, then 1 h per further failure, answered 429 with `Retry-After` and in words ("Try
  again in 15 minutes"); the counter and its step live in the app database (per account, and per address as today), so an
  engine restart does not reset them; a successful sign-in clears that account's counter. Never a hard lock: the back-off is
  the whole penalty, so a stranger cannot lock a person out for good, only slow them. Acceptance: 6th failure 1 min, 7th 5 min;
  restart, still backing off. *Test:* `test_failed_sign_ins_back_off_and_persist_to_spec.py` (not yet written).
- `signin.failures.mac-shows-who-is-being-tried` — **[GAP]** (#6568) after 10 failures on one account the Mac's own app shows,
  in its own window, "<name> has had 10 failed sign-ins from <address>" with **Unlock** (clears the back-off; over the Unix
  socket only, `signin.only-the-macs-own-app-decides`) and **Reset password** (the owner's existing account route). The sheet
  is shown once per run of failures and in Settings › Sharing › Accounts as a row until cleared. Acceptance: the 10th
  failure raises the sheet; Unlock over TCP is 403. *Test:* `test_unlock_is_uds_only_to_spec.py`,
  `FailedSignInsSheetTests.swift` (not yet written).
- `signin.failures.local-app-and-passkeys-are-exempt` — **[GAP]** (#6568) the Mac's own app over its Unix socket is never
  throttled or backed off (it signs in by key, and it is the one that unlocks); a passkey assertion is not a password try and
  neither counts toward nor is refused by an account's back-off (the key cannot be guessed); method 1 and 2 redeems keep the
  pairing limit (`PAIRING_RATE_LIMIT`). Acceptance: an account in 1 h back-off still signs in by passkey. *Test:*
  `test_backoff_exempts_uds_and_passkeys_to_spec.py` (not yet written).

## Security notes

| Method | Trusts | Revoked by | Multi-user off | Exposed beyond tailnet/LAN |
|---|---|---|---|---|
| 1 Own devices | The Apple ID and iCloud Keychain (anyone signed into it) | Devices list; switch off retires the secret | Binds to the owner | Nothing: the item names the Mac's own listeners |
| 2 Approve on Mac | Whoever can press Allow in the Mac's own window | Devices list | Binds to the owner | Nothing: the request route is on the existing listeners |
| 3 Passkey | The account, plus the device's biometrics | Devices list, or the passkey from Accounts | Not offered | Nothing; RP id is the open question |
| 4 QR / code | Whoever holds the link, 10 minutes | Devices list | Works as today | Nothing |
| 5 Password | The account's password | Devices list, change the password | Not offered | Nothing |

A method's credential is never a session: it mints one. No method sends a password where a key will do, and no method ever
puts a secret in a file a sync service copies (`sharing.synced-project-names-its-host`).

## Open questions for the owner

*Ruled by the owner 2026-11-12 (questions 1 and 2):* the DMG builds get the shared keychain group too, so method 1 is not limited to TestFlight and App Store builds; passkeys use `tubb.ca` as the relying-party id, provided it asks nothing of the owner: the app's `webcredentials` entry is added to tubb.ca's apple-app-site-association (today it carries only `applinks`) by the site deploy. Question 5 (rotation) was left to the manager: the enrollment secret rotates every 30 days, renewed silently by the device while it is signed in, so nobody is asked anything. Question 3 the owner left open; the manager's default until the owner rules: the Mac must be unlocked to approve (the Allow sheet waits for unlock; nothing shows on the lock screen), since approving is a decision made at the Mac. Question 4 stays open.

1. **Keychain access group and team id** for method 1: the shared group (`<team id>.app.fichero.shared`) exists for the Dev
   build only; the DMG builds carry none (`multiuser.owner-key-kept-locally-without-keychain-entitlement`, #6374). Method 1
   needs the group on the Mac AND the iOS App Store profile. Give the DMG builds the group, or ship method 1 for the App
   Store/TestFlight builds first?
2. **Relying-party id for passkeys on `.ts.net`**: option (a) a static RP id on `tubb.ca` with every engine under it, or (b)
   defer passkeys until the platforms allow a non-domain RP. (a) ties every private Mac to one public domain's AASA.
3. **Does approve-on-Mac need the Mac unlocked?** Wait for unlock (safer, the person is there), or show the sheet on the
   lock screen (faster, anyone at the Mac can press Allow)?
4. **Method 2 with Multi-user on**: the owner's own devices only (this draft), or may the Allow sheet pick a person?
5. **Rotation of the enrollment secret**: 30 days as drafted, or never (fewer rewrites, a leaked secret lives longer)?

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | switch defaults and captions, Keychain item shape, option order, Allow sheet words | `fichero/Tests/Unit/general/Sharing/` (names above, not yet written) |
| Backend (pytest) | y | enroll mint/retire/rotate, request cap and expiry, UDS-only Allow, passkey challenge, method on the device row | `fichero-server/tests/unit/security/` (names above, not yet written) |
| Guard | y | no new listener, forward or `funnel` | `test_sign_in_methods_bind_nothing_new_to_spec.py` (not yet written) |
| Real Mac + iPhone | y | item syncs, zero-tap open, Allow round trip, revoke | the two-Mac-and-iPhone checklist, a new section |

## Build order

Steps a long-running builder can take from the heading. `Depends on` defaults to the step before. Order: the ground
rules and method 2 first (on by default, no entitlement question), method 1 once question 1 is answered, passkeys last
and only after question 2. Each step's test is written first and red.

### Stage 1 — ground rules and approve-on-Mac

#### Step 1.1 — the switches, the device row's method, the Mac's app decides
- Behaviours: `signin.methods-are-options`, `signin.every-device-gets-its-own-session`, `signin.only-the-macs-own-app-decides`, `signin.nothing-beyond-the-tailnet-or-lan`
- Tests: SignInOptionsSwitchesTests.swift, test_every_method_makes_its_own_device_to_spec.py, test_only_the_mac_app_decides_sign_in_options_to_spec.py, test_sign_in_methods_bind_nothing_new_to_spec.py (not yet written)
- Size: M

#### Step 1.2 — the request route, cap and expiry; the phone waits
- Behaviours: `signin.approve.tap-asks-the-mac`, `signin.approve.default-and-unlock`
- Tests: test_pair_request_is_capped_and_expires_to_spec.py, test_requests_route_follows_sharing_to_spec.py, ApproveOnMacWaitingTests.swift (not yet written)
- Size: M

#### Step 1.3 — the Allow sheet over the Unix socket; Allow enrols, Deny leaves nothing
- Behaviours: `signin.approve.mac-shows-allow`, `signin.approve.allow-enrols-the-device`
- Tests: test_approve_only_over_uds_to_spec.py, test_allow_registers_the_key_deny_leaves_nothing_to_spec.py, AllowDeviceSheetTests.swift (not yet written)
- Size: M

#### Step 1.4 — the iPhone lists Macs and the fallbacks in order; the Devices list names the method
- Behaviours: `signin.approve.ios-lists-macs`, `signin.password-comes-last`, `signin.qr-stays-the-fallback`, `signin.revoke-from-the-mac`, `signin.multiuser-off-still-works`
- Tests: HostChoicesTests.swift, SignInOptionsOrderTests.swift, AddDeviceSheetModelTests.swift, DevicesListMethodWordsTests.swift, test_revoke_names_the_method_to_spec.py, test_methods_under_multiuser_off_to_spec.py (not yet written)
- Depends on: 1.3
- Size: M

#### Step 1.5 — failed sign-ins: persisted back-off, the Mac's sheet, the exemptions
- Behaviours: `signin.failures.escalating-backoff-persists`, `signin.failures.mac-shows-who-is-being-tried`, `signin.failures.local-app-and-passkeys-are-exempt`
- Tests: test_failed_sign_ins_back_off_and_persist_to_spec.py, test_unlock_is_uds_only_to_spec.py, test_backoff_exempts_uds_and_passkeys_to_spec.py, FailedSignInsSheetTests.swift (not yet written)
- Depends on: 1.1
- Size: M

### Stage 2 — your own devices (after open question 1)

#### Step 2.1 — the engine mints, hashes, retires and rotates the enrollment secret
- Behaviours: `signin.own.off-ends-enrolment-not-devices`, `signin.own.secret-is-rate-limited-and-rotates`
- Tests: test_enrollment_secret_is_minted_hashed_and_revoked_to_spec.py, test_enrollment_off_retires_the_secret_to_spec.py, test_enrollment_secret_rotates_to_spec.py (not yet written)
- Depends on: 1.1
- Size: M

#### Step 2.2 — the Mac writes the Keychain item; the iPhone finds it and connects
- Behaviours: `signin.own.mac-writes-the-keychain-item`, `signin.own.ios-finds-it-and-connects`, `signin.own.setting-says-the-trade-off`
- Tests: OwnDevicesKeychainItemTests.swift, OwnDevicesConnectTests.swift, test_enroll_makes_one_device_per_redeem_to_spec.py (not yet written)
- Size: M

### Stage 3 — passkeys (after open question 2)

#### Step 3.1 — the engine as relying party
- Behaviours: `signin.passkey.rp-id-is-decided-first`, `signin.passkey.engine-is-the-relying-party`
- Tests: test_passkey_register_and_assert_to_spec.py (not yet written)
- Depends on: 1.1
- Size: M

#### Step 3.2 — the offer after a password sign-in; Face ID afterwards
- Behaviours: `signin.passkey.offered-after-first-password`, `signin.passkey.face-id-sign-in`
- Tests: PasskeyOfferTests.swift, PasskeySignInTests.swift (not yet written)
- Size: M
