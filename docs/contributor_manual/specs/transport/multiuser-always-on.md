# Multi-user always on: every connection is a signed-in person — Design Spec (→ #2403)

> Milestone: Sharing & Pairing — Dead-Simple UX; Engine - Sharing - Accounts, Multi-user & Libraries
> Manual: TBD — "Signing in on your other devices", "Letting Claude Code or the CLI use your library".
>
> Design-led (Testing Constitution). **Status: DRAFT rev 2, 2026-10-18 — revised after review 94 (slice order, UDS only, the launch secret, verified peer); awaiting review.**
>
> **Scope (owner, 2026-10-18):** on the same Mac, local clients (the app, the CLI, MCP) connect over the local socket file (UDS) ONLY, never loopback TCP. Loopback/TCP is for the network side (a paired device through Sharing) only. A Linux/Windows server, a web front end and a Mac client/server split are LATER: out of scope, not built here.
> Written from the owner ruling of 2026-10-18 (`agent-work/status/briefs/multiuser-always-on-2026-10-18.md`)
> and a read of the code on `m-sharing-p1`. It SUPERSEDES the 2026-10-18 #3331 ruling in `library-sharing.md`
> (access enforced only while Multi-user is on): there is no switch any more. Every [GAP] names its
> `(not yet written: …)` test. Companion: `library-sharing.md` (pairing, Sharing switch, transport),
> `transport-http-uds.md` (how the app dials its engine).

## Intent

Multi-user is not a mode, it is how the engine works. Every request, from the app on the same Mac, from a
paired device, from the CLI or from an MCP client, belongs to an **authenticated person** acting through a
named **client**. There is no ambient owner and loopback proves nothing. The owner never types a password:
their Mac holds a private key (synced to their other Apple devices by iCloud Keychain), the engine holds the
public half, and signing in is a challenge the app answers silently. Everyone and everything else gets the
same shape of credential: a public key registered once, a private key that never leaves its holder.

What the user observes: Settings › Sharing has ONE switch (Sharing). Opening the app on the Mac that holds
the library never prompts. Opening it on a second Mac, iPhone or iPad signed into the same iCloud account
never prompts either. Claude Code or the CLI can use the library only after the person has said yes once, in
the app, to that named client, and Activity says "Claude Code (MCP) for Daniel on MacBook Pro".

## The rulings this rests on (owner, 2026-10-18)

- Multi-user is always on and required; the Multi-user switch is removed (supersedes #3331 and the morning's
  routing; #2403 = yes). Stop any work that adds or keeps the toggle.
- No ambient owner; loopback is not the owner.
- The owner signs in passwordless with a Keychain key synced through iCloud Keychain; the engine holds only the
  public half; a password is the fallback for other people and for non-Apple clients.
- CLI and MCP are audited identities acting for a person, each with its own revocable credential, behind a
  Settings switch, approved once in the app.
- The owner's own Mac never prompts.

## Prior art (adopt, don't invent)

- **Passkeys / WebAuthn** (W3C): a per-account public-key credential, challenge-response, private key synced
  by iCloud Keychain. This is exactly the owner's model. Decision for review: the wire format is a plain
  challenge-response over a P-256 key (CryptoKit on Apple, `cryptography` in the engine), NOT full WebAuthn,
  because the engine is a localhost API and the clients are our own; the key type and "synced credential"
  semantics are the same, so moving to real passkeys (`ASAuthorization`) later changes the signer, not the engine.
- **SSH public keys** (`authorized_keys`, agent forwarding): the host stores public keys, one per client, each
  revocable, each logged. The CLI/MCP credentials follow this.
- **Xcode's "Allow external agents" / macOS TCC prompts**: a Settings switch plus a first-use approval naming
  the client; we reuse the idea, not the code.
- **Tailscale node approval / Signal linked devices**: a new device that lacks the key is approved from one
  that has it (QR or short code). This is the existing pairing flow, now approving a person's device.

## Model

- **Person** (`users` row): has one or more **credentials**: public keys (kind `synced` or `device`), and optionally a password
  hash (fallback). The **owner** is the person the library was created for.
- **Client** (new `clients` table): `id`, `person_id`, `kind` (`app` | `device` | `cli` | `mcp`), `name`
  ("Claude Code (MCP)", "fichero CLI", "Daniel's iPhone"), `host` (machine name), `public_key`, `approved_by`
  (person), `created_at`, `revoked_at`. The existing `devices` table becomes the `device` kind (its
  `paired_by_device_id`, `paired_route` carry over).
- **Session**: a short-lived token minted after a verified challenge. It carries `(person_id, client_id)`.
  Every `ActionContext`, audit row and Activity line shows both.
- **Challenge**: `POST /api/auth/challenge {client_id}` → random nonce, 60 s, single use. `POST /api/auth/sign-in
  {client_id, nonce, signature}` → session. Failure is 401 with a stable code; rate-limited like login today.

## Transports and the two secrets

- **UDS only for local clients.** The app, the CLI and MCP reach the engine through its Unix socket (mode 0600, in the
  app container). The engine reads the connecting process from the socket (pid, uid, executable path from the peer
  credentials). Loopback TCP serves only the network side (paired devices, who sign in with keys or passwords like
  anyone else); it carries no local-client routes and no bootstrap.
- **The launch secret** (replaces "the bootstrap token" on the sensitive routes): 32 random bytes made by the app at
  each launch, handed to the engine it spawns over an inherited pipe (never an environment variable, argv or a file),
  held only in the app's memory and the engine's memory. It authorises exactly three routes: first-run,
  migrate-owner and the reset challenge. The old bearer-token file the CLI/MCP read today is **refused** on those
  three routes, and a process that did not spawn the engine cannot obtain the secret. Dev Local: the Xcode pre-action
  (`fichero-server/scripts/dev-uds-engine.sh`) starts the engine on the container socket
  (`~/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock`), so the app did not spawn it. Once an owner exists
  the Dev Local app needs no launch secret at all: it signs in with the owner's Keychain key over the UDS like any
  local client. For FIRST RUN only (no owner yet) the script passes the secret to the engine on stdin and writes it
  0600 into the app container next to the socket; the app reads it once and deletes it. That file path is compiled out of
  Release, Beta and App Store builds, which only ever spawn their own engine. Tests start the engine in-process with a
  fixed test secret. One rule everywhere: the engine takes the secret on stdin at start-up; only Debug has a file.
- **Session lifetime:** app and device sessions last 12 h, sliding; CLI/MCP sessions last 1 h and renew by silent
  re-sign-in (a challenge costs nothing); a revoked client or person ends at once.
- **Keychain access group:** one shared group (team id + `app.fichero.shared`) holds the owner key for every bundle
  id (Dev, Alpha, Beta, App Store, iOS), so a person's key is the same whichever build opens the library.

## Behaviors

### A. The engine (no ambient owner)

- `multiuser.always-on` — **[GAP]** (→ #2403) there is no Multi-user setting. `sharing.set_multiuser`, `GET/PUT` of the flag, `FICHERO_MULTIUSER`, `multiuserEnabledKey` and `_use_multiuser_auth()` are removed; the engine always enforces. Test: (not yet written: `fichero-server/tests/unit/security/test_multiuser_always_on_to_spec.py::test_no_switch_and_enforcement_is_unconditional`).
- `multiuser.loopback-is-not-owner` — **[GAP]** (→ #2403) a request from 127.0.0.1 or the UDS with the bootstrap token and no signed-in client is refused 401 everywhere except the three first-run/sign-in routes. `_pairing_user`'s "loopback + bootstrap = owner" and `_require_owner_or_bootstrap` go. Test: (not yet written: `…/test_multiuser_always_on_to_spec.py::test_loopback_bootstrap_alone_reaches_nothing`).
- `multiuser.sign-in-by-challenge` — **[GAP]** (→ #2403) the challenge-response above; the nonce is single use and expires; a signature over another client's nonce, a replayed nonce and a revoked client all fail. Test: (not yet written: `…/test_challenge_sign_in_to_spec.py`).
- `multiuser.password-fallback` — **[PARTIAL]** (→ #2403) (login exists: `POST /api/auth/login`, rate-limited) stays for other people and non-Apple clients; a password session is a client of kind `device` named by the caller. The owner can switch their own password fallback off. Test: (existing `test_auth_accounts.py`; add `test_password_session_names_a_client`, not yet written).
- `multiuser.audit-names-person-and-client` — **[PARTIAL]** (→ #5319; `ChangeEvent.person/device`, `BackgroundJob.started_by` built) every audit row, change event, background job and Activity line carries person AND client; a CLI call shows "fichero CLI for Ann". Test: (extend `test_sharing_who_did_it.py`; client column not yet written).

### B. First launch and the owner's own Mac

- `multiuser.first-launch-creates-owner-and-key` — **[GAP]** (→ #2403) on first launch the app creates the owner person (name from the macOS full name, editable later) and a P-256 key in the Keychain (synchronizable, `AfterFirstUnlock`, no user-presence prompt), then registers the public key through `POST /api/auth/first-run`. That route works ONLY while the library has no owner, only over the UDS, and only with the launch secret (above), never the old token file; once an owner exists it returns 409 forever. No dialog is shown. Test: (not yet written: `…/test_first_run_owner_to_spec.py::test_first_run_works_once_then_409`; Swift `OwnerKeyBootstrapTests`).
- `multiuser.owner-mac-never-prompts` — **[GAP]** (→ #2403) the app signs in as the owner with the Keychain key on every launch and every engine restart; no password sheet, no Touch ID, no "allow" dialog. Test: (not yet written: Swift `OwnerSignInTests::testSignInNeedsNoPrompt` against a fake signer; the real Keychain is the M4 checklist).
- `multiuser.embedded-and-dev-engines` — **[GAP]** (→ #2403) the embedded engine, the Dev Local engine and tests all use the same sign-in; tests get a helper that mints a test person + client (`tests/conftest.py::signed_in_client`), so no test relies on ambient owner. Test: (not yet written: the new guard `check_no_ambient_owner_in_tests`).

### C. Same person, more devices

- `multiuser.second-device-by-synced-key` — **[GAP]** (→ #2403) a Mac, iPhone or iPad signed into the same iCloud account already has the person's key (iCloud Keychain). Pointing it at the library signs in by challenge with no password and no pairing code; the engine registers it as a new `device` client named by the device on first success (the key is already trusted, the client row is new). Test: (not yet written: `…/test_synced_key_registers_device_client_to_spec.py`).
- `multiuser.device-without-the-key-is-approved` — **[PARTIAL]** (→ #2403) (pairing codes and QR exist, S8 person picker) a device without the synced key shows "Ask a signed-in device": the engine creates an approval request, a signed-in device of that person approves it by QR or 6-digit code, and the new device gets its own key registered. Test: (existing pairing tests; `test_approval_request_needs_a_signed_in_device`, not yet written).
- `multiuser.password-comes-last` — **[GAP]** (→ #2403) the sign-in screen offers, in this order: silent key, approval from another device, password. Test: (not yet written: Swift `SignInOptionsOrderTests`).

### D. A library shared by another person

- `multiuser.invite-registers-public-key` — **[GAP]** (→ #2403) Daniel invites Ann (existing invite). Ann accepts once; her app sends her PERSON public key, which Daniel's engine stores on a new person row for Ann, scoped by the invite's grant. No password is ever set unless Ann asks for the fallback. Test: (not yet written: `…/test_invite_registers_public_key_to_spec.py`).
- `multiuser.every-device-of-theirs-opens-it` — **[GAP]** (→ #2403) Ann's other devices answer the same challenge with the same synced key, so they open Daniel's library with no password; Daniel's engine sees one person (Ann) and several clients. Test: (not yet written: `…/test_second_device_of_invited_person_to_spec.py`).
- `multiuser.revoke-a-person-or-a-client` — **[PARTIAL]** (revoke cascade built: #5351) revoking Ann ends every session and client of hers; revoking one client ends only that one. Test: (extend `test_revoke_cascades_to_spec.py`).

### E. Local MCP and CLI

- `multiuser.local-client-switches` — **[GAP]** (→ #2403) Settings › Sharing gains two switches under "This Mac": *Allow local MCP clients* and *Allow the fichero CLI* (default off). While a switch is off the engine answers a client request of that kind with 403 "not allowed on this Mac". Test: (not yet written: `…/test_local_client_switch_to_spec.py::test_off_means_refused`; Swift `LocalClientSwitchesTests`).
- `multiuser.first-connection-asks-the-person` — **[GAP]** (→ #2403) a client with the switch on calls `POST /api/clients/request {kind, name, host}` over the UDS and ONLY the UDS (the route does not exist on the TCP listener: loopback gives no peer credentials). The engine reads the peer from the socket, refuses a different macOS user, records the request together with what it VERIFIED about the peer (pid, executable path, and the signing identity when the binary is signed) and returns a request id. The app's sheet shows the verified path and signer first and the self-asserted name second, flagging an unsigned binary or a bare interpreter: "python3 (/usr/bin/python3, not signed by Fichero) says it is Claude Code (MCP), for Daniel. Allow / Deny". Nothing else works until Allow. Test: (not yet written: `…/test_client_request_needs_approval_to_spec.py` with `test_tcp_listener_has_no_client_routes`, `test_request_records_verified_peer_not_claimed_name`, `test_other_macos_user_refused`; Swift `ClientApprovalSheetTests`, verified path leads and interpreters are flagged).
- `multiuser.client-gets-its-own-credential` — **[GAP]** (→ #2403) on Allow, the client generates its OWN P-256 key, stores the private half in the login Keychain (item ACL bound to the client binary), and registers the public half against the pending request. No secret crosses the wire. It then signs in by challenge as that client. **Stated limit:** a Keychain ACL binds to the binary, so for a client that runs under an interpreter (`python3`, `node`) any script that interpreter runs can read the credential. The approval is therefore of "this binary on this Mac", shown that way; the credential is per client, revocable, capped to the person's rights (optionally read-only), and the CLI and the MCP server ship as signed single binaries so their ACL binds to Fichero's own signature. Settings lists the client with Revoke; revoking deletes the registration and ends its sessions. Test: (not yet written: `…/test_client_registers_own_public_key_to_spec.py`; a CLI-side `test_signs_in_as_client`; an MCP-side `test_signs_in_as_client`).
- `multiuser.client-acts-for-a-person` — **[GAP]** (→ #2403) a client's session carries `(person, client)`; it can do what that person can, never more, and never act as another person. The owner can restrict a client to read-only (optional, slice 6). Test: (not yet written: `…/test_client_cannot_exceed_its_person_to_spec.py`).
- `multiuser.cli-mcp-sign-in-flow` — **[GAP]** (→ #2403) the CLI and MCP server, when they find no credential, print/return a single sentence: "Ask the app to allow this client (Settings › Sharing › This Mac)", start the request, and wait up to 60 s for the answer. They never fall back to the bootstrap token. Test: (not yet written: a CLI-side `test_no_credential_asks_the_app`).

### F. iOS

- `multiuser.ios-signs-in-with-the-synced-key` — **[GAP]** (→ #2403) the iPhone/iPad app reads the same synchronizable Keychain key (shared access group where needed), signs in by challenge to a library it has already paired, and shows "Sign in with another device" only when the key has not synced yet (iCloud Keychain off, or the first minutes after enabling). Test: (not yet written: Swift `iOSSignInTests` with a fake signer).
- `multiuser.ios-no-local-engine-no-bootstrap` — **[OK]** iOS has no local engine, so there is no bootstrap, no first-run and no local-client approval; it is always a remote device client. Test: n/a (documented here so nobody adds one).

### G. Migration of existing libraries and device tokens

- `multiuser.migrate-owner` — **[GAP]** (→ #2403) a library that predates this change has an owner row (or none, in single-user libraries). On first start of the new engine: if no owner exists, the app's first-run creates one (B); if one exists with no key, the app registers a key for them through a one-time local migration route that works only for the owner row, only once, only over the UDS, only with the launch secret (the old token file the CLI/MCP read is refused there), and only until a key exists. Test: (not yet written: `…/test_migrate_existing_owner_to_spec.py`).
- `multiuser.migrate-device-tokens` — **[GAP]** (→ #2403) every non-revoked `devices` row becomes a `device` client of its `user_id` (or the owner if NULL) and its token keeps working as that client's credential for one release, with a banner on the device ("sign in again to keep this device"); the next successful key or password sign-in revokes the old token. Tokens of revoked devices stay revoked. Test: (not yet written: `…/test_migrate_device_tokens_to_spec.py::test_old_token_works_once_then_is_replaced`).
- `multiuser.migrate-the-flag` — **[GAP]** (→ #2403) the stored multi-user flag and its UserDefaults key are read once to decide nothing and then deleted; libraries that had it OFF now enforce too (this is the point of the ruling). The CLI/MCP clients that used the bootstrap token are told, once, to ask the app. Test: (not yet written: `…/test_old_flag_is_ignored_to_spec.py`).
- `multiuser.library-copy-keeps-people` — **[GAP]** (→ #2403) copying or opening a library on another Mac never carries keys or sessions; people and their public keys travel, credentials do not. Test: (not yet written: `…/test_library_move_carries_no_credentials.py`).

### H. Lost keys and recovery

- `multiuser.lost-one-device` — **[PARTIAL]** (→ #2403) revoke the device in Settings from any signed-in device (existing). Nothing else to do. Test: (existing revoke tests).
- `multiuser.lost-all-synced-key` — **[GAP]** (→ #2403) Settings › Sharing offers (never at launch, never forced) a **recovery code**: 24 words that derive a second owner key, shown once, to be printed or saved. Typing it on a new Mac registers a fresh key and revokes the old. Test: (not yet written: `…/test_recovery_code_registers_new_owner_key_to_spec.py`).
- `multiuser.lost-everything-on-the-host` — **[GAP]** (→ #2403) on the Mac that hosts the library, the owner can reset their own key with macOS authentication. The ENGINE does not trust the app's word: at first launch the app also creates a **reset key** in the Secure Enclave with a user-presence access control (Touch ID or the Mac's password) and registers its public half; a reset is a challenge from the engine that only that key can sign, and signing makes macOS ask for Touch ID or the password. The engine verifies the signature, the launch secret and the UDS peer, so a process without the user's presence cannot produce a reset. Old keys and sessions are revoked. Test: (not yet written: Swift `OwnerResetNeedsMacAuthTests`; `…/test_owner_reset_revokes_old_keys_to_spec.py`).
- `multiuser.other-person-lost-key` — **[GAP]** (→ #2403) the owner revokes that person's key and re-invites them; no admin password reset exists. Test: (covered by revoke + invite tests above).

## The trade-off: iCloud Keychain key vs Secure Enclave key

| | Synced Keychain key (the ruling) | Secure Enclave key (per device) |
|---|---|---|
| Second device | Already there; no step | Each device makes its own key; needs approval from a signed-in device (C) |
| Extractability | Private key lives in iCloud Keychain, end-to-end encrypted by Apple, but is copied between devices; compromise of the iCloud account or any one device exposes it | Non-exportable; a stolen disk or backup yields nothing |
| Loss of a device | Revoke the device; the key itself stays valid, so rotate it if the device was compromised | Revoke exactly that device's key; no rotation |
| Non-Apple clients | Cannot use it; password fallback | Same |
| Setup effort | None | Approval ping per device; breaks "dead simple" |
| Prompts | None | None unless user-presence is required |

**Recommendation (for the owner to confirm):** ship the synced key as the default for ordinary scholars — it is
the only option that satisfies "second device is easy" with no step. Offer **Secure Enclave per-device keys as
an opt-in "Strict" setting** (slice 9): turning it on generates Enclave keys, registers them, and revokes the
synced key. Local CLI/MCP clients use plain Keychain keys (never synced; they belong to one Mac). Open question
for review: should Strict be offered at all in the first release? (Cheap to defer; the engine already handles
both kinds because `credentials.kind` is `synced | device`.)

## What this retires in library-sharing.md

- the behaviors named multiuser-mode-single-source, acl-status-when-multiuser-off and private-by-default
  (a single-user paired device is no longer a thing), the "Multi-user" half of `sharing.two-toggles-wording`
  (one switch left: Sharing), `sharing.switch-from-cli`'s `set_multiuser` half, and the pending `owner_only`
  declaration for `sharing.set_multiuser`. `sharing.device-chooses-person` and the S8 person picker stay and now
  authenticate with a key or a password.
- The #3331 ruling of 2026-10-18 is superseded; its test (`test_acl_status_multiuser_off_to_spec.py`) is deleted
  in slice 10, not left to rot.

## Implementation plan in slices

Order: this spec → SPEC READY → review → red tests → code, **one slice at a time, each slice reviewed for security**.
Rule of the order (review 94): add every way to sign in FIRST, remove the ambient owner LAST, so the app, Dev Local,
the CLI and the MCP operator keep working after every slice.

1. **Slice 1: tables + challenge**: `clients` + `credentials` tables, the challenge and sign-in routes, sessions carry `(person, client)`. Additive; nothing removed. Contract regen.
2. **Slice 2: audit columns**: person AND client on audit rows, change events, background jobs, Activity.
3. **Slice 3: test-fixture migration**: the `signed_in_client` helper; every existing test moves to it and the new guard `check_no_ambient_owner_in_tests` lands in warn mode.
4. **Slice 4: App sign-in**: first-run route (UDS + launch secret), the Keychain owner key, silent sign-in, the launch-secret pipe in the embedded, Dev Local and test engines.
5. **Slice 5: Migration**: owner key via migrate-owner, device tokens → clients, flag retirement, banner. Reviewed against a copy of Daniel's real library, never the live one.
6. **Slice 6: CLI and MCP sign-in**: the two switches, UDS-only client request, verified-peer approval sheet, client-owned keys, the no-credential flow, signed single-binary CLI/MCP.
7. **Slice 7: More devices + iOS**: synced-key registration, approval request/QR, sign-in options order.
8. **Slice 8: Other people**: invite registers a public key, revoke person/client, password fallback naming clients.
9. **Slice 9: Recovery + Strict**: recovery code, host reset by the Secure Enclave reset key, optional Strict mode (deferrable).
10. **Slice 10: No ambient owner (LAST engine slice)**: remove the Multi-user switch and `sharing.set_multiuser`, loopback/bootstrap = owner, `_require_owner_or_bootstrap`, the old bearer file on owner routes; the guard turns blocking. Only now can anything stop working, and everything has a replacement.
11. **Slice 11: Docs + manual + M4 checklist**: user-manual sections; M4 steps for two Macs + iPhone + Claude Code approve/revoke, including the macOS "access data from other apps" prompt the CLI/MCP may hit reaching a socket inside the app's container (answer it once; the checklist says so); closes the tester items.

Risks to review first: (1) first-run, migrate-owner and reset are the only privileged writes: each once-only,
UDS-only, launch-secret-gated, replay-tested; (2) local-client routes exist only on the UDS listener, with a test
that the TCP listener's route table lacks them; (3) the synced key means an iCloud compromise equals an owner
compromise, which Strict mitigates; (4) every route in `security/authz_kinds.py` keeps its declaration and no route
may use `bootstrap == owner` after slice 10.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | sign-in option order, approval sheet text, switches | `fichero/Tests/Unit/general/Sharing/` (`OwnerKeyBootstrapTests`, `OwnerSignInTests`, `ClientApprovalSheetTests`, `LocalClientSwitchesTests`, `SignInOptionsOrderTests`) |
| Availability (Swift) | y | iOS sign-in, Settings switches reachable | `iOSSignInTests` |
| Backend (pytest) | y | challenge, first-run once, no ambient owner, migration, client approval, revoke, recovery | `fichero-server/tests/unit/security/`, `…/transport/` (names above) |
| MCP | y | signs in as a client; no credential asks the app | an MCP-side `test_signs_in_as_client` |
| CLI | y | same | a CLI-side `test_signs_in_as_client`, `test_no_credential_asks_the_app.py` |
| Guard | y | no test relies on ambient owner; no route uses bootstrap as owner | a new guard, `check_no_ambient_owner_in_tests` (not yet written) |
| Real Mac/iPhone | y | Keychain sync, Touch ID reset, approval round trip | M4 checklist (slice 11) |
