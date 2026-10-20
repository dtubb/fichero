# Library Sharing between Macs — Design Spec (→ #5049)

> Milestone: Sharing & Pairing — Dead-Simple UX; Engine - Sharing - Accounts, Multi-user & Libraries
> Manual: TBD — "Working on one library from two Macs".
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-17** (every [GAP] names its `(not yet written: …)` test, so `check_specs_have_tests` guards it; APPROVED waits for the manual section, because `Manual: TBD` blocks it). Written from the rulings in
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
- **2026-10-17:** shared editing (a deletion on one Mac is a deletion on the other); no open lookup of libraries; Multi-user sits beside Sharing; `.ts.net` is system trust, `.local` is the SPKI pin; the owner account owns every library.
- **2026-10-18 (later, SUPERSEDES the next line): multi-user is always on, no switch, no ambient owner** — see `multiuser-always-on.md`.
- **2026-10-18 (#3331), SUPERSEDED the same day:** this entry said access is enforced only while Multi-user is on. The owner then ruled multi-user always on, with no switch (`multiuser-always-on.md`). What follows about the switch describes TODAY's code only, until slice 10 of that plan removes it; nothing new is built on it.
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
- `sharing.listener` — **[PARTIAL]** (→ #5897; owner ruling 2026-10-20: Sharing on listens on this network, by itself) the Mac's own app always dials its engine over the Unix socket. Sharing off: loopback only, no network listener. Sharing on: the engine listens on this network, with no separate "This network" switch: when the app names the host's `.local` address (`FICHERO_LAN_HOST`, set only while Sharing is on at one) the engine binds it beside the loopback port, TLS and a pairing token required, never `0.0.0.0` (`remote_access_tls._bind_host_for_public_host`), whatever devices are paired. Tailscale reaches the engine through `tailscale serve` to the loopback port (`.ts.net` is publicly trusted, no pin), so it needs no further listener; when Tailscale is up the sharing sheet offers its address. Built: `__main__._listener_hosts` binds the LAN address whenever it is named, the old gate (`FICHERO_THIS_NETWORK`, `_this_network_on`, `has_lan_paired_device`) is deleted; pinned by `fichero-server/tests/unit/transport/test_share_on_listeners_to_spec.py` (unrun). Not built (Swift, HELD): the app stops passing `FICHERO_THIS_NETWORK`, and the unused key, `thisNetworkChoice` and the 'off' note go (`ShareOnChoiceTests`).
- `sharing.link-names-a-listener` — **[PARTIAL]** (owner ruling 2026-10-20, `briefs/pairing-proper-2026-10-20.md`; → #5897) a pairing link never names an address nothing listens on. Seen live (M4, build 329fcfb28): Sharing on, the engine started with the Remote Access certificate and bound only `127.0.0.1:8765`, while the link named `macbook-air-m4.local:8765` (the old "This network" gate had closed the `.local` listener, `sharing.listener`). Sharing on now binds that listener by itself; this is the guard that stays: the engine records the addresses it really bound; minting a pairing code (`POST /api/pair/code`) for a sharing address that needs a network listener (any address but `.ts.net`, which Tailscale serves to the loopback port) refuses, in words, with 409, while no non-loopback listener is up (for example the bind failed: "Sharing is on at <name>, but this Mac is not listening there yet…"); a `.ts.net` link, and an engine that did not record its binding (a dev or test engine started another way), are not refused. Built (engine): the recording and the refusal, pinned by `fichero-server/tests/unit/security/test_link_names_a_listener.py` (unrun).
- `sharing.switching-restarts-the-engine-once` — **[GAP]** (#5909; UNPROVEN link to the 2026-10-20 engine death on Sharing + Multi-user) the Sharing and Multi-user switches each stop and start the app's own engine (`ShareSettingsView.applySharing`: `backendService.stop()` then `start()`), while the heartbeat can start one too after seeing it down (`EngineLifecycleController.handleSupervisedBackendDropped`); `EmbeddedBackendService.start()` returns silently when a start is already in flight (#3108). A switch can therefore stop the engine another start is waiting on and its own start does nothing: no engine is left, and `applySharing` goes on to the health check as if one were. Rule: a switch restarts the engine once; a start in flight is awaited, never skipped (`EmbeddedBackendService.startDisposition`); the switch ends only with an engine answering, or says why it has none. Test (red until the fix compiles): held, Swift, 0519a8379 (the start-in-flight tests). Fix is Swift, HELD; the engine log of the failing start (Fichero > Show Log) is wanted to confirm the death.
- `sharing.share-on-choice` — **[SUPERSEDED]** (→ #5897, #5736; owner ruling 2026-10-20) there is no "Share on: This network / Tailscale" sub-choice and no separate "This network" switch: Sharing on listens on this network and, when present, Tailscale (`sharing.listener`). What stays is the safety of the pairing link (`sharing.link-names-a-listener`) and the tailnet offer on the share sheet. The unset-until-chosen key and the engine gate built for it are removed.
- `sharing.synced-device-registers` — **[GAP]** (**#5898**, S5, 2026-10-20) a second device that arrives by sync (its library copied, not paired by the link) cannot register itself with the engine, so it never appears among the paired devices and cannot act as its user. Neither the pairing link nor the "Share on" choice (`sharing.share-on-choice`) fixes it. *Test:* (not written: a synced device registers once, with the user it belongs to, and never as the owner by fallback).
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
  with a `.ts.net` sharing address the engine binds loopback only and makes `tailscale serve --https=<port> https+insecure://127.0.0.1:<port>` at start and removes it at stop (only the forward it made; a port serving something else is refused). Tailscale terminates TLS with its own public certificate, so the client trusts the **system** certificate for `.ts.net` (Tailscale identity plus the pairing token protect it) and keeps the **SPKI pin** only for `.local` hosts (ruled 2026-10-17). Proxied requests carry Tailscale headers and are never loopback (`api/auth.py`). Pairing codes carry the address as `tailnet_url`. #5752/#5753 fixed: no forward for a socket-only engine; a `.ts.net` invite carries no pin (`test_tailnet_invite_has_no_pin_to_spec.py`). **Still open:** an app pairing over the tailnet (#5320, needs the M4); the sandboxed app cannot run the Tailscale CLI, so it shows one command to paste with a copy button (#5317); the address is offered in the share sheet, not typed (#5318).
- `sharing.invite` — **[PARTIAL]** (→ #5049) the pairing card's QR / link carries the address, a one-time
  code, the pin and ONE library path (the host's current library).
- `sharing.pairing.copy-link-says-why` — **[PARTIAL]** (#5891; owner, 2026-10-20 07:40: "Copy Pairing Link" did nothing on the host)
  the pairing card never shows a code with neither a pairing link nor a reason. When the link cannot be built (no pin
  derived yet for this address, an address that does not work) the card says why in words, with the cure where the app can
  do it (the blocker's own headline and detail: "Preparing the security certificate …"), instead of "use the pairing link
  below" over nothing; the blocker used to be hidden whenever a one-time code existed. Copy Pairing Link reads the clipboard
  back and says "Fichero couldn't copy the link to the clipboard" when it did not take. The link carries the pin of
  an address that serves its own certificate (`.local`); an address a public CA terminates (`.ts.net` behind
  `tailscale serve`) gets a link with NO pin, which the guest checks with normal TLS validation (system trust + hostname
  match) and the pairing code still grants trust; plain http gets no link at all, with the reason in words: never a link
  with no pin and no TLS check. A missing pin is made by the button "Make a Pairing Link" on the blocker, which says it restarts sharing (and so stops work in flight); never automatically when the pane opens. Pinned by
  `fichero/Tests/Unit/general/Sharing/PairingLinkCopyTests.swift` (unrun: **[PARTIAL]** until compiled and tried on the
  owner's Pro).

### B. Connecting from the second Mac

- `sharing.mac-finds-host` — **[PARTIAL]** (→ #5734, #5892; owner's two-Mac test 2026-10-20, which overrules the
  manager's "no host picker" of 2026-10-17) Settings › Sharing › "Connect This Mac to Another Fichero" lists the
  Fichero Macs nearby, found by browsing Bonjour (`_fichero._tcp`, `NearbyHosts.swift`), without this Mac and
  without a host that has no secure address (`HostChoices.offered`); with none found it says so and the invite
  link still works. A `.ts.net` host is listed only when it is in THIS Mac's own tailnet: its suffix equals the
  Mac's own MagicDNS suffix, read from Tailscale by the engine (`/api/pair/tailnet`), never from Bonjour; a host in
  another tailnet is not listed, and when this Mac's suffix is unknown no `.ts.net` host is (the Bonjour record is
  unauthenticated, so a name on it proves nothing: an impostor could advertise the owner's Mac name with its own
  tailnet address and take the code). Picking a host starts pairing with it, showing "Connects to <full address>"
  before anything is sent: a listed `.ts.net` host asks for the pairing code shown on that host, certified by a
  public authority and checked by the system's trust and the host name (no pin, no bypass; http is refused); a
  `.local` host asks for its invite link, because the invite carries the key to pin, which Bonjour never does, and
  an invite that points at another host than the one picked is refused in words. There is
  still **no open lookup** of libraries: the list is hosts, never their libraries, and the pairing code grants
  trust. The drawer shows the host being connected to, read-only. Tests: `HostChoicesTests.swift` (the pure
  rules); Swift, not built or run. Not built: the camera/QR scan on a Mac. Open: the drawer still says "Scan the
  QR code shown on the host Mac" (`MacRemoteClientPairingSection.swift`); the Mac has no scanner, so it needs
  paste-only wording or a Mac scan.
- `sharing.connect-section-always-shown` — **[PARTIAL]** (#5893, owner's test 2026-10-20) the "Connect This Mac to
  Another Fichero" section is on the Devices pane whether or not Sharing is on: connecting to another Mac does not
  need this Mac to share (`ShareSettingsView.swift`: outside the `hostingEnabled` branch, and placed right under the
  Sharing switch and its pairing card, above Connected Devices, Connected Clients and Advanced, because a guest Mac
  needs it first and the pane is long; found by reading, no test can show a view's place). Swift, not built or run.
- `sharing.mac-pairs` — **[PARTIAL]** (→ #5049, read, not run) pairing sends the code to `POST /api/pair` with the pin
  enforced, checks health, and stores the token in the Keychain with its expiry, the pin, the host
  and the library path (`RemoteClientPairingFlow.swift`). Never run between two Macs (#5049).
- `sharing.library-confirmed` — **[PARTIAL]** (#3273; pinned by `fichero/Tests/Unit/general/Transport/RemoteClientPairingLibraryConfirmTests.swift`, `RemoteClientPairingFlow.confirmLibraryAccess`) before opening, the Mac asks the host whether it may open the invite's library. Swift tests run only on the M4 (#4511); issue stays open with needs-your-test.
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
- `sharing.revoke-cascades` — **[PARTIAL]** (#5351; engine built, pinned by `fichero-server/tests/unit/transport/test_revoke_cascades_to_spec.py`) revoking a paired device also revokes every device it paired (and theirs, down the chain): a code minted by a paired device records it (`devices.paired_by_device_id`), `revoke_device` walks the chain, and `GET /api/pair/devices` returns `paired_by_device_id` for each device. The Swift revoke confirm lists the devices that go with it (`PairingCardView.devicesRevokedWith`), parse-checked only. (Ruled 2026-10-04.) Needs `paired_by_device_id` on pairing codes and on `devices` (an idempotent ALTER migration; ruled 2026-10-17) and a walk in `AppDatabase.revoke_device`. Most useful with Multi-user on, where a paired person can mint codes. Test: `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py` (cascade case).

### D. Other people (Multi-user on)

- `sharing.multiuser-pairing` — **[PARTIAL]** (→ #5049, read, not run) with Multi-user on, creating a pairing code needs a
  signed-in person, or the host app itself: the app's bootstrap token on loopback acts as the one
  active owner for minting a code, listing devices and revoking one (#5346, 2026-10-01; before, the
  card could be refused and the host could not list or revoke). A code minted that way pairs a device
  for the owner; choosing another person is `sharing.device-chooses-person`. Pinned by
  `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_multiuser_on_the_host_app_can_list_and_revoke_a_device`.
- `sharing.private-by-default` — **[PARTIAL]** (→ #2403) only with Multi-user on: a single-user paired device
  sees every library as owner.
- `sharing.device-chooses-person` — **[PARTIAL]** (#2403) a remote device must choose and authenticate a person; there is no ambient owner. Engine built as opt-in: with Multi-user on, `POST /api/pair` takes `username` and `password` and binds the device to that person, not to whoever minted the code; a wrong password pairs nothing (`fichero-server/tests/unit/transport/test_device_chooses_person_to_spec.py`, 4 passed). With Multi-user on, a code minted by the host app (no signed-in person) is refused 401 `person required: ...` unless the device names a person; a code minted by a signed-in person still binds to that person. The Mac drawer reveals username/password on exactly that answer and sends them in `POST /api/pair` (`PairingPersonPickerTests.swift`; Swift unbuilt, the drawer unrun on a Mac). *Not built: the same picker for iOS and the scanned-QR path.*

## Acceptance: two Macs, two people, end to end (ruled 2026-10-17)

- `sharing.two-macs-end-to-end` — **[PARTIAL]** (→ #5049) The maintainer ruled that sharing a library between Macs must work in the next
  release and Multi-user is on. In plain words: on Mac A the owner turns **Sharing** on (Settings › Sharing) and the pairing card
  appears. Mac B, on the same network or the tailnet, finds A (or is given the link) and pairs with the one-time code over
  Bonjour and pinned TLS, then opens A's library. A has an owner account; a second person has an account and signs in on B; each
  edit in the shared library shows its author's own name and device, on either Mac. A read run started on B shows in A's Activity
  while it runs and when it ends. B's edits land on A within seconds, and A's Command-Z (one stack per window) still takes back only
  A's steps. When A turns Sharing off, B says "A stopped sharing this library", closes the shared windows and returns to its own
  projects, with no error screens. Nothing here asks the user for a port, certificate or token. Drilled by the tester with
  `docs/contributor_manual/testing/sharing-two-mac-checklist.md`; its parts are the behaviours below. Test (in-process half: pair, open, stale-edit 409, revoke; not the stream, not two accounts): `fichero-server/tests/unit/transport/test_two_macs_end_to_end_to_spec.py`; the real run is the checklist on the M4.
- `sharing.two-toggles-wording` — **[PARTIAL]** (built 5ff159856, #3284; `SharingTogglesTests` written, not yet run in the Swift host: needs the builder's test run) Settings › Sharing has exactly two switches. *Sharing*: "Share Fichero on this Mac with other devices, the fichero command-line tool, and MCP clients." *Multi-user*: "Give other people their own accounts on this Mac's libraries." Nothing else is asked. Today the Sharing switch reads On/Off with that caption; the Multi-user switch sits beside Sharing in Settings › Sharing (ruled 2026-10-17; #3284), and `EngineSettingsView` holds no toggle (`ShareSettingsView.swift` renders both rows from `SharingToggles`). Red test written, not run (needs the pure `SharingToggles` type from #3284, so the test target will not compile until then): `fichero/Tests/Unit/general/Sharing/SharingTogglesTests.swift` (the two labels and captions, and that no third switch exists).
- `sharing.names-on-edits` — **[PARTIAL]** (→ #5735; engine half pinned by `fichero-server/tests/unit/transport/test_two_accounts_names_on_edits_to_spec.py`, passing: owner on the host and a second person on a paired device each get their own name and device on the audit row; the change-stream `actor` field is still a category, not a person ; the event now carries `person` and `device` too (`test_change_event_names_person_to_spec.py`; the Swift stream does not read them yet, #5735), and the app windows are unrun) with two accounts, an edit made by the second person on B is recorded as that person on device B, and the owner's on A as the owner on A (needs `sharing.device-chooses-person`, `sharing.who-did-it`). Test: `fichero-server/tests/unit/transport/test_two_accounts_names_on_edits_to_spec.py`.
- `sharing.remote-run-in-host-activity` — **[PARTIAL]** (→ #5732) a read run started from B is a row in A's Activity (`/api/activity/stream`), started by B's person, on device B, live to its end. Built: every run starter takes `started_by` from `started_by_for(ctx)`, "person on device name" for a paired device (ruled 2026-10-17), pinned by `fichero-server/tests/unit/transport/test_remote_run_in_activity_to_spec.py` (3 passed). The host's Activity jobs list carries `started_by` (`GET /api/activity/jobs`, pinned by `test_a_run_started_from_a_paired_mac_is_a_row_in_the_hosts_activity_naming_who`). *Not proven: the row live on A's stream while the run goes, and ending (two-Mac checklist).*
- `sharing.undo-after-remote-edit` — **[PARTIAL]** (→ #5733) A's undo reverses only A's own steps; if B changed the same thing since, it is refused in a sentence naming who and when (`undo-everywhere.md`, #5658). Built: the engine refuses over later work in a sentence naming actor and time (`actions/undo.py:181`, reason `changed`). Pinned by `fichero-server/tests/unit/transport/test_undo_after_remote_edit_to_spec.py` (host's undo after a paired person's edit: 409 `changed` naming them). Not proven: per-window undo in the app (two-Mac checklist).
- `sharing.off-closes-the-guest` — **[PARTIAL]** (→ #5731) turning Sharing off on A ends B's change stream with a typed `sharing.stopped` event before the listener closes; B shows one sentence, closes the shared windows and returns to its own projects; no reconnect loop. Engine built: a non-loopback `/api/changes/stream` yields `sharing.stopped` when the engine shuts down, the host's own windows get none (`fichero-server/tests/unit/transport/test_sharing_off_to_spec.py`, 2 passed). *Not built: the guest's one sentence, closing its windows, and no reconnect loop (Swift, `LibraryManager.swift`); the window behaviour is on the checklist.*
- `sharing.stale-edit-both-ways` — **[PARTIAL]** (→ #5348) engine half built; the app sends the version (see `sharing.stale-note-edit-is-refused-and-offered-a-choice`): B's edit on a note A changed is refused 409, never silently lost. Engine pinned by `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_two_macs_editing_one_note_the_second_stale_edit_is_refused` (no xfail remains); the Swift editor half needs its own test, to be written with #5348.

### E. Sharing in the sidebar (ruled 2026-10-17; cross-cited from `ui/sidebar-crud.md`)

- `sharing.sidebar.guest-row` — **[GAP]** (→ #5737) on the guest Mac a shared library is a project row under PROJECTS in the same style as local projects, with a small "shared" mark, named as on the host; the host's name is shown in the Inspector. No separate section. Built: a remote-host project already sits under PROJECTS like any other; its row now carries the small shared mark (`person.2`) and the Inspector's Location reads "Shared from <host>" (`SharedProjectRowTests.swift`; Swift unbuilt, the row unrun on a Mac).
- `sharing.sidebar.host-mark` — **[PARTIAL]** (→ #5738) on the host Mac the shared project's row carries a small shared mark while Sharing is on; the Inspector lists the connected people and devices, each with Revoke and Forget machine (`transfer.machine.forget-machine`). Nothing else changes in the sidebar. Built: the mark on the row and the Inspector's devices list with Remove (revoke, which cascades) while Sharing is on (`HostSharedMarkTests.swift`; Swift unbuilt, unrun on a Mac). Not built: Forget machine in that list, and the list naming people.
- `sharing.sidebar.off-greys-row` — **[GAP]** (→ #5739; engine event is `sharing.off-closes-the-guest`, #5731) when Sharing goes off on the host the guest's row stays, greyed, with one sentence, "Not available: sharing is off on <host>"; its windows close with that sentence; Forget removes the row. Built for the session: the row (`HostGoneRowView`) renders from `LibraryManager.hostGoneRows`, filled by the `sharing.stopped` event, Forget removes it (`SharingOffGreysRowTests.swift`; Swift unbuilt, the row unrun on a Mac). Not built: the row surviving an app relaunch.

- `sharing.switch-from-cli` — **[GAP]** (→ #5751) Sharing and Multi-user can be read and set through one audited action (`sharing.set`), so the CLI/MCP and Settings share one path. Test: (not yet written: test_sharing_switch_action_to_spec.py).

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
- `sharing.accounts-and-users-settings` — **[PARTIAL]** (#2083; read, not run: `UsersSettingsView.swift`, `UsersContent+*.swift`, `InviteAccountSection.swift` already give invites, add member, role picker, remove, disable/enable; login and a real run are unchecked) Settings has an Accounts & Users screen to log in, add/remove users and assign owner/editor/viewer.
- `sharing.ios-device-token-hygiene` — **[PARTIAL]** (#3290) outbox blobs and the manifest are written with file protection until first unlock on iOS (`MobileCaptureQueue.writeOptions`; test `fichero/Tests/Unit/general/Models/MobileCaptureQueueFileProtectionTests.swift`, written, not run); token resolution, foreground renewal and the re-pair prompt are not covered by this slice. an iOS device build never resolves the bootstrap token, renews its device token on foreground, and shows a re-pair prompt on expiry or revocation; outbox blobs are file-protected.
- `sharing.owner-shared-libraries-view` — **[GAP]** (#2054) Settings shows the owner every library, which are shared with whom and in what role, and whether each is open.
- `sharing.multiuser-mode-single-source` — **[PARTIAL]** *(superseded by `multiuser-always-on.md`: describes today's code until its slice 10 removes the switch)* (#3331, #3284, #5751) multi-user access is enforced ONLY while the Multi-user switch is on (owner ruling 2026-10-18); account rows alone never turn it on, and `FICHERO_MULTIUSER=0` is an authoritative off (the reading "accounts imply enforcement" was ruled out; `test_multiuser_accounts_dont_flip.py`). The toggle persists to the engine and the app, and the spawn env and engine agree. Built: the persisted setting is written by one audited, undoable action (`PUT /api/pair/multiuser`, `test_sharing_state_and_multiuser_switch_to_spec.py`), and the environment wins with a 409 that says so. **Left:** the app-started engine still takes the flag by restart with `FICHERO_MULTIUSER` (a second path to the same setting); folding that onto the one action needs the supervisor to stop passing the env (design call, #5751).
- `sharing.acl-status-when-multiuser-off` — **[PARTIAL]** *(superseded by `multiuser-always-on.md`: describes today's code until its slice 10 removes the switch)* (#3335; engine pinned by `fichero-server/tests/unit/transport/test_acl_status_multiuser_off_to_spec.py`; app wording parse-checked only, not built) with Multi-user off the Accounts section reads "Accounts: Off" (and no role or access rows) instead of a red Server error; an authz error is an orange warning label (Fable UI review, ShareSettingsView+Security.swift).
- `sharing.ios-discovers-host` — **[GAP]** (#3371) an iOS/iPad client browses Bonjour, lists verified reachable Mac engine candidates and shows stale ones as failed, without persisting trust.
- `sharing.actor-not-from-the-body` — **[OK]** (#3285; pinned by `fichero-server/tests/unit/security/test_invoke_actor_cannot_be_forged.py`, 3 passed) `POST /api/actions/invoke` never takes the author from the request: a body `actor` or `origin_window` is refused, and the audit row's actor comes from the signed-in session.
- `sharing.loopback-is-owner` — **[OK]** *(superseded by `multiuser-always-on.md`: describes today's code until its slice 10 removes the ambient owner)* (pinned by `fichero-server/tests/unit/security/test_loopback_owner_never_gated.py`, `fichero-server/tests/unit/security/test_resolve_single_user_owner.py`) a request on loopback carrying the bootstrap token is the owner, Multi-user on or off; a remote device is never the owner by being on the same Mac; the bootstrap secret is never a device token (`api/auth.py:166-181`).
- `sharing.owner-owns-every-library` — **[OK]** (#5755; pinned by `fichero-server/tests/unit/transport/test_owner_account_owns_every_library_to_spec.py`) an owner account owns every library this Mac hosts: a new or promoted owner gets owner on the existing libraries, and a library opened later is owned by every owner account (ruled 2026-10-17).
- `sharing.owner-only-asserted-in-the-action` — **[OK]** (#5766; `fichero-server/tests/unit/security/test_owner_only_is_declared_to_spec.py`) an owner-only action is declared `owner_only=True` on its registration (`acl.set`) and `registry.invoke` refuses a non-owner before the action runs, so `/api/actions/invoke`, MCP and chat cannot reach it with library WRITE alone; the loopback owner passes. A guardrail fails any action whose docstring says owner-only without the flag. Actions that other people may also run (`device.revoke`: the owner or the one who paired) assert their own rule inside.
- `sharing.account-changes-are-audited` — **[PARTIAL]** (#5765, → #5792; `fichero-server/tests/unit/security/test_account_changes_are_audited_to_spec.py`) creating, changing, disabling or deleting an account, minting or revoking an invite and revoking a session each write an audit row (`user.create|update|delete`, `invite.create|revoke`, `session.revoke`) naming the actor (`user:<id>` or `bootstrap`), the client and the paired device; no password or token is recorded. The row is written first and hash-chained like an action audit (`AppDatabase.save_chained_account_audit`; client and device are stored and, on `v2:` rows, covered by the hash; rows written before verify as they did), so a failed audit write stops the change. *Not built: nothing verifies the app chain yet (`verify_audit_chain` reads the library database only; → #5792), so it is chained, not yet tamper-evident.* The owner check stays in the route.
- `sharing.cli-session-per-engine` — **[OK]** (#5757; `fichero-cli/tests/test_cli_session_per_engine_5757.py`, 4 passed) the CLI keeps a session per engine it dials (keyed by socket path or URL); a token one engine rejects never shadows another engine's bootstrap token. A session saved before this change (no engine stamp) is dropped from the file the first time an engine answers it 401, so it is never offered to another engine.
- Accounts imply enforcement: superseded by `multiuser.always-on` in `multiuser-always-on.md` (owner 2026-10-18); the full always-on (#2403, slice 10) is still the plan.
- `sharing.device-acts-as-its-binding` — **[PARTIAL]** (#5888; code and tests written; PARTIAL until an M4 run) (S1, tests `tests/unit/security/test_sharing_probe_2026_10_01.py::test_s1_*`) a paired device authenticates as the user it is bound to, never as the owner by fallback: an owner-bound device is the owner by its binding; a device bound to anyone else is refused while Multi-user is off (roles are only evaluated with it on) and acts as that person with it on (a viewer-bound device reads and cannot write; an editor-bound one writes, audited as that person with the device named; neither ingests a host path: `test_s1_with_multiuser_on_*`); a device with no binding is 401. A host path is ingested only by the host app or an ENGINE-owner credential, session or device (`_require_ingest_owner`; a library-owner person is refused). Loopback+bootstrap as owner stays until slice 10.
- `sharing.stale-note-edit-is-refused-and-offered-a-choice` — **[PARTIAL]** (#5348) a note or document edit made against an old version is refused 409 and the app offers keep-mine, take-theirs or compare. Engine built for both: `PATCH /api/notes/{id}` and `PUT /api/documents/{id}` take `expected_updated_at` (pinned by `fichero-server/tests/unit/security/test_sharing_probe_2026_10_01.py::test_two_macs_editing_one_note_the_second_stale_edit_is_refused` and `fichero-server/tests/unit/transport/test_stale_document_edit_to_spec.py`). The note editor sends the version and offers Keep mine, Take theirs and Compare (both texts side by side; `fichero/Tests/Unit/general/Sharing/NoteStaleResolutionTests.swift`). *Not built: the same choice for a document edit.*
- `sharing.note-deleted-elsewhere-stays-deleted` — **[PARTIAL]** (→ #5348; owner ruling 2026-10-17) a shared library is shared
  editing: a note deleted on another Mac is deleted here too. When a refused (stale) save finds the note gone, the
  app says so in one sentence and offers nothing: no keep-mine resurrection, no clipboard copy, no dialog.
  (`NotesInspectorPane.saveNote`, `NoteStaleResolution.deletedElsewhere`; Swift, parse-checked only.)
- `sharing.ios.unpaired-phone-opens-on-connect` **[PARTIAL]** (#5396) read 2026-10-17, not run: the gate routes a never-paired launch to the connect screen (`EngineConfig.iosLaunchPhase`), and the tier glyphs are Mac-only (`FeatureManager.shouldShowTierChrome`; test `fichero/Tests/Unit/general/Views/Shell/IOSNoTierChromeTests.swift`); the layout items (doubled nav bar, landscape sidebar, offline chat pane, empty-sidebar hint, Mac vocabulary) are unverified and open. Behavior: an iPhone that has never paired opens on a welcome screen with Connect to a Mac (Bonjour list, QR or address), then the project list, never an empty 'Nothing Selected' view or a server-down error. Its screens are laid out for a phone: one navigation bar, a sidebar that survives landscape, no offline chat pane and no internal α/β/δ markers.

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
