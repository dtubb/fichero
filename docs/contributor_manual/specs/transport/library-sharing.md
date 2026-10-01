# Library Sharing between Macs — Design Spec (→ #5049)

> Milestone: Sharing & Pairing — Dead-Simple UX; Engine - Sharing - Accounts, Multi-user & Libraries
> Manual: TBD — "Working on one library from two Macs".
>
> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-01.** Written from the rulings in
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

## Behaviours

### A. Turning sharing on (the host)

- `sharing.toggle-restarts-engine` — **[PARTIAL]** (→ #5049) Settings › Sharing's switch saves the choice,
  turns Bonjour on, fills a `https://<host>.local:8765` address, restarts the bundled engine with an
  HTTPS listener, and lists paired devices (`ShareSettingsView+StateManagement.swift`). Never seen
  on two machines (#5049).
- `sharing.listener` — **[PARTIAL]** (→ #5049, read, not run) the engine keeps its loopback listener and adds ONE listener
  on the Mac's network address for a `.local` host (`FICHERO_LAN_HOST`, `__main__.py`). It never
  binds `0.0.0.0` (`remote_access_tls._bind_host_for_public_host`), which the older transport
  ruling allowed; the code's model (loopback + one LAN address) is the stricter one and this spec
  takes it.
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
  with a `.ts.net` sharing address the engine binds loopback only and makes
  `tailscale serve --https=<port> https+insecure://127.0.0.1:<port>` at start (removing it at stop,
  only the forward it made; a port serving something else is refused). Tailscale terminates TLS
  with the tailnet host's public certificate, so devices need no pin (the app holds none for a
  `.ts.net` host, #5041), and its forwarding headers mark tailnet peers as remote: the bootstrap
  token is refused through the tailnet address. Pairing codes carry the address as `tailnet_url`.
  Run 2026-10-01 evening, Air host: the engine logged the forward created, the MBP reached it
  with a standard TLS check (Let's Encrypt), `tailnet_status` was `reachable`, and the bootstrap
  token over the tailnet was 403. The first form, a raw `--tcp` forward, gave devices the engine's
  self-signed certificate and made every tailnet peer look like loopback (#5320). **Still open:**
  the sandboxed app running the Tailscale CLI (#5317); the address is still typed under
  Advanced (#5318).
- `sharing.invite` — **[PARTIAL]** (→ #5049) the pairing card's QR / link carries the address, a one-time
  code, the pin and ONE library path (the host's current library).

### B. Connecting from the second Mac

- `sharing.mac-finds-host` — **[GAP]** (→ #5049; its own issue once the test confirms it) a Mac cannot browse for hosts (Bonjour browsing is iOS
  only) and has no camera flow; the section says "Scan the QR code" but the only way in is pasting
  the link (`MacRemoteClientPairingSection.swift`).
- `sharing.mac-pairs` — **[PARTIAL]** (→ #5049, read, not run) pairing sends the code to `POST /api/pair` with the pin
  enforced, checks health, and stores the token in the Keychain with its expiry, the pin, the host
  and the library path (`RemoteClientPairingFlow.swift`). Never run between two Macs (#5049).
- `sharing.library-confirmed` — **[GAP]** (#3273) the Mac keeps the invite's library path without
  asking the host whether it may open it; iOS checks.
- `sharing.opens-the-library` — **[PARTIAL]** (→ #5049, read, not run) the second Mac switches its active host to the
  first, adopts the invite's library and lists the host's libraries from `/api/authz/libraries`;
  the library path header names the path ON THE HOST. One host at a time for the whole app (#2573).
- `sharing.pairing-over-uds` — **[PARTIAL]** (#4224) pairing builds its own HTTPS client; an app
  that runs its engine over the Unix socket (Dev Local) cannot use it.

### C. Working on it from both

- `sharing.edits-both-ways` — **[PARTIAL]** (→ #5049) an edit on either Mac lands in the one library and
  appears on the other through the change stream (`/api/changes`, read-authorised per library).
  Run 2026-10-01 engine to engine (CLI, over Tailscale): notes written on each Mac read on the other;
  the stream lost an event when the host's loop stalled past its keepalive, fixed in #5314
  (`test_an_event_queued_while_the_loop_stalls_past_the_keepalive_is_still_sent`). Run again
  2026-10-01 evening, Air host, over Tailscale's HTTPS: a note made on either Mac arrived on the
  other's `fichero changes stream-library` at once (the CLI printed nothing until #5321). The
  app's windows were not run.
- `sharing.who-did-it` — **[OK]** (→ #5319; pinned by `tests/integration/test_sharing_who_did_it.py`, Multi-user off and on) each edit's audit row names who made it
  and, for a paired device, which device: `actor` is the owner on the host (loopback + bootstrap
  token, ruled) and the device's person elsewhere, and `device` is `{id, name}`. Run 2026-10-01
  evening over the tailnet: the Air's note read `owner`, no device; the MBP's read `owner` on
  `MBP-3way`. The live change event names the person, not the device.
- `sharing.revoke` — **[PARTIAL]** (→ #5049) the host lists paired devices and can revoke one; a revoked
  token is refused (pinned in `test_device_pairing_e2e.py`, in-process; run 2026-10-01 across two
  Macs: the paired MBP's next call was 401). The app's device list was not run.

### D. Other people (Multi-user on)

- `sharing.multiuser-pairing` — **[PARTIAL]** (→ #5049, read, not run) with Multi-user on, creating a pairing code needs a
  signed-in person, and the app's own bootstrap token carries none, so the pairing card may be
  refused (`pairing.py`, `auth.py`). The one end-to-end test signs in as owner first.
- `sharing.private-by-default` — **[PARTIAL]** (→ #2403) only with Multi-user on: a single-user paired device
  sees every library as owner.
- `sharing.device-chooses-person` — **[GAP]** (#2403) a remote device must choose and authenticate a
  person; there is no ambient owner.

## The three-device test (2026-10-01 evening, continuing)

Air host (engine with a `.ts.net` sharing address), MBP and iPad mini over Tailscale. Done
engine to engine: pairing over the tailnet, notes both ways with the change stream, who-did-it
in the audit, the bootstrap token refused from the tailnet. Owed, needing a person:
1. MBP app: unlock the screen; open the invite link with the built app by path; press Connect;
   edit in its window; see it in the Air's history.
2. iPad: open Tailscale (offline since July); trust the developer certificate; install
   `fichero-ios`; scan or paste the invite; edit; see it arrive on both Macs.
3. Revoke each device on the Air; each is refused.
Each failure: an issue, fixed one at a time, its behaviour above re-tagged.
