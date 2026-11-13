# Two Macs (and an iPhone) share a library, reliably — Spec

> Milestone: Sharing & Pairing — Dead-Simple UX. Companion to `transport/library-sharing.md` (the
> design and its rulings), `transport/transport-http-uds.md` and `transport/multiuser-always-on.md`.
> Manual: docs/contributor_manual/manual-facts/2026-11-02-sharing.md (the researcher-facing section authored in the user manual, tracked by this file: a "Share a library with another Mac or your iPhone" section: turn Sharing on, pick the address, send the link, and what each failure sentence means).
> **Status: APPROVED by the owner 2026-11-02 (the build order added 2026-11-02; #5908 ruled the same day: 409 in the engine; the manual facts page written the same day at the owner's word).**
> Before that: DRAFT, 2026-10-30; every claim re-checked against the code 2026-10-31 (file:line cited). §10 (2026-10-31, approved
> for build) covers the owner's five live items on Mac, iPad and iPhone, with the per-platform test matrix, the live script and the slices.
> Written from the owner's order ("try this Mac to the Air and vice
> versa; the M4 to the M1 is not working; we need this rock solid"), a code read at integration
> `98990d947`, and a headless two-Mac probe on 2026-10-30 (the MacBook Pro `macbook-pro-m1`, the M1 Air
> `macbook-air-m1`, the M4 `macbook-air-m4`, all on the university /22 `131.202.228.0/22` plus one
> tailnet `tail677e72.ts.net`). Tags: **[OK]** built and seen working · **[PARTIAL]** built, unproven
> or incomplete · **[GAP]** not built or seen broken. Swift items are spec only here (unbuilt).
> Secrets (tokens, keys, pairing codes) appear nowhere in this file.

## Intent

A person turns sharing on at one Mac and, within a minute, opens that library from another Mac or an
iPhone, by one link or one QR, with no port, certificate or token typed. When it cannot work the app
says **which step failed, in plain words, and what to do**, never a bare "request timed out", never a
raw `undocumented(statusCode: 404 …)`.

## 1. The intended flow (read from code and specs)

**Host side.**
1. Sharing on (Settings › Sharing, and — new — Set Up, §6). The app names the host address
   (`RemoteAccessConfig.autoLocalBaseURL`, `Services/RemoteAccessConfig.swift:64-71`: the first label of
   `ProcessInfo.processInfo.hostName`, lowercased, + `.local`, port 8765; or a `.ts.net` name the
   person chose with "Use"), makes a self-signed certificate (`--prepare-remote-access`, stored under
   `…/Application Support/Fichero/Remote Access/<host>-8765-<hash>/server.crt|key`, the hash of URL + SANs,
   `security/remote_access_tls.py:215-232`; SAN = the host, `127.0.0.1`, `localhost`; valid 10 years,
   `_MAX_CERT_AGE`, `:37`; **a new EC key with every new folder**, `_generate_material`, `:244`), and restarts the bundled
   engine with `FICHERO_TCP_TLS_ALSO=1`, `FICHERO_LAN_HOST=<lan ip>`, `FICHERO_PUBLIC_BASE_URL`,
   `FICHERO_TLS_CERTFILE/KEYFILE/SPKI_HASH`.
2. The engine binds `127.0.0.1:8765` and **one** LAN address (never `0.0.0.0`; `__main__._listener_hosts`, `:66-74`;
   `bind_host.resolve_lan_bind_host`, `:114-134`) beside its Unix socket; advertises `_fichero._tcp` on Bonjour
   (`security/discovery.py`; the instance name "Fichero Server on <name>" and the record's server host both come from
   `socket.gethostname()`, `:64-66`, `:162`); and, when the sharing address is a `.ts.net` name (or `FICHERO_TAILNET_URL`
   is set, `tailscale_serve.tailnet_url`, `:41-55`), makes `tailscale serve --bg --https=8765
   https+insecure://127.0.0.1:8765` (`ensure_forward`, `:106-128`). It never overwrites a forward it did not make,
   with one exception: a raw `tcp://127.0.0.1:8765` forward left by an earlier Fichero build is replaced (#5320, `:118-119`).
   A failure to forward is a WARNING in the log, not a failed launch (`start_for_engine`, `:135-163`).
3. `POST /api/pair/code` (`api/routes/auth/pairing.py:664`) mints a one-time code (10 min; `PAIRING_CODE_TTL`, `:36`) and
   refuses with a 409 in words, never a link to an address nothing listens on (`network_listener_gap`,
   `transport_diagnostics.py:149-160`, raised at `pairing.py:724`; and `:752` when the tailnet address fails
   `validate_tailnet_url`). The app wraps it in a
   payload `{v, api_url, pair_code, expires_at, spki, library_path}` as a QR and as
   `fichero://pair?payload=<base64 json>` (or `https://tubb.ca/apps/fichero/pair?payload=…`). `spki` is the SHA pin of the
   host certificate's public key for a `.local`/IP host, absent for `.ts.net` (public CA; the one decision point is
   `RemoteCertificatePinning.usesPublicCertificateAuthority(host:)`, `fichero-api-client/…/RemoteCertificatePinning.swift:71-76`).
   **The payload carries ONE address (`api_url`).** The engine's response also carries `tailnet_url`
   (`PairCodeResponse.tailnet_url`, `pairing.py:139-147`) but the app's payload builder
   (`PairingService.buildQRCodePayload`, `Services/PairingTypes.swift:309-323`) takes one `apiRoot` and does not put it in the link.
4. Multi-user (optional): owner account + password, `PUT /api/pair/multiuser` (`pairing.py:589-608`; the persisted
   `multiuser.enabled` setting). While off: **403** "sign in as the owner to change Multi-user" without the owner's
   signed-in session (`:601`), **409** `owner_password_gap` until the owner has chosen a password (`:607`,
   `security/multiuser.py:69-76`).

**Client side (Mac).** Settings › Sharing › Connect to Another Mac… (`Views/Settings/Sharing/Pairing/MacRemoteClientPairingSection.swift`):
Nearby hosts (Bonjour, `Services/Connectivity/NearbyHosts.swift`, `HostChoices`) or paste the link →
`RemoteClientPairing.pairingFields(fromInviteOrPayload:)` (`Services/RemoteClientPairingFlow.swift:60-96`: decode, https only,
pin required for a non-`.ts.net` host, **a payload with no `library_path` is refused before any network call**,
`missingLibraryPath`, `:88-90`) → `pairDevice`: `POST <api_url>/api/pair {code, device_name[, username, password]}` with the pin
enforced by `RemoteCertificatePinning` (`:197-227`) → `probeRemoteHealth`: `GET /api/health` and the contract check
(`ContractCompatibility.mismatch`, `:268-290`) → `persistPairedHost` (device token into the Keychain,
`AuthTokenMiddleware.persistRemoteToken`; the pin; the token expiry for renewal) → the app's one engine host switches to the host
(`EngineHostSwitch.run`, `Services/EngineHostSwitch.swift:23-40`, the previous host put back on failure). **The Mac path never
calls `confirmLibraryAccess`** (`MacRemoteClientPairingSection.swift:158-176` calls `pairDevice` + `persistPairedHost`, not
`pairAndPersistHost`): the invite's library is not checked against `GET /api/authz/libraries` on a Mac. Failover afterwards walks the paired
host's *other known endpoints* (`Models/PairedHostEndpoints.swift`, loopback filtered out, LAN before tailnet, `:21-23`, `:70`) — but only the
endpoints it recorded at pairing, which today is the one address in the link. Every failure reaches the person as
`error.localizedDescription` (`MacRemoteClientPairingSection.swift:181`).

**Client side (iOS / iPad).** `fichero://pair?payload=…` opened from Messages/Mail/Notes (`CFBundleURLTypes`
scheme `fichero`, `Info.plist:26-29`), or the QR scanner / pasted link / nearby list in `Views/Connect/ConnectPairingIOS.swift`,
`ConnectPairingEntryIOS.swift`, `ConnectDiscoveredMacsSectionIOS.swift`; `.onOpenURL` (`FicheroApp_iOS.swift:164`) →
`PairingIncomingLinkSheet` (`:48-70`) → `pairAndPersistHost` (`RemoteClientPairingFlow.swift:294-337`): `pairDevice` → token into the
Keychain → `confirmLibraryAccess` (`GET /api/authz/libraries`; the token is cleared when the library is not in the list) →
`persistPairedHost`. **The iOS path runs no contract check** (`probeRemoteHealth` has two callers, both Mac:
`MacRemoteClientPairingSection.swift:165`, `Views/Library/SyncedHostAskSheet.swift:39`). The two clients therefore run two different
check lists: `sharing.both-clients-run-the-same-checks` (§4).

## 2. Failure modes the specs already name

`library-sharing.md` names: `.local` does not resolve where mDNS does not cross (campus networks:
`sharing.bonjour-advertises`); a link to an address nothing listens on (`sharing.link-names-a-listener`); no pin
yet (`sharing.pairing.copy-link-says-why`); the wrong/absent pin or plain http (`#5891`); person required
(`sharing.device-chooses-person`); host stopped sharing (`sharing.off-closes-the-guest`); revoked
(`sharing.revoke`); contract mismatch (`#5047`); the tailnet forward cannot be made by a sandboxed app
(`tailnet_serve_command`, #5317); a tailnet port already serving something else. What none of them
specify is the **client trying more than one address**, **what the person is told for each network failure**, and
**the same checks on a Mac and on a phone**.

## 3. What was tested (2026-10-30, headless, read-only on the Macs)

| Step | Result |
|---|---|
| Air engine up (`/Applications/Fichero.app`, build 19, engine 2026.10.28) | listening `127.0.0.1:8765` and `131.202.228.243:8765` (the LAN address only, not `*`) — **OK** |
| Air macOS firewall | enabled; `Fichero.app` and `Fichero Server.app` both "Allow incoming connections"; stealth off; block-all off — **OK, not the cause** |
| Air certificate | CN `macbook-air-m1.local`; SAN `DNS:macbook-air-m1.local, IP:127.0.0.1, DNS:localhost`. Valid to 2036 — **OK for the `.local` name; it does NOT name the LAN IP or the `.ts.net` name** |
| Air → itself (`.local`, LAN IP) | HTTP 200 — **OK** |
| **Pro → Air `.local`** | `Could not resolve host: macbook-air-m1.local` (4.8 s) — **FAIL (mDNS does not cross)**. The Air itself resolves the name (`dns-sd -G`), so it is advertised, just not received |
| **Pro → Air LAN IP `131.202.228.243:8765`** | `Host is down` / connect timeout; ARP `incomplete`; ping 100 % loss; port 22 also down — **FAIL (layer-2: client isolation between hosts on the campus /22; not the Air's firewall, which allows it)** |
| **M4 → Air** (`ssh m4`) | `.local`: could not resolve; LAN IP: connect timeout 6 s — **FAIL, identical to the Pro. This is the owner's "M4 to the M1 does not work"** |
| **Pro → Air tailnet `https://macbook-air-m1.tail677e72.ts.net:8765`** | TLS completes with a **publicly trusted** certificate (system trust, `ssl_verify=0`), `/api/health` 200 in 0.4 s; `POST /api/pair` with a bad code → `401 {"detail":"invalid or expired pairing code"}` (the endpoint is alive and the answer is the plain one) — **OK** |
| **M4 → Air tailnet name:8765** | HTTP 200 in 0.5 s — **OK. The M4 can reach the Air; the link just does not name this address** |
| Pro → Air by tailnet IP `100.107.68.106:8765` | `tlsv1 alert internal error` — **expected**: Tailscale's certificate is for the MagicDNS name, not the IP; an address by IP never works through `tailscale serve` |
| Air tailnet forward | `tailscale serve status`: `https://macbook-air-m1.tail677e72.ts.net:8765 (tailnet only) → https+insecure://127.0.0.1:8765` — **OK, made by the engine** |
| Air `/api/health` `remote_backend` | `{"enabled": false, "connection_model": "ssh-loopback", "api_url": null, "token_configured": false, "tailnet_status": "not_configured"}` while sharing IS on and the tailnet forward IS up. Same on the Pro and the M4. **This block describes the ACENET/ssh-loopback env model (`FICHERO_REMOTE_BACKEND=1`, `security/remote_backend.py`), not app sharing**; it is `false` whenever the app, not a script, shares. It says nothing about listeners, addresses, certificate or the tailnet forward — a person (or a tester) reading it is misled. |
| **Air → Pro (Pro as host)** | The Pro app (build 19, engine **2026.10.27**) is running, listening `127.0.0.1:8765` and `131.202.228.242:8765`, certificate CN `unb-c02f45gaq05p.local`. Air → `https://131.202.228.242:8765` timeout; Air → `macbook-pro-m1.local` unresolved; Air → `unb-c02f45gaq05p.local` unresolved; Air → Pro `…ts.net:8765` connection refused (the Pro's Tailscale serves `:443` → `http://127.0.0.1:5006`, another service's forward; nothing is served on 8765, so the engine did not make its tailnet forward on the Pro: the Pro's sharing address is not a `.ts.net` name, which is expected — the forward is made only for a `.ts.net` sharing address — but then the link names only `unb-c02f45gaq05p.local`); Air → Pro `…ts.net` (443) answers 200 but that is the other service, not Fichero. **FAIL on every path.** Causes: C1/C2 (network) and C4/C5 below. |
| **M4 as host** | The M4's tailnet port 8765 is a **raw TCP forward to `localhost:8000`** (`tcp://…ts.net:8765 → tcp://localhost:8000`), nothing listens on 8000: `Pro → M4 ts.net:8765`: `Connection reset by peer`; the M4 to itself the same. The engine's own forward (`https+insecure://127.0.0.1:8765`) cannot be made while another forward holds the port (`ensure_forward` refuses, by design). M4's engine health also `remote_backend.enabled=false`. LAN: `.207` timeout from the Pro. **FAIL (stale forward, C6).** (The M4 stopped answering ssh part-way; M4 findings are from before.) |
| Air as **client** to the Pro as host | Not possible while the Pro is unreachable on every path (above). **Untested.** |
| Headless two-engine run (host + client engine on one box) | The harness exists (`tests/integration/_two_engines.py`: `start_host`, `start_guest`, `pairing_link`, `pair_with_link`, `turn_multiuser_on/off`; `test_sharing_release_bar_5911.py`, `FICHERO_TWO_ENGINES=1`) but pairs by IP with a stand-in client, one cert name, no failure cases. The real client, `fichero devices pair <link>` (`fichero-cli/src/fichero_cli/__main__.py:796`, `pairing.py`), exists: it checks https, the public-CA rule (`_is_public_ca`, `:60`) and the pin against the served certificate (`check_trust`, `:87-110`; a 5 s fetch, `:82`) **before** sending anything, with its own sentences — a second copy of the Swift rules. Not run here (other agents' pytest/gate running; brief says one at a time). The plan in §8 extends it. |

### Causes, ranked (what stops the owner's two-Mac connection)

- **C1 (the owner's error).** The link names ONE address, the `.local` name; the campus network does not carry mDNS between
  Macs, so the guest's `POST https://macbook-air-m1.local:8765/api/pair` can never leave; the client waits the transport's default
  60 s request timeout (no `timeoutInterval` is set anywhere in the app, grep 2026-10-31) and shows "request timed out (-1001)". The
  working address (`…tail677e72.ts.net`) is known to the host (`GET /api/pair/tailnet`, `pairing.py:652-661`;
  `PairCodeResponse.tailnet_url`) and is not in the link. Fix: §4 `sharing.address-choice`, `sharing.link-carries-every-address`.
- **C2.** The LAN IP does not work either (client isolation), so even "use the IP" would fail. Hence the need for the client to try
  each address and say which failed (`sharing.client-tries-every-address`).
- **C3.** The certificate names the `.local` host only. A link with an IP address or the `.ts.net` name with a pin would fail the
  SAN check; `.ts.net` is public-CA and needs no pin (correct today), but a **LAN IP** address in a link would be refused by hostname
  match (`validateServerTrust` evaluates `SecPolicyCreateSSL(true, host)`, `RemoteCertificatePinning.swift:231-250`). Spec: the host
  certificate's SAN includes every address the link may carry that is not a public-CA name (the LAN IP too), or an IP link is refused at mint in words.
- **C4 (Pro as host; a naming inconsistency, NOT proven to be the cause of the failure).** The address is derived from `ProcessInfo.processInfo.hostName`
  (`autoLocalBaseURL`, `RemoteAccessConfig.swift:64-71`); the engine's Bonjour record uses `socket.gethostname()` the same way (`discovery.py:64-66`, `:162`), and the
  client's own-name filter uses `ProcessInfo.hostName` too (`MacRemoteClientPairingSection.swift:109`), so the three agree with each other and differ from what
  macOS's own mDNS publishes. On the Pro that is the directory/DNS name `UNB-C02F45GAQ05P` while the Bonjour LocalHostName is `macbook-pro-m1`. The Pro's certificate is
  `CN=unb-c02f45gaq05p.local` (the Remote Access folder says the same) and the Pro's own resolver does map that name to its LAN IP, but the Air resolves
  **neither** `unb-c02f45gaq05p.local` nor `macbook-pro-m1.local` (the same mDNS failure as C1), so on this network the failure is the network's, and the name
  mismatch is only a second trap on a network where mDNS works: a link naming a name other than the one Bonjour publishes. Fix: the address uses the LocalHostName
  (`scutil --get LocalHostName`), `sharing.host-name-is-the-bonjour-name`. Needs a check on a network where mDNS works to know whether it bites.
- **C5.** Version drift: the Pro's engine is 2026.10.27, the Air's 2026.10.28. A client refuses a host built from another contract
  (`ContractCompatibility.mismatch`; its `headline` already names both versions and the older side,
  `fichero-api-client/…/ContractCompatibility.swift:36-77`) — fine, but only after the network step succeeded, and only on a Mac (§1: iOS never
  probes); nothing tells the person beforehand and the pair sheet on the Pro showed no version. See `sharing.version-mismatch-says-which-side`.
- **C6.** A stale or foreign `tailscale serve` forward holds the port (M4: raw TCP to `localhost:8000`; Pro: `:443` to another service). The engine
  refuses to overwrite it (correct; only its own old `tcp://127.0.0.1:8765` is replaced, `tailscale_serve.py:118-124`), logs a WARNING (`:158-160`) and the
  person is not told: sharing "on" with a tailnet address that answers "connection reset". `GET /api/pair/sharing` then offers the generic
  `tailscale serve --bg --https=8765 …` command (`_tailnet_serve_command`, `pairing.py:169-188`), which does not free the port. `sharing.stale-forward-says-so`.
- **C7.** Health says nothing about sharing (`remote_backend.enabled=false` while sharing): `sharing.health-reports-sharing`.
- **C8 (account creation).** "Create Account" with Owner on shows `undocumented(statusCode: 404 … content-length: 40 …)`. The body is
  `{"detail":"multi-user auth is disabled"}` (`_multiuser_disabled`, `api/routes/auth/accounts.py:198-200`, the owner-password exception `:822-830`;
  `pairing.py:278-280`): `POST /api/users` and the people routes answer 404 while
  Multi-user is off (the persisted setting `multiuser.enabled`, or the env `FICHERO_MULTIUSER`, `security/multiuser.multiuser_enabled`, `:15-39`; **default off**).
  The app's `UsersStore.error(from:)` is `UsersStoreError(message: "\(response)")` (`Models/UsersStore.swift:164-166`) — it prints the raw generated enum. Fix: §5.

## 4. Behaviours — addresses and connecting

An **address** here is one `https://<name>:<port>` the host can be reached at. The host knows these, in this order of preference:
(1) tailnet MagicDNS name (`<machine>.<tailnet>.ts.net`) when Tailscale is up and the forward is made; (2) the `.local` Bonjour name; (3) the LAN IP.

- `sharing.address-choice` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (owner: "could we have an option to select that?") the Sharing pane (Add Device sheet and Advanced) lists **every
  address this Mac can be reached at**, each with a plain label and a live test result, and lets the person choose which goes into the link. Rows:
  "Tailscale — `macbook-air-m1.tail677e72.ts.net`: works from anywhere your Tailscale is on", "This network (Bonjour) — `macbook-air-m1.local`: works only on
  the same Wi-Fi when the network allows it", "This network (IP) — `131.202.228.243`: works only on the same network". Each row shows a result of the host's own
  probe where it can know one (listening ✓, Tailscale forward ✓, certificate names it ✓) and says "not tested from another Mac" where it cannot: **the host can never see client isolation** (the campus /22 passed neither mDNS nor LAN traffic on 2026-10-30 while every host-side check was green), so a `.local` or IP row is never shown as "works", only as "listening"; the guest's try (`sharing.client-tries-every-address`) is the only test of reach. The default
  pick is the tailnet name when Tailscale is up and its forward is made, else `.local`, else the IP. A row that cannot work shows why in one line ("Tailscale is not
  running on this Mac", "port 8765 on your tailnet is used by another service; run `tailscale serve --https=8765 off` or choose another"). The engine owns the list:
  `GET /api/pair/addresses` → `[{kind, url, label, listening, reason}]` (reuses `tailscale_serve.detected_tailnet_url`, `bind_host.primary_lan_ip`, the discovery name);
  the app only draws it (four-architecture rule). Engine change adds a route: an OpenAPI regen follows, held. *Test (red first, when built):* `test_pair_addresses_to_spec.py` (exists): with a tailnet name the first row is the tailnet; with none it is `.local`; a `.ts.net` row says why when the forward is not ours; no row is loopback.
- `sharing.link-carries-every-address` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the pairing payload (QR and link) carries an ordered list of every usable address plus the chosen first one: `{"api_url": <chosen>, "alt_urls": [...], …}` (`alt_urls` optional; an old client ignores it, an old link has none). Each address carries its own trust rule (`.ts.net`: system TLS, no pin; others: the one `spki` pin, which is the same key whatever the name). Never a loopback address (`PairedHostEndpoints` already forbids it). The payload stays small enough for a QR at correction level M (≤ 3 addresses, ≤ ~600 bytes of JSON). *Test:* `test_pair_payload_carries_every_address_to_spec.py` (exists) for the engine's list and `PairingPayloadTests.swift` (exists) for the Swift encode/decode, both old-link and new-link shapes. *Built:* (#6431) the three places that compose a link (the project Share sheet's copy and link, the Settings pane's per-address copy and QR) put the chosen address first and every other address that can work after it, Tailscale before This network, at most three (`PairingLinkAddresses`); one pin serves them all, so a Tailscale-first link still carries the pin the `.local` name needs; the joiner already tried them in order and said which answered. *Tests:* `PairingLinkAddressesTests.swift`.
- `sharing.client-tries-every-address` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (C1, C2; owner's failure) pairing and reconnecting try the link's addresses **one after another, in the link's order, each with a 5-second budget** for name lookup + connect + TLS + the first byte of an unauthenticated `GET /api/health` (a `URLSessionConfiguration` with `timeoutIntervalForRequest = 5` for the probe only; the transport's default 60 s stays for everything after), and stop at the first that answers. Sequential, not a race: a race hides which address failed and why, and three addresses cost at most 15 s. The probe is the health call, so the pin/name check (TLS) and the version check (`contract`) happen on the address that answered, before any code is sent. All attempts are reported, the first success is named, and the paired host records every address that answered (so the failover `PairedHostEndpoints` has the others; the ones that did not answer are kept too, marked, for a later network). With the result the person reads, in plain words, what happened for each, e.g.:
  "Connected through Tailscale (macbook-air-m1.tail677e72.ts.net). The local-network address (macbook-air-m1.local) did not answer: this network does not let Macs find each other by name."
  If none answers: "Could not reach macbook-air-m1. Tried Tailscale (…): no answer in 5 s — is Tailscale on this Mac? · macbook-air-m1.local: this Mac cannot find that name on this network · 131.202.228.243: no answer in 5 s — the network may keep devices apart." A bare "The request timed out" or a code (-1001, -1003, -1004, -1200) never reaches the person. Only after TLS and an HTTP answer does the pin/code stage begin, so "the Mac answered" is distinct from "the code was wrong". *Test:* `PairingAddressTryTests.swift` (exists): fake transport, address 1 hangs, address 2 resolves-fails, address 3 answers → success names 3 and lists 1 and 2 with their reasons; all fail → the sentence lists every one; each attempt capped at 5 s (injected clock).
- `sharing.failure-names-the-step` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) every pairing/connect failure says which of these steps failed, in this order, and the fix (the person never sees a code or an enum). Steps and sentences:
  1. **Link** — "This isn't a Fichero pairing link." / "This link is for an older Fichero. Ask for a new one." (`RemoteClientPairingError.invalidInviteLink`)
  2. **Name** — `NSURLErrorCannotFindHost` (-1003): "This Mac can't find *host.local* on this network. Try the Tailscale address, or put both Macs on the same Wi-Fi." (`.ts.net`: "…Tailscale isn't running on this device.")
  3. **Reach** — -1001 timed out / -1004 refused / -1009 offline / -1005 lost: "*host* didn't answer in 5 seconds. Is Fichero open on *host*, and is Sharing on? (If you are on a campus or hotel network, it may keep devices apart: use Tailscale.)"; refused: "*host* is on, but Fichero isn't listening there: turn Sharing off and on."
  4. **Local network permission (iOS)** — see `sharing.ios-local-network-permission`.
  5. **Certificate** — -1200/-1202: pin mismatch: "*host* showed a different security key than the link. This may be a different Mac with the same name. Scan or paste a new link from *host*." Name mismatch (SAN): "*host*'s security certificate doesn't name the address in the link. Turn Sharing off and on on *host* so it makes a new one."
  6. **Code** — 401 `invalid or expired pairing code`: "That code was used or has expired (codes last 10 minutes). Make a new one on *host*."; 429: "Too many tries. Wait a minute."
  7. **Person** — 401 `person required`: "This library uses accounts. Enter your username and password."
  8. **Version** — `contractMismatch`: "*host* runs Fichero 2026.10.27 and this Mac 2026.10.28. Update the older one." (both versions named; `sharing.version-mismatch-says-which-side`)
  9. **Library** — `libraryPathNotConfirmed`: "*host* didn't give this device that project. Ask for a new link."
  10. **Stopped** — the host stopped sharing / revoked this device: `sharing.stopped`, `sharing.revoked` words from `library-sharing.md`.
  A `.ts.net` address tried **by its 100.x number** fails TLS (seen: `tlsv1 alert internal error`; Tailscale's certificate names the MagicDNS name only), so a link never carries a 100.x address and step 5 for a `100.*` host reads "Tailscale addresses work by name, not by number. Ask for a new link."
  Each step's sentence is a single table in one Swift file keyed by a typed `PairingFailure` case, so a test can walk the table; the raw `NSError` code goes to the log only (and to **Copy details**). The Mac sheet (`MacRemoteClientPairingSection.swift:181`) and both iOS sheets show the table's sentence, never `localizedDescription`. The CLI's `check_trust` (`fichero_cli/pairing.py:87-110`) has its own four sentences today; they are kept in step with the table by name (`test_cli_pair_words_match_the_spec.py`, exists: each CLI refusal contains the step's key phrase). *Test:* `PairingFailureWordsTests.swift` (exists): every `PairingFailure` case has a non-empty sentence that contains no digit-only code and none of "undocumented", "NSURLError", "statusCode", "SSL"; every `URLError.Code` the transport can throw maps to a case. *Built:* (#6431) a step that fails with an error that is not a network error is its own sentence in step 3 (`PairingFailure.unexpected`): "*host* and this Mac could not finish this; try again, and if it happens again use Copy Details", with the real error in the log, no longer "didn't answer"; step 5's pin mismatch on a `.ts.net` address adds that a Tailscale web proxy replaces the key and the pass-through port is the one to use. *Tests:* `PairingFailureWordsTests.swift`.
- `sharing.both-clients-run-the-same-checks` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) a Mac and a phone pair through **one** sequence: decode → try addresses (`sharing.client-tries-every-address`) → contract check → `POST /api/pair` → token → `GET /api/authz/libraries` confirms the invite's library (or, with no library in the link, lists the host's and lets the person pick; never `missingLibraryPath` before the network) → persist → (Mac only) engine host switch. Before this step the Mac skipped the library confirm and iOS skipped the contract check, so a phone paired into a host whose contract it could not read and a Mac persisted a library path nothing confirmed (#3372's rule); both now call the one sequence (`pairAndPersistHost`), and the sequence undoes a pairing a later step refused. *Test:* `PairingSequenceTests.swift` (exists): one fake host; the Mac entry point and the iOS entry point produce the same ordered call log (`health`, `pair`, `authz/libraries`), and a contract mismatch stops both before `pair`.
- `sharing.host-name-is-the-bonjour-name` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (C4) the `.local` name in the address, in the certificate and in the Bonjour record is the Mac's **LocalHostName** (what mDNS publishes: `scutil --get LocalHostName`), never `ProcessInfo.hostName` (the DNS/directory name). On the Pro, `ProcessInfo.hostName` = `UNB-C02F45GAQ05P` and LocalHostName = `macbook-pro-m1`; the Remote Access folder, the CN and the link all say `unb-c02f45gaq05p.local`, which no other Mac resolved on this network (the network, C1, is the proven cause; the name differs from what Bonjour publishes). The engine's own check: the Add Device sheet verifies the name resolves **on this Mac** (`dns-sd -G`/`getaddrinfo`) before showing it, else drops that row. *Test:* `RemoteAccessConfigTests` (exists) with an injected local-host-name source; and the engine's cert SAN follows the address passed (`test_remote_access_tls.py`, exists).
- `sharing.certificate-names-every-address` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (C3) the host certificate's SAN holds every non-public-CA address the link can carry: the `.local` name, the LAN IP, `127.0.0.1`, `localhost` (today: the name, `127.0.0.1`, `localhost`; the LAN IP rides `FICHERO_LAN_HOST` into `subject_alt_hosts` only on `--prepare-local-access`). When the LAN IP changes (DHCP) the certificate is made again (the folder name hashes URL + SANs, so a changed SAN set is a new folder and a new pin) **and the person is told the old links are void** (the pin changed). Today every new folder gets a **new** EC key (`_generate_material`, `remote_access_tls.py:244`), so any SAN change voids every link and every paired device's stored pin. The pin follows the SPKI (key), so re-using the key across a SAN change keeps links valid: preferred — one key per Mac (`Remote Access/key.pem`), a certificate re-issued per SAN set (open question 5). *Test:* `fichero-server/tests/unit/security/test_remote_access_tls.py` (exists) + `test_certificate_keeps_its_key_when_a_name_is_added_to_spec.py` (exists): two `prepare_remote_access_tls` calls with a grown SAN list return the same `spki_pin`.
- `sharing.trust-rule-is-one-function` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) which addresses need a pin is decided in **two** places today: `RemoteCertificatePinning.usesPublicCertificateAuthority(host:)` (`RemoteCertificatePinning.swift:71-76`; the Swift mint and client sides share it through `advertisableSPKIPin`/`resolvedSPKIPin`, `RemoteClientPairingFlow.swift:131-160`) and the CLI's `_is_public_ca` (`fichero_cli/pairing.py:60`). Both say: `.ts.net` → system trust, no pin; anything else → the link's pin, enforced by SPKI after the hostname policy (`validateServerTrust`, `:231-250`), and a pinned host whose certificate does not name the address is refused. The rule is written once as a table of (host → rule) that both a pytest and a Swift test read, so the two cannot drift. *Test:* `test_trust_rule_table_to_spec.py` (exists) over the CLI and `RemoteCertificatePinningTests.swift` (exists; add the table cases: `x.ts.net`, `x.local`, `192.168.1.2`, `100.64.0.1`, `localhost` refused).
- `sharing.stale-forward-says-so` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (C6) when `tailscale serve` for the sharing port is held by a forward Fichero did not make (a raw TCP forward, another service), the engine refuses (correct, `tailscale_serve.ensure_forward`, `:120-124`; its own old raw forward is the one it replaces, `:118-119`) and the Sharing pane and the address list say it in one line with the command that frees it: "Port 8765 on your tailnet already goes to localhost:8000, not to Fichero. Run `tailscale serve --tcp=8765 off`, then turn Sharing off and on." Today the pane offers the generic `tailscale serve --bg --https=8765 …` line instead (`_tailnet_serve_command`, `pairing.py:169-188`), which fails the same way. The engine reports the conflict in `GET /api/pair/addresses` (`reason`) and `GET /api/pair/sharing` (new field `tailnet_serve_conflict: {"holds": "tcp://localhost:8000", "free_with": "tailscale serve --tcp=8765 off"}`; `tailnet_serve_command` becomes None while a conflict stands). *Test:* `fichero-server/tests/unit/security/test_tailscale_serve.py` (exists) + `test_tailnet_conflict_is_reported_to_spec.py` (exists): a fake `serve status` naming a foreign target → `ensure_forward` raises, `_sharing_state` carries `tailnet_serve_conflict` and no `tailnet_serve_command`.
- `sharing.link-never-names-a-dead-tailnet` — **[PARTIAL]** (→ #6358; continues `sharing.stale-forward-says-so`, `sharing.link-names-a-listener`) app. A saved `.ts.net` sharing address is not an always-working link: when the engine says no forward of Fichero's reaches the sharing port (`tailnet_forward` none or foreign) the Tailscale row is greyed with the engine's reason, the pair link and QR name the Mac's LAN address instead, and with no LAN address there is no link and the reason shows. The engine's bind is not changed (loopback and the named LAN address only, #5897). *Exists:* the row rule and the fallback (`AddressChoiceModel.rows(…, lanIP:)`, `AddressChoiceModelTests.swift`; Swift unbuilt, the link unseen on a Mac). *Left:* why the app did not make the forward on the 2026-11-05 Pro (sandbox, or the engine log's warning), the run. *Tests:* `fichero/Tests/Unit/general/Sharing/AddressChoiceModelTests.swift`.
- `sharing.link-grants-its-project` — **[PARTIAL]** (→ #6359; continues `sharing.ios-bad-library-path`, `sharing.link-names-a-listener`) engine and app. A pairing link minted for a project reaches that project on the paired device: the redeem puts the project on the host's known-library list, gives the owner's own device an owner role on it when the project never had a roles row (one the app made on first run did not), and the guest compares the link's path with the host's list by NFC and symlink-resolved path, taking the host's spelling, and logs both lists when it still finds no match. A registry that cannot be written refuses the redeem with a 503 before any account, grant or device is made and the code is spent, and the 503 does not count as the guest's failed attempt (`test_pair_redeem_refuses_unwritable_registry.py`). Today (2026-11-05, the Air pairing with the Pro's "Isthima GHG") the guest was told "didn't give this device that project" with the host's list empty. *Exists:* `_library_a_link_is_for`, `_register_link_library`, the owner role at redeem (`test_link_grants_its_project_to_spec.py`), `PairingSequence.samePath` and the log line (`PairingSequenceTests.swift`; Swift unbuilt). *Left:* a non-owner person's project role stays the owner's choice (not granted by a link), the run on the Air and the Pro. *Tests:* `fichero-server/tests/unit/transport/test_link_grants_its_project_to_spec.py`, `fichero-server/tests/unit/transport/test_pair_redeem_refuses_unwritable_registry.py`, `fichero/Tests/Unit/general/Sharing/PairingSequenceTests.swift`.
- `sharing.health-reports-sharing` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (C7; answers the lead's question 2: `remote_backend.enabled=false` is the *ssh-loopback/ACENET env* status, not sharing, not client state) `GET /api/health` gains a `sharing` block next to `remote_backend`: `{on, listeners: ["127.0.0.1:8765","131.202.228.243:8765"], addresses: [{kind,url,listening}], certificate_names: [...], tailnet_forward: "ours"|"foreign"|"none", multiuser: bool, paired_devices: n}`; no secrets; `remote_backend` is renamed in the docs "ssh-loopback status" and its `enabled=false` no longer reads as "sharing off". Testers and the Add Device sheet read this instead of guessing. *Built: the response carries a `sharing` block.* *Test:* `test_health_reports_sharing_to_spec.py` (exists).
- `sharing.version-mismatch-says-which-side` — **[PARTIAL]** (→ #5049) (C5; `RemoteClientPairingError.contractMismatch` exists, `#5047`) the refusal names both versions and which Mac is older; and the **host's** Add Device sheet shows its own version beside the link so the person sees "Fichero 2026.10.28" before the guest tries. Health already carries `backend_version` and `contract`; shown nowhere on the host. *Test:* `PairingFailureWordsTests` (the version case), above.
- `sharing.pair-answers-in-words` — **[OK]** `POST /api/pair` with a bad code answers `401 {"detail":"invalid or expired pairing code"}` (seen live on the Air over the tailnet, 2026-10-30); `422` for a malformed body is the framework's field list (the app reads it as such: `sharing.pair-code-refusals-in-words`).
- `sharing.listener-is-lan-only-not-wildcard` — **[OK]** (seen 2026-10-30 on the Air, the Pro, the M4: `lsof` shows `127.0.0.1:8765` plus one LAN address; never `*`). Binding the LAN address, not `0.0.0.0`, means an address-change (DHCP renewal, Wi-Fi ↔ Ethernet) leaves the listener on a dead IP: `sharing.listener-follows-the-network` **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the engine notices (or the app tells it) when the Mac's primary address changes, rebinds and re-makes the link's address list; until then the Sharing pane says "This Mac's network address changed. Turn Sharing off and on." *Test:* `test_listener_rebinds_when_the_address_changes_to_spec.py` (exists; fake `primary_lan_ip`).
- `sharing.listener-slots-bind-alone` — **[PARTIAL]** (→ #6367; t52, live 2026-11-06) engine. With Sharing on, each listener (the loopback port, the LAN address) is bound on its own: one that fails never closes the others, so Tailscale, the CLI and MCP keep the loopback port when the LAN address is gone; a port the engine being replaced still holds is tried again for about two seconds; a LAN address the Mac no longer has is replaced by the address it has now; the log names the address, the slot and the error. Seen: the Air had Sharing on and nothing on 8765, not even loopback, because one bind error closed every listener and the engine ran socket-only until restarted. *Built:* `__main__._bind_sharing_listeners`. *Not built:* a live look on two Macs. *Tests:* `test_listeners_bind_on_their_own_to_spec.py`.
- `sharing.listener-binds-private-interfaces` — **[PARTIAL]** (→ #6383; owner ruling 2026-11-07, a reasoned extension of #5897) engine and app. With Sharing on the engine also listens on every private interface address of the Mac (RFC 1918 or IPv4 link-local: the Thunderbolt bridge's 10.10.10.x, a second Ethernet port), each its own slot beside the loopback port and the named LAN address; never `0.0.0.0`, never a public address it was not named, never Tailscale's 100.64/10 (Tailscale reaches the loopback port through `tailscale serve`); with Sharing off only the loopback port. An IP or `.local` address with no port (a saved sharing address `https://10.10.10.1`, a typed host, a link from an older host) means the engine's port 8765, never 443, so the port travels through the link, the redeem, the saved server and every later call. A pasted address where a link goes is "This isn't a pairing link", naming what was pasted; a host whose answer this app cannot read stops with the address, its port and the call named (`10.10.10.1:8765 answered its project list (GET /api/authz/libraries), but not in a form this Fichero can read`), the decoder's words to the log only. Seen 2026-11-07: the Air bound 127.0.0.1 and its campus address only, so 10.10.10.1:8765 refused the Pro and the M4; the M4 then called 10.10.10.1 on 443; the M4 showed "The data couldn't be read because it isn't in the correct format". *Built:* `bind_host.private_interface_ips` (getifaddrs, no DNS), `__main__._listener_hosts`; the port in `AddressChoiceModel.rows` and `validatedRemoteURL`; the pasted address in `RemoteClientPairing.pairingFields(fromInviteOrPayload:)`; the named call in `PairingSequence.run`. *Not built:* the cause of the M4's decode error itself (no console text yet), a bare address typed into Connect to Library that pairs without a link (Step 8.9's typed address), a live look across the Pro, the Air and the M4. *Tests:* `fichero-server/tests/unit/transport/test_listener_binds_private_interfaces_to_spec.py`, `Sharing/AddressChoiceModelTests.swift`, `Sharing/HostChoicesTests.swift`, `Sharing/PairingSequenceTests.swift`.
- `sharing.listener-follows-the-network-by-itself` — **[PARTIAL]** (→ #6367; t52) app. When health says the Mac's address changed under a running Sharing listener (`sharing.address_changed`, `sharing.listener-follows-the-network`), the app restarts its own engine once (at most once a minute, never a remote engine), which binds the address the Mac has now, so a link minted after names an address something listens on. One restart per change: a restart that did not cure it is not repeated until health stops saying "changed". The engine compares the address it bound, never the `.local` name the app asked for (t73, live on the Air: name against IP read "changed" on every check, so the app restarted its engine every minute and there was never a listener or a pin). *Built:* `SharingAddressFollower`, `AppState.followSharingAddress`. *Not built:* a live look after a Wi-Fi change. *Tests:* `SharingFollowsTheNetworkTests.swift`.
- `sharing.link-counts-a-live-tailnet-forward` — **[PARTIAL]** (→ #6367, #5317; t55, t58) engine. Links point to Tailscale: the engine makes Fichero's own forward at start when Sharing is on and Tailscale runs (`tailscale_serve.start_for_engine`, already built; seen live on the Air: `https://macbook-air-m1.<tailnet>.ts.net:8765 -> https+insecure://127.0.0.1:8765`) and makes it again after every restart. Minting a code counts that live forward to the loopback listener as somewhere to listen, so a `.local` sharing address with no LAN listener is not refused while the forward is up, and the link names the tailnet address first (the LAN addresses after it). With nothing bound at all it is still refused. An engine that makes no forward says why in its log, never nothing. *Built:* `network_listener_gap(..., tailnet_forward=)`, the mint's check (`forward_state == "ours"`), the log line. *Not built:* a live look on the Air. *Tests:* `test_link_counts_a_live_tailnet_forward_to_spec.py`.
- `sharing.share-this-mac-is-this-mac` — **[PARTIAL]** (→ #6367; t52 second finding) app. Share this Mac speaks only for this Mac's engine: while the app shows another Mac's library, the Settings switch is disabled with "Sharing is set on the Mac that runs this project" (`PairingBlocker.engineIsRemote`) and the project Share sheet mints no link ("This project is hosted on another machine"). *Built:* both guards (`EngineConfig.engineIsLocal`). *Not built:* sharing this Mac's own projects while a shared library is open (needs this Mac's engine running beside the other host: Step 8.6). *Tests:* none yet. Not built: `ShareThisMacIsThisMacTests.swift`.
- `sharing.firewall-prompt-says-what-to-click` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the macOS firewall's "Do you want Fichero Server to accept incoming network connections?" prompt appears the first time the LAN listener binds (the unsigned-prompt behaviour depends on the signature; the Air's firewall is on and both bundles are already allowed). With Sharing on and the firewall on, the Add Device sheet reads `socketfilterfw --getappblocked`-equivalent state through the host app (`/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate`, `--listapps`; both readable without admin) and when the engine is *not* allowed says: "macOS is blocking other devices from reaching Fichero. Open System Settings › Network › Firewall › Options and allow Fichero Server." (and does not offer a link that cannot work). *Seen on the Air: allowed, therefore not the cause of the owner's failure.*
- `sharing.stale-server-holding-the-port` — **[PARTIAL]** (→ #5049) (an old engine on 8765: `uds_claim` refuses a second engine on the *socket*; for TCP `__main__` logs "Port %d is already in use on %s. Stop the existing backend process and retry." and exits) the app's engine start shows that line as a plain sentence ("Another copy of Fichero's server is using port 8765. Quit it (Activity Monitor › Fichero Server) or restart this Mac.") instead of "engine failed to start". The host's Sharing pane shows the same line next to the switch. *Test:* `test_port_in_use_message_to_spec.py` (exists).
- `sharing.token-expired-or-rotated` — **[PARTIAL]** (→ #5049) a paired device's token expires and renews (`/api/pair/devices/renew`); a host that revoked the device or whose engine state was reset (new app database) answers 401 to the device token: the client says "*host* no longer knows this Mac. Ask for a new link." and keeps the host listed greyed (`sharing.sidebar.off-greys-row`). A rotated bootstrap token on the host never affects a paired device (the bootstrap secret is never a device token, `sharing.loopback-is-owner`). *Test:* `test_device_pairing_e2e.py` (exists: revoke → 401); the Swift sentence needs `PairingFailureWordsTests`.
- `sharing.tailnet-down-says-so` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) with Tailscale off on the guest (no `100.x` route) a `.ts.net` address does not resolve or does not connect: sentence "Tailscale isn't running on this Mac." (step 2/3 above, chosen by the host name's suffix `.ts.net`), with "Open Tailscale" as the action. On the host: Tailscale down → the tailnet row is "Tailscale is not running on this Mac" and not the default; Tailscale not installed → the row reads "Install Tailscale to share beyond this network" (open question 6). *Test:* `test_pair_addresses_to_spec.py` (above): `tailscale_cli()` None → the tailnet row carries that reason and is not first.

## 5. Multi-user: the Create Account 404 (C8)

How it is enabled (code read): Multi-user is **default OFF** (`security/multiuser.multiuser_enabled`, `:15-39`: env `FICHERO_MULTIUSER` wins when set, else the persisted `multiuser.enabled` setting, else off; account rows never turn it on). It is switched by **one** route, `PUT /api/pair/multiuser {enabled}` (`pairing.py:589-608`), the audited, undoable, app-wide action `sharing.set_multiuser` (`:626-643`, `owner_scope="app"`), by the owner's **signed-in key session** (403 "sign in as the owner to change Multi-user" otherwise, `:601`; never the bootstrap token) and only once the owner **has chosen a password** (`owner_password_gap`, `multiuser.py:69-76`: 409 "Multi-user needs the owner's account to have a password first: set one, then turn it on"). The owner's password is set by `PATCH /api/users/{owner_id} {password}`, the one change allowed while it is off (`accounts.py:819-830`; at least `MIN_NEW_PASSWORD_LENGTH` characters, 422 in words, `:136-140`). `POST /api/auth/first-run` (`accounts.py:1049`) makes the owner (key-only, random password) and `POST /api/auth/migrate-owner` (`:1079`) gives an **existing** owner row its first key; both local-only (UDS + launch secret). So `migrate-owner` is **not** the step that turns Multi-user on; it is the repair for an owner made before keys existed. The order is: **owner exists with a key (first-run or migrate-owner) → owner chooses a password → PUT multiuser true → engine restart is not required by the engine (the app's spawn no longer passes `FICHERO_MULTIUSER`, `EmbeddedBackendService+Spawn.swift:372`) → create accounts.**

- `sharing.multiuser-always-on` — **[GAP]** (#3284, P1, owner ruling 2026-11-08: multi-user is ALWAYS ON, there is no switch, every connection is authenticated; `transport/multiuser-always-on.md` slice 10 is the engine side) the Multi-user switch is gone from Settings › Sharing, from Set Up and from the engine (`PUT /api/pair/multiuser`, `multiuser.enabled`, `FICHERO_MULTIUSER` all retired, with the on-open migration that reads an old `false` as nothing); every connection that is not the app's own loopback-with-launch-secret carries a signed-in session or a person-bound invite and is otherwise 401 in words; the wording "with Multi-user off" in this spec's bullets and steps is retired by this ruling (a Note under each). Acceptance: there is no switch anywhere in the app or the contract; a request from another machine with no session is 401 "sign in"; the owner's own app on its Mac still opens its libraries with no sign-in step (the launch secret); an old library whose settings carried `multiuser.enabled: false` opens and behaves as always on.
- `sharing.multiuser-off-says-so` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) with Multi-user off, the Sharing pane (Accounts row and the `+` / Create Account sheet) says it in one sentence and offers the next step instead of letting a create fail: "Accounts are off. Turn on accounts so other people can have their own sign-in." with **Turn on accounts…**, which (1) asks the owner to choose a password if none was chosen (the engine's `owner_password_gap` is read from `GET /api/pair/sharing` → a new field `multiuser_blocker`, else the app guesses), (2) calls the owner password `PATCH`, (3) `PUT /api/pair/multiuser`, (4) re-reads state and then enables Create Account. The Create Account button is **disabled with the reason beside it** while off ("turn on accounts first"), so the 404 cannot be reached by the UI. If the owner has no key (an owner from before keys): the same button runs `migrate-owner` first (UDS + launch secret, the app holds it) and says "Setting up your sign-in key…". *Test:* `AccountsOnSequenceTests.swift` (exists for the sequence; the pane's own test is still to add): off → Create disabled with the sentence; the on-sequence calls password, then the switch, then reload; a 409 password-gap becomes the password prompt, not an error. Engine: `fichero-server/tests/unit/security/test_owner_session_sets_the_switch_5908.py` (exists) pins the order. #6565: step (2) uses the local-only owner-password call (`POST /api/auth/owner-password`), not the people `PATCH`, which needs a key session the app may not have; the sheet shows the engine's refusal in words and never goes back to asking when a password was already typed. Built (Swift, needs compile): `AccountsOnSequence` (`needsPasswordPrompt`, `sentence(for:)`), `UsersStore.setOwnerPassword`, `TurnOnAccountsSheet`; test `fichero/Tests/Unit/general/Sharing/AccountsOnSequenceTests.swift`. Not tested: the drawing.
- `sharing.undocumented-never-reaches-the-person` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) no generated-client `.undocumented(statusCode:payload)` value, and no `"\(response)"` interpolation of a response enum, is ever shown. `UsersStore.error(from:)` (`UsersStore.swift:165`: `UsersStoreError(message: "\(response)")`) is the one found; the rule is global: one function `PersonFacingError.message(for: statusCode, detail: String?, context:)` maps (a) the engine's `detail` string when the body is the framework's `{"detail": "..."}` (`EngineErrorDetail.message(from:)` already reads it and is used by `PairingTypes`), (b) otherwise by status: 401 "Sign in again.", 403 "You don't have permission to do that.", **404 "That isn't available on this Mac right now."** + the context's fix, 409 the engine's words, 422 the field list, 429 "Too many tries, wait a minute.", 5xx "Fichero's server had a problem; try again, and if it keeps happening quit and reopen Fichero." For Create Account's 404 with `multi-user auth is disabled` the context says "Accounts are off. Turn on accounts first." (`sharing.multiuser-off-says-so`). A guard `scripts/check_swift_transport.py` rule (the file's rules 1-4 guard sessions, WKWebView, http and SSE; this is a new rule): a Swift file that interpolates a `response`/`undocumented` value into a string shown to the person fails the check; the 387 `.undocumented` sites in `fichero/fichero` (grep 2026-10-31, tests excluded) are listed, not rewritten at once, but each new one uses the function. *Test:* `PersonFacingErrorTests.swift` (exists): no mapped sentence contains "undocumented", "statusCode", "content-length" or "HTTPBody"; the 404 multi-user body maps to the accounts-off sentence; an unknown status maps to the generic line; plus `fichero-server/tests/unit/scripts/test_check_swift_transport.py` for the new rule.
- `sharing.multiuser-404-is-a-409-in-the-engine` — **[PARTIAL]** (engine done; `/api/auth/me` stays 404 because the app's gate reads it as "no accounts") (→ #5049, umbrella; file its own issue when taken) the engine answers a *correct, understood* state with **404** `multi-user auth is disabled` (`accounts.py:200`, `828-830`, `pairing.py:280`). A 404 says "no such thing" and is why a generic client reads it as "route missing". Proposed: **409** with the same `detail` (the state refuses the request, as every other refusal in this module is a 409) and a `code: "multiuser_off"` key in the body so clients branch on a name. This is a contract change (new status on several routes, OpenAPI regen, held; and every test that pins 404 changes), so it is **built in the engine** (the app's wording of it waits on the Mac pane). The app does not wait for it (`sharing.undocumented-never-reaches-the-person` handles 404 either way).
- `sharing.multiuser-needs-sharing-for-anyone-else` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) Multi-user on with Sharing off is valid (accounts on this Mac only); the pane says so ("Other people can sign in only on this Mac until Sharing is on").

## 6. Set Up asks about sharing and accounts

The owner's rule: Fichero's Set Up must tell the person about sharing and multi-user and ASK, not bury them in Settings › Sharing. It follows the Set Up stage pattern (`Views/Onboarding/Stages/SetupStagePage.swift`, `Models/RecipeSetupStore+Stages.swift`; engine list `recipes/stages.py` `STAGES`, served by `GET /api/recipes/stages`, `api/routes/system/recipes.py:525-541`; each question a `Question(key, ask, kind="yes-no", default=False)` whose answer is a `job_answers` key saved in the project's `recipe/setup.yaml`, as Prepare Images' `two_pages_per_image`, `stages.py:57`; the app writes such an answer with `jobAnswers[question:] = .yesNo(true)`, `RecipeSetupStore+LeftOff.swift:27`).

A new stage, **Sharing and accounts** (`id: "sharing"`, no jobs, no recipe steps: it carries questions only), page after the material questions and before Ready. Default OFF for both. Nothing is turned on by merely reaching the page.

- `sharing.setup-stage-is-offered-without-jobs` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) today `listing` drops any stage none of whose jobs Start runs or a tool does by hand (`offered`, `stages.py:227-230`, applied at `:242-243`), so a questions-only stage is **never listed**. `offered` also accepts a stage with no jobs and at least one question. *Test:* `test_sharing_stage_to_spec.py` (below): the `sharing` stage is in the listing with `jobs: []`.

- `sharing.setup-asks-sharing` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the first question: **"Let other people or your other Macs open this library?"** — *Yes / No* (default No). Under it, one grey line: "Others open it by a link or QR code. Nothing is shared until you say yes." Yes = host sharing on **for this Mac** (the engine's listener is per Mac, not per library: the one Sharing switch of Settings › Sharing; see `sharing.setup-answer-is-per-library`) and shows, in place: the **address choice** (`sharing.address-choice`: the rows, the default picked, each with its test result), the **pair link and QR** (Copy Link, the 10-minute code renewing, `sharing.settings.add-device-sheet`), and the one-line status ("Sharing on your network and Tailscale"). A failure to turn it on is the one sentence of `sharing.failure-names-the-step` / `sharing.stale-forward-says-so`, never the engine's internals. No = nothing starts; if sharing was on, turning it off stops it as the Sharing switch does (`sharing.off-closes-the-guest`: guests get the one sentence). Works on iOS/iPad as a *client* question instead (§7): "Connect this iPhone to a Mac?".
- `sharing.setup-asks-accounts` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the second question: **"Give each person their own account?"** — *Yes / No* (default No). Under it: "Each person signs in with their own name, and what they change is recorded under it. For anyone else to join, sharing has to be on as well." Yes = Multi-user on: the **owner path is created** — if the owner has no key the app runs `first-run`/`migrate-owner`, asks the owner to **choose a password** (a field right there, the 8-character rule of `multiuser.invite-registers-public-key`), `PATCH`es it, then `PUT /api/pair/multiuser true` (`sharing.multiuser-off-says-so`'s sequence), so no later step can meet "404 multi-user auth is disabled". It then offers "Add a person…" (the `+` sheet, `sharing.settings.accounts-add-sheet`). Yes with sharing No is allowed and says what it means (`sharing.multiuser-needs-sharing-for-anyone-else`); Yes to sharing with accounts No is allowed (anyone with a link gets the owner's view is the device-bound rule, `sharing.device-acts-as-its-binding`; the page says "Anyone you give the link to can open this library as you. Turn on accounts to give people their own sign-in."). No = Multi-user off; if it was on, turning it off asks once ("Everyone returns to being the owner. Turn off?") because it changes what other people see (`sharing.set_multiuser` is audited and undoable).
- `sharing.setup-answer-is-per-library` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the two answers are **saved with the library's Set Up answers** (`recipe/setup.yaml`, keys `sharing_open_to_others`, `accounts_each_person`) so Set Up… reopens with them and a shared copy of the library carries the intent. **They are not the switch itself**: sharing and Multi-user are properties of the **Mac's engine** (one listener, one app-wide `multiuser.enabled`), not of a library (`sharing.sidebar.host-mark`, `PUT /api/pair/multiuser` is app-wide). So: the saved answer is "the person wants this library open to others"; the *switch* is the engine's state. The page therefore always **shows the engine's real state** (read from `GET /api/pair/sharing`, `sharing.health-reports-sharing`) and, when the saved answer and the engine disagree (answer Yes, sharing off because it failed or was turned off in Settings), says so with the action ("You asked for this library to be open to others, but sharing is off. Turn on"). A library the person turns sharing on for is the *shared* library (`sharedLibraryPath`); sharing on/off for a different library on the same Mac is the per-library **share** (`POST /api/authz/share`, the project Share sheet, `sharing.settings.project-share-sheet`), unchanged. Open question 3 below.
- `sharing.setup-answers-change-later` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) Settings › Sharing's switch, Multi-user row, Devices list, Add Device sheet and Connect sheet **are the same controls** as the page's (the page hosts the same views, `SharingPaneModel`/`AddDeviceSheetModel`/`ConnectSheetModel`, not copies), so a change in either shows in the other at once and writes the one stored state; the page's saved answers follow the engine on next open (`sharing.setup-answer-is-per-library`). The page ends with "You can change this any time in Settings › Sharing." *Test:* `SharingStageTests.swift` (exists): default both No and nothing started on reaching the page; Yes→ calls the same `applySharing`/multi-user sequence the Settings pane calls (one fake backend, call log compared); a Settings change is reflected on the page; accounts Yes with no owner key runs `first-run`/`migrate-owner` then password then switch, in that order, and never calls `POST /api/users` while off. Engine: `test_sharing_stage_to_spec.py` (exists): `GET /api/recipes/stages` lists the stage after the material stages, no jobs, two yes-no questions defaulting False, `job_answers` round-trip in `setup.yaml`.
- `sharing.setup-stage-wording` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the stage's title "Sharing and accounts"; its sentence: "Decide now whether other people or your other devices can open this library, and whether each person gets their own account. You can leave both off and change this later."; its example: none. No words about pins, certificates, HTTPS, restarts, ports or tokens (`sharing.settings.add-device-sheet`). The tester's check: the two questions appear verbatim, in this order, and neither is pre-answered.

## 7. iPhone and iPad

Same host flow as §1; the phone is a **client only** (no engine, `sharing.ios.unpaired-phone-opens-on-connect`). Read from code, no device. What the phone does with a link: `fichero://pair?payload=<base64 json>` (or `https://tubb.ca/apps/fichero/pair?payload=…`) → `.onOpenURL` (`FicheroApp_iOS.swift:164`) → `PairingIncomingLinkSheet` → `RemoteClientPairing.pairingFields(fromInviteOrPayload:)` (decode, https required, pin required unless `.ts.net`) → `pairAndPersistHost` → `POST <api_url>/api/pair` → `confirmLibraryAccess` → `persistPairedHost`. The iOS client trusts a self-signed host **only by the SPKI pin in the payload** (`RemoteCertificatePinning`, session delegate; an unpinned non-public host is cancelled); a `.ts.net` host by system trust.

The owner reports iOS cannot connect, cause unknown. Likeliest causes, ranked (no device access; each has the check a person or a test can run):

- `sharing.ios-link-has-one-address` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) (likeliest; the same as the Macs, C1) the link names one address, the `.local` name; iOS resolves `.local` only on a Wi-Fi network that passes mDNS and **requires the Local Network permission** to do so; on a campus or cellular network it never resolves. A phone often is on cellular or guest Wi-Fi, so this fails most. Check (person): open the link's host (`https://<host>.local:8765/api/health`) in Safari on the phone; "Safari can't find the server" confirms it. Check (test): `PairingAddressTryTests` (above) with a `.local`-first link and a tailnet alt address; the phone must pair over the second. Fix: `sharing.address-choice`, `sharing.link-carries-every-address`, `sharing.client-tries-every-address`.
- `sharing.ios-tailscale-not-on-the-phone` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the tailnet address works only if Tailscale is installed and connected on the phone (`ipad-mini` and `iphone-12-mini` showed *offline, last seen 120 d / 16 d* in `tailscale status` on 2026-10-30: the owner's phone/iPad are not currently on the tailnet). The app gets "cannot find host" for `…ts.net` and says nothing about Tailscale. Fix: `sharing.tailnet-down-says-so` with an "Open Tailscale" button (`tailscale://` / App Store link). Check (person): open `https://<machine>.tail677e72.ts.net:8765/api/health` in Safari on the phone; Check (test): `PairingFailureWordsTests` the `.ts.net` + -1003 case reads "Tailscale isn't running on this phone."
- `sharing.ios-local-network-permission` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) iOS shows "Fichero would like to find and connect to devices on your local network" the first time the app touches the LAN (`NSLocalNetworkUsageDescription` is set to "Fichero uses local network discovery to find a nearby Mac host for QR pairing." in the project settings, and `NSBonjourServices = [_fichero._tcp]` is in `Info.plist`). If the person **declined** (or it never appeared because the first touch was a direct IP connection rather than a Bonjour browse), every LAN connect silently fails: `NWBrowser` goes to `.waiting(.posix(.EHOSTUNREACH))`/`kDNSServiceErr_PolicyDenied`, and a direct connect to a LAN IP fails with -1009/-1001 and no prompt. The app does not read the denial (`NearbyHosts.swift` has no `.waiting`/policy-denied handling). Fix: on a LAN-address failure (private IP, `.local`) on iOS, say "Allow Fichero to find devices on your local network: Settings › Fichero › Local Network." with an **Open Settings** button, and let `NearbyHosts` surface `.waiting` as that line instead of an empty "Searching…". Check (person): Settings › Privacy & Security › Local Network › Fichero is on. Check (test): `NearbyHostsPolicyDeniedTests` (exists; a fake browser state `.waiting(PolicyDenied)` → the sentence).
- `sharing.ios-app-transport-security` — **[PARTIAL, read, not run]** (→ #5049) ATS blocks plain http; Fichero requires https for any remote host (`validatedRemoteURL(requireSecureTransportForRemote: true)`), and there is no `NSAppTransportSecurity` exception in `Info.plist` or the project settings, which is right for https. The risk is a **self-signed https** host: ATS rejects it before the app's trust delegate unless the delegate handles the server-trust challenge, which `RemoteCertificatePinning.resolveServerTrustChallenge` (`RemoteCertificatePinning.swift:189-228`) does for pinned hosts. A code read on 2026-10-31 found **no** `URLSession.shared` or `URLSession(configuration:)` call site in `fichero/fichero` (only comments in `StorageResourceURLProtocol.swift`), and `scripts/check_swift_transport.py` rules 1-4 forbid an unpinned engine-bound session, so this is not the likely cause; it stays listed because the guard runs over the whole tree, not per target, and a `WKWebView` pane (`DocumentKGWebPaneCoordinatoriOS.swift`) is the one place a non-URLSession trust path exists. Check (test): `scripts/check_swift_transport.py` keeps passing; `RemoteCertificatePinningTests.swift` (exists) covers the delegate. Check (person): the failure text would be "an SSL error has occurred and a secure connection to the server cannot be made" (-1200).
- `sharing.ios-certificate-name` — **[GAP]** (→ #5049, umbrella; file its own issue when taken) the SAN check: iOS evaluates `SecPolicyCreateSSL(true, host)` (hostname match) in `validateServerTrust` and then compares the pin. A certificate that does not name the address in the link (the LAN IP, the tailnet name with a pin) fails the policy and then the pin comparison is the only trust — OK only because `validateServerTrust` ignores the trust error and compares the key. A *Mac* client uses the same code, so a name mismatch is not the iOS-specific cause; but the failure's words are (step 5 of `sharing.failure-names-the-step`).
- `sharing.ios-link-opened-from-messages` — **[PARTIAL, read]** (→ #5049) the scheme `fichero` is registered (`CFBundleURLTypes`, `app.fichero.fichero.pairing`) and the universal link `https://tubb.ca/apps/fichero/pair` needs Associated Domains + the `apple-app-site-association` served from tubb.ca (**moved from fichero.app, owner ruling 2026-11-02**: the AASA lives in the tubb.ca site repo, one source, appID `QAPB6CWYR6.app.fichero.fichero`, path `/apps/fichero/pair`, committed there by the manager; `web/README.md` says so and the template is deleted). **No `com.apple.developer.associated-domains` entry exists in any `.entitlements` file** in `fichero/fichero/`: the https form of the link will open Safari, not the app, until it is added and the AASA is served. The custom-scheme form works where tapped from Messages (iOS offers "Open in Fichero"); some mail/web views do not make `fichero://` clickable at all, and a link longer than ~2000 chars (the base64 payload) may be wrapped or truncated by the sender. Check (person): paste the link into Notes, tap it. Check (test): `PairingLinkRoundTripTests` (decode what `inviteLinkString` encodes, with a payload of 3 addresses) and a size ceiling test. Fix: add `com.apple.developer.associated-domains` (`applinks:tubb.ca`) to the iOS entitlements (the owner's provisioning change; the AASA is already served); until then the Add Device sheet's "Copy Link" copies the `fichero://` form only, so no link opens Safari. Built 2026-11-08 [app] the iOS entitlements `fichero/FicheroIOS.entitlements` carry `com.apple.developer.associated-domains` = `applinks:tubb.ca` (owner approved; the iOS App Store profile now holds Associated Domains and the AASA is served from tubb.ca), selected for the iOS SDKs only so the Mac profiles are untouched. Not built: a tap-through check on a device
- `sharing.ios-qr-payload-size` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) a QR carrying the JSON payload (not a short link) at level M gets dense when `alt_urls` and a long library path are added; the iPhone camera misreads it. The QR carries the *short* form (`fichero://pair?c=<code>&h=<host>&…`) or a payload without the library path (the guest asks the host for it: `sharing.guest-addresses-the-hosts-library` already does that). Cap the encoded payload at ≤ 400 characters for the QR. *Test:* `PairingQRSizeTests` (exists).
- `sharing.ios-bad-library-path` — **[PARTIAL]** (→ #5049) a host with no project open mints a payload with `libraryPath == nil`. The pairing field check no longer throws `missingLibraryPath` for it (the same code runs on a Mac and a phone): the sequence pairs, lists `/api/authz/libraries` and, with one project, uses it (`PairingSequence`, `RemoteAccessConfigTests.testRemoteClientPairingFieldsAcceptAMissingLibraryPathAndAskTheHost`). **Left:** when the host shares several, there is no picker yet; the pairing is discarded and the person is told to ask for a link that names one. Check (person): a host with two projects, QR shown with none open.
- `sharing.ios-says-which-step` — **[PARTIAL]** (→ #5049, umbrella; file its own issue when taken) the iOS pairing sheet (`PairingIncomingLinkSheet.swift:68`) shows `error.localizedDescription` — for a network failure that is the system's "The request timed out." / "A server with the specified hostname could not be found." — in a red triangle (`:26`) with a Cancel button (`:40`) and no retry; the connect screen shows the same string (`ConnectPairingIOS.swift:246`, `:254`, `:317`), and so does the Mac (`MacRemoteClientPairingSection.swift:181`). Same rule as the Mac: `sharing.failure-names-the-step` (shared Swift), a **Try again** button and **Copy details** (log text, never the token) on the sheet. *Test:* `PairingFailureWordsTests` (shared).

`sharing.ios-end-to-end` — **[GAP]** nobody has paired a phone since the 2026-10-20 build (`library-sharing.md`: "a paired iPhone showed nothing"); no device was available for this investigation. The owner's check after the fixes: on the phone, with Wi-Fi off and Tailscale on, tap the link; it pairs through the tailnet name.

## 8. Tested against spec: the plan

**8.1 Headless two-process engine test (the lead can run it).** New file `test_two_macs_names_and_addresses_to_spec.py`, `FICHERO_TWO_ENGINES=1`, one test at a time (`OMP_NUM_THREADS=2`), using `_two_engines.start_host` / `start_guest` (throwaway `FICHERO_BASE_PATH`, HOME, token dir, free port, never 8765):
1. Host engine on loopback + the machine's LAN IP (`start_host(lan)`), certificate **name 1**: `host-a.test` (a SAN-only name, with `--resolve host-a.test:<port>:127.0.0.1` in httpx via a transport that maps the name; no DNS needed).
2. Guest engine (own socket, no listener) acting as client via the **real** `fichero devices pair <link>` (exists: `fichero_cli/__main__.py:796`, `fichero_cli/pairing.py`), with `pair_with_link` (the stand-in) kept for the cases the CLI cannot drive yet (several addresses, `sharing.client-tries-every-address`, until its CLI half lands).
3. Cases (each a test; red before the fix named in brackets):
   - the link with the host's addresses `[unreachable.test (never answers), host-a.test (answers)]`: pairs through the second, within `2 × timeout` (`sharing.client-tries-every-address`, CLI half in `fichero_cli`);
   - all addresses dead: the error text names every address and a reason per address, no "timed out" alone (`sharing.failure-names-the-step`); each attempt ends within 5 s ± 1 s on a never-answering address (a listening socket that never accepts);
   - a link with **no library path**: pairing succeeds and the host's `/api/authz/libraries` list is what the client sees, on the CLI and on the Swift fake (`sharing.both-clients-run-the-same-checks`, `sharing.ios-bad-library-path`);
   - a certificate for **name 2** `host-b.test` at the same IP: pairing with a link naming `host-a.test` and the pin of cert 2 → refused with the *pin/name* sentence; with the right pin and a name not in the SAN → the *name* sentence (`sharing.certificate-names-every-address`);
   - the host started with a **different engine version header** (`FICHERO_CONTRACT_VERSION_OVERRIDE`, a test knob if one exists, else a stub middleware) → the *version* sentence naming both (`sharing.version-mismatch-says-which-side`);
   - a **stale server holding the port**: bind a plain socket to the host port first → the host exits with "Port … already in use" (`__main__.py:603-607`) and the harness reads that line (`sharing.stale-server-holding-the-port`);
   - a **stale tailscale forward**: `tailscale_serve.ensure_forward` against a fake CLI that reports a foreign forward → `RuntimeError` text and `GET /api/pair/sharing` reports `tailnet_serve_conflict` (`sharing.stale-forward-says-so`);
   - **multi-user off**: `POST /api/users` as the owner → 404 `multi-user auth is disabled` (documents today's answer; changes to 409 `multiuser_off` with the proposal), `PUT /api/pair/multiuser true` before the owner has a password → 409 with the password words, after → 200, then `POST /api/users` → 201 (`sharing.multiuser-off-says-so`, the engine order);
   - **expired/used code**: a second redeem and an expired code both answer the same 401 words; revoke → the device's next call 401 (`sharing.token-expired-or-rotated`, exists in `test_device_pairing_e2e.py`).
4. `GET /api/health` after each case: the `sharing` block matches the listeners the harness bound (`sharing.health-reports-sharing`).
5. The stage: `GET /api/recipes/stages` with no project lists `sharing` with two yes-no questions, both `False`, `jobs: []`, after the material stages (`sharing.setup-stage-is-offered-without-jobs`, `sharing.setup-answers-change-later`).

**8.2 Two-Mac live checklist** (extends `testing/sharing-two-mac-checklist.md`; the lead runs; one record per row with the address that worked):
1. Air as host, Pro as client; then Pro as host, Air as client (both with the Mac's `LocalHostName` equal to its DNS hostname, see C4). Record `scutil --get LocalHostName` and `hostname` on each.
2. For each of {tailnet name, `.local`, LAN IP}: `curl -sk --max-time 8 https://<addr>:8765/api/health` from the other Mac; the app's address list must show the same results.
3. Pair over the tailnet with Wi-Fi isolation on (as today's campus): works; pair over `.local` on a home network: works; the failure sentence on each failing address.
4. iPhone: with Tailscale on and Wi-Fi off, tap the link in Messages; again with Local Network denied (Settings › Fichero) over the same Wi-Fi: the sentence names the permission.
5. Set Up: a new library, the Sharing and accounts page: answer No/No (nothing starts; `lsof -iTCP:8765` shows loopback only or no new listener); Yes/No (address list, link; a second Mac pairs); Yes/Yes (owner password, `+` creates an account, no 404).

## 9. What is built and what was verified, in one table

| Behaviour | Tag |
|---|---|
| `sharing.listener-is-lan-only-not-wildcard` | **[OK]** (seen: loopback + one LAN address on Air, Pro, M4) |
| `sharing.pair-answers-in-words` | **[OK]** (seen over the tailnet) |
| Air firewall allows Fichero + Fichero Server | **[OK]** (verified; not the cause) |
| Air tailnet forward made by the engine | **[OK]** (seen) |
| `sharing.address-choice` | **[PARTIAL]** |
| `sharing.link-carries-every-address` | **[PARTIAL]** |
| `sharing.client-tries-every-address` | **[PARTIAL]** |
| `sharing.failure-names-the-step` | **[PARTIAL]** (seen: every sheet shows `localizedDescription`) |
| `sharing.both-clients-run-the-same-checks` | **[PARTIAL]** (read: Mac skips the library confirm, iOS skips the contract check) |
| `sharing.trust-rule-is-one-function` | **[PARTIAL]** (read: Swift and CLI each hold the rule) |
| `sharing.host-name-is-the-bonjour-name` | **[PARTIAL]** (seen: Pro's address/certificate name `unb-c02f45gaq05p.local` differs from its LocalHostName `macbook-pro-m1`; not proven to cause a failure) |
| `sharing.certificate-names-every-address` | **[PARTIAL]** |
| `sharing.stale-forward-says-so` | **[PARTIAL]** (seen: M4 `:8765 → tcp localhost:8000`, Pro `:443 → :5006`) |
| `sharing.health-reports-sharing` | **[PARTIAL]** (seen: `remote_backend.enabled=false` while sharing) |
| `sharing.version-mismatch-says-which-side` | **[PARTIAL]** |
| `sharing.listener-follows-the-network` | **[PARTIAL]** |
| `sharing.firewall-prompt-says-what-to-click` | **[PARTIAL]** |
| `sharing.stale-server-holding-the-port` | **[PARTIAL]** |
| `sharing.token-expired-or-rotated` | **[PARTIAL]** |
| `sharing.tailnet-down-says-so` | **[PARTIAL]** |
| `sharing.multiuser-off-says-so` | **[PARTIAL]** (seen: Create Account 404 with the raw enum) |
| `sharing.undocumented-never-reaches-the-person` | **[PARTIAL]** (seen) |
| `sharing.multiuser-404-is-a-409-in-the-engine` | **[PARTIAL]** (engine, held: contract) |
| `sharing.multiuser-needs-sharing-for-anyone-else` | **[PARTIAL]** |
| `sharing.setup-stage-is-offered-without-jobs` | **[PARTIAL]** (read: `offered()` drops a jobless stage) |
| `sharing.setup-asks-sharing` | **[PARTIAL]** |
| `sharing.setup-asks-accounts` | **[PARTIAL]** |
| `sharing.setup-answer-is-per-library` | **[PARTIAL]** |
| `sharing.setup-answers-change-later` | **[PARTIAL]** |
| `sharing.setup-stage-wording` | **[PARTIAL]** |
| `sharing.ios-link-has-one-address` | **[PARTIAL]** |
| `sharing.ios-tailscale-not-on-the-phone` | **[PARTIAL]** |
| `sharing.ios-local-network-permission` | **[PARTIAL]** |
| `sharing.ios-app-transport-security` | **[PARTIAL]** (read) |
| `sharing.ios-certificate-name` | **[GAP]** |
| `sharing.ios-link-opened-from-messages` | **[PARTIAL]** (read; no associated-domains entitlement found) |
| `sharing.ios-qr-payload-size` | **[PARTIAL]** |
| `sharing.ios-bad-library-path` | **[PARTIAL]** |
| `sharing.ios-says-which-step` | **[PARTIAL]** |
| `sharing.ios-end-to-end` | **[GAP]** |
| `sharing.share-sheet-offers-both-addresses` (§10.1) | **[PARTIAL]** (M2 written, not yet built) |
| `sharing.state-names-every-address` (§10.1) | **[OK]** (E2) |
| `sharing.tailnet-forward-whenever-tailscale-is-up` (§10.1) | **[OK]** (E2; gated on sharing, review) |
| `sharing.sandboxed-engine-says-it-cannot-ask-tailscale` (§10.1) | **[PARTIAL]** (`unknown` built; the DMG live check is the lead's) |
| `sharing.card-keeps-its-code` (§10.2) | **[PARTIAL]** (M1 written, not yet built; was: `refreshKey` carried `isBackendRunning`, a mint after each health check in the Air's log) |
| `sharing.qr-drawn-once-per-payload` (§10.2) | **[PARTIAL]** (S1 + M1 written, not yet built) |
| `sharing.token-saves-on-every-build` (§10.3) | **[PARTIAL]** (S1 written, not yet built; the DMG gap proved live) |
| `sharing.failed-save-spends-nothing` (§10.3) | **[PARTIAL]** (S1 written, not yet built) |
| `sharing.multiuser-switch-needs-no-library` (§10.4) | **[OK]** (E1; was 400 in the Air's log: the route's library dependency) |
| `sharing.multiuser-switch-says-the-refusal` (§10.4) | **[PARTIAL]** (S2 written, not yet built) |
| `sharing.people-pane-off-state` (§10.4) | **[PARTIAL]** (M3 written, not yet built; iOS needs a Settings surface first) |
| `sharing.cli-mints-a-link` (§10.5) | **[OK]** (E3) |

## 10. Live findings 2026-10-31: the five owner items, on every platform

The owner paired the M4 to the Air (host) live on 2026-10-31 and reported five things. Each is read against the code at
`0f1ad5afe` (this branch's base) and the Air's engine log (`ssh air`, read-only; the Fichero.app there is build 20, engine
2026.10.28; this Pro runs build 18). What was verified is said; what was not is said too. Secrets appear nowhere here.

### 10.1 The link names one address (`.local`); the person must choose (owner item 1, #5318)

**Today (verified in code).** The Add Device sheet and the project Share sheet build one payload from
`validatedPublicURL` = the sharing address (`ShareSettingsView+QRCode.swift:29-44`, `ShareLibrarySheet+Sharing.swift:125-140`).
The engine already tells the app the second address: `PairCodeResponse.tailnet_url` (`pairing.py:764`) and
`GET /api/pair/sharing` → `tailnet_url` (`_sharing_state`, `:191-199`), which the pane fetches into `sharingState` /
`detectedTailnetURL` (`refreshSharingState`, `+StateManagement.swift:112-117`) and then uses for nothing but the Advanced "Use"
button. The tailnet forward is made only when the **sharing address itself** is a `.ts.net` name
(`tailscale_serve.start_for_engine`, `:145`: `tailnet_url()` is empty otherwise), so with a `.local` sharing address the engine makes
no forward; the Air's forward exists from an earlier `.ts.net` choice (`tailscale serve --bg` persists), which is why the tailnet
address answered while the link named `.local`.

- `sharing.share-sheet-offers-both-addresses` — **[PARTIAL]** (#5318; slice M2 written 2026-10-31, not yet built: `AddressChoiceModel` rows/default/root, the Add Device sheet's segmented choice with a Copy per row, the project Share sheet's choice; `SharingStateRecord` carries `publicBaseURL`, `lanIP`, `tailnetForward`) the Add Device sheet and the project Share sheet show the
  addresses as a choice above the QR: **"This network"** (`<name>.local`) and **"Tailscale"** (`<machine>.<tailnet>.ts.net`), each with
  its one-line reach ("same Wi-Fi only, when the network allows it" / "anywhere your Tailscale is on"). On the Mac's Add Device sheet
  each address is ONE line, said once (#6554, seen 2026-11-12: the picker, the row and the engine's host list each named it, with the
  key line under them): a mark for the chosen one, its name and host, where it works or why it cannot, and its **Copy**; clicking a
  line that can work chooses it. No segmented picker, no second address list; "This Mac's key" moves to Settings › Sharing › Advanced.
  The project Share sheet shows the same lines (one view, `AddressLines`), and shows them whenever one line cannot work, even
  with only one usable address: it had hidden the choice then, so a greyed Tailscale line and its reason never showed there. The chosen row is what the QR
  shows and what **Copy Link** copies; each row also has its own **Copy** so both links can be sent at once. The pin follows the row
  (`RemoteClientPairing.invitePin(_:for:)` already decides by host: `.ts.net` carries no pin, the rest carry the one SPKI pin); the code
  is the same in both links (one mint, two addresses). The default row is Tailscale when the engine reports a tailnet address and its
  forward is Fichero's own, else This network. A row that cannot work is shown disabled with why (Tailscale not running: "Tailscale is
  not running on this Mac"; forward held by another service: `sharing.stale-forward-says-so`; the engine could not ask Tailscale (`tailnet_forward`
  `unknown`, a sandboxed build): the row is offered as "This build cannot ask Tailscale; see Settings › Sharing", not first, and
  never "not running"; a greyed row names no host; a `.ts.net` sharer's row is its own address whatever detection says). On iPhone and iPad there is no host
  card (`ShareSettingsView` is `canImport(AppKit)`; `SharingSettingsView.availableSections` is `[.people]` on iOS,
  `SettingsGroupContainers.swift:81-92`): the phone is a client and consumes whichever link it gets. *Test:* `AddressChoiceModelTests.swift`
  (Swift Testing, written with the slice): rows from a `SharingStateRecord` with and without a tailnet address; default row; the payload for
  each row carries the right pin; both links carry the same code. UI: `SharingPaneUITests/testAddDeviceSheetShowsBothAddressRows` in
  `fichero-ui-mac` (seeded sharing state).
- `sharing.tailnet-name-known-without-the-cli` — **[PARTIAL]** (#6554; seen 2026-11-12 on the Pro, Dev DMG) engine. A sandboxed
  engine runs the Tailscale CLI and reads nothing, so it could not name this Mac's tailnet address and the Tailscale row was greyed
  ("This build cannot ask Tailscale"). When Tailscale cannot be asked (no answer, or not JSON), the engine names the tailnet address it
  already knows: the `.ts.net` sharing address, else a `.ts.net` name on its serving certificate, else a Remote Access folder named for
  one; the row is then offered, not first, with the "cannot ask" line. A Tailscale that answers "stopped" or "logged out" still names
  nothing. *Built:* `tailscale_serve.known_tailnet_url`, used by `detected_tailnet_url`. *Not built:* a look on the Pro.
  *Tests:* `fichero-server/tests/unit/security/test_tailnet_name_known_without_the_cli_to_spec.py`.
- `sharing.tailnet-serve-command-on-the-sheet` — **[PARTIAL]** (#6554) app and engine. When the engine knows the tailnet name but
  cannot make the forward itself (sandboxed), `tailnet_serve_command` is the one `tailscale serve --bg --https=<port>
  https+insecure://127.0.0.1:<port>` command to paste, and the Add Device sheet shows it under the addresses with its Copy (as
  Settings › Sharing › Advanced already did; one view, `TailnetServeCommandLine`). Nothing when the forward is already Fichero's.
  *Not built:* a look on the Pro. *Tests:* `test_tailnet_name_known_without_the_cli_to_spec.py`, `Sharing/AddressChoiceModelTests.swift`.
- `sharing.state-names-every-address` — **[OK]** (#5318; engine, slice E2, 2026-10-31: `public_base_url`, `lan_ip`, `tailnet_forward`; contract regenerated) `GET /api/pair/sharing` gains `public_base_url` (the sharing
  address the engine was started with), `lan_ip` and `tailnet_forward: "ours" | "foreign" | "none"`, so the app, the CLI and a tester read
  the host's addresses from one place instead of guessing (the first step of `sharing.address-choice`, §4, which stays the fuller design).
  Additive response fields: the Swift client ignores unknown keys until the regen that consumes them. *Test:*
  `tests/unit/api/test_sharing_state_names_every_address_to_spec.py`.
- `sharing.sandboxed-engine-says-it-cannot-ask-tailscale` — **[PARTIAL]** (→ #5317; review 2026-10-31 H4) the shipped engine is sandboxed
  (`FicheroRelease.entitlements`, `FicheroEngine*.entitlements`: app-sandbox + inherit) and `pairing.py:162` records that a sandboxed app
  cannot run the Tailscale CLI (#5317). If that holds on a DMG, `detected_tailnet_url`, `forward_state` and `start_for_engine` all get a
  refusal: no forward is made by the engine, `tailnet_url` is null, and a `.local` sharer gets no `tailnet_serve_command`. What the engine
  does about it: `forward_state` answers **`unknown`** (not `none`) when Tailscale is installed but the CLI could not be run, timed out or
  printed no JSON, and the app's Tailscale row then reads "This build cannot ask Tailscale; see Settings › Sharing" rather than "Tailscale
  is not running on this Mac" (`AddressChoiceModel`); a `.ts.net` sharer's row uses the sharing address itself, which works whatever
  detection says. Not yet known: whether the DMG's engine really gets the refusal; the Air's forward exists from an earlier `.ts.net` choice
  made by hand, which is not evidence. **LIVE-CHECK (lead, on the Air or M4 DMG, read-only):** with Sharing on, `curl -sk --unix-socket
  "$HOME/Library/Containers/app.fichero.fichero/Data/Library/Application Support/Fichero/fichero.sock" http://x/api/pair/sharing -H
  "Authorization: Bearer $(cat "$HOME/Library/Containers/app.fichero.fichero/Data/Library/Application Support/Fichero/.api-key")"` and read
  `tailnet_url` and `tailnet_forward` (`unknown` = the sandbox refusal is real; `ours`/`none` = the CLI runs); and in the engine log
  (`…/Library/Logs/Fichero/engine.log`) grep "Sharing over Tailscale" after turning Sharing off and on. If `unknown`: the forward must be made by
  the app (unsandboxed helper) or the person (the `tailnet_serve_command` line), its own slice. *Test:*
  `test_forward_made_with_a_local_sharing_address_to_spec.py` (the `unknown` arm: PermissionError, timeout, bad JSON; `none` for not installed).
- `sharing.tailnet-forward-whenever-tailscale-is-up` — **[OK]** (#5318; engine, slice E2, 2026-10-31: `start_for_engine` forwards for any sharing address while Tailscale runs; `forward_state`; review fix: gated on `tailscale_serve.sharing_on`, so an engine nobody shared, a certificate alone or a loopback address, never asks Tailscale and is never published) `start_for_engine` makes (or keeps) the `tailscale serve`
  forward whenever Tailscale is running and a certificate exists, not only when the sharing address is `.ts.net`, so the Tailscale row
  works whichever address the person chose. A foreign forward is still never replaced (`ensure_forward`, `:118-124`). *Test:*
  `tests/unit/security/test_tailscale_serve.py` (exists) + `test_forward_made_with_a_local_sharing_address_to_spec.py`.

### 10.2 The code card "keeps resetting" (owner item 2)

**Verified in code and in the Air's log.**
1. *What re-mints the code.* `.task(id: refreshKey)` (`ShareSettingsView.swift:131-134`) re-runs `refreshPairingCode()`, which sets
   `pairingCode = nil` and mints again (`+StateManagement.swift:98-109`), whenever `refreshKey` changes; the key contains
   `appState.isBackendRunning` (`:8-12`), which is `engine.isReady` (`AppState.swift:53`). **Every `checkBackendHealth()` call flips it**:
   it calls `engine.markStarting()` on entry (`AppState+HealthCheck.swift:44`) and `markReady` at the end, so the key changes twice and
   the card is cleared and re-minted. `checkBackendHealth()` is called by the Multi-user switch (`setMultiuserOnEngine`,
   `+StateManagement.swift:59`), by `applySharing` (`:74`, `:92`), by the project Share sheet (`ShareLibrarySheet+Sharing.swift:82,91`),
   by Engine settings and by a host switch. The Air's engine log shows the pattern: each `PUT /api/pair/multiuser` (§10.4) is followed by a
   `POST /api/pair/code` (21 mints in the log; the uvicorn access lines carry no timestamp, so the cadence is not readable there).
2. *What redraws the picture without changing the code.* `qrCodeImage` is a computed property that runs `CIFilter` and makes a new
   `NSImage` on **every body evaluation** (`+QRCode.swift:51-62`); the Devices poll sets `pairedDevices` every 10 s
   (`ShareSettingsView.swift:122-129`, `lastSeen` changes), and any other state change re-evaluates the body, so the image is rebuilt
   and SwiftUI redraws it. The bytes are the same within one app process (below), so what the person sees is a redraw, not a new QR.
   **Not verified:** the ~30 s cadence the owner saw; `log show` on the Air returned no app lines for the filters tried in this
   session. To pin it: on the host, `log stream --predicate 'subsystem == "app.fichero.fichero"' --style compact` while the card is up,
   and note which lines land at each flash.
3. *Why two copies of the same link had different JSON key order.* Both the link (`RemoteClientPairingFlow.swift:71-72`) and the QR
   (`+QRCode.swift:53`) use a `JSONEncoder()` without `.sortedKeys`. On this macOS (27.0) `JSONEncoder` orders keys **per process**: a
   three-run script with the payload's six keys gave three different orders across runs and the same order within a run. So two links
   from one app launch match byte for byte; two from different launches (or different Macs) do not. Decoding is unaffected; comparing
   links by eye is.
4. *Lifetime and clock.* `expires_at = utc_now() + PAIRING_CODE_TTL` at the mint (`pairing.py:729-730`, the engine's clock, UTC); the
   card shows it in the Mac's local time (`AddDeviceSheetModel.expiresText`). **Copy Link copies the code on the card** (`inviteLinkString`
   ← `pairingQRPayload` ← `pairingCode`, `+QRCode.swift:46-49`), nothing cached and nothing re-minted; the QR is built from the same
   `pairingQRPayload`. A link re-sent after its ten minutes answers `401 invalid or expired pairing code` (`pair_device`, `:827`); the
   manager's observation (a link minted 15:13:40Z, received 15:14Z, re-sent at 15:28Z) is consistent with this: the card handed out a
   fresh code and the old link was re-sent, not a stale mint.

- `sharing.card-keeps-its-code` — **[PARTIAL]** (→ #5915, its second half; new issue 1 below; slice M1 written 2026-10-31, not yet built: `PairingCardRefresh.key` without the engine phase, `keepsCode`, `mintsWhenEngineChanges`) the card re-mints only when: the code expires
  (`sharing.pairing-code-renews-at-expiry`, built), Sharing is turned on, the sharing address or pin changes, or the person asks for a new one.
  **A health check, a Multi-user flip, a Devices refresh or the engine's phase passing through `starting` never clears the card**, but
  **an engine restart does**: codes live in the engine's memory (`_PAIRING_CODES`), so a code is kept only across the SAME engine process,
  told by health's `engine_pid` (`PairingCardRefresh.sameEngine`; review M1). `refreshKey` drops `isBackendRunning`; when the engine is not
  ready the card shows its blocker (`.engineNotRunning`) over the *kept* code; when it is back it mints again only if the card is empty or
  the code came from another engine process. *Test:* `ShareSettingsRefreshKeyTests.swift`: the key is
  unchanged across `isBackendRunning` true→false→true; changes on address/pin/sharing. `PairingCodeRenewalTests.swift` (exists) stays.
- `sharing.qr-drawn-once-per-payload` — **[PARTIAL]** (→ #5915; new issue 1 below; S1 sorted both encoders, M1 draws the QR once per link into `@State qrImage`; written, not yet built) the QR image is made once per payload string and kept in `@State`
  (`.task(id: inviteLinkString)`), never in a computed property the body re-runs; both encoders use `.sortedKeys` (and `.withoutEscapingSlashes`
  is **not** added: the iOS decoder and the CLI accept either, but a changed link shape is not needed) so Copy and QR are byte-identical and a
  link reads the same from every launch and every Mac. *Test:* `PairingLinkEncodingTests.swift`: two encodes of one payload are equal; keys
  are in sorted order; the QR message equals the link's payload bytes.

### 10.3 The guest could not save the device token: `errSecMissingEntitlement` (-34018) (owner item 3)

**Verified.** Every Keychain query for the remote device token carries `kSecUseDataProtectionKeychain: true`
(`AuthTokenMiddleware.swift:398`, `remoteTokenKeychainQuery`, used by read, write and clear). On macOS the data-protection keychain
needs the app to carry a `keychain-access-groups` or `com.apple.application-identifier` entitlement. The Xcode Debug and Dev Embedded
configurations sign with `Fichero.entitlements`, which has the group (`CODE_SIGN_ENTITLEMENTS`, `project.pbxproj:1601`, `:1998`). The
Release, Alpha Embedded and Beta Embedded configurations use `FicheroRelease.entitlements` (`:1659`, `:2060`, `:2137`), which has
**no** keychain key, and the DMG lane re-signs the app with that raw file (`scripts/build-release-dmg.sh:114-141`; codesign *replaces*
entitlements). Checked on the installed apps: the Air's `/Applications/Fichero.app` (build 20) and this Pro's (build 18) carry neither
key (`codesign -d --entitlements`). So **every DMG (GitHub / Sparkle / dev DMG) build fails to save the token; every Xcode Debug and
Dev Embedded run saves it**, which is why the failure was never seen in testing. **Proved live (2026-10-31):** a swiftc probe doing
`SecItemCopyMatching/Add/Copy/Delete` on a throwaway service, ad-hoc signed with `FicheroRelease.entitlements`, run bare and inside a
minimal sandboxed bundle, gave the same answer both times: with `kSecUseDataProtectionKeychain` the lookup says not-found (-25300) and the
add and delete answer **-34018**; without it (the login keychain) add, read and delete answer 0, with or without `kSecAttrAccessible`.
So the shipped path was: lookup not-found → `SecItemAdd` -34018 → the macOS fallback (`:314-327`) dropped `kSecAttrAccessible` and added
again → -34018 again, because the query still named the data-protection keychain → `keychainWriteFailed(-34018)`, the owner's sentence.
The fallback was reachable but ineffective. The session token's query has no such flag
(`sessionTokenKeychainQuery`, `:404-410`) and works on the DMG, which shows the login keychain is the working home on a Mac. App Store /
TestFlight builds (`FicheroAppStore.entitlements`, no group either) are signed by Xcode with a profile, which injects
`application-identifier`: **expected to work, not verified**. iPhone and iPad have only the data-protection keychain; the flag is a
no-op there and the profile supplies the identifier: **expected to work, not verified on a device** (no phone has paired since 2026-10-20).

**The spent-code trap (verified).** `pair_device` marks the code used and pops it (`pairing.py:920-922`) *before* answering, and creates
the device row (`:905-909`); the token exists only in the answer. When the client then fails to persist it, the host lists a device nobody
holds a token for and the code is gone. The client's own remedy exists: `POST /api/pair/devices/revoke-self` with the token it still holds
in memory (`:1043`, #6133).

- `sharing.token-saves-on-every-build` — **[PARTIAL]** (→ #5049, umbrella; new issue 2 below; slice S1 written 2026-10-31, not yet built) on
  macOS the device token lives in the **login keychain**, always, with no fallback: the ONE query that read, write and clear share
  (`AuthTokenMiddleware.remoteTokenKeychainQuery`, decided by `remoteTokenLivesInDataProtectionKeychain`) omits `kSecUseDataProtectionKeychain`
  **and** `kSecAttrAccessible` on a Mac (an explicit class routes a Mac item to the data-protection keychain too; the test asserts no class is read
  back), and keeps both on iOS/iPadOS (`AfterFirstUnlock`, #3772). A token a Debug build wrote earlier into the data-protection keychain is not found
  by the login-keychain query: that Mac re-pairs once; the old item stays (S-L1, a one-shot delete is a later slice). The alternative, adding
  `com.apple.application-identifier` + `keychain-access-groups` to `FicheroRelease.entitlements`, is S1b, **not** the path taken.
  *Test:* `KeychainTokenAccessibilityTests.swift` (exists, extended): on macOS the remote-token query has no data-protection key and no
  protection class is read back; on iOS it has the key and reads back `AfterFirstUnlock` (`#3772`); a transient token is read once and gone.
- `sharing.failed-save-spends-nothing` — **[PARTIAL]** (→ #5049, umbrella; new issue 2 below; slice S1 written, not yet built:
  `RemoteClientPairing.storeTokenOrRevoke` on all three paths, the iOS flow, the Mac Connect sheet and the synced-project ask) when the token
  cannot be saved (any `AuthTokenStorageError`), the client asks the host to revoke the device it just made (`revoke-self`, with the token held
  once in memory under the host's account, dropped after the call) and says: **"This Mac couldn't save the connection key in its Keychain, so
  nothing was paired. Update Fichero on this Mac and ask for a new link."** (`RemoteClientPairingError.tokenNotSaved`; the OSStatus goes to the
  log only). Nothing is persisted, so there is no host to forget. On iPhone/iPad the subject is "This device" (the idiom is main-actor
  state a `LocalizedError` cannot read, review S-H1). A refused revoke is logged and the host keeps the row (accepted). Not built: a "Copy
  details" control, the one-shot delete of an old data-protection item. *Test:*
  `PairingPersistFailureTests.swift` (written): a throwing persist → the revoke is asked while the middleware holds that token, then it is
  gone, nothing saved, the sentence. Engine: `test_a_device_revokes_its_own_pairing_6133.py` (exists) already proves `revoke-self` right after `pair`.

### 10.4 The Multi-user switch does not stick; Create Account gives a 404 (owner item 4)

**Verified in the Air's log and in code.** The Air's engine answered `PUT /api/pair/multiuser` with **400 Bad Request** seven times
in a row. The route declares `db: Database = Depends(get_library_database_for_write)` (`pairing.py:593`), which answers
`400 "Missing X-Fichero-Library-Path header. Please open a library document first."` (`api/main.py:1646-1647`) when the request carries
no library header. The Settings pane's `PairingService(apiRoot:)` makes its own `FicheroClient` with no library path
(`PairingTypes.swift:127-129`), and `/api/pair` is not in `LibraryPathMiddleware.isAppWidePath` (`:81-89`), so the header is sent only
when that client has a library, which it never has: the dependency refuses before the body runs. The action itself is app-wide
(`owner_scope="app"`, `:626-627`) and reads the app DB; the library DB is used for nothing. The Swift side then throws
`APIError.httpError(statusCode: 400, message: "Unexpected response")` (`MultiuserSwitch.swift:28-29`, the engine's `detail` is thrown
away), the pane shows that, and `multiuserBinding` reads the engine's unchanged state: the switch snaps back. The existing engine tests pass
because the harness client sends the header. After this 400 the next refusals in order are the designed ones: 403 without the owner's
signed-in key session while Multi-user is off (`:601`), 409 until the owner chose a password (`:607`).

**The 404.** `POST /api/users` answers `404 multi-user auth is disabled` while Multi-user is off (`accounts.py:198-200`); the People
pane's `+` is enabled whatever the state (`UsersContent+Layout.swift:24-27`), the Add sheet offers **Create Account** with a password
(`AccountsAddSheetModel.buttonTitle`), and the store shows the raw enum (`UsersStore.swift:166`). **#5917 is not built in the UI**:
`SharingToggles.multiUserOffHint` exists with its test (`SharingTogglesTests.swift`) but no view uses it (grep 2026-10-31: the definition
only). `library-sharing.md` marks it [PARTIAL]; it is **[GAP]** at the UI.

- `sharing.multiuser-switch-needs-no-library` — **[OK]** (→ #5751; new issue 3 below; engine, slice E1, 2026-10-31: `app_action_context` + the global library database, no library header) `PUT /api/pair/multiuser` takes no library
  dependency: the action is invoked against the global library package (`global.fichero`, where the known-library registry's app-wide
  actions already write) with an app-scoped context, so a Settings window with no project open can flip it; the undo routes look there
  too when the window's library does not hold the step, so ⌘Z from a project window, the CLI or MCP still takes the switch back. *Test:* `tests/unit/api/test_multiuser_switch_needs_no_library_to_spec.py`: the owner's key session, **no** library header →
  409 (password gap) then 200, never 400; the returned `audit_id` is undone from a library window; a header-less paired device → 403;
  `test_owner_session_sets_the_switch_5908.py` (exists) stays green.
- `sharing.multiuser-switch-says-the-refusal` — **[PARTIAL]** (#6299; slice S2 written 2026-10-31, not yet built: `MultiuserSwitchWords.sentence`, `MultiuserSwitch.put` reads the engine's detail; the Choose Password… button is not built: no owner-password sheet exists in the app yet, the sentence names the step) `MultiuserSwitch.put` reads the engine's `detail` from an undocumented
  status (as `PairingService` does for the other calls, `EngineErrorDetail.message(from:)`) and the pane shows it beside the switch; a 409
  password gap becomes **"Choose a password for your account first"** with a **Choose Password…** button (the owner `PATCH`, `#5908`).
  *Test:* `MultiuserSwitchWordsTests.swift`: 400/403/409 bodies → their sentences; never "Unexpected response".
- `sharing.people-pane-off-state` — **[PARTIAL]** (#5917 reopened to this; slice M3 written 2026-10-31, not yet built: `PeoplePaneOffState`, the People pane hides `+` and shows the line + Open Sharing, which hops to Devices; **iPhone and iPad have no Settings surface at all today**: `SettingsView` is presented only by the Mac `Settings` scene (`FicheroApp.swift:702`), nothing on iOS presents it, so the phone words exist in the model and no phone pane shows them, `sharing.ios-settings-surface` below) with Multi-user off the People pane shows the
  owner's row, **no `+`, no Create Account, no Invite**, and one line with a button: on a Mac **"Multi-user is off. Turn it on in Sharing."
  [Open Sharing]** (selects the Devices section, where the switch is: `ShareSettingsView+Advanced.swift:77`); on iPhone/iPad, which have
  no switch, **"Multi-user is off. Turn it on in Sharing on the Mac that shares this library."** (no button). The state comes from the engine
  (`authzSnapshot.multiuserEnabled` / `identityStore.multiuserEnabled`), never a local flag. With Multi-user on, `+` returns. *Test:*
  `PeoplePaneOffStateTests.swift`: off → no add control, the sentence per platform; on → `+`. UI: `SharingPaneUITests/testPeopleOffStateHidesAdd`
  (`fichero-ui-mac`), `IOSSettingsPeopleUITests/testPeopleOffStateSentence` (`fichero-ui-ios`, not written, #5049), `IPadSettingsPeopleUITests` (`fichero-ui-ipad`, not written, #5049).
- `sharing.multiuser-404-is-a-409-in-the-engine` — **[GAP]** (→ #5049; §5, unchanged: held, contract).
- `sharing.ios-settings-surface` — **[PARTIAL]** (→ #5049, umbrella; new issue 5 below) iPhone and iPad have no Settings at all: `SettingsView` compiles for iOS but only the Mac `Settings` scene presents it, and the connection menu (`IOSConnectionMenu.swift`) offers host, reconnect, change server, forget and logs. So the per-platform rows of §10.6 that say "People only" on iPad/iPhone describe code that is never reached. Needed first: a Settings sheet from the connection menu (General, Sharing › People) so `sharing.people-pane-off-state`'s phone words can show and `IOSSettingsPeopleUITests` can exist. Until then the phone's only sharing surface is the Connect flow (§7).

### 10.5 Minting a code from the CLI (owner item 5)

**Verified.** `fichero devices` has `list`, `pair`, `forget`, `revoke` (`fichero_cli/__main__.py:790-840`); there is **no mint**. The
engine already lets the host's bootstrap owner mint over the Unix socket (`_pairing_user` → `_owner_for_pairing` with `bootstrap_auth`,
`pairing.py:304-331`; the UDS transport is exempt from the https rule, `:535-536`), so no engine change is needed to mint, only to *name
the addresses* (`sharing.state-names-every-address`).

- `sharing.cli-mints-a-link` — **[OK]** (→ #5751; new issue 4 below; slice E3, 2026-10-31: `fichero devices invite`, `fichero_cli/pairing.py` `invite_link`; the link's `library_path` is the CLI's `--library`, which the Mac and iOS apps still require, `sharing.ios-bad-library-path`) `fichero devices invite [--address this-network|tailscale] [--link-file PATH]`
  on the host mints one code and prints the pairing link for the chosen address (default: tailscale when the engine reports one, else
  this-network), or writes it to `--link-file` (0600) and prints only the address and the expiry. The link carries the pin for a
  `.local`/IP address (`spki_pin` from the mint answer) and none for `.ts.net`, the same rule as the app (`_is_public_ca`). The two
  machines are then linked with no GUI: `fichero devices invite --link-file ~/fichero-pair/link` on the host (a private directory, never a
  shared `/tmp` path: the file is created owner-only at 0600 through a fresh temp file, and a symlink, a directory or another user's file
  is refused in words), copied to the guest, then `fichero devices pair --link-file ~/fichero-pair/link` there. The raw code is never printed on its own. *Test:* `fichero-cli/tests/test_cli_mints_a_link_to_spec.py` (beside `test_cli_pairs_a_device_5907.py`): the link decodes to the
  engine's code and the chosen address; the tailnet link carries the sharing port (the engine reports the `.ts.net` origin without one, review H3);
  `.ts.net` → no `spki`; `.local` → the pin; the payload is percent-encoded so any library path round-trips (review L4); `--link-file` is 0600
  and stdout holds no payload; a refusal names only addresses that exist. A link to an address nothing listens on is refused by the engine's
  mint (409, `sharing.link-names-a-listener`) and shown as "Could not invite: …".

### 10.6 Each platform today, what is broken, what "working" means

| Area | Mac | iPad | iPhone |
|---|---|---|---|
| Pairing / join | Connect sheet: paste link or pick a Nearby host (`MacRemoteClientPairingSection`); failures show `localizedDescription` (`:181`). **Broken:** one address in the link; -1001/-1003 as raw text; token save fails on DMG builds (§10.3). *Working:* link with both addresses, each tried in turn, step-named sentences, token saved, host switch. | `ConnectPairingIOS` (QR scan, paste, nearby) + `PairingIncomingLinkSheet` on a tapped link; `error.localizedDescription` (`PairingIncomingLinkSheet.swift:68`); no contract check (§1). **Untested on a device since 2026-10-20.** *Working:* same sequence as the Mac (`sharing.both-clients-run-the-same-checks`), Tailscale-first on a campus network, the sentence names the step and offers Try again. | Same as iPad, plus the Local Network prompt (§7). |
| Device token | Data-protection keychain → **fails on every DMG build** (-34018); works in Xcode Debug/Dev Embedded. *Working:* login keychain; failed save revokes and says so. | Data-protection keychain (the only one); entitlement injected by the profile: expected OK, **not verified**. *Working:* a save failure revokes and says so, same words with "this iPad". | Same as iPad. |
| Multi-user switch + People pane | Switch in Sharing › Devices › Advanced; **PUT answers 400** (§10.4), pane says "Unexpected response"; People `+` → Create Account → **404 raw enum**. *Working:* switch flips (or says the password gap), People hides `+` while off with the sentence and a button. | **No Settings surface at all** (`sharing.ios-settings-surface`): the People pane and the switch are unreachable. *Working:* a Settings sheet with People; People hides `+` while off, the sentence names the Mac. | Same as iPad. |
| Address choice | Host only; one address. *Working:* two rows, choice, per-row Copy. | Client: consumes either link; opens `fichero://` from Messages. | Same. |
| Code card | Host only; **re-mints on every health check**, redraws every render. *Working:* code kept until expiry; one QR per payload. | No card. | No card. |

### 10.7 Test matrix per platform

| Behaviour | Engine (pytest) | Swift Testing (`fichero.xctestplan`, general) | UI test (plan) |
|---|---|---|---|
| `sharing.share-sheet-offers-both-addresses` | — | `AddressChoiceModelTests` | `SharingPaneUITests/testAddDeviceSheetShowsBothAddressRows` (`fichero-ui-mac`) |
| `sharing.state-names-every-address` | `test_sharing_state_names_every_address_to_spec.py` | — | — |
| `sharing.tailnet-forward-whenever-tailscale-is-up` | `test_forward_made_with_a_local_sharing_address_to_spec.py` | — | — |
| `sharing.card-keeps-its-code` | — | `ShareSettingsRefreshKeyTests`, `PairingCodeRenewalTests` (exists) | `SharingPaneUITests/testCodeSurvivesAHealthCheck` (`fichero-ui-mac`) |
| `sharing.qr-drawn-once-per-payload` | — | `PairingLinkEncodingTests` | — |
| `sharing.token-saves-on-every-build` | — | `KeychainTokenAccessibilityTests` (Mac + iOS arms) | `IOSConnectPairingUITests/testPairStoresTokenAndOpens` (`fichero-ui-ios`, not written, #5049), `IPadConnectPairingUITests` (`fichero-ui-ipad`, not written, #5049), seeded host |
| `sharing.failed-save-spends-nothing` | `test_a_device_revokes_its_own_pairing_6133.py` (exists) | `PairingPersistFailureTests` | — |
| `sharing.multiuser-switch-needs-no-library` | `test_multiuser_switch_needs_no_library_to_spec.py`, `test_owner_session_sets_the_switch_5908.py` (exists) | — | — (the switch is covered by the engine tests; no UI test written) |
| `sharing.multiuser-switch-says-the-refusal` | — | `MultiuserSwitchWordsTests` | — |
| `sharing.people-pane-off-state` | — | `PeoplePaneOffStateTests` | `SharingPaneUITests/testPeopleOffStateHidesAdd` (mac), `IOSSettingsPeopleUITests` (ios, not written, #5049), `IPadSettingsPeopleUITests` (ipad, not written, #5049) |
| `sharing.cli-mints-a-link` | `test_cli_mints_a_link_to_spec.py` | — | — |
| `sharing.failure-names-the-step` (§4) | `test_cli_pair_words_match_the_spec.py` (not written, #5049) | `PairingFailureWordsTests` (not written, #5049) | `IOSConnectPairingUITests/testDeadHostNamesTheStep` (ios/ipad, not written, #5049) |

UI tests join the existing plans by adding the suite names to `fichero/Tests/plans/fichero-ui-mac.xctestplan` (`FicheroUITests`),
`fichero-ui-ios.xctestplan` and `fichero-ui-ipad.xctestplan` (`FicheroIOSUITests`); each plan today selects three canary/smoke suites,
so a new suite is listed explicitly or it does not run. Every UI test runs against a seeded engine (`IOSSimSameSocketTests` shows the
socket pattern) and never against the owner's running app (the owner's running app).

### 10.8 Live script: Air host, M4 guest, iPhone or iPad over Tailscale

Run after the slices; one record per numbered step (what the screen said, verbatim). Never paste a code, pin or token into the record.
1. **Air (host):** Settings › Sharing › Sharing on. Devices › Add Device…: two rows, "This network (macbook-air-m1.local)" and
   "Tailscale (macbook-air-m1.<tailnet>.ts.net)", Tailscale selected by default. Note the expiry time shown. Leave the sheet open 3 minutes:
   the code must not change; the picture must not flash. Flip Multi-user off/on in Advanced (expect "Choose a password for your account
   first" or a flip, never "Unexpected response"): the code on the card is still the same.
1b. **Air (host), project Share sheet** (`sharing.share-sheet-offers-both-addresses`): Settings › Sharing › Sharing OFF, wait for the engine. Open a project's Share
   sheet, pick a person, press Share. Wait up to 6 s. The link names the `.ts.net` address (not `.local`), the sheet shows no "only works on the same
   local network" line, and the Tailscale row is not greyed. This is the only proof the sheet re-reads the state after turning Sharing on.
2. **Air:** Copy Link with Tailscale selected, send to the M4 (Messages). Then select This network, Copy, send too.
3. **M4 (guest, DMG build):** Settings › Sharing › Connect to Another Mac…, paste the Tailscale link. Expect: connected in < 10 s; the
   host's library opens; no Keychain error. On the Air, Devices shows the M4 within 10 s. Quit and reopen Fichero on the M4: it reconnects
   without asking (the token was saved). **Keychain ACL (S-M3):** install the NEXT DMG over it: it must reconnect with no keychain prompt; then
   run a Dev Embedded build on the same Mac: note whether it prompts or reads "not paired" (a login-keychain item is tied to the signing
   identity that wrote it). **Gate note (S-M4):** `KeychainTokenAccessibilityTests`, `DeviceTokenRenewalTests` and `WorkflowStreamConnectionTests`
   write the real login keychain: run them in a GUI session; over SSH or with the keychain locked, -25308 is the session, not a defect.
4. **M4:** paste the This-network link (a new code from the Air). On the campus network expect the sentence "This Mac can't find
   macbook-air-m1.local on this network. Try the Tailscale address…" in < 10 s, never "The request timed out".
5. **M4:** paste the first (now used) Tailscale link again. Expect "That code was used or has expired…", and no new row on the Air.
6. **Air:** Devices › select the M4 › −. On the M4 within 10 s: "macbook-air-m1 no longer knows this Mac…" and the row greys.
7. **Air:** Sharing › Advanced › Multi-user on (choose a password when asked). People: `+` appears. Multi-user off: `+` goes, the line
   "Multi-user is off. Turn it on in Sharing." with its button.
8. **iPhone (Tailscale app connected, Wi-Fi off):** tap the Tailscale link in Messages → Open in Fichero → pairs; the library list shows the
   Air's project. Settings › Sharing › People: with Multi-user off on the Air, the line names the Mac and shows no `+`.
9. **iPad (same Wi-Fi as the Air, Local Network allowed):** scan the QR with This network selected. On a campus network expect the
   network sentence; with Tailscale selected the pair succeeds. Deny Local Network in Settings › Fichero and retry This network: the sentence
   names the permission with Open Settings.
10. **Sandbox check (lead, first on a DMG; see `sharing.sandboxed-engine-says-it-cannot-ask-tailscale`):** read `GET /api/pair/sharing` over the
    socket on the Air; `tailnet_forward` must be `ours` for the Tailscale row to be offered as working. `unknown` means the DMG's engine cannot run
    the Tailscale CLI and items 1-3 cannot pass on that build until the forward is made another way.
11. **CLI (host Air, no GUI):** `fichero devices invite --link-file ~/fichero-pair/link` prints the address and expiry; copy the file to the M4;
    `fichero devices pair --link-file ~/fichero-pair/link` pairs; `fichero devices list` on the Air shows it; `fichero devices revoke <id>` ends it.

### 10.9 Build order: slices, engine first, then shared Swift, then per platform

Each slice is one commit with its test written first (red), the code, the test green, and this spec's tag updated in the same commit.
Swift tests are written and marked "written, not yet built" until a build runs them (Pro disk and XCTest host are out, 2026-10-31).
- **E1** `sharing.multiuser-switch-needs-no-library`: drop the library dependency from `PUT /api/pair/multiuser`; test above.
- **E2** `sharing.state-names-every-address` + `sharing.tailnet-forward-whenever-tailscale-is-up`: `SharingStateResponse` fields; `start_for_engine`
  condition; tests above. (Additive contract: regen when Swift consumes the fields.)
- **E3** `sharing.cli-mints-a-link`: `fichero devices invite`; `FicheroClient.create_pairing_code`, `sharing_state`; test above.
- **E4** (held) `sharing.multiuser-404-is-a-409-in-the-engine`: not built; owner ruling (open question 4).
- **S1** `sharing.token-saves-on-every-build` + `sharing.failed-save-spends-nothing` + `sharing.qr-drawn-once-per-payload`'s encoders: `AuthTokenMiddleware`
  macOS queries; `RemoteClientPairing.inviteLinkString` and the QR encoder `.sortedKeys`; `pairAndPersistHost`/the Mac sheet call `revoke-self` on a
  persist failure; tests above (`fichero-api-client` package tests + general).
- **S1b** (optional, not taken) the entitlement route instead of the login keychain: `com.apple.application-identifier` = `QAPB6CWYR6.app.fichero.fichero` and `keychain-access-groups` = [the same] in `FicheroRelease.entitlements` (literal team id: the DMG lane substitutes nothing), which the embedded Developer ID profile authorises; no `release-all.sh` change. Only if a shared data-protection item is ever needed on a Mac.
- **S2** `sharing.multiuser-switch-says-the-refusal` + the People off-state model (`PeoplePaneOffState`, platform-aware words).
- **M1** `sharing.card-keeps-its-code` + `sharing.qr-drawn-once-per-payload`'s cache: `refreshKey`, `@State qrImage` keyed on the link; Mac UI test.
- **M2** `sharing.share-sheet-offers-both-addresses`: Add Device sheet + project Share sheet rows; Mac UI test.
- **M3** `sharing.people-pane-off-state` on the Mac: hide `+`, the line and the Open Sharing button; Mac UI test.
- **I1** `sharing.ios-settings-surface` (a Settings sheet from the connection menu with People) and then `sharing.people-pane-off-state`'s phone words (model built in M3); `IOSSettingsPeopleUITests` / `IPadSettingsPeopleUITests` added to their plans once the surface exists.
- **I2** (from §4/§7, after the above) `sharing.client-tries-every-address` + `sharing.failure-names-the-step` shared Swift, then the iOS Try again button.

### 10.10 Issues: reuse and new (titles proposed; nothing filed by this spec)

Reuse: **#5318** (address choice: `sharing.share-sheet-offers-both-addresses`, `sharing.state-names-every-address`,
`sharing.tailnet-forward-whenever-tailscale-is-up`); **#5917** (People off-state, reopened to `sharing.people-pane-off-state`); **#6299**
(raw `undocumented` errors: `sharing.multiuser-switch-says-the-refusal`, `sharing.undocumented-never-reaches-the-person`); **#5915**
(code lifetime on the card: `sharing.card-keeps-its-code` is its second half); **#5049** umbrella for the live script; **#5908** (the
password-gap words on the switch).
New, needed:
1. "Sharing card re-mints its code on every engine health check (refreshKey carries isBackendRunning) and rebuilds the QR on every render" — `sharing.card-keeps-its-code`, `sharing.qr-drawn-once-per-payload`.
2. "Pairing: DMG builds cannot save the device token (data-protection keychain, errSecMissingEntitlement -34018); the spent code leaves a ghost device on the host" — `sharing.token-saves-on-every-build`, `sharing.failed-save-spends-nothing`.
3. "PUT /api/pair/multiuser needs a library header the Settings window never sends: 400, the switch snaps back, the app says 'Unexpected response'" — `sharing.multiuser-switch-needs-no-library`.
4. "CLI: `fichero devices invite` mints a pairing link on the host so two machines link without the GUI" — `sharing.cli-mints-a-link`.
5. "iPhone and iPad have no Settings surface: the People pane and Sharing settings are unreachable" — `sharing.ios-settings-surface`.

### 10.11 Review findings (code against spec), ranked

Engine (B):
- **HIGH** `pairing.py:593` `PUT /api/pair/multiuser` depends on `get_library_database_for_write`: 400 with no library header; the action is app-scoped (§10.4).
- **HIGH** `pairing.py:920-922` + `:905` the code is spent and the device row made before the client has stored the token; no engine-side grace, the client must revoke (§10.3). Acceptable once `sharing.failed-save-spends-nothing` is built; until then every DMG guest leaves a ghost row.
- **MED** `tailscale_serve.py:145` the forward is made only for a `.ts.net` sharing address, so the one address that works on a campus network is unavailable to a `.local` sharer (§10.1).
- **MED** `pairing.py:191-199` `_sharing_state` names the tailnet address but not the sharing address or the LAN IP; the CLI cannot build a link without them (§10.5).
- **MED** `accounts.py:198-200`, `pairing.py:278-280` 404 for a known state (§5; held).
- **LOW** `pairing.py:113` `_PAIRING_CODES` is process-local and unbounded between prunes; `_prune_pairing_codes` runs on mint and redeem only, so an idle host keeps expired codes until the next call (memory only, no security effect).
- **LOW** `fichero_cli/pairing.py:60` and `RemoteCertificatePinning.swift:71-76` hold the same trust rule twice (§4 `sharing.trust-rule-is-one-function`).
- **MED** `sharing_host_file.py:30-36` the `sharing-host.json` a host writes into a synced project names ONE address, `FICHERO_PUBLIC_BASE_URL` (the `.local` name on a campus network), so a guest's "ask the host for a link" points at an address that may not resolve; it should carry the tailnet address too once `sharing.state-names-every-address` exists (`synced_host.SyncedHost` forbids extra keys: a reader change goes first). `synced_host.py`: read, no defect.
Front end (C):
- **HIGH** `AuthTokenMiddleware.swift:398` the data-protection flag on every macOS query; the fallback at `:314-327` is unreachable (§10.3).
- **HIGH** `ShareSettingsView+StateManagement.swift:8-12` `refreshKey` carries `isBackendRunning` (§10.2).
- **HIGH** `MultiuserSwitch.swift:28-29` throws away the engine's `detail` (§10.4); `UsersStore.swift:166` prints a raw enum (§5).
- **HIGH** `UsersContent+Layout.swift:24-27` `+` is offered while Multi-user is off; `SharingToggles.multiUserOffHint` is unused (§10.4; #5917 not built).
- **MED** `ShareSettingsView+QRCode.swift:51-62` QR rebuilt on every body evaluation; `RemoteClientPairingFlow.swift:72` and `+QRCode.swift:53` encoders without `.sortedKeys` (§10.2).
- **MED** `ShareSettingsView+QRCode.swift:29-44`, `ShareLibrarySheet+Sharing.swift:125-140` one address per payload while `sharingState.tailnetURL` is already loaded (§10.1).
- **MED** `MacRemoteClientPairingSection.swift:181`, `PairingIncomingLinkSheet.swift:68`, `ConnectPairingIOS.swift:246,254,317` show `localizedDescription` (§4).
- **MED** `SettingsGroupContainers.swift:81-92` iPhone/iPad Sharing settings hold People only: no words about where the switch is (§10.4).
- **LOW** `PairingIncomingLinkSheet.swift:40` Cancel only, no Try again (§7 `sharing.ios-says-which-step`).
UX completeness (every state has words and a way out): **off** → the switch and its caption (built); **on without Tailscale** → the
Tailscale row disabled with "Tailscale is not running on this Mac" (M2); **on with Tailscale** → two rows, default Tailscale (M2);
**code expired** → renewed at expiry (built, #5915), the guest's sentence (I2); **code used** → the guest's sentence (I2), the host's card
unchanged (M1); **error** → the engine's words beside the switch (S2), the step sentence on every sheet (I2), the Keychain sentence (S1).

## 11. Two Macs living with one library: the marks, the people, the sync (added 2026-11-05)

Owner rulings 2026-11-05: the accounts and people issues stay in this milestone; the shared-marks UI is one step and is built; the five sync issues are specified and built. Each line below is what a test can check; what exists was read from the code on 2026-11-05 (grep, not assumed). Ids here are new; the older ids they continue live in `transport/library-sharing.md` and `transport/multiuser-always-on.md` and are named in brackets. "Engine" is `fichero-server`, "app" is Swift.

**The marks (one step, 6.1).**

- `sharing.marks.guest-row` — **[PARTIAL]** (→ #5737; continues `sharing.sidebar.guest-row`) app. On the guest Mac a shared library is a row under PROJECTS in the same style as a local project, named as on the host, with the small shared mark (`person.2`), and the Inspector's Location reads "Shared from <host>"; no section of its own. *Exists:* the row, the mark and the Inspector line (`SharedProjectRowTests.swift`, written, the Swift unbuilt and the row unseen on a Mac). *Left:* build, run, and the two-Mac run. *Tests:* `fichero/Tests/Unit/general/Sharing/SharedProjectRowTests.swift`. Not built: `SharingSidebarMarksUITests.swift`.
- `sharing.marks.host-row` — **[PARTIAL]** (→ #5738; continues `sharing.sidebar.host-mark`) app, one engine field. On the host the shared project's row carries the mark while Sharing is on and loses it within one state read of Sharing going off; the Inspector lists each connected device as "<person> on <device>", each with **Remove** (revoke, which cascades, `sharing.sync.revoke-cascades-and-bites-at-once`) and **Forget** on the guest side (`DELETE /api/machines/{machine_id}`, `transfer.py:363`, `transfer.machine.forget-machine`). *Exists:* the mark observing the switch, and the Inspector's devices list with Remove (`HostSharedMarkTests.swift`, unbuilt). and the person's name (`GET /api/pair/devices` carries `username`; the Inspector reads "<person> on <device>", `PairedDeviceRecord.inspectorLabel`). *Left:* nothing on the host's list: Forget machine (`DELETE /api/machines/{machine_id}`, `transfer.py:363`) removes THIS Mac's saved token for a machine it paired with, so it belongs on the guest's list of machines, not here; the host removes a device with Remove. *Tests:* `fichero/Tests/Unit/general/Sharing/HostSharedMarkTests.swift`, `fichero-server/tests/unit/transport/test_pair_devices_name_the_person_to_spec.py`.
- `sharing.marks.off-greys-row` — **[PARTIAL]** (→ #5739; continues `sharing.sidebar.off-greys-row`; the event is `sharing.off-closes-the-guest`, #5731, Step 4.2) app. When `sharing.stopped` arrives the guest's row stays, greyed, reading "Not available: sharing is off on <host>"; its windows close with that one sentence; **Forget** removes the row; and the greyed row is still there after the guest app relaunches (the paired-host record carries the host-gone state). *Exists:* `HostGoneRowView` drawn from `LibraryManager.hostGoneRows`, filled by the event, Forget removes it (`SharingOffGreysRowTests.swift`, unbuilt); the host-gone rows are kept on this Mac in `UserDefaults` across a relaunch (`HostGoneRowStore`, `greyedRowsSurviveARelaunch`); they are not yet fields of a stored pairing record. *Left:* the windows' sentence, the run. *Tests:* `fichero/Tests/Unit/general/Sharing/SharingOffGreysRowTests.swift` . Not built: `SharingSidebarMarksUITests.swift`. *Built:* (#6360) an UNOPENED Shared Libraries row greys when its paired host answers and no longer lists its library: asked once at launch and when the app comes forward, at most once a minute per host, by the existing `GET /api/authz/libraries` read; a failed read changes nothing (`SharedRowAvailability`, `LibraryManager.checkSharedRows`, `SharedRowAvailabilityTests.swift`).

**The sync (Stage 7).**

- `sharing.sync.stream-keeps-every-event` — **[PARTIAL]** (→ #5314) engine. An event queued on the change stream while the engine's loop stalls past the 10 s keepalive is still sent (never dropped by the timeout branch); an audit secret already in the file wins over the keychain, so an audited action never waits on a keychain that does not answer; and in the live run a note made on A is on B's stream within 2 s. *Exists:* both engine fixes with tests (`changes.py:99-113`, `test_an_event_queued_while_the_loop_stalls_past_the_keepalive_is_still_sent`; `audit_chain.py:161-164`, `test_once_the_secret_fell_back_to_a_file_the_keychain_is_not_asked_again`). *Left:* the green run shown and the live step; the broad "sync actions on the loop stall every client" is its own issue, not this one. *Tests:* `fichero-server/tests/unit/api/test_changes_stream_endpoint.py`, `fichero-server/tests/unit/actions/test_action_audit_chain.py`, `docs/contributor_manual/testing/sharing-two-mac-checklist.md` (the note-appears step).
- `sharing.sync.stale-document-edit-offers-a-choice` — **[PARTIAL]** (→ #5348; continues `sharing.stale-edit-both-ways`, `sharing.stale-note-edit-is-refused-and-offered-a-choice`) app. A document edit sends `expected_updated_at` on `PUT /api/documents/{id}` and, on the engine's 409, the person gets **Keep mine** / **Take theirs** / **Compare** (both texts side by side), as the note editor does; the first edit is never silently lost on either Mac; a document deleted on the other Mac stays deleted here with one sentence. *Exists:* the engine refuses stale notes and documents (`test_stale_document_edit_to_spec.py`, the probe test); the note editor sends the version and offers the three choices (`NoteStaleResolutionTests.swift`). the document editor's text save sends the version it saw and, when refused, copies its text to the clipboard and says so (`DocumentService.updateDocument`, `persistPageContent`, `DocumentStaleResolutionTests.swift`). *Left:* the document editor's three-choice dialog (keep mine, take theirs, compare; today the next save replaces theirs), the two-Mac run. *Tests:* `fichero-server/tests/unit/transport/test_stale_document_edit_to_spec.py`, `fichero/Tests/Unit/general/Sharing/DocumentStaleResolutionTests.swift`.
- `sharing.sync.remote-run-live-in-activity` — **[PARTIAL]** (→ #5732; continues `sharing.remote-run-in-host-activity`) engine and app. A read run started on B is a row in A's Activity **list** within 2 s of starting, named "<person> on <device>", moves live through `/api/activity/stream` and ends there; headless, two engines: a job posted with the guest's token appears on the host's stream as started, progressing and finished. *Exists:* every run starter takes `started_by` from `started_by_for(ctx)`; the jobs list carries it (`test_remote_run_in_activity_to_spec.py`); the Swift detail shows it (`ActivityDetails.swift:137`). and the Activity list row's second line says "Started by <person> on <device>" for a run another Mac's person started (`ActivityMonitorRow.remoteStarter`, `ActivityRowStartedByTests.swift`; Swift unbuilt). *Left:* the live stream proof, the run. *Tests:* `fichero/Tests/Unit/general/Models/ActivityRowStartedByTests.swift`, `fichero-server/tests/unit/transport/test_remote_run_in_activity_to_spec.py`. Not built: `test_remote_run_live_on_the_hosts_stream_to_spec.py` (`FICHERO_TWO_ENGINES=1`, the `_two_engines.py` harness).
- `sharing.sync.undo-per-window-after-remote-edit` — **[PARTIAL]** (→ #5733; continues `sharing.undo-after-remote-edit`; the stack is `ui/undo-everywhere.md`, #5658) app. ⌘Z in A's window reverses A's last step in that window only; when B changed the same thing since, A's window shows the engine's sentence ("This was changed afterwards by <person> on <when>") and applies nothing; B's window's own undo is untouched. *Exists:* the engine refuses 409 `changed` naming the paired person (`undo.py:182`, `test_undo_after_remote_edit_to_spec.py`). the app's per-window stack shows the engine's sentence and keeps its step on `changed` (`WindowSteps`, `UndoRefusal.keepsTheStep`, `changedKeepsTheStep` in `UndoableChangeTests.swift`, #5658). *Left:* the two-Mac run. *Tests:* `fichero-server/tests/unit/transport/test_undo_after_remote_edit_to_spec.py`, `fichero/Tests/Unit/general/Models/UndoableChangeTests.swift`.
- `sharing.sync.revoke-cascades-and-bites-at-once` — **[PARTIAL]** (→ #5351; continues `sharing.revoke-cascades`, `sharing.revoke-closes-the-stream`) engine and app. Removing a device revokes it and every device it paired, down the chain; the confirm names those devices first; the removed devices' open streams end with `sharing.revoked` and their next request is 401; and a tailnet peer behind `tailscale serve` is never read as loopback (a live check: a guest over the tailnet with the bootstrap token alone reaches nothing). *Exists:* the engine cascade (`test_revoke_cascades_to_spec.py`), the Swift confirm (`devicesRevokedWith`, `PairedDevicesSectionView.swift`, parse-checked), the stream close (#5913). *Left:* the run on a Mac; the tailnet-not-loopback live step. *Tests:* `fichero-server/tests/unit/transport/test_revoke_cascades_to_spec.py`, `fichero/Tests/Unit/general/Transport/RemoteAccessConfigTests.swift` (`devicesRevokedWith`), the checklist (revoke and tailnet steps).

**The people (Stage 8).**

- `sharing.people.settings-screen` — **[PARTIAL]** (→ #2083; continues `sharing.accounts-and-users-settings`, the Accounts row of `sharing.settings.three-panes`) app. Settings › Sharing › Accounts shows who is signed in, lists every account, adds a person, removes or disables a non-owner, and shows each person's access across **every** library (owner / editor / viewer / no access, in those words) with the per-library role edited from there, not only from the project Share sheet; password and account actions sit apart from library access; no invitations UI. Acceptance: with libraries L1 and L2 and a person Maya, editor on L1 and no access on L2, `GET /api/authz/libraries` as Maya lists L1 only and a write to L2 is 403. *Exists:* `UsersSettingsView.swift`, `AccountsAddSheet.swift`, `TurnOnAccountsSheet.swift`, `UsersStore.swift` (add, remove, disable; read, not run); per-library roles are edited in the project Share sheet (`ShareLibrarySheet+Members.swift`); the access-across-libraries view, read-only (`GET /api/authz/access-matrix`, owner-only; `AccessMatrixView`, `UsersStore.loadAccessMatrix`, `test_access_matrix_to_spec.py`, `AccountsAccessMatrixTests.swift`; Swift unbuilt). *Left:* editing a person's role per library from that grid, sign-in from this screen, a run with two accounts. *Tests:* `fichero-server/tests/unit/security/test_auth_accounts.py` (the role rows), `fichero-server/tests/unit/security/test_access_matrix_to_spec.py`, `fichero/Tests/Unit/general/Sharing/AccountsAccessMatrixTests.swift`.
- `sharing.people.device-is-a-person` — **[PARTIAL]** (→ #2403, #5735; continues `sharing.device-chooses-person`, `sharing.names-on-edits`) engine and app. A paired device is bound to the person who signed in on it, never to whoever minted the code: the engine refuses a pairing that names no person (401 `person required`) and every guest entry point (the Mac drawer, the phone's link sheet, the QR scan, the nearby list) asks for the person at exactly that answer (key or password); an edit made on B is recorded as B's person on B's device, and A shows that name on the change (the change event's `person` and `device` read by the app, the Inspector's "edited by <person> on <device>"). *Exists:* the engine (`test_device_chooses_person_to_spec.py`, `test_two_accounts_names_on_edits_to_spec.py`, `ChangeEvent.person/device`); the Mac drawer (`PairingPersonPickerTests.swift`). the app reads `person`/`device` from the change stream and the Inspector's Info tab says "Edited by <person> on <device>" (`RemoteEditor`, `DocumentStore.remoteEditors`, `EditNamesPersonTests.swift`; Swift unbuilt). *Left:* the iOS and QR entry points, the run. *Tests:* `fichero/Tests/Unit/general/Sharing/PairingPersonPickerTests.swift`, `fichero/Tests/Unit/general/Sharing/EditNamesPersonTests.swift`, `fichero-server/tests/unit/transport/test_two_accounts_names_on_edits_to_spec.py`.
- `sharing.people.every-connection-signed-in` — **[PARTIAL]** (→ #3284; continues `multiuser.always-on`, `multiuser.loopback-is-not-owner`, `sharing.multiuser-mode-single-source`) engine. No request from a paired device, the CLI or an MCP client is served without a signed-in person; loopback TCP or the socket with the bootstrap token and no session reaches only first-run and sign-in (401 elsewhere); `check_no_ambient_owner_in_tests` turns blocking with a baseline of 0. The Multi-user **switch** itself (kept by §5 and Steps 3.3/4.3, removed by `multiuser-always-on.md` slice 10) is the owner's ruling, held as Step 1.6 holds the 404: this behaviour is built either way, and the switch's removal is its own commit on the ruling. *Exists:* the switch moved beside Sharing, persisted by one audited action (`SharingToggles.swift`, `test_sharing_state_and_multiuser_switch_to_spec.py`); the ambient owner ratchet in warn mode (baseline 43); the challenge sign-in routes. *Left:* the enforcement, the ratchet blocking, the ruling. *Tests:* `scripts/check_no_ambient_owner_in_tests.py`. Not built: `test_multiuser_always_on_to_spec.py` (named by `multiuser-always-on.md`).
- `sharing.people.deny-reaches-the-documents-records` — **[OK]** (→ #4917; continues `sharing.multiuser-access`) engine. A deny or grant on a document, or on a folder above it, applies to everything addressed by an id that belongs to the document: its artifacts, segments and their passes, matches and versions, its notes, annotations and citations. `authz._target_ancestor_ids` resolves the id to its owning document first (`_DOCUMENT_ID_RESOLVERS`), then walks `parent_id`; a lookup error, a row with no document or a missing document REFUSES (`AuthzResolutionError` is a deny), never "no ancestors, no deny". Multi-user mode only; loopback owner and single-user unchanged. *Exists:* all of it, built after the issue was filed. *Left:* nothing in the engine; the issue stays open only until a request-level test names its three cases (a GET by artifact id, the document's artifact list, a forced lookup error) under #4917, and #4917 is then closed. *Tests:* `fichero-server/tests/unit/security/test_authz_ancestor_adversarial.py`, `fichero-server/tests/unit/api/test_segments_multiuser_access.py`, `fichero-server/tests/unit/security/test_a_page_deny_reaches_every_record_on_it.py`.
- `sharing.guest.machines-group` — **[PARTIAL]** (→ #6360; continues `sharing.marks.guest-row`) app. The sidebar has a group for paired machines, like Finder's Locations: one row per Mac this Mac has paired with, named as the host names itself, and under it the libraries that host gave this device (the host's `GET /api/authz/libraries` for this device), each a row that opens it. Choosing one makes it the library on screen; Sharing off on the host greys it once it is open (`sharing.marks.off-greys-row`), and a row the host no longer lists greys unopened too; an unopened row of a host that is wholly off is not greyed (manager ruling 2026-11-08, above). *Built:* pairing and the token in the Keychain (`PairingSequence`, `LivePairingHost`, `RemoteClientPairingFlow.pairAndPersistHost`); the guest row mark and the host-gone row (`SharedMark`, `HostGoneRow`). *Built (#6360):* one sidebar section per host Mac below Projects, titled by its name (`SharedLibraryRowView`, one row per library) and the list behind it (`PairedMachineStore`, written on every successful pairing, one row per host, kept across a relaunch). *Not built:* a row that opens its library beside the local ones (a row opens it through the one host switch, `SharedLibraryOpener`: the whole window switches to the host, a stopgap until Step 8.6; the app keeps ONE paired host: `EngineConfig.storeHost`, `PairedHostEndpointStore.clear()` then `record`, one `pairedLibraryPathKey`), a way to open a host's library beside the local ones: today a successful pairing makes the host THE app-wide engine host (the app dials it for everything), and a library reads its host from that one setting (`LibraryManager.LibraryReference.locationDescriptor`: "once libraries are pinned to a SPECIFIC remote host (#2866 follow-up)"). *Tests:* `PairedMachinesGroupTests.swift` (the store). *Built:* (#6432, #6433) the Settings connect window closes once a connect succeeded (`ConnectSheetModel.finishConnect`); a Connect reads the host's whole list for this device at once (`checkSharedRows`), and a Tailscale-named host is read with no pin, which it keeps none of (`SharedRowAvailability.readTrust`). *Tests:* `ConnectSheetModelTests.swift`, `SharedRowAvailabilityTests.swift`. *Built (#6459, builder's choice):* every paired Mac has its section, so one whose library list is empty shows "<host> hasn't shared any project yet" under its name instead of vanishing (`SharedMachineSections`, the Mac sidebar only; the phone's chooser keeps its own rule, `sharing.ios.shared-library-chooser`); the sidebar's how-to-pair sentence is for no paired Mac at all. *Not built:* a Reconnect on that row, the same on the phone. *Tests:* `SharedMachineSectionsTests.swift` (a paired Mac that shared nothing is listed with its own sentence, each Mac keeps its libraries in order).
- `sharing.guest.connect-to-library` — **[GAP]** (→ #6360) app. File › Connect to Library… (Finder's Connect to Server in shape) takes a pair link or an address and a code, pairs, and adds that Mac to the same list the sidebar group reads, with the libraries it gave this device; a link that names a project opens it. There is one list behind the menu item and the group, and Settings › Sharing › Connect to Another Mac… (`ConnectSheetModel`) is the same sheet. *Built:* the Connect to Another Mac sheet in Settings (`sharing.settings.connect-sheet`) pairs from a link or address; File › Connect to Library… (#6360) opens that sheet. *Not built:* opening the project the link names, and what pairing does after it succeeds beyond replacing the one paired host. *Tests:* none yet. Not built: `ConnectToLibraryTests.swift`.
- `sharing.guest.empty-state-says-how-to-pair` — **[PARTIAL]** (→ #6360) app, iPhone and iPad. With no paired Mac the chooser reads "No Macs yet. On the Mac, turn on Sharing and show its pairing code, then choose Connect." *Built (#6360):* the sentence in the empty chooser. *Not built:* a live look at it. *Tests:* `PairedMachinesGroupTests.swift`. The Mac sidebar does not show it: see `sharing.guest.no-section-until-paired`.
- `sharing.guest.no-section-until-paired` — **[PARTIAL]** (→ #6360) app, Mac. With no paired Mac the sidebar has no "Shared Libraries" section at all, heading and sentence both; the way in is File › Connect to Library…. Owner ruling 2026-11-11, which replaces the 2026-11-06 ruling that kept the group with a how-to-pair sentence. *Built:* the section is not drawn. *Not built:* a live look at it. *Tests:* `SharedMachineSectionsTests.swift`.
- `sharing.host.asks-which-projects-when-nothing-is-shared` — **[PARTIAL]** (→ #6366) app. When sharing comes on and no project of this Mac is shared with anyone, the person is asked, in a dialog, which project(s) to share, instead of being left on the Settings pane with a switch and a grey line. The dialog opens from every place sharing comes on: the Settings › Sharing switch ("Share this Mac's projects", `SharingPaneText.switchTitle`), Set Up's sharing *Yes* (`sharing.setup-asks-sharing`), and the project Share sheet's own turn-on (`ShareLibrarySheet+Sharing.swift` `enableHostingForShare`, which already knows its project and so pre-checks it). It also opens from a button on the pane, "Share a Project…", shown under the switch whenever sharing is on and nothing is shared, so Not Now is not the end. "Nothing is shared" is the engine's answer, one field: `GET /api/pair/sharing-state` gains `shared_library_count` (the libraries with at least one role granted to a person, or given to a paired device), so the app asks nothing new and the pane, Set Up and the sheet read one number. Acceptance: with sharing off and no grants, turning the switch on shows the dialog; with one project already shared, turning the switch on shows no dialog; with sharing on and nothing shared, the pane shows the "Share a Project…" button and a sentence "Sharing is on. No project is shared yet.", and the button opens the dialog; `GET /api/pair/sharing-state` on a Mac with two libraries and one grant says `shared_library_count: 1`. *Decided here:* the engine counts, not the app, because the app would otherwise have to read the access matrix (owner-only) and the devices' libraries and agree with itself across three screens. *Built (#6366):* `shared_library_count` on `GET /api/pair/sharing` (`pairing._shared_library_count`: projects a person other than the owner holds a role on; with no accounts, this Mac's known projects once a device is paired); the Settings switch opens the dialog when the count is 0; the pane's sentence and "Share a Project…" button. *Not built:* the dialog from Set Up's *Yes* and from the project Share sheet's turn-on (that sheet already shares its own project). *Tests:* `test_sharing_state_counts_shared_libraries.py`, `ShareWhichProjectsDialogTests.swift`.
- `sharing.host.which-projects-dialog` — **[PARTIAL]** (→ #6366) app. The dialog is a native sheet titled "Which projects do you want to share?", one row per library this Mac has (the libraries list the sidebar shows, in its order), each a check box with the project's name; a checked row shows who can open it: with Multi-user on, a picker of the people in Accounts (`sharing.people.settings-screen`), many may be chosen, each with Editor or Viewer (the Share sheet's two roles, `ShareLibrarySheet.shareRoles`; Owner is never offered here either); with Multi-user off, the row reads "Any device you pair with this Mac" and offers no picker. Two buttons: **Share** (default, enabled once one row is checked) and **Not Now**. Share runs, for each checked project and each chosen person, the one audited share action the Share sheet runs (`POST /api/authz/share`, `acl.set`), nothing else; with Multi-user off it records the checked projects as the ones a new pairing is given (what a project link already does for one project, `sharing.link-grants-its-project`). Not Now leaves sharing on, closes the sheet and shows the pane's sentence and button. Acceptance: on a Mac with projects A and B, Multi-user on and people Maya and Sam, checking A, choosing Maya as Editor and pressing Share sends exactly one share call (A, Maya, editor) and the sheet closes with A's row showing "Maya can edit A" in its Share sheet; checking nothing leaves Share disabled; Not Now sends no call and the pane shows "Sharing is on. No project is shared yet." with the button; with Multi-user off the row shows the device sentence and Share with A checked ends with one link that grants A, shown with Copy Link. a11y ids: `sharing.whichProjects.sheet`, `sharing.whichProjects.row.<libraryId>`, `sharing.whichProjects.people.<libraryId>`, `sharing.whichProjects.share`, `sharing.whichProjects.notNow`, `sharing.whichProjects.shareAProject` (the pane's button). *Decided here:* the sheet is a thin front on the Share sheet's own action, so a project shared here and one shared from its Share sheet are the same grant; no new engine route beyond the one count. *Built (#6366):* `ShareWhichProjectsSheet` and `ShareWhichProjectsModel`: a row per open project (never the always-there one), a check box each; with Multi-user on, each person in Accounts with No access / Editor / Viewer; Share sends the Share sheet's own call per grant; a failure is an alert and the checks stay. With Multi-user off the first checked project's own Share sheet opens and makes its link with Copy Link (`sharing.host.share-in-every-mode`). *Built (the ruled sub-bullet):* with Multi-user off, Share opens the first checked project's Share sheet, whose ONE link gives every checked project (`ShareWhichProjectsModel.linkSet`, `ShareLibrarySheet.alsoLibraries`, `POST /api/pair/code`'s `libraries`; the redeem registers and grants each that is a project on this Mac, a path with none is left out), with Copy Link. *Not built:* the link on the dialog's own last page (it is the first project's Share sheet); the libraries the sidebar shows but are not open; the UI test. *Tests:* `ShareWhichProjectsDialogTests.swift`, `transport/test_one_link_for_a_set_of_projects_to_spec.py`.
  - Ruled 2026-11-06 (the manager's default; the owner may veto): with Multi-user off, Share ends by minting ONE pairing link that grants the checked projects and shows it in the sheet with **Copy Link** (the person leaves with something clear to send); Devices › Add Device… stays for further devices. Acceptance: with Multi-user off, A and B checked and Share pressed, the sheet's last page shows one link and a Copy Link button, the link redeemed on another Mac gives that device A and B and nothing else (`sharing.link-grants-its-project`, now for a set), and Add Device… still mints its own links afterwards. a11y ids: `sharing.whichProjects.link`, `sharing.whichProjects.copyLink`.
- `sharing.host.dialog-errors-are-alerts` — **[PARTIAL]** (→ #6366, #6361) app. Nothing in this flow writes raw text to the pane's grey line (`SharingPaneText.statusLine`'s `error`, today set from `error.localizedDescription` in eight places of `ShareSettingsView+StateManagement.swift`, among them the devices list, which is where "Client encountered an error invoking the operation list_devices_api_pair_devices_get … Connection refused" came from on the M1 Air when its engine was not listening on 8765). Every failure while sharing comes on, while the dialog loads its rows or shares, and while the pane refreshes its devices, is one alert of the kind `sharing.alerts.one-alert-per-failure` describes (lane-sharing's Step 8.8, #6361): what happened, why in plain words, the fix as a button where there is one. For the engine-not-listening case the alert says the engine on this Mac is not accepting connections on the sharing port and offers **Turn Sharing Off and On**, which re-applies the listener. Acceptance: with the engine's listener closed, turning the switch on shows that alert and the pane's grey line stays grey with no error text; a share call that fails with 403 shows an alert saying this Mac's owner must share (the fix: Sign In as Owner) and the dialog stays open with the person's checks kept; after the alert is dismissed nothing is written to the grey line. *Decided here:* the dialog keeps its state through an alert, because retyping the choice after a transient error is what #6366 complains of. *Built:* every failure write in the pane (`ShareSettingsView.showFailure`: Multi-user, turning Sharing on or off, the code and its renewal, the devices list, removing a device, starting the engine) and in the Share sheet (`ShareLibrarySheet.showFailure`) is the alert of `SharingFailurePrompt.make(sharing:)`; a refused or unanswered engine offers Turn Sharing Off and On (it runs `applySharing`); a 403 says only the owner can share and offers **Sign In as Owner** (the pane and the Share sheet), which signs this app in again by the owner key with no password (`OwnerSignInCoordinator.run`), the sheet keeping its choices for the second try; the engine's own words are shown as they are; the grey line keeps only our notes (the Multi-user migration's). *Tests:* `Sharing/SharingFailureAlertTests.swift`.
- `sharing.host.share-in-every-mode` — **[PARTIAL]** (→ #6373, #6366) app. Share… is on a project row's right-click (and the library header's menu) in every mode, Multi-user on or off; never on the always-there project. With Multi-user off the Share sheet is the project's link (no person picker, no members): one line says whoever opens the link connects to this project and that named people need accounts, then the link; with Sharing off it offers Turn Sharing On, which turns Sharing on and makes the link. With Multi-user on it is the person form as before. A folder is still shared to a person. *Built:* `ProjectRowMenuOffers` (Share in every mode), `ShareLibrarySheet.sharesWithPeople`, `noAccountsSection`. *Not built:* the sidebar badge "Sharing is off" as a button, and the which-projects dialog (#6366, Step 8.10 on the spec writer's branch). The sheet's code names its project (`PairingService.createPairingCode(library:)`, the body's `library`), so the redeem gives the device that project in both modes (`sharing.link-grants-its-project`; before this the sheet's code named none, and a guest of a Mac whose list was empty read "didn't give this device that project"). An empty list on the host is its own failure, `hostSharesNothing` (Step 8.8's table). *Tests:* `ShareWithoutAccountsTests.swift`, `PairingSequenceTests.swift` (an empty host list).
- `sharing.guest.library-pinned-to-its-host` — **[GAP]** (→ #6360, #2866) app. A shared library opens beside the Mac's own projects and each library dials its own host: the local project keeps the embedded engine, the shared one the paired Mac, in the same window set, so choosing one in the paired-machines group does not switch the whole app away from the local ones. *Built (slice 1, #6360):* `LibraryReference.pinnedToHost`: a pinned library dials its own `host` over HTTPS and `reconfigureBackendHost` / `reresolveEndpoint` read `currentEndpoint`, so the app-wide host switch and an engine restart leave it alone. *Built (slice 2, #6360):* a Shared Libraries row opens its library through `switchToRemoteLibrary(pinnedTo:)` (`SharedLibraryOpener`): pinned, beside the local projects, no engine stop and no app-wide host write; the token is read per request from the library's own host (`AuthTokenMiddleware`); a host that does not answer drops the library again with the one failure alert. *Built (slice 3, #6360):* the services made from a library's `APIClient` (`ActivityService`, `ArtifactService`, `RenditionService`, `StorageService`, `ImportService`) share its client instead of building one on the app-wide host. *Not built:* the app-wide parts that still read the one host (AppState health and heartbeat, the stores and views that build a `FicheroClient(baseURL: EngineConfig.host)` of their own); of these, item (3), the status pill and heartbeat also showing a pinned host that is down, is CLOSED AS BY DESIGN after the lane-sharing audit of 2026-11-08 (the Shared Libraries sidebar row is the one place a down host shows; Step 8.14's connection popover lists every connection's state), so no app-wide heartbeat is built for it. Slice 7 (#6418), built: pairing a Mac no longer writes the paired host as THIS Mac's engine (`persistPairedHost(makesAppHost: false)`; before it, the next launch dialled that Mac and started no engine of its own, so a sleeping host left a dead window); Connect in Settings › Sharing pairs and keeps this Mac's engine, and "Use It as This Mac's Engine" is the explicit whole-Mac switch (`EngineConfig.wholeMacHostKey`); a paired Mac stored as the engine without that choice is dropped at launch (`EngineConfig.dropUnchosenPairedHost`). *Tests:* `PairingKeepsLocalEngineTests.swift`. Slice 6 (#6360), built: the host's own list of libraries for this device is the one the same read brings back (`GET /api/authz/libraries`, no new route): a library the host lists that the row did not show is added and kept across a relaunch (`SharedRowAvailability.merged`); one it stopped listing stays, greyed, until Forget. Ruled by the manager 2026-11-08 (the builder asked; an unopened row is NOT greyed when Sharing is off on the whole host no answer is the same as a sleeping host, so a heuristic would false-grey; open rows grey through `sharing.stopped`; revisit if the owner's pairing walk shows the gap). Slice 5 also: an unopened row greys when its host answers and no longer lists its library (`sharing.marks.off-greys-row`). Slice 4 (#6360), built: the open pinned libraries are saved apart from the local paths (`FicheroPinnedLibraries`, never restored as a local path) and reopened beside the local ones at launch for each host still paired (`restorePinnedLibraries`). Entries an older build saved into the local list are not removed on open. *Tests:* `LibraryPinnedToHostTests.swift` (the endpoint, open beside local, saved apart, services). *Built:* (#6418, second half) a host the person set that does not answer at launch shows the window's connection failure with a sentence naming the Mac ("Fichero could not reach <host>. You can use this Mac's own engine instead; your libraries here are untouched.") and a "Use Own Engine" button, on a Mac only; it runs the one host switch with the host cleared (and the whole-Mac choice forgotten), so the embedded engine starts and the paired Macs stay paired. *Tests:* `OwnEngineOfferTests.swift` (only a Mac dialling another machine offers it, the sentence names the host, forgetting the host forgets the choice).
- `sharing.launch.opens-few-at-a-time` — **[PARTIAL]** (#6430; owner: the Pro's launch spinner with four libraries) engine and app. A launch that restores several libraries opens at most two at once, the one asked for first first, so a small machine is not starved while they all open; the app says which it is opening ("Opening <name> (2 of 4)…"). *Built:* (#6430) the engine's `OpenGate` in `DatabaseManager.get_database` (the cap is `FICHERO_LIBRARY_OPEN_CAP`, default 2; an open already running inside the gate, such as a move resuming, passes). (#6430 app) the pane of a library still loading says "Opening <name> (2 of 4)…" when more than one is open (`LibraryOpeningProgress`, the order `launchOpenOrder` set at ready); the front library, the one last on screen, is loaded and awaited first by `backendDidBecomeReady`, so the engine is asked for it first and its gate lets it in first. *Tests:* `test_library_open_gate.py` (the gate: four opens never exceed the cap, first asked is first opened, a nested open passes; and `get_database` opens real libraries through it), `LibraryOpeningProgressTests.swift` (the line, the first place, one library, a stranger).
- `sharing.connections.popover-lists-every-connection` — **[PARTIAL]** (#6434; owner on the 2026-11-08 dev build; `ui/menus-and-commands.md` `menus.less-text-more-indicator`) the toolbar's connection popover (`EngineStatusToolbarItem`, today one title, one sentence and one action: "Connected · Connected to a Fichero server on another machine", #4380) lists EVERY connection as one row each, no sentences: **This Mac** (the embedded engine: a state glyph for running, starting, stopped; the local projects open), then each PAIRED Mac by NAME (`PairedMachine.name`, `PairedMachineStore`), its row showing a state glyph (connected, asleep, unreachable: the glyphs of `activity.pane.one-glyph-per-state`), the address in use as a badge (Tailscale or LAN, read from the host's address), the library or libraries it gave this device, and when it last answered as ONE short time; a problem is ONE short line under the row (the typed failure's title from `ConnectionPresentation`) with its FIX BUTTON (`ConnectionPresentation.Action`: Reconnect, Reset Sign-In, Reset Certificate, Forget This Mac; the one the failure names, as `sharing.alerts.one-alert-per-failure` maps them), never a paragraph; per-row actions **Use** (Use It as This Mac's Engine, the explicit whole-Mac switch `EngineConfig.wholeMacHostKey`, greyed on the row already in use) and **Disconnect** (closes that host's pinned libraries and forgets the pairing, the existing Forget), plus Show Log for that host; the toolbar glyph carries ONE summary (the count connected as a badge, the worst state's glyph when one is down). The states come from the paths that exist: This Mac from the engine-status heartbeat (`AppState+Heartbeat`, `pingBackendOnce`), a paired host from its pinned libraries' own clients (`LibraryReference.pinnedToHost`, `currentEndpoint`) and the host read `SharedRowAvailability` already makes; no new route. Text budget: a row's name at most four words, the problem line at most eight, no full stop in a row. Acceptance: with the local engine running and two paired Macs, one asleep, the popover shows three rows: This Mac running, one connected with its library and "2 min", one asleep with "Not answering" and Reconnect; Use on the connected one switches the whole Mac and greys its button; the toolbar badge reads 2. *Built:* the popover lists This Mac and each paired Mac as one row (`ConnectionRows`, `ConnectionRowsView`, shown once a Mac is paired) with a state glyph, name (at most four words), first library, Tailscale or LAN badge, one short time since the host last answered, and for a Mac that did not answer ONE short line ("Not answering") with Reconnect, which asks that host again past the 60 s throttle (`LibraryManager.askHostAgain`); a row's state is read from the host. A paired Mac's state is what `checkSharedRows` last saw (`hostStates`, `hostLastAnswered`), else connected when one of its libraries is open. *Not built:* Disconnect (it must forget the pairing the way Forget This Mac does, token, pinned key and the host's revoke, with a confirm), Use (the whole-Mac switch from a row), Show Log per host, the toolbar badge count and worst-state glyph, Reset Sign-In and Reset Certificate on a row, an `unreachable` state apart from `asleep`. *Tests:* `ConnectionPopoverRowsTests.swift` (the acceptance's three rows, Use greyed on the row in use, the text budget, Restart on a stopped engine); `SharedRowAvailabilityTests.swift` (an answer is connected with its time, a failed read is asleep, Reconnect asks past the throttle). *Test:* `ConnectionPopoverRowsTests.swift` (slice 1 written; the rows from a paired list and two states, the problem line and its button, the summary badge, the word counts), the existing `HeartbeatLowersAlarmTests.swift` and `PairingKeepsLocalEngineTests.swift`.
- `sharing.ios.shared-library-chooser` — **[PARTIAL]** (→ #5396, #5734, #3371) app, iPhone and iPad. After pairing, the phone or tablet shows a list of only the libraries shared with the signed-in person (the same `PairedMachineStore` the Mac's Shared Libraries section reads, from the host's `GET /api/authz/libraries` for that person or this device), each labelled by its host Mac; tapping one opens it through the same host switch the Mac row uses. With none yet, the list says how to pair (the empty-state sentence, with "Connect" in place of the File menu). *Built:* the phone's pairing screen (`RemoteConnectionSetupView` in `ConnectPairingIOS.swift`: nearby Macs, QR scan, typed entry) calls the shared `RemoteClientPairing.pairAndPersistHost`, which records the host in `PairedMachineStore` (#6360). *Built (#5396):* the list (`SharedLibraryChooserView`) behind a Libraries toolbar button, and as the screen when no library is open; tapping a row writes that host and library and runs the phone's one connect path (`SharedLibraryOpener.openOnDevice`); the list refreshes on every pairing (`adoptPairedRemoteLibrary`). *Not built:* asking the host for its current list (the list holds what pairing confirmed), a live look on a phone. *Tests:* `SharedLibraryChooserIOSTests.swift`.
- `sharing.ios.no-empty-detail` — **[PARTIAL]** (→ #5396) app, iPhone and iPad. The phone never lands on an empty detail view or the Mac's split layout squeezed onto a phone: on iPhone the chooser is the root and a library pushes on top of it (back returns to the chooser); on iPad the chooser is the sidebar and the detail shows the chosen library, or the chooser's one sentence when none is chosen. *Built (#5396):* with no library open the phone shows the chooser (or its how-to-pair sentence), not "Project Unavailable". *Not built:* the iPhone push from chooser to library and the iPad sidebar form; the Mac split layout on a phone. *Tests:* `SharedLibraryChooserIOSTests.swift`.
- `sharing.alerts.one-alert-per-failure` — **[PARTIAL]** (→ #6361) app, Mac, iPhone and iPad. Every pairing or sharing failure the app can show is ONE native alert from the run-failure alert component (`RunFailureAlert`, `specs/ai/run-failure-alerts.md` Step 2.1): the title says what happened, the message says why in plain words and then the fix, and a button acts on the fix where one exists, then "Copy Details" and "OK". No raw error text (`error.localizedDescription`, an OSStatus, an HTTP code) reaches the person. The cases and their buttons:

  | Case (`PairingFailure` or source) | What happened (title) | Why, then the fix (message: today's `sentence`) | Fix button |
  |---|---|---|---|
  | `invalidLink` | This isn't a pairing link | not a Fichero link; copy it again from Sharing on the other Mac | Paste Link Again |
  | `olderLink` | This link is for an older Fichero | the link's format changed; ask for a new link | — |
  | `nameNotFound` | Can't find <host> | the name is not on this network; use the Tailscale address or the same Wi-Fi | Open Tailscale |
  | `tailnetNameNotFound` | Can't find <host> | Tailscale isn't running on this device; start it | Open Tailscale |
  | `noAnswer` (timeout) | <host> didn't answer | Fichero is not open there, Sharing is off, or the network keeps devices apart | Try Again |
  | `refused` | <host> isn't listening | Fichero is on but not sharing; turn Sharing off and on there | Try Again |
  | `offline` | No network | this device has no connection | Open Network Settings |
  | `certificatePin` (pin mismatch) | A different Mac answered | its security key is not the link's; scan or paste a new link | Paste Link Again |
  | `certificateName` | <host>'s certificate doesn't match | turn Sharing off and on there so it makes a new one | Try Again |
  | `tailnetByNumber` | Tailscale needs the name | the link used a number; ask for a new link | — |
  | `codeUsedOrExpired` (link expired) | That code has expired | codes last 10 minutes or are used once; make a new one | Paste Link Again |
  | `tooManyTries` | Too many tries | wait a minute | Try Again (after the wait) |
  | `personRequired` | Sign in to <host> | this library uses accounts | Sign In… (focuses the name field) |
  | `versionMismatch` | Fichero versions don't match | names both versions and which Mac is older | Check for Updates… |
  | `libraryNotGiven` | <host> didn't share that project with you | the link was for another project or person; ask for a new link | — |
  | `hostSharesNothing` (t63: the host's list for this device is empty) | <host> hasn't shared any project yet | Sharing is on but no project is shared; on that Mac, right-click a project and choose Share…, then use that link | — |
  | `hostStopped` (`SharingStopped`) | <host> stopped sharing | ask them to turn Sharing on; the row stays greyed (`sharing.marks.off-greys-row`) | — |
  | `deviceForgotten` (revoked token) | <host> no longer knows this device | the owner removed it; pair again | Paste Link Again |
  | missing `:8765` tailnet forward (#6358) | <host>'s Tailscale address isn't set up | the host saved a Tailscale name but has no forward to Fichero; on the host, turn Sharing off and on | Copy Details |
  | host unreachable after a Shared Libraries row (`SharedLibraryOpener`, `EngineHostSwitch` not responding) | <host> isn't responding | it is off, asleep, or Sharing is off; the app went back to this Mac's projects | Try Again |
  | the Keychain refused the token (`tokenNotSaved`, `sharing.failed-save-spends-nothing`) | This device couldn't keep its key | the pairing was undone on the host; pair again | Try Again |

  *Built:* `SharingFailurePrompt` turns a `PairingFailure` (or whatever a pairing threw: a transport code becomes its step, our own sentences stay, anything else is a plain line with the raw text in Copy Details only) into the generic `FailureAlertPrompt` that `FailureAlert` shows (lane-onboard's component, #6354): the table's title, the step's sentence, its fix where the view can do it, Copy Details, OK. The Mac connect sheet (`MacRemoteClientPairingSection`) offers every fix (Paste Link Again reads the pasteboard, Sign In… shows the person fields, Check for Updates… is Sparkle's); the phone's Connect screen and link sheet offer the URL fixes, Try Again and Paste Link Again; a host that stopped sharing and a Shared Libraries row that would not open are `LibraryManager.sharingFailure`, shown at the app's root on Mac and iPhone (a row that would not open says which: a revoked key is `deviceForgotten`'s words with no Try Again, a certificate that no longer matches is `certificateName`'s, a host that timed out is "<host> is slow to answer" (it may be busy opening a large library; Try Again), anything else is "isn't responding"; `SharedLibraryOpener.failureWords`, #6459) (it replaces `sharingStoppedNotice`, which no view showed); `PairingFailureButtons` is gone. *Not built:* the missing tailnet forward (#6358) and the Keychain refusal as their own titled rows (the Keychain one has its title in `make(pairing:)`, the forward reaches the person as `refused` or `noAnswer`); Try Again for `tooManyTries` is offered at once, not after the wait. *Tests:* `Sharing/SharingFailureAlertTests.swift`, `SharedLibraryOpenerFailureTests.swift` (each cause its own words; a revoked key offers no Try Again).
- `sharing.alerts.no-bottom-strip` — **[OK]** (→ #6361) app. The raw error lines go: the connect sheet's error `Label`, the connection view's failure text for a paired host, and any text set from `error.localizedDescription` for a sharing failure. Each becomes the alert above. *Built:* the Mac connect sheet's `Label`, the phone's red line and its buttons, the link sheet's error page, the pane's and the Share sheet's error writes are all `SharingFailurePrompt` alerts; `PairingCodeRenewal.Outcome.failed` carries the error, not its text; a scanned QR that is not a pairing payload is the "This isn't a pairing link" alert; the which-projects dialog's share failure (`ShareWhichProjectsSheet`), the Users pane's account and role changes (`UsersContent+AccountActions`, `+RoleActions`), the Share sheet's member changes and Create Person (`ShareLibrarySheet+Members`, `+UserManagement`) and the sidebar badge's member changes (`LibrarySharingBadge`) are the alert too, each offering Sign In as Owner on a 403; a member list that will not load says so in plain words, and a roles snapshot that will not load hides the roles section without an alert on every open. The Add Account sheet shows only the engine's words (`SharingFailurePrompt.engineWords`), else "Couldn't add the account". *Tests:* `Sharing/SharingFailureAlertTests.swift` (a client error's text never reaches the message).
- `sharing.people.one-way-to-do-people` — **[PARTIAL]** (→ #2083, #2403, #5735, #3284) app and engine. The one design for people, end to end (manager's default, owner may veto, 2026-11-06): **people** live in Settings › Sharing › Accounts on the host (add a person with a name and a sign-in, remove or disable one; Step 8.1, `sharing.people.settings-screen`); **what each person can see** is set in the project's Share sheet (a person and a role, owner / editor / viewer, and one line per person saying what they can see, e.g. "Maya can edit Marshall"); **the guest** signs in on the connect sheet when the host uses accounts (`personRequired`, the alert of Step 8.8, then the name and password fields; Step 8.2, `sharing.people.device-is-a-person`); **every connection** is that person (Step 8.3, `sharing.people.every-connection-signed-in`); and the guest's sidebar and chooser show only that person's libraries (Steps 8.5, 8.7). This step adds no new mechanism; it ties those together and adds the Share sheet's one-line summary. *Built:* the Accounts screen and access matrix (`AccessMatrixView`, `UsersStore.loadAccessMatrix`), the Share sheet's member rows with a role menu and Remove (`ShareLibrarySheet+Members.memberRow`, `setLibraryRole`), the connect sheet's person fields on `personRequired`, the person filter on the host (`GET /api/authz/libraries`). *Not built:* the Share sheet's one line per person in words (the row shows the name and a role menu), the walk-through as one live run. Open for the owner: Step 8.1's text also lets Accounts edit a library role from the grid; this design sets roles in the Share sheet; both can stand (the grid edits through the same `setLibraryRole`), or the grid can be read-only with each cell opening that project's Share sheet. *Tests:* `test_access_matrix_to_spec.py` (a person sees only their libraries); not built: `SharePeopleSummaryTests.swift`.
- `sharing.multiuser-shares-by-address` — **[PARTIAL]** (#6568; owner 2026-11-12) app. With Multi-user on, sharing a Mac is
  its Tailscale address and an account, not a pairing link: **Add Device…** shows the Mac's Tailscale address
  (`https://<mac>.<tailnet>.ts.net:<port>`, its one line and **Copy**) and says to choose Connect to Another Mac on the other
  device, paste the address and sign in with an account; no code, no QR. The project Share sheet does the same (owner 2026-11-13): the address, its Copy and Send…, and that the person signs in with the username and password
  you tell them; no link. The address is Tailscale's only when its row can work
  (`AddressChoiceModel`: a `.ts.net` host whose forward is Fichero's, or unchecked from a sandbox); a `.ts.net` host carries
  Tailscale's public certificate, so no pin travels. Without a usable Tailscale address (only `.local` or an IP), and always
  with Multi-user off, the sheet keeps the pinned link, its QR and the code. Connect to Another Mac (Mac and iOS) already takes
  a typed address, a username and a password (`sharing.people.sign-in-without-a-code`): the sign-in gives that device its own
  renewable session, never stores the password, and the owner can revoke the device. Who may switch Multi-user is #6565's.
  *Built:* `AddDeviceSheetModel.signInAddress`, the address-only state of both sheets (`ShareLibrarySheet.linkNotes(atAddress:)`).
  *Not built:* a look on two Macs. *Tests:* `Settings/AddDeviceSheetModelTests.swift`, `Sharing/SignInWithoutCodeTests.swift`.
- `sharing.people.sign-in-without-a-code` — **[PARTIAL]** (→ #2083, #2403) engine and app. With accounts on, a person reaches a shared library with only the host's address, their username and their password: no pair code. The host's share link is a link to the LIBRARY that carries how to reach the Mac (the host's addresses and its public key pin, the SPKI hash, which is not a secret) and the library, as the pairing payload does today, and no code; the person is told their username and password separately, never in the link. The guest opens the link, or types the Mac's address in File › Connect to Library…, is asked for username and password, and receives a device token bound to that person (the same device row and Keychain entry a paired device has, `sharing.people.device-is-a-person`), then sees only the libraries shared with that person, under that Mac's section. The pair code stays for a device with no person (accounts off). First contact: a link's pin is checked before the password is sent; a typed address with no pin shows the host's key fingerprint once and asks the person to trust it (a `.ts.net` name behind `tailscale serve` has a public certificate and needs no pin). Passwords: typed into a secure field, sent once over the pinned TLS connection, never stored, logged, put in a link or a URL; only the device token is kept, in the Keychain (`PairingService.persistAuthToken`). *Built:* the engine signs a person in (`POST /api/auth/login`, open path, rate-limited, a 30-day session token); a code-bound pairing already asks for the person (401 `person required`, `RemoteClientPairingError.personRequired`, the connect sheet's name and password fields) and binds the device to them; the pin check before any code is sent (`PairingSequence`). *Built:* the engine's code-less device sign-in, `POST /api/pair/sign-in` (device name, username, password; accounts on only, else 409 naming the pairing link; an unknown name reads as a wrong password; a disabled person is refused; every refusal counts against the pairing rate limit; the device row is the person's, audited `device.sign_in`), open to an unauthenticated caller on both sides (`_UNAUTHENTICATED_PATHS`, `AuthTokenMiddleware`); with accounts on the Share sheet's link has no code (`mintPairingCodeIfPossible`) and its note says to tell the username and password separately; a link with no code and no person is `personRequired` before anything is sent, so the alert's Sign In… shows the fields, and the Mac connect sheet shows them at once for a code-less link; with a person the sequence checks the pin at health and then signs in (`pairDevice`). On the phone and iPad the host's ask is an alert that has the username and password fields itself (`personSignInAlert`), on the connect screen and on the sheet for a tapped link; Sign In pairs again with the person, and the password is cleared from the alert as it is sent. On the Mac a typed address in the connect sheet's link field (`studio.local`, `10.10.10.1`, with the engine's port when none is given) is the typed route (`HostKeyProbe.typedAddress`): the name and password fields show at once; Connect first reads the key the host presents, sending nothing (the TLS handshake is cancelled at the trust challenge, `HostKeyProbe.sha256Pin`), and asks **Trust studio.local?** with its fingerprint, the first 8 bytes of the key's SHA-256 as four groups of hex (`HostKeyFingerprint`), which the host's Sharing pane shows as "This Mac's key"; Trust and Connect signs the person in pinned to that key, and the pin is kept like a link's; a `.ts.net` name a public CA certifies is trusted with no ask. The phone and iPad take the same route from the link field of their manual entry: the same trust alert (`hostTrustAlert`), then the sign-in alert. *Not built:* a picked nearby Mac whose certificate is our own still needs its link. *Tests:* `transport/test_sign_in_without_a_code_to_spec.py`, `Sharing/SignInWithoutCodeTests.swift`, `Sharing/SharingFailureAlertTests.swift` (the host's ask opens the sign-in, not a failure alert), `Sharing/HostKeyFingerprintTests.swift` (one fingerprint for both pin forms, an address is the typed route and a link is not).

## Build order

Steps a long-running builder can take from the heading. `Depends on` defaults to the step before. Order: what is written gets built and walked on two Macs first; then the engine, the shared Swift, the Mac panes, Set Up, and the phone last (§8, §10.9). A step with no number has no issue yet. No dates (no deadline, do it right). Each step's test is written first and red, as §10.9 says.

### Stage 0 — built: build it, run its tests, walk the live script

The engine slices E1-E3 and the Swift slices S1, S2, M1, M2, M3 are on integration; the Swift ones are written and not yet built. These steps build them, run the tests, fix only what those runs find, and move no tag without the run. Step 0.5 is the owner's two-Mac check, §10.8 steps 1-7, 10 and 11. If §10.8 step 10 reads `unknown` on a DMG (#5317), the Tailscale row cannot pass on that build, and the owner hears that before Stage 1.

#### Step 0.1 — the code card keeps its code; one QR per link (#5915)
- Behaviours: `sharing.card-keeps-its-code`, `sharing.qr-drawn-once-per-payload`
- Tests: fichero/Tests/Unit/general/Sharing/ShareSettingsRefreshKeyTests.swift, fichero/Tests/Unit/general/Sharing/PairingCodeRenewalTests.swift, fichero/Tests/Unit/general/Transport/PairingLinkEncodingTests.swift, fichero/Tests/UI/mac/SharingPaneUITests.swift
- Size: S

#### Step 0.2 — the guest saves its token on every build; a failed save spends nothing
- Behaviours: `sharing.token-saves-on-every-build`, `sharing.failed-save-spends-nothing`
- Tests: fichero/Tests/Unit/general/Transport/KeychainTokenAccessibilityTests.swift, fichero/Tests/Unit/general/Transport/PairingPersistFailureTests.swift, fichero-server/tests/unit/security/test_a_device_revokes_its_own_pairing_6133.py
- Size: S

#### Step 0.3 — the Add Device and project Share sheets offer both addresses (#5318)
- Behaviours: `sharing.share-sheet-offers-both-addresses`
- Tests: fichero/Tests/Unit/general/Sharing/AddressChoiceModelTests.swift, fichero/Tests/UI/mac/SharingPaneUITests.swift
- Size: S

#### Step 0.4 — the Multi-user switch says the refusal; the Mac half of the People off-state, whose id closes in Step 5.1 (#6299)
- Behaviours: `sharing.multiuser-switch-says-the-refusal`
- Tests: fichero/Tests/Unit/general/Sharing/MultiuserSwitchWordsTests.swift, fichero/Tests/Unit/general/Sharing/PeoplePaneOffStateTests.swift, fichero/Tests/UI/mac/SharingPaneUITests.swift
- Size: S

#### Step 0.5 — the live two-Mac script on the built app, one record per step (#5049)
- Behaviours: `sharing.sandboxed-engine-says-it-cannot-ask-tailscale`, `sharing.state-names-every-address`, `sharing.tailnet-forward-whenever-tailscale-is-up`, `sharing.multiuser-switch-needs-no-library`, `sharing.cli-mints-a-link`
- Tests: docs/contributor_manual/testing/sharing-two-mac-checklist.md, fichero-server/tests/unit/security/test_forward_made_with_a_local_sharing_address_to_spec.py, fichero-server/tests/unit/api/test_sharing_state_names_every_address_to_spec.py, fichero-server/tests/unit/api/test_multiuser_switch_needs_no_library_to_spec.py, fichero-cli/tests/test_cli_mints_a_link_to_spec.py
- Depends on: 0.1, 0.2, 0.3, 0.4
- Size: M

### Stage 1 — the engine: names, the address list, what it reports

One contract regen for the stage, in Step 1.6, so the 404 question (open question 4) never forces a regen of its own. The §8.1 headless file starts here and gains a case with each step that has one.

#### Step 1.1 — one key per Mac, a certificate naming every address, the `.local` name is the Bonjour name; open question 5 first (#2603, #5311)
- Behaviours: `sharing.certificate-names-every-address`, `sharing.host-name-is-the-bonjour-name`
- Tests: fichero-server/tests/unit/security/test_remote_access_tls.py, test_certificate_keeps_its_key_when_a_name_is_added_to_spec (exists), RemoteAccessConfigTests (exists)
- Depends on: 0.5
- Size: M

#### Step 1.2 — the trust rule as one table both clients read
- Behaviours: `sharing.trust-rule-is-one-function`
- Tests: test_trust_rule_table_to_spec (exists), fichero/Tests/Unit/general/Transport/RemoteCertificatePinningTests.swift
- Depends on: 0.5
- Size: S

#### Step 1.3 — `GET /api/pair/addresses`, and a forward Fichero did not make is reported with the command that frees it (#5320)
- Behaviours: `sharing.stale-forward-says-so`
- Tests: fichero-server/tests/unit/security/test_tailscale_serve.py, test_tailnet_conflict_is_reported_to_spec (exists), test_pair_addresses_to_spec (exists)
- Depends on: 1.1
- Size: M

#### Step 1.4 — the `sharing` block in health, and `multiuser_blocker` in the sharing state (#5751)
- Behaviours: `sharing.health-reports-sharing`
- Tests: test_health_reports_sharing_to_spec (exists)
- Size: S

#### Step 1.5 — the listener follows the network; a stale server holding the port gets a sentence (#5736)
- Behaviours: `sharing.listener-follows-the-network`, `sharing.stale-server-holding-the-port`
- Tests: test_listener_rebinds_when_the_address_changes_to_spec (exists), test_port_in_use_message_to_spec (exists)
- Depends on: 1.3
- Size: M

#### Step 1.6 — the stage's one regen; 404 becomes 409 in it only on the owner's ruling, else the id stays held
- Behaviours: `sharing.multiuser-404-is-a-409-in-the-engine`
- Tests: fichero-server/tests/integration/test_device_pairing_e2e.py
- Depends on: 1.3, 1.4
- Size: S

#### Step 1.7 — the link carries every address, within the QR's size
- Behaviours: `sharing.link-carries-every-address`, `sharing.ios-qr-payload-size`
- Tests: test_pair_payload_carries_every_address_to_spec (exists), PairingPayloadTests (exists), PairingQRSizeTests (exists)
- Depends on: 1.2, 1.6
- Size: M

### Stage 2 — one table of words, one client sequence

#### Step 2.1 — the failure table: every step's sentence, the versions named, a forgotten device told so (#3335)
- Behaviours: `sharing.failure-names-the-step`, `sharing.version-mismatch-says-which-side`, `sharing.token-expired-or-rotated`, `sharing.ios-certificate-name`
- Tests: PairingFailureWordsTests (exists), test_cli_pair_words_match_the_spec (exists), fichero-server/tests/integration/test_device_pairing_e2e.py
- Depends on: 0.5
- Size: M

#### Step 2.2 — one person-facing error function, and the guard rule against a raw response in words (#6299)
- Behaviours: `sharing.undocumented-never-reaches-the-person`
- Tests: PersonFacingErrorTests (exists), fichero-server/tests/unit/scripts/test_check_swift_transport.py
- Depends on: 0.5
- Size: S

#### Step 2.3 — the client tries every address in turn, 5 seconds each, in Swift and the CLI (#4224)
- Behaviours: `sharing.client-tries-every-address`, `sharing.ios-link-has-one-address`
- Tests: PairingAddressTryTests (exists), test_two_macs_names_and_addresses_to_spec (exists)
- Depends on: 1.7, 2.1
- Size: M

#### Step 2.4 — one pairing sequence for Mac and phone; a link with no library lists the host's (#3273, #5734)
- Behaviours: `sharing.both-clients-run-the-same-checks`, `sharing.ios-bad-library-path`
- Tests: PairingSequenceTests (exists), test_two_macs_names_and_addresses_to_spec (exists)
- Size: M

### Stage 3 — the Mac panes

#### Step 3.1 — the sheet draws the engine's address list, with each row's reason; open questions 1 and 6 first
- Behaviours: `sharing.address-choice`, `sharing.tailnet-down-says-so`
- Tests: test_pair_addresses_to_spec (exists), fichero/Tests/Unit/general/Sharing/AddressChoiceModelTests.swift, fichero/Tests/UI/mac/SharingPaneUITests.swift
- Depends on: 1.6, 2.1
- Size: M

#### Step 3.2 — the firewall sentence, and no link that cannot work
- Behaviours: `sharing.firewall-prompt-says-what-to-click`
- Tests: a model test of the sheet's firewall sentence (not yet written; §4 names none)
- Size: S

#### Step 3.3 — accounts off says so and offers the way on; accounts without sharing says what it means (#5908, #5319)
- Behaviours: `sharing.multiuser-off-says-so`, `sharing.multiuser-needs-sharing-for-anyone-else`
- Tests: MultiuserOffPaneTests (not yet written), fichero-server/tests/unit/security/test_owner_session_sets_the_switch_5908.py
- Depends on: 1.6, 2.2
- Size: M

### Stage 4 — Set Up asks

#### Step 4.1 — the questions-only stage is offered, in its words
- Behaviours: `sharing.setup-stage-is-offered-without-jobs`, `sharing.setup-stage-wording`
- Tests: test_sharing_stage_to_spec (exists)
- Depends on: 0.5
- Size: S

#### Step 4.2 — the sharing question on the page, with the same controls as Settings (#2054, #5731)
- Behaviours: `sharing.setup-asks-sharing`, `sharing.setup-answers-change-later`
- Tests: SharingStageTests (exists)
- Depends on: 3.1, 4.1
- Size: M

#### Step 4.3 — the accounts question, and the saved answers beside the engine's state; open question 3 first
- Behaviours: `sharing.setup-asks-accounts`, `sharing.setup-answer-is-per-library`
- Tests: SharingStageTests (exists), test_sharing_stage_to_spec (exists)
- Depends on: 3.3, 4.2
- Size: M

### Stage 5 — iPhone and iPad, and the whole thing live

#### Step 5.1 — a Settings surface on iPhone and iPad; People's off-state in the phone's words (#5917)
- Behaviours: `sharing.ios-settings-surface`, `sharing.people-pane-off-state`
- Tests: fichero/Tests/Unit/general/Sharing/PeoplePaneOffStateTests.swift, IOSSettingsPeopleUITests (not yet written), IPadSettingsPeopleUITests (not yet written)
- Depends on: 0.4
- Size: M

#### Step 5.2 — the phone's sheet says the step, with Try again, Copy details and Open Tailscale (#5317)
- Behaviours: `sharing.ios-says-which-step`, `sharing.ios-tailscale-not-on-the-phone`
- Tests: PairingFailureWordsTests (exists)
- Depends on: 2.4
- Size: S

#### Step 5.3 — a denied Local Network permission gets its sentence and Open Settings
- Behaviours: `sharing.ios-local-network-permission`
- Tests: NearbyHostsPolicyDeniedTests (exists)
- Depends on: 2.4
- Size: S

#### Step 5.4 — the link opens the app from Messages: the entitlement, and the site file on the owner's word
- Behaviours: `sharing.ios-link-opened-from-messages`
- Tests: PairingLinkRoundTripTests (exists)
- Depends on: 1.7
- Size: S

#### Step 5.5 — on real devices: all of §8.2 and §10.8, two Macs, iPhone, iPad (#5049)
- Behaviours: `sharing.ios-end-to-end`, `sharing.ios-app-transport-security`
- Tests: IOSConnectPairingUITests (not yet written), IPadConnectPairingUITests (not yet written), fichero/Tests/Unit/general/Transport/RemoteCertificatePinningTests.swift, fichero-server/tests/unit/scripts/test_check_swift_transport.py
- Depends on: 3.2, 4.3, 5.1, 5.2, 5.3, 5.4
- Size: M

### Stage 6 — the marks in the sidebar (added 2026-11-05, §11)

Stages 6-8 take the issues placed by the owner's rulings of 2026-11-05. Order: the marks first (Swift written, unbuilt), then the sync (engine mostly built, the app halves small), then the people last, because every-connection-signed-in changes the most and waits on a ruling. None of these blocks Stage 5.

#### Step 6.1 — the shared marks on both Macs: the guest's row, the host's row with its people, greyed when sharing stops (#5737, #5738, #5739)
- Behaviours: `sharing.marks.guest-row`, `sharing.marks.host-row`, `sharing.marks.off-greys-row`
- Tests: fichero/Tests/Unit/general/Sharing/SharedProjectRowTests.swift, fichero/Tests/Unit/general/Sharing/HostSharedMarkTests.swift, fichero/Tests/Unit/general/Sharing/SharingOffGreysRowTests.swift, SharingSidebarMarksUITests.swift (not yet written), fichero-server/tests/unit/transport/test_pair_devices_name_the_person_to_spec.py
- Depends on: 0.5, 4.2
- Size: M

### Stage 7 — two Macs editing one library

#### Step 7.1 — the stream keeps every event; the audit key never waits on the keychain (#5314)
- Behaviours: `sharing.sync.stream-keeps-every-event`
- Tests: fichero-server/tests/unit/api/test_changes_stream_endpoint.py, fichero-server/tests/unit/actions/test_action_audit_chain.py, docs/contributor_manual/testing/sharing-two-mac-checklist.md
- Depends on: 0.5
- Size: S

#### Step 7.2 — a stale document edit is refused and offered the choice, as a note is (#5348)
- Behaviours: `sharing.sync.stale-document-edit-offers-a-choice`
- Tests: fichero/Tests/Unit/general/Sharing/DocumentStaleResolutionTests.swift, fichero-server/tests/unit/transport/test_stale_document_edit_to_spec.py
- Depends on: 0.5
- Size: S

#### Step 7.3 — a run from the paired Mac lives in the host's Activity; undo per window holds after a remote edit (#5732, #5733)
- Behaviours: `sharing.sync.remote-run-live-in-activity`, `sharing.sync.undo-per-window-after-remote-edit`
- Tests: test_remote_run_live_on_the_hosts_stream_to_spec.py (not yet written), fichero/Tests/Unit/general/Models/ActivityRowStartedByTests.swift, fichero/Tests/Unit/general/Models/UndoableChangeTests.swift, fichero-server/tests/unit/transport/test_undo_after_remote_edit_to_spec.py
- Depends on: 7.1
- Size: M

#### Step 7.4 — removing a device removes the devices it paired, named first, and bites at once (#5351)
- Behaviours: `sharing.sync.revoke-cascades-and-bites-at-once`
- Tests: fichero-server/tests/unit/transport/test_revoke_cascades_to_spec.py, fichero/Tests/Unit/general/Transport/RemoteAccessConfigTests.swift, docs/contributor_manual/testing/sharing-two-mac-checklist.md
- Depends on: 0.5
- Size: S

### Stage 8 — the people: accounts, a device is a person, every connection signed in

#### Step 8.1 — Settings › Sharing › Accounts: who is signed in, add and remove people, access across every library (#2083)
- Behaviours: `sharing.people.settings-screen`
- Tests: fichero/Tests/Unit/general/Sharing/AccountsAccessMatrixTests.swift, fichero-server/tests/unit/security/test_access_matrix_to_spec.py, fichero-server/tests/unit/security/test_auth_accounts.py
- Depends on: 3.3
- Size: M

#### Step 8.2 — a paired device is a chosen person on every entry point, and its edits carry the name (#2403, #5735)
- Behaviours: `sharing.people.device-is-a-person`
- Tests: fichero/Tests/Unit/general/Sharing/PairingPersonPickerTests.swift, fichero/Tests/Unit/general/Sharing/EditNamesPersonTests.swift, fichero-server/tests/unit/transport/test_two_accounts_names_on_edits_to_spec.py
- Depends on: 6.1, 8.1
- Size: M

#### Step 8.3 — every connection is signed in: no ambient owner; the switch's removal only on the owner's ruling (#3284)
- Behaviours: `sharing.people.every-connection-signed-in`
- Tests: test_multiuser_always_on_to_spec.py (not yet written), scripts/check_no_ambient_owner_in_tests.py
- Depends on: 8.2
- Size: M

#### Step 8.4 — a deny on a document covers the records addressed by their own id: confirm, name the tests, close #4917 (#4917)
- Behaviours: `sharing.people.deny-reaches-the-documents-records`
- Tests: fichero-server/tests/unit/security/test_authz_ancestor_adversarial.py, fichero-server/tests/unit/api/test_segments_multiuser_access.py
- Depends on: 8.1
- Size: S

#### Step 8.5 — the connecting Mac shows and opens the shared library: a paired-machines group and File › Connect to Library… (#6360)
- Behaviours: `sharing.guest.machines-group`, `sharing.guest.connect-to-library`, `sharing.guest.empty-state-says-how-to-pair`, `sharing.guest.no-section-until-paired`
- Tests: PairedMachinesGroupTests.swift, ConnectToLibraryTests.swift (not yet written)
- Depends on: 6.1
- Size: M

Acceptance (the owner's, 2026-11-06): two Macs pair and the host shares a library, and the connecting Mac can see it and open it. (1) After pairing, the sidebar's paired-machines group lists the host and the libraries it gave this device; choosing one shows it. (2) File › Connect to Library… with a pair link adds the host and opens the project the link names. (3) With no paired Mac the group says how to pair, in one sentence. (4) The group and the menu item read one list. What stands in the way is that the app has one app-wide engine host: a first slice may make choosing a library switch the app to that host (what pairing does today) while the list and the menu item are built; a library that sits beside the local ones needs each library pinned to its own host (#2866 follow-up) and is Step 8.6.

Owner rulings (2026-11-06): each Mac that shares libraries with this person gets its own sidebar section below Projects, a bar like Projects titled by that Mac's name, listing only the libraries it shares with this person (this replaced, the same day, one "Shared Libraries" section labelled by host); with no Mac paired, the Mac sidebar shows no section (ruling of 2026-11-11, replacing the earlier one that held a how-to-pair sentence there). A host whose Sharing is off keeps its greyed row (`sharing.marks.off-greys-row`). It shows only what is shared with the signed-in person: the list comes from the host's `GET /api/authz/libraries` for that person (their library roles in multiuser, the device's grants for a device with no person), so a library shared with someone else never appears. Tested on the host by `test_access_matrix_to_spec.py` (a person sees only the library they hold a role on). On iPhone and iPad the person chooses the library from a list of only these (Step 8.7). File › Connect to Library… stays the way to add a host.

Built: one sidebar section per sharing Mac with its empty state, the list behind it (written on each pairing), and File › Connect to Library… opening the connect sheet. Built (#6360): a row opens its library through the host switch (the whole window switches to that Mac). Not built: the host's own library list, greying on Sharing off, and a library opening beside the local projects (Step 8.6): the Air test reaches the list and the connect sheet, not the beside-local open.

#### Step 8.6 — a shared library opens beside the local ones: each library dials its own host (#6360, #2866)
- Behaviours: `sharing.guest.library-pinned-to-its-host`
- Tests: LibraryPinnedToHostTests.swift (endpoint and open beside local)
- Depends on: 8.5
- Size: M

Status 2026-11-08: item (3), the status pill and heartbeat also showing a pinned host that is down, is CLOSED AS BY DESIGN after the lane-sharing audit of 2026-11-08: the Shared Libraries sidebar row shows a down host, one place; no code. The connection popover (Step 8.14) lists every connection's state instead.

#### Step 8.10 — sharing comes on with nothing shared: a dialog asks which projects, and who can open them (#6366)
- Behaviours: `sharing.host.asks-which-projects-when-nothing-is-shared`, `sharing.host.which-projects-dialog`, `sharing.host.dialog-errors-are-alerts`
- Tests: test_sharing_state_counts_shared_libraries.py, ShareWhichProjectsDialogTests.swift, ShareWhichProjectsUITests.swift (not yet written)
- Depends on: 8.6
- Size: M

Acceptance (the owner's, 2026-11-06): when sharing is allowed but no project is shared yet, the person is not left with a bare settings pane and raw error text; a clear dialog asks which project(s) to share, a list with check boxes and who can open each, with a Share button and a Not Now; errors in this flow are the proper alerts of #6361. Order: the engine's one count (`shared_library_count`) with its test red then green; the dialog's model and sheet (one new view, `ShareWhichProjectsSheet`, in `Views/Settings/Sharing/Share/`), opened from the three turn-on points and the pane's button; the pane's error writes replaced by the alert. Numbered 8.10 because lane-sharing's unlanded branch holds 8.7-8.9 (8.8 is the alerts step this one leans on, #6361); it lists `Depends on: 8.6` only because this checkout has no 8.8 to name; it runs after 8.8, and if 8.8 has not landed when this is built, this step builds the one alert component for its own three cases and 8.8 reuses it.

- test (to write): `test_sharing_state_counts_shared_libraries.py` in fichero-server/tests/unit/api/ (zero grants → 0; one person-role on one of two libraries → 1; a library given to a paired device → counted once)
- test (to write): `ShareWhichProjectsDialogTests.swift` in fichero/Tests/Unit/general/Sharing/ (the model: opens only when the count is 0; rows from the libraries list; Share's payloads per check and person; Not Now sends nothing; a 403 keeps the checks)
- test (to write): `ShareWhichProjectsUITests.swift` in fichero/Tests/UI/mac/ (XCUITest beside `SharingPaneUITests.swift`: switch on with nothing shared → the sheet; check one project, Share; the pane no longer shows the button; switch on again → no sheet)
#### Step 8.7 — iPhone and iPad choose a shared library from a list of only theirs (#5396, #5734, #3371)
- Behaviours: `sharing.ios.shared-library-chooser`, `sharing.ios.no-empty-detail`
- Tests: SharedLibraryChooserIOSTests.swift
- Depends on: 8.5
- Size: M

Acceptance (the owner's, 2026-11-06): on iPhone or iPad, the person pairs with a Mac and chooses which library to show from a list of only the libraries shared with them; it opens. The stopgap of 8.5 holds here too: opening switches the app to that Mac.

#### Step 8.8 — every pairing and sharing failure is a native alert with its fix (#6361)
- Behaviours: `sharing.alerts.one-alert-per-failure`, `sharing.alerts.no-bottom-strip`
- Tests: SharingFailureAlertTests.swift
- Depends on: 8.7
- Size: M

Acceptance (the owner's, 2026-11-06): no sharing or pairing error appears as raw text at the bottom of the window; each is an alert saying what happened, why, and the fix, with a button where there is one. One alert component serves runs and sharing (`specs/ai/run-failure-alerts.md` Step 2.1); if that step has not landed when this is built, this step builds the component and 2.1 reuses it.

#### Step 8.9 — one way to do people: people in Accounts, roles in the Share sheet, the guest signs in (#2083, #2403, #5735, #3284)
- Behaviours: `sharing.people.one-way-to-do-people`, `sharing.people.sign-in-without-a-code`
- Tests: test_access_matrix_to_spec.py, SharePeopleSummaryTests.swift (not yet written), test_sign_in_without_a_code_to_spec.py, SignInWithoutCodeTests.swift
- Depends on: 8.1, 8.2, 8.3, 8.8
- Size: M

Acceptance (the owner's, 2026-11-06, through the manager's design): on the host, the owner adds Maya in Settings › Sharing › Accounts; in the Marshall project's Share sheet gives Maya Editor and reads "Maya can edit Marshall"; on the Air, Connect to Library… with the link asks Maya to sign in (an alert, then the fields); after signing in the Air's sidebar shows the host's section with Marshall only; a project not shared with Maya does not appear; her edits show "edited by Maya on <the Air>" on the host. The owner's further sentences (2026-11-06): (a) people are chosen in Settings, where the list of people lives; (b) the Share sheet then picks from that list who gets this library and with what role; (c) the share link is a link to the library, and it carries the way to reach the Mac (the host's address and its key pin), as the payload does today; (d) entering only the Mac's address in Connect to Library… also works, and then shows the libraries that Mac shares with that person, each under that Mac's section. (e) Sign-in works with just the address, a username and a password, no pair code: the link carries the address, the key pin and the library; the username and password are told separately; the guest is asked for them and gets only that person's libraries; the pair code stays for a device with no person. The password is never in the link, never stored; only the device token, in the Keychain.

#### Step 8.11 — the listener and the link follow the network; links name Tailscale first (#6367, #5317)
- Behaviours: `sharing.listener-slots-bind-alone`, `sharing.listener-follows-the-network-by-itself`, `sharing.link-counts-a-live-tailnet-forward`, `sharing.share-this-mac-is-this-mac`, `sharing.listener-binds-private-interfaces` (#6383)
- Tests: test_listeners_bind_on_their_own_to_spec.py, test_link_counts_a_live_tailnet_forward_to_spec.py, SharingFollowsTheNetworkTests.swift, test_listener_binds_private_interfaces_to_spec.py
- Depends on: 8.5
- Size: M

Acceptance (the owner's, 2026-11-06): with Sharing on, the Mac always listens (one failing address never takes the others down), a link names an address something listens on after the network changes, and when Tailscale runs the link names the Tailscale address first. And (2026-11-07, #6383): another Mac connects over the Thunderbolt bridge (Air 10.10.10.1, Pro 10.10.10.2, M4 10.10.10.3) with the engine's port on every call.

#### Step 8.12 — Share… on every project row in every mode; the sheet is a link with Multi-user off (#6373)
- Note (owner 2026-11-08, #3284): "with Multi-user off" here reads "with no accounts yet" once Step 8.13 lands; the link is a person-bound invite, authentication is never off.
- Behaviours: `sharing.host.share-in-every-mode`
- Tests: ShareWithoutAccountsTests.swift
- Depends on: 8.5
- Size: S

Acceptance (the owner's, 2026-11-06): with Multi-user off, right-clicking a project in the sidebar offers Share…; it gives a link for that project (turning Sharing on first when it is off), and the other Mac opens that project from the link.

#### Step 8.13 — multi-user is always on: the switch retired everywhere, every connection authenticated (#3284)
- Behaviours: `sharing.multiuser-always-on`
- Tests: test_acl_status_multiuser_off_to_spec.py, test_multiuser_always_on_to_spec.py (not yet written), MultiuserAlwaysOnTests.swift (not yet written)
- Depends on: 8.9, 8.12
- Size: M

Owner ruling 2026-11-08, P1. The engine side is `transport/multiuser-always-on.md` slice 10 (no ambient owner; the switch and `sharing.set_multiuser` removed); this step is the app and contract side and the migration. Steps 8.9 and 8.12 keep their acceptance as written, with the Note that "with Multi-user off" there now reads "with no accounts yet": a share link still works for a project with no people, because the link is itself a person-bound invite, not because authentication is off. `sharing.multiuser-off-says-so`, `sharing.acl-status-when-multiuser-off` and `sharing.multiuser-needs-sharing-for-anyone-else` describe today's code until this step lands and are retired by it.

- test (to write): `test_multiuser_always_on_to_spec.py` in fichero-server/tests/unit/transport/ (no switch route in the contract; a remote request with no session is 401 in words; the loopback launch secret still opens the owner's libraries; an old `multiuser.enabled: false` setting is read as nothing)
- test (to write): `MultiuserAlwaysOnTests.swift` in fichero/Tests/Unit/general/Views/Settings/ (no Multi-user row in Settings › Sharing or Set Up; the Share sheet for a project with no people still gives a link)

#### Step 8.14 — the connection popover lists every connection: This Mac and each paired host, a glyph, its library, Use and Disconnect (#6434)
- Behaviours: `sharing.connections.popover-lists-every-connection`
- Tests: fichero/Tests/Unit/general/App/HeartbeatLowersAlarmTests.swift, ConnectionPopoverRowsTests.swift (not yet written)
- Depends on: 8.6
- Size: S

The popover's one table (`ConnectionPresentation`'s mapped title, glyph and action, #4400) gains rows, not a second view: one row model built from `PairedMachineStore` plus the pinned libraries' states, the same fix actions, the text budget enforced in the test. Written under the 2026-11-08 spec pause as the manager's one exception.

## Open questions: decided, defaulted, or for the owner

Each question states what the code or the 2026-10-30 probe decides, the default this spec builds on, and whether the owner still has to rule.

1. **The default (first) address in the link.** *Evidence:* on the campus network the tailnet name was the only address that worked from any Mac (§3), and the engine already treats a `.ts.net` address as served by Tailscale to loopback (`network_listener_gap`, `transport_diagnostics.py:152-156`). Once `sharing.link-carries-every-address` lands the default only decides the first try and what an **old** client (one address) gets. *Default built on:* tailnet name when Tailscale is running and the forward is Fichero's own, else `.local`, else the LAN IP; the person can override per link (`sharing.address-choice`). **Owner to confirm** the default order only; the mechanism is not in question.
2. **The per-attempt budget: 5 s.** *Decided by evidence:* over the tailnet `/api/health` answered in 0.4-0.5 s from two Macs; a dead `.local` name failed resolution in 4.8 s; the CLI already gives a certificate fetch 5 s (`fichero_cli/pairing.py:82`, `:167`); a cellular first connect is 3-4 s. Shorter would cut off a slow phone; longer only delays the next address. Fixed at 5 s per address, ≤ 3 addresses, so a wholly dead link fails in ≤ 15 s. No ruling needed.
3. **Per library or per Mac?** *Decided by the code:* sharing is the Mac's engine listener (`_listener_hosts`, `__main__.py:66-74`) and Multi-user is one app-wide setting (`sharing.set_multiuser`, `owner_scope="app"`, `pairing.py:626-627`); neither is a property of a library. *Default built on:* the Set Up page asks once per Mac (the first library whose Set Up reaches the page); every later library's page shows the Mac's state and one line, "This Mac already shares libraries. Share this one too" → the project Share sheet (`POST /api/authz/share`, `authz.py:311`); the two saved answers stay per library as the person's intent (`sharing.setup-answer-is-per-library`). **Owner to confirm** the once-per-Mac wording; a per-library switch would need an engine the code does not have.
4. **404 → 409 `multiuser_off` in the next regen?** *Evidence:* four sites (`accounts.py:198-200`, `:822-830`, `pairing.py:278-280`); the app handles the 404 either way (`sharing.undocumented-never-reaches-the-person`), and `test_device_pairing_e2e.py` and the multi-user tests pin 404. *Recommended:* yes, bundled with the first regen that `sharing.health-reports-sharing` or `GET /api/pair/addresses` forces, never as a regen of its own. **Owner to rule** (contract change).
5. **One certificate key per Mac?** *Evidence:* today a new key per folder (`remote_access_tls.py:244`), so a DHCP change or a name fix voids every link and every paired device's stored pin, and the person is told nothing. *Recommended:* yes: one `Remote Access/key.pem` per Mac, the certificate re-issued whenever the SAN set changes, the pin therefore stable; the key is revoked by turning Sharing off and deleting the folder ("Forget this Mac's sharing identity" in Advanced), which is the same remedy a stolen device needs today. The risk the question names, a key that outlives a network, is no larger than a paired device's token, which already outlives it. **Ruled YES (manager, 2026-11-02):** one key per Mac, the certificate re-issued for each set of addresses, so links and pins survive an address change; built in Step 1.1 (`sharing.certificate-names-every-address` is written for yes).
6. **(New) The address list without Tailscale on a campus network.** When Tailscale is not installed on the host and the network isolates clients, no address can work and the host cannot know it. *Default built on:* the Add Device sheet shows the two rows as "listening" and the sentence "On a campus or hotel network, Macs often can't see each other. If pairing fails, install Tailscale on both and try again." (`sharing.tailnet-down-says-so`). **Owner to confirm** that recommending Tailscale in the app is acceptable.
