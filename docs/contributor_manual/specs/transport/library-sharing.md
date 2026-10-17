# Library Sharing between Macs — Design Spec (→ #5049)

> Milestone: Sharing & Pairing — Dead-Simple UX; Engine - Sharing - Accounts, Multi-user & Libraries
> Manual: TBD — "Working on one library from two Macs".
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-01** (stays DRAFT: most of the acceptance story is [GAP], and the new `*_to_spec.py` tests do not exist yet). Written from the rulings in
> memory (two toggles; accounts are people; loopback + `tailscale serve`; device pairing; loopback is
> owner; transport invariants) and a read of the code on integration at 5293d084f. Tags: **[OK]**
> built and seen working · **[PARTIAL]** built, unproven or incomplete · **[GAP]** not built.
> "Read, not run" marks what is known only from the code: each becomes OK, or BROKEN with its own
> issue, on the two-machine test (the Air and the MBP) that follows this draft (#5049). Companion:
> `transport-http-uds.md` (how the app dials its engine).

## Intent

A scholar with two Macs works on one library from both. One Mac holds the library and runs its
engine; the other opens that library over the network and edits it, and each sees the other's
edits as they land. Turning it on is two switches and one pairing step, never a configuration
screen. Off the local network it works through Tailscale without exposing anything to the
internet. A second PERSON is a separate question (multi-user), answered by accounts, not devices.

## The rulings this rests on

- **Two toggles, independent** (ratified): *Sharing* (is the engine reachable from another device)
  and *Multi-user* (are there accounts for other people). Nothing else in Settings.
- **Accounts are for people, not devices.** Local use logs in as owner; a remote device always
  authenticates. Roles: owner, editor, viewer. Libraries are private by default and shared
  explicitly.
- **Transport:** HTTPS always, with a self-signed certificate pinned by its public key (SPKI) on
  the client. The host reaches its own engine on loopback. Off-network reach is `tailscale serve`
  (never `funnel`); Tailscale is connectivity, not identity.
- **Loopback with the bootstrap token is always owner.**
- **Pairing:** the host shows a QR / one-time code; the device sends it to `POST /api/pair` over the
  pinned connection and receives its own token, revocable per device.
- **2026-10-04 (#5351): revoking cascades.** Revoking a paired device also revokes the devices it
  paired; the revoke sheet lists them first (`sharing.revoke-cascades`).
- **2026-10-04 (#5319): an audit row names person and device.** With Multi-user off both are the
  owner, told apart by device; the host's own edit is never `system` (`sharing.who-did-it`).

## Behaviours

### A. Turning sharing on (the host)

- `sharing.toggle-restarts-engine` — **[PARTIAL]** (→ #5049) Settings › Sharing's switch saves the choice,
  turns Bonjour on, fills a `https://<host>.local:8765` address, restarts the bundled engine with an
  HTTPS listener, and lists paired devices (`ShareSettingsView+StateManagement.swift`). Never seen
  on two machines (#5049).
- `sharing.listener` — **[PARTIAL]** (→ #5736) the Mac's own app always dials its engine over the Unix socket. Sharing off: loopback only, no network listener. The one extra `.local` listener (`FICHERO_LAN_HOST`, `__main__.py`) exists ONLY while Sharing is on AND "This network" is checked (`sharing.share-on-choice`), bound to the host's `.local` address, never `0.0.0.0` (`remote_access_tls._bind_host_for_public_host`), TLS and a pairing token required. Built: the listener; not built: it follows the checkbox (today it follows the `.local` address alone).
- `sharing.share-on-choice` — **[GAP]** (→ #5736) Sharing has one sub-choice, "Share on:", with two checkboxes: "This network (Bonjour, .local)" and "Tailscale (.ts.net)". Defaults: Tailscale checked when Tailscale is up; This network unchecked (safe at work, one tap at home). At work nothing is advertised on Bonjour; at home phones and iPads reach the Mac on the local network. Test: `fichero-server/tests/unit/security/test_share_on_listeners_to_spec.py`, `fichero/Tests/Unit/general/Sharing/ShareOnChoiceTests.swift`.
- `sharing.certificate-pinned` — **[PARTIAL]** (→ #5049) a self-signed certificate is made once
  (`--prepare-remote-access`), names the host, 127.0.0.1 and localhost, and the app records its pin
  per host. Fixed by #5041, unproven across machines (#5049).
- `sharing.bonjour-advertises` — **[OK]** (→ #5316; pinned by `fichero-server/tests/unit/security/test_discovery.py::test_sharing_advertises_the_lan_listener_never_loopback`) the engine advertises `_fichero._tcp` with the
  public URL in its record and no pin (presence, not trust). The record's address is the one the
  LAN listener binds, under the `.local` name the invite uses; with no LAN listener (loopback only,
  e.g. Tailscale) it carries no address. Run 2026-10-01 on the MBP: it advertised 127.0.0.1 under
  `UNB-C02F45GAQ05P.local` before `edd6c4938`, and `131.202.228.23` under `macbook-pro-m1.local` after.
  Where mDNS does not cross between machines (the campus network) nobody sees it: that is the network.
- `sharing.tailscale-serve` — **[PARTIAL]** (→ #2603, #5311, #5320; pinned by `tests/unit/security/test_tailscale_serve.py`, `tests/unit/security/test_remote_access_tls.py::test_a_tailscale_address_binds_loopback_and_its_certificate_names_it`)
  with a `.ts.net` sharing address the engine binds loopback only and makes `tailscale serve --https=<port> https+insecure://127.0.0.1:<port>` at start and removes it at stop (only the forward it made; a port serving something else is refused). Tailscale terminates TLS with its own public certificate, so the client trusts the **system** certificate for `.ts.net` (Tailscale identity plus the pairing token protect it) and keeps the **SPKI pin** only for `.local` hosts (ruled 2026-10-17). Proxied requests carry Tailscale headers and are never loopback (`api/auth.py`). Pairing codes carry the address as `tailnet_url`. **Still open:** an app pairing over the tailnet (#5320, needs the M4); the sandboxed app cannot run the Tailscale CLI, so it shows one command to paste with a copy button (#5317); the address is offered in the share sheet, not typed (#5318).
- `sharing.invite` — **[PARTIAL]** (→ #5049) the pairing card's QR / link carries the address, a one-time
  code, the pin and ONE library path (the host's current library).

### B. Connecting from the second Mac

- `sharing.mac-finds-host` — **[GAP]** (→ #5734) a Mac cannot browse for hosts (Bonjour browsing is iOS
  only) and has no camera flow; the section says "Scan the QR code" but the only way in is pasting
  the link (`MacRemoteClientPairingSection.swift`).
- `sharing.mac-pairs` — **[PARTIAL]** (→ #5049, read, not run) pairing sends the code to `POST /api/pair` with the pin
  enforced, checks health, and stores the token in the Keychain with its expiry, the pin, the host
  and the library path (`RemoteClientPairingFlow.swift`). Never run between two Macs (#5049).
- `sharing.library-confirmed` — **[OK]** (#3273; pinned by `fichero/Tests/Unit/general/Transport/RemoteClientPairingLibraryConfirmTests.swift`, `RemoteClientPairingFlow.confirmLibraryAccess`) before opening, the Mac asks the host whether it may open the invite's library. Swift tests run only on the M4 (#4511); issue stays open with needs-your-test.
- `sharing.opens-the-library` — **[PARTIAL]** (→ #5049, read, not run) the second Mac switches its active host to the
  first, adopts the invite's library and lists the host's libraries from `/api/authz/libraries`;
  the library path header names the path ON THE HOST. One host at a time for the whole app (#2573).
- `sharing.pairing-over-uds` — **[PARTIAL]** (#4224) pairing now dials with the app's resolved transport (`PairingTypes.swift`, fixed in 734d16f56, read, not run); unproven in a Release build whose engine is on the socket, where the issue says sharing never worked. Test: `fichero/Tests/Unit/**/PairingTransportTests.swift` and the checklist step 1.

### C. Working on it from both

- `sharing.edits-both-ways` — **[PARTIAL]** (→ #5049) an edit on either Mac lands in the one library and
  appears on the other through the change stream (`/api/changes`, read-authorised per library).
  Run 2026-10-01 engine to engine (CLI, over Tailscale): notes written on each Mac read on the other;
  the stream lost an event when the host's loop stalled past its keepalive, fixed in #5314
  (`test_an_event_queued_while_the_loop_stalls_past_the_keepalive_is_still_sent`). The app's
  windows were not run.
- `sharing.who-did-it` — **[OK]** (→ #5319; pinned by `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_pin_who_did_it_*` and `fichero-server/tests/integration/test_sharing_who_did_it.py::test_the_host_and_a_paired_mac_are_told_apart_in_the_audit`) each edit's audit row names both the person AND the device that made it. With Multi-user off both people are the owner, each row naming its device; the host's own edit is never `system` (ruled 2026-10-04). Fixed in 6b6115612 (engine, in-process). Not yet seen across two real Macs: #5319 stays open with needs-your-test until the checklist passes.
- `sharing.revoke` — **[PARTIAL]** (→ #5049) the host lists paired devices and can revoke one; a revoked
  token is refused (pinned in `test_device_pairing_e2e.py`, in-process; run 2026-10-01 across two
  Macs: the paired MBP's next call was 401). The app's device list was not run.
- `sharing.revoke-cascades` — **[GAP]** (#5351) revoking a paired device also revokes every device
  it paired (and theirs, down the chain); the revoke sheet lists those devices first, before the
  person confirms. (Ruled 2026-10-04.) Needs `paired_by_device_id` on pairing codes and on `devices` (an idempotent ALTER migration; ruled 2026-10-17) and a walk in `AppDatabase.revoke_device`. Most useful with Multi-user on, where a paired person can mint codes. Test: `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py` (cascade case).

### D. Other people (Multi-user on)

- `sharing.multiuser-pairing` — **[PARTIAL]** (→ #5049, read, not run) with Multi-user on, creating a pairing code needs a
  signed-in person, or the host app itself: the app's bootstrap token on loopback acts as the one
  active owner for minting a code, listing devices and revoking one (#5346, 2026-10-01; before, the
  card could be refused and the host could not list or revoke). A code minted that way pairs a device
  for the owner; choosing another person is `sharing.device-chooses-person`. Pinned by
  `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_multiuser_on_the_host_app_can_list_and_revoke_a_device`.
- `sharing.private-by-default` — **[PARTIAL]** (→ #2403) only with Multi-user on: a single-user paired device
  sees every library as owner.
- `sharing.device-chooses-person` — **[GAP]** (#2403) a remote device must choose and authenticate a
  person; there is no ambient owner.

## Acceptance: two Macs, two people, end to end (ruled 2026-10-17)

- `sharing.two-macs-end-to-end` — **[GAP]** (→ #5049) The maintainer ruled that sharing a library between Macs must work in the next
  release and Multi-user is on. In plain words: on Mac A the owner turns **Sharing** on (Settings › Sharing) and the pairing card
  appears. Mac B, on the same network or the tailnet, finds A (or is given the link) and pairs with the one-time code over
  Bonjour and pinned TLS, then opens A's library. A has an owner account; a second person has an account and signs in on B; each
  edit in the shared library shows its author's own name and device, on either Mac. A read run started on B shows in A's Activity
  while it runs and when it ends. B's edits land on A within seconds, and A's Command-Z (one stack per window) still takes back only
  A's steps. When A turns Sharing off, B says "A stopped sharing this library", closes the shared windows and returns to its own
  projects, with no error screens. Nothing here asks the user for a port, certificate or token. Drilled by the tester with
  `docs/contributor_manual/testing/sharing-two-mac-checklist.md`; its parts are the behaviours below. Test: `fichero-server/tests/unit/transport/test_two_macs_end_to_end_to_spec.py` (in-process: two clients, two accounts, one engine); the real run is the checklist on the M4.
- `sharing.two-toggles-wording` — **[GAP]** (→ #5049) Settings › Sharing has exactly two switches. *Sharing*: "Share Fichero on this Mac with other devices, the fichero command-line tool, and MCP clients." *Multi-user*: "Give other people their own accounts on this Mac's libraries." Nothing else is asked. Today the Sharing switch reads On/Off with that caption; the Multi-user switch lives in Engine settings (`EngineSettingsView.swift`) and must MOVE, not be duplicated, to sit beside Sharing in Settings › Sharing (ruled 2026-10-17; #3284). Test to be written: `fichero/Tests/Unit/general/Sharing/SharingTogglesTests.swift` (the two labels and captions, and that no third switch exists).
- `sharing.names-on-edits` — **[GAP]** (→ #5735) with two accounts, an edit made by the second person on B is recorded as that person on device B, and the owner's on A as the owner on A (needs `sharing.device-chooses-person`, `sharing.who-did-it`). Test: `fichero-server/tests/unit/transport/test_two_accounts_names_on_edits_to_spec.py`.
- `sharing.remote-run-in-host-activity` — **[GAP]** (→ #5732) a read run started from B is a row in A's Activity (`/api/activity/stream`), started by B's person, on device B, live to its end. Test: `fichero-server/tests/unit/transport/test_remote_run_in_activity_to_spec.py`.
- `sharing.undo-after-remote-edit` — **[GAP]** (→ #5733) A's undo reverses only A's own steps; if B changed the same thing since, it is refused in a sentence naming who and when (`undo-everywhere.md`, #5658). Test: `fichero-server/tests/unit/transport/test_undo_after_remote_edit_to_spec.py`.
- `sharing.off-closes-the-guest` — **[GAP]** (→ #5731) turning Sharing off on A ends B's change stream with a typed "sharing stopped" event before the listener closes; B shows one sentence, closes the shared windows and returns to its own projects; no reconnect loop. Test: `fichero-server/tests/unit/transport/test_sharing_off_to_spec.py` (engine); the window behaviour on the checklist.
- `sharing.stale-edit-both-ways` — **[PARTIAL]** (→ #5348) engine half built; the app must send the version (see `sharing.stale-note-edit-is-refused-and-offered-a-choice`): B's edit on a note A changed is refused 409, never silently lost. Engine pinned by `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_two_macs_editing_one_note_the_second_stale_edit_is_refused` (no xfail remains); the Swift editor half needs its own test, to be written with #5348.

## The two-machine test (next)

On the Air (host) and the MBP (client), apps launched by path, one xcodebuild at a time on each:
1. Air: Sharing on; read the advertised address, the listeners (`lsof -iTCP -sTCP:LISTEN`), the
   Bonjour record (`dns-sd -B _fichero._tcp`, `dns-sd -L`).
2. MBP: paste the invite link; pair; open the shared library.
3. Edit on the MBP (rename, a reading); see it on the Air. Edit on the Air; see it on the MBP.
4. Revoke the MBP on the Air; the MBP is refused.
5. The same over Tailscale (`tailscale serve`), by hand, to learn what automating it needs.
Each failure: an issue, fixed one at a time, its behaviour above re-tagged.

## Triaged from the backlog (2026-10-04)
- `sharing.accounts-and-users-settings` — **[GAP]** (#2083) Settings has an Accounts & Users screen to log in, add/remove users and assign owner/editor/viewer.
- `sharing.ios-device-token-hygiene` — **[GAP]** (#3290) an iOS device build never resolves the bootstrap token, renews its device token on foreground, and shows a re-pair prompt on expiry or revocation; outbox blobs are file-protected.
- `sharing.owner-shared-libraries-view` — **[GAP]** (#2054) Settings shows the owner every library, which are shared with whom and in what role, and whether each is open.
- `sharing.multiuser-mode-single-source` — **[GAP]** (#3284) the Multi-user toggle persists to the engine and the app, spawn env and engine agree, so a hosted engine never runs with authz off while accounts exist.
- `sharing.acl-status-when-multiuser-off` — **[GAP]** (#3335) with Multi-user off the Library ACL row reads "not enforcing per-library access" instead of a red Server error (ShareSettingsView+Security.swift shows authzError in red).
- `sharing.ios-discovers-host` — **[GAP]** (#3371) an iOS/iPad client browses Bonjour, lists verified reachable Mac engine candidates and shows stale ones as failed, without persisting trust.
- `sharing.stale-note-edit-is-refused-and-offered-a-choice` — **[GAP]** (#5348) a note or document edit made against an old version is refused 409 and the app offers keep-mine, take-theirs or compare (the notes PATCH check landed in 9339a2e7d; the Swift editor and PUT /api/documents/{id} remain).
- `sharing.ios.unpaired-phone-opens-on-connect` **[BROKEN]** (#5396): an iPhone that has never paired opens on a welcome screen with Connect to a Mac (Bonjour list, QR or address), then the project list, never an empty 'Nothing Selected' view or a server-down error. Its screens are laid out for a phone: one navigation bar, a sidebar that survives landscape, no offline chat pane and no internal α/β/δ markers.

## Future (ideas, not scheduled)
- (#2029) Multi-writer concurrency and presence: design pass explicitly last, after users and attribution land.
- (#3706) Cross-library/window/app drag and drop; design-blocked on atomicity per the issue's own comment
- (#3375) Optional mTLS, UDS and iCloud identity sync for pairing; design-only, after the MVP is stable
- (#2096) Native iOS/iPad client for a Mac-hosted engine; pairing slices are specced as sharing.* behaviours, the client epic itself is vision
- (#2899) fichero-web keystone (browser access under a per-user token, writes via the audited registry); no web client exists and auth has no web-login route; Future section of library-sharing
- (#3123) fichero-web HttpOnly cookie session /api/auth/web-login + CSRF guard; not in the server (grep finds no web-login), prerequisite for an unscheduled web reader; Future of library-sharing
- (#4219) Retire LibraryReference.deinit's scope stop so the nonisolated hole closes (deinit still present at LibraryManager.swift:481); a cleanup follow-up to the #4216 lock, Future
- (#2162) iOS connection stack (NWBrowser discovery, QR scan, Keychain token, SPKI-pinned URLSession, optional mTLS/UDS); later with the iPhone/iPad app.
- (#3778) iOS-initiated pairing (tap discovered Mac, Mac shows number, enter it); blocked on the SPKI pinning question.
