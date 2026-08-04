# Design Review: Should `.debugExternal` (the developer-run local engine) survive?

**Date:** 2026-08-04 (rev. 2 — folds in Daniel's CLI/MCP ruling) · **Status:** review, not a
decision record · **Asked by:** Daniel
**Question:** Would there be benefits to supporting only **embedded**, **remote**, and **iOS**
engine modes — dropping the developer-run local engine?

**Ruling folded in as a CONSTRAINT (Daniel, 2026-08-04):** *"On Mac, the CLI is a client of
the GUI app, and so is MCP. Without the GUI app, there is no MCP and no CLI on Mac."* This
document does not re-litigate that; §5 traces its consequences.

**Method note (honesty about tooling):** this review was produced without a shell. Git
evidence comes from reading `.git/logs/refs/heads/integration` reflog subjects directly
(EMPIRICAL, marked below) — commit *bodies* were not searchable, so the defect sweep is a
lower bound. jCodemunch MCP tools were unavailable this session; code claims come from
direct file reads with line numbers. CLI/MCP sources were read from the **main checkout**
(`~/code/fichero/fichero-cli`, `~/code/fichero/fichero-mcp`) because this worktree carries
only their `pyproject.toml` + `README.md` (EMPIRICAL: glob of `fichero-cli/*` and
`fichero-mcp/*` here; only `fichero-cli/src/fichero_cli/generated/` is gitignored, so the
`src/` trees appear to be untracked and therefore absent from worktrees — #4227's "sibling
trees"). Main-checkout sources may not be at this worktree's commit; marked where it matters.

---

## 1. The five provisioning strategies, verified

Source: `fichero/fichero/Services/EngineConfig+Launch.swift:113-160` (enum + precedence),
`:235-242` (transport mapping), `:31-54` (debug transport overrides);
`AGENTS.md:33-51` (scheme→configuration mapping). All DOCUMENTED.

| Strategy | Selected by | Process owner | Connection owner | Transport | Engine sandboxed? |
|---|---|---|---|---|---|
| `.inert` | Preview / XCTest host / UI-test (`isInertHost`, `:150,192`) | Nobody — adopts an external engine *if one is already up*, else runs inert; never spawns (`:114-116`) | App (adoptive) | `.https` (`:239`) | n/a / whatever the adopted engine is |
| `.configuredRemote` | Explicit Settings host, macOS or iOS (`:158`, `:154`) | The remote host | App | `.https` | Remote's concern |
| `.iosCompanion` | iOS with no explicit host (`:154`) — never probes localhost (#2465, `:120-121`) | The paired Mac | App | `.https` | Remote's concern |
| `.debugExternal` | macOS + `DEBUG` defined → the **`Fichero (Dev Local)`** scheme (`:159`, AGENTS.md:46-48) | **The developer** (terminal, `start_backend.sh`); engine deliberately not bundled in Debug (#3042, `:123-126`); never spawns | App adopts | Nominally `.https` (`:239`) — but the Dev Local scheme overrides to UDS via `FICHERO_FORCE_UDS=1`, dialing the app-computed container socket (`:44-52`) | **No** — a terminal-launched Python process. The *app* is sandboxed; the engine is not |
| `.releaseEmbedded` | macOS without `DEBUG` → **`Fichero (Dev Embedded)`** (config `Dev Embedded`, no `DEBUG` flag) and Release (`:159`, AGENTS.md:33-39) | **The app** — the only strategy with `spawnsBundledEngine == true` (`:133`) | App | `.uds` at `$TMPDIR/fichero.sock` in the container (`:215-229`, `:237-238`) | **Yes** — sandbox-inherited child; gets library access via security-scoped bookmarks in `FICHERO_LIBRARY_BOOKMARKS` (`EmbeddedBackendService+Spawn.swift:237-247`) |

Both Dev schemes compile Swift at `-Onone`; "they differ in who owns the engine, not in
speed" (AGENTS.md:50-51). DOCUMENTED.

One engine-side fact matters everywhere below: **when `FICHERO_UDS_PATH` is set, the engine
binds a plaintext Unix socket and nothing else — "no TCP port, no TLS, no network
listener"** (`fichero-server/src/fichero_server/__main__.py:209-239`). DOCUMENTED.

The key structural fact: **`.debugExternal` is the only macOS mode where the engine's
process lifecycle, filesystem view, code identity, token file, and socket are owned by a
different principal than the app that dials it.** Every defect analyzed below lives in
that seam.

---

## 2. Per-bug attribution — today's evidence, honestly counted

### Bug 1 — Keychain ACL failure (rc 36, key reported absent)

DOCUMENTED: `fichero-server/src/fichero_server/security/keychain.py:33-57` — the engine
stores provider keys via the `security` CLI under `SERVICE = "com.fichero.fichero"`;
`security` exits 36 when the item's ACL does not trust the calling binary and cannot
prompt; the code's own docstring records that this told the app Daniel's OpenRouter key
"did not exist when it was sitting in his login keychain … merely unreadable by this
process" (#4534, fixed 853acfa68 as tri-state `FOUND/ABSENT/UNREADABLE`).

**Attribution: an artifact of the external engine — with a caveat.** A keychain item's ACL
trusts specific code identities. A venv Python launched from a terminal has no stable,
signed identity: reboots, venv rebuilds, and interpreter updates all produce "a binary the
item does not trust", and with no UI session `security` cannot prompt, so it fails rc 36.
An app-spawned engine is *better* but not immune: the caller of the `security` CLI is
still the engine process, and during development its bundle is re-signed on rebuild —
whether the ACL survives depends on the signing identity's designated requirement, which
I could not verify empirically (no shell). UNVERIFIED: whether a Dev-Embedded-spawned
engine reads the same item without prompting today.

**Does Daniel's parallel decision (app owns the keychain item, passes the key to the
engine) moot this?** For this bug, **yes** — it removes the engine's code identity from
the trust equation entirely, in *every* mode, including remote (where the engine is on
another Mac and could never read this Mac's keychain anyway). The tri-state read (#4534)
remains worth keeping as defense-in-depth. So: bug 1 is evidence *for* the thesis, but the
fix that actually kills it is the app-owned key, not mode removal. The mode question is
not mooted overall — bugs 2–4 are untouched by it. See §6 for how this decision and the
CLI/MCP ruling express one principle.

### Bug 2 — Bootstrap token sync (two `.api-key` copies)

DOCUMENTED: `fichero-server/src/fichero_server/api/auth.py` — `_token_file_path()` (home
Application Support, `:73-79`), `_sandbox_token_file_path()` (container copy, `:82-94`),
`_uuid_sandbox_token_paths()` (sweeping *UUID-named* containers for more copies,
`:115-146`), `sync_app_bootstrap_token()` (the mirror, `:236-255`),
`prepare_app_bootstrap_token_for_launch()` (the don't-clobber-a-live-engine guard,
`:267-294`), `_is_stale_sandbox_bootstrap_token()` (widened-401 diagnosis, `:297-311`).
App-side half: `EmbeddedBackendService+Spawn.swift:86-102` — pre-write only when
absent/empty, "the old unconditional write here clobbered a LIVE engine's token: if this
spawn never takes the port over (an external/older engine still serving …)" (#4432 /
c40cf116c, narrowed 2026-08-04).

**Attribution: substantially an artifact of the external-engine arrangement.** Count what
each piece exists *for*:

- The **container mirror** exists because a non-sandboxed engine writes the home path
  while the sandboxed app reads the container path. Sandbox asymmetry (bug 4) — which is
  itself a property of `.debugExternal`.
- The **clobber guards on both sides** exist because *two* processes can mint/write the
  token and an app spawn can race a still-serving external engine. Under
  `.releaseEmbedded` alone there is exactly one minting authority (the app, #2862,
  `auth.py:323-329`) and one adopter; the race the guards defend against cannot occur.
- The **UUID-container sweep** and the multi-bundle-id list (`:97-108`) exist to find
  whichever sandbox the app-of-the-day lives in — again, only needed because the writer
  is outside every sandbox.

What would *survive* an embedded-only world: a CLI/MCP-readable credential still has to
exist somewhere the app controls (§5.4), and `initialize_token`'s reuse-don't-rotate
behavior (#1110) still protects concurrent pytest/uvicorn instantiations in *engine-alone*
development. Verdict: **attributable**; roughly 150 lines of auth.py plus the Swift-side
guard exist to serve the two-owner case.

### Bug 3 — UDS socket path (two-owner socket)

DOCUMENTED: `EngineConfig+Launch.swift:44-52` — Dev Local requests UDS with
`FICHERO_FORCE_UDS=1`; the app computes its container socket path, "the same one the dev
pre-action binds". `EmbeddedBackendService+Spawn.swift:216-221` — only the
`.releaseEmbedded` spawn sets `FICHERO_UDS_PATH`. AGENTS.md:41-44 — "Two engines, one
socket path": a hand-started engine and a Dev Embedded spawn bind the same socket.
History: #4222 (Dev Local dialed the container socket the engine wasn't bound to);
EMPIRICAL reflog subjects: "fix(transport): the banner told Dev Local it could not reach
the socket it dials" (2026-08-03), "fix(lifecycle): raise debug-UDS readiness budget
5s→15s (#4056)".

**Attribution: attributable.** The defect class is *path agreement between two processes
configured by two different mechanisms* (a scheme pre-action script vs. app code). Under
`.releaseEmbedded` the agreement is enforced by construction: one function
(`udsSocketPath`) computes the path and the same process both dials it and hands it to
its child via env. There is nothing to drift. The residual embedded-world hazard is the
AGENTS.md one — a *leftover* hand-started engine squatting the socket — which is a
symptom of the external workflow existing at all.

### Bug 4 — Sandbox asymmetry

DOCUMENTED: the app is sandboxed in all current schemes; a terminal engine is not.
Consequences visible in code: the container-vs-home token split (bug 2);
`FICHERO_LIBRARY_BOOKMARKS` (`Spawn.swift:237-247`) — Powerbox grants don't inherit into
children, so a *sandboxed* engine needs security-scoped bookmarks to open a library in
`~/Documents` at all, while a terminal engine has full filesystem access and **never
exercises that code path**. `Path.home()` in a sandbox-inherited engine resolves into the
container; in a terminal engine it is the real home — so every `Path.home()`-derived
location in the engine (token file `auth.py:78`, importer key discovery
`importers/http_client.py:11`) silently means a *different directory* per mode.

**Attribution: structural, and the strongest argument for the thesis.** This isn't one
bug; it's a generator of bugs, and worse, a *concealer*: Dev Local cannot reproduce
sandbox-only failures (file access denials, container path resolution, bookmark
plumbing), so they surface first in Dev Embedded / Release — "bugs that only surface
later" is precisely the mechanism Daniel suspects. Verdict: **attributable, class-level.**

### Bug 5 — Systematic sweep for other external-mode defects

EMPIRICAL (reflog subjects only — lower bound, bodies not searched): beyond the above:
"fix(in-memory,#4052): treat asgi.local as loopback so .inMemory auth attaches the
bootstrap token"; "feat(transport): withhold the local control surface from the TCP
listener (#4222)"; "fix(tests): EntityStoreTests restores the REAL app token it was
clobbering" (a *test* corrupting the developer's live `.api-key` — only possible because
the token file is a shared cross-process ambient); "feat(transport): every Mac Local
scheme uses UDS; iOS/iPad stay HTTPS" (2026-08-03 — itself churn in this seam). Also
prior recorded incidents: sharing broken via hardcoded HTTPS client (#4224), Debug 401
requiring a manual token copy into the container.

**Honest tally for today's afternoon: 4 of 4 presented defects are artifacts of, or
materially aggravated by, the adopt-an-external-engine arrangement.** One of them (bug 1)
is fixed by an orthogonal decision (app-owned keychain); the other three are fixed only
by removing the second owner.

---

## 3. Steelman: what `.debugExternal` actually buys, and what removal costs

Re-weighed after the CLI/MCP ruling (§5), which removes one leg of the original steelman.

1. **Backend iteration speed — the surviving leg, and it is real.** The developer engine
   runs under `--reload`, so a Python edit is live in seconds with the app still
   attached. Under embedded, a backend change visible *in the app* costs: `briefcase
   build macOS --app server` + an app rebuild + relaunch (`Spawn.swift:141-143` documents
   exactly this recipe). I could not time this without a shell (UNVERIFIED), but the
   project record is unambiguous that builds on this machine are slow, must be
   serialized, and have pushed the machine into process-killing load (AGENTS.md:72-74).
   Call it minutes-per-iteration vs. seconds — an order-of-magnitude loss **for the
   specific workflow of iterating backend code while watching the result in the live app
   UI**, and "just rebuild" is not a free answer on this machine.
   *Counter-counter:* most backend iteration does not need the app at all — `pytest`,
   `start_backend.sh` + direct HTTP, and contract tests cover engine logic headlessly,
   and none of that depends on `.debugExternal` (an *app* mode). The cost is confined to
   full-stack, UI-visible backend work. It is not zero and should not be waved away;
   whether it is decisive is Q2 in §7.

2. **Headless and CI — this leg stands, and it is untouched by both the removal and the
   ruling.** Verified path by path in §5.2: every gate exercises the engine directly
   (in-process import or TestClient) or the CLI/MCP against `httpx.MockTransport`; no
   gate connects the CLI to a live engine. Removing `.debugExternal` does not touch
   `start_backend.sh`, pytest, or the guardrails.

3. **Debuggability.** A terminal engine has live stdout/stderr, independent restart, and
   debugger/profiler attachment. Partially answered: the embedded engine's output is
   captured to `~/Library/Logs/Fichero/engine.log` (#757, `Spawn.swift:79-84,251-261`)
   and its crash diagnosis pipeline (termination handler, log tail, crash-loop breaker,
   `:263-325`) is genuinely good. But "restart just the engine, under pdb, without
   relaunching the app" dies with the mode. Mitigation exists only for the read side
   (logs), not the interact side.

4. **`.inert` already covers part of the territory.** `.inert` adopts an external engine
   if one is up (`:114-116`) — that is how hermetic UI tests and XCTest hosts work today.
   So the *capability* to adopt an unowned engine cannot be deleted from the codebase;
   what `.debugExternal` uniquely adds is making that arrangement the **default daily
   driver** for a human developer. Removing it removes the exposure, not the seam —
   the seam shrinks to test-controlled contexts where the harness owns both ends.

5. **The removed leg: "CLI/MCP automation must work without the app."** The original
   review weighed cron jobs, agent workflows, and scripted CLI use against a bare engine
   as a cost of gating on the app. Daniel's ruling withdraws that use case *on Mac* by
   decision, and §5.1 shows it was already withdrawn *by architecture*: against a UDS-only
   embedded engine the CLI and MCP cannot connect today at all. This leg no longer
   supports keeping `.debugExternal`.

---

## 4. RECOMMENDATION (engine modes)

**Retire `.debugExternal` as a daily-driver mode. Converge the app on
embedded / remote / iOS (+ `.inert` for test hosts). Confidence: high on the direction
(raised from medium-high after the CLI/MCP ruling); medium on sequencing.**

Reasoning: today's score was 4-for-4; the two-owner arrangement is not merely correlated
with these defects, it is their *mechanism* (two writers of one token file, two
configurators of one socket path, two filesystem views of one `Path.home()`, two code
identities at one keychain item). The ruling then closes the strategic question: if on Mac
the GUI app is the sole owner of the engine and everything else is its client, a mode
whose entire purpose is *an engine the app does not own* is doctrinally dead — keeping it
would preserve, as the default developer experience, the exact arrangement the product
now forbids. The steelman survives only on iteration speed — real, but confined to
UI-visible backend iteration and mitigable without a second engine owner. Daniel has
already moved his run target to Dev Embedded, which is the correct experiment: he is now
testing what ships.

**But not yet.** Gate the removal on:

1. **App-owned provider keys land** (decided in parallel). Kills bug 1 in every mode;
   nothing about mode removal should wait on keychain behavior or vice versa.
2. **A decision on the iteration loop** (Q2 below). Two candidate answers:
   - *Accept engine-alone iteration:* backend logic loops through pytest / direct HTTP
     against a `start_backend.sh` engine; the app rebuild happens only when you need to
     see UI. Cheapest; costs the live full-stack loop.
   - *App-spawned dev engine:* a Debug-only variant of `.releaseEmbedded` where the app
     spawns the **venv Python with `--reload`** instead of the bundled binary — the app
     still owns the process, mints the token, sets `FICHERO_UDS_PATH`; only the
     executable differs. This keeps one-owner semantics *and* the reload loop, and is
     fully consistent with the ruling (the app remains the engine's only owner).
     **UNVERIFIED and needs a spike:** whether a sandboxed app can spawn an unsigned
     venv interpreter at all (sandbox inheritance normally requires the child to carry
     `com.apple.security.inherit`), and whether the sandbox-confined interpreter can read
     the venv outside the container. If the spike fails, this variant may require the dev
     app to run unsandboxed — which re-opens bug 4 in a different place. Do not assume.
3. **The sanctioned CLI/MCP client path exists first** (§5.4) — under embedded-only there
   is no TCP listener and no real-home token file, so shipping the removal before the
   client path bricks the CLI/MCP for everyone including Daniel.
4. **Keep** `start_backend.sh`, `.inert`, and the pytest in-process path untouched — they
   are the headless/CI story (§5.2) and are not part of this removal.

What to delete when it lands: the `.debugExternal` case and its Debug-no-bundle special
path (`Spawn.swift:138-143`), the Dev Local scheme + pre-action, the sandbox token mirror
machinery (`auth.py:82-146,236-311`) once the CLI story replaces it, the
`FICHERO_FORCE_UDS` path-free override (`EngineConfig+Launch.swift:49-52`), and the CLI's
engine lifecycle commands (§5.1, item e). Each removal shrinks the auth/transport surface
the team has been patching weekly.

---

## 5. The CLI/MCP ruling: consequences (constraint, not a question)

**The ruling (Daniel, 2026-08-04):** on Mac, CLI and MCP are clients of the GUI app;
without the GUI app there is no MCP and no CLI on Mac.

### 5.1 What breaks / conflicts — concrete call sites

How the two products reach the engine today (main checkout; may lag this worktree):

- (a) **Base URL:** `fichero-cli/src/fichero_cli/client.py:77` — `DEFAULT_BASE_URL =
  "http://127.0.0.1:8765"`; `:224-225` — constructor takes `base_url` or
  `$FICHERO_API_URL` or the default. `fichero-mcp/src/fichero_mcp/server.py:34,46-63`
  wraps `FicheroClient`; `:416-425` — `--api-url` / `$FICHERO_API_URL`, same default.
- (b) **Credential discovery:** `client.py:83` — `_TOKEN_PATH = Path.home()/…/Fichero/
  ".api-key"` (real home); `:84` — `cli-session.json` beside it; `:138-173` —
  `_read_token()`; `:227-229,256-271` — lazy re-discovery on every refresh.
- (c) **Importer commands:** `fichero-cli/src/fichero_cli/__main__.py:755-1481` — a dozen
  `import_*_via_http` commands that import `fichero_server.importers.*` and post to the
  engine over HTTP; `:1000,1111` — `--key` defaults to "the app's `.api-key`";
  server-side reader `fichero-server/src/fichero_server/importers/http_client.py:11`
  (real-home `.api-key` again).
- (d) **Connection-failure UX:** `client.py:312,330,378` — "Cannot connect to the Fichero
  backend at …" errors, currently phrased around a bare backend, not around "launch
  Fichero".
- (e) **Engine lifecycle commands — the direct conflict:** `__main__.py:3739-3747` wires
  `fichero engine status/start/stop/restart` to
  `fichero-cli/src/fichero_cli/engine_manager.py` (own PID file `~/.fichero/engine.pid`,
  `:24`; port-probe spawn logic). This makes the CLI a **third engine owner** on Mac.
  Under the ruling it cannot exist in its current form: the CLI must never own an engine
  on a user's Mac. Delete it or confine it to an explicit dev flag (Q4 is now closed by
  the ruling for the *user* case; the dev-only remnant is a scoping detail).

**The decisive empirical fact:** items (a)–(c) are *already broken* against the embedded
engine. The embedded engine binds **UDS only — no TCP port** (`__main__.py:209-239`,
DOCUMENTED), the CLI has **no UDS transport code at all** (EMPIRICAL: grep for
`uds|sock` in `client.py` — no matches), and the sandbox-inherited engine writes its
token file under the *container* home (`auth.py:78` + `Path.home()` resolution), which is
not the real-home path at `client.py:83`. So under Dev Embedded / Release today, `fichero
docs list` cannot reach the engine by transport *or* authenticate if it could. The ruling
does not newly break these paths — it **ratifies what the embedded architecture already
enforces** and obliges us to build the sanctioned replacement:

- a UDS client transport in `FicheroClient` (httpx supports `uds=` transports), dialing
  the app's socket, and
- an app-controlled credential visible to outside-the-sandbox clients (§5.4 / Q3), and
- error text at (d) that says "launch Fichero", plus removal of (e).

### 5.2 The headless question, settled path by path

The obvious objection to "no CLI without the app" is CI. Verified: **no gate routes
through the CLI or MCP to a live engine.** Every path is direct:

| Gate path | How it reaches the engine | Evidence |
|---|---|---|
| `fichero-server/tests/unit/` (all gates) | In-process — FastAPI TestClient / library import; `auth.py:317-321` explicitly accounts for "pytest's TestClient" as a concurrent in-process instantiation (#1110) | DOCUMENTED |
| `fichero-server/tests/contracts/` (`verify_all.sh:364`) | Library import only — e.g. `test_extensibility_guarantee.py:5-21` imports `duckdb`, `fichero_server.db`, workflow tools directly; no HTTP client anywhere in the directory | EMPIRICAL (grep for `TestClient|httpx|127.0.0.1` — no live-connection hits) |
| `fichero-cli/tests/` (`verify_all.sh:357-358`) | `httpx.MockTransport` at the transport seam — "no subprocess, no live server" (`test_cli_dispatch.py:3`, `test_cli_connection_resolution.py:4-6`) | EMPIRICAL/DOCUMENTED |
| `fichero-mcp/tests/` (`verify_all.sh:358`; `scripts/gate:101`) | Same — "an `httpx.MockTransport` stands in at the transport seam" (`test_mcp_connection.py:6`) | DOCUMENTED |
| `verify_python.sh:63-64` | `python -c "import fichero_cli"` and `--help` — import/argparse smoke, no connection | DOCUMENTED |
| `scripts/check_*.py` guardrails | Static analysis of source trees (e.g. `check_endpoint_usage.py:34`, `check_openapi_client_parity.py:29` read files under `fichero-cli/src/`) — never execute the CLI against an engine | DOCUMENTED |
| `build-and-validate.sh:56-77` | ruff + pytest as above | DOCUMENTED |

**Conclusion: the ruling does not touch the gates.** They exercise the engine as a
library and the CLI/MCP against mocks. There is no conflict to escalate. (One operational
wrinkle, orthogonal to the ruling: the CLI/MCP `src/` trees exist only in the main
checkout, so gate invocations that reference `fichero-cli/src` resolve only when run
there — EMPIRICAL, this worktree lacks the sources. That is #4227 housekeeping, not a
consequence of the ruling.)

### 5.3 Geographic scope: "on Mac"

The ruling as stated is Mac-scoped, and the codebase confirms the other deployments are
real and different:

- **Headless Linux / server engine:** `FICHERO_LIBRARY_ALLOWED_ROOTS` exists precisely
  "for remote/server deployments" (`api/main.py:949`; parser at
  `security/path_security.py:142-162`). There is no GUI app in that picture, the macOS
  keychain module reports unavailable off-macOS (`keychain.py:96-98,134-139`), and the
  engine runs standalone behind its own token. The rule *cannot* hold there in the form
  "no CLI without the GUI app" — the honest reading is: **on a Mac, the local engine's
  only owner is the app; on a server, the engine is the service and the CLI is its
  remote client.**
- **CLI against a remote engine:** the plumbing exists today — `--base-url` /
  `$FICHERO_API_URL` (`__main__.py:102-105`), loopback detection choosing bootstrap-file
  auth vs. session auth (`client.py:87-98,138-173`), `cli-session.json`. Running
  `fichero --base-url https://host …` from a Mac against a *remote* engine involves no
  local engine and no local GUI.

Rather than quietly carving the exception, this is put to Daniel as **Q1 (§7)**: does the
ruling mean (a) only "the CLI must never own or adopt a *local* Mac engine" (remote
targets stay legal without the local app), or (b) the stronger "the Mac CLI binary exists
only as a companion to a running app" (remote use routes through the app too)? The
architecture supports either; they produce different deletions in `client.py`.

### 5.4 The credential/transport question the ruling sharpens

If CLI/MCP are clients of the *app*, the app becomes the distributor of their credential
and endpoint. Today's discovery (real-home `.api-key` written by a non-sandboxed engine)
dies with `.debugExternal`. The replacement must be one of: the app exports a
client-visible token + socket path to a stable real-home location it controls; or a small
handshake (the CLI asks the running app, which is also a liveness check — "app not
running" and "no credential" become the same actionable error). This is Q3 in §7 and is a
**hard prerequisite** of §4 — sequencing note: the client path must land *before*
`.debugExternal` is removed, or the CLI/MCP have no working configuration at all on Mac.

---

## 6. Convergence check: two rulings, one principle

Daniel's parallel decision — **the app owns the provider-API-key keychain item and passes
the key to the engine**, because the app is the signed, stable identity and the engine is
not — and the CLI/MCP ruling are the same principle applied twice: **on macOS, the GUI
app is the root of identity, lifecycle, and trust; engine, CLI, and MCP are all its
subordinates.** The provisioning-mode recommendation (§4) is the third application:
`.releaseEmbedded` is the only strategy where the app actually *is* that root
(`spawnsBundledEngine`, app-minted token #2862, app-computed socket, app-supplied
bookmarks), while `.debugExternal` is the one mode that inverts it.

Places the two decisions could pull against each other — checked, mostly clean, one flag:

- **Clean:** CLI/MCP never handle provider keys (no keychain call sites in either tree —
  EMPIRICAL grep), so app-owned keys don't change their client contract.
- **Clean:** app-owned keys + app-owned engine remove *both* reasons the engine shells out
  to `security` (`keychain.py:101-120`) on Mac — the module trends toward legacy there.
- **Flag (shared blind spot, not a conflict):** *neither* ruling has a story for the
  no-app deployments. On a headless Linux server there is no app to own the keychain item
  **and** no app to gate the CLI. Both decisions need the same one-line non-Mac corollary
  (likely: server engine owns its own secrets via env/config, CLI is a remote client) —
  Q1/Q5 in §7. Deciding them together keeps the principle coherent instead of
  Mac-only-by-accident.

---

## 7. Open questions for Daniel

- **Q1 (scope of the CLI/MCP ruling):** Does "on Mac" mean (a) the CLI must never own or
  adopt a *local* Mac engine, but may still target a **remote** engine
  (`--base-url`/session auth) without the local app running — or (b) the Mac CLI exists
  only alongside a running app, full stop? And explicitly: the rule cannot hold on a
  headless Linux server (no GUI app exists; `FICHERO_LIBRARY_ALLOWED_ROOTS` is built for
  that case) — confirm the server corollary: *engine-as-service, CLI as its remote
  client*?
- **Q2 (iteration loop):** Once Dev Local is gone: (a) engine-alone iteration
  (pytest/direct HTTP, app rebuild only for UI-visible checks), or (b) the app-spawned
  `--reload` venv engine from Q1-spike? (b) preserves the fast loop under one-owner
  semantics but hinges on the sandbox-inheritance spike
  (`com.apple.security.inherit` on an unsigned interpreter — UNVERIFIED).
- **Q3 (client credential/endpoint):** Under embedded-only, how do CLI/MCP get the token
  and socket: app-exported file in real-home Application Support, or an app handshake
  (which doubles as the "is the app running" check)? Blocks §4 step 3.
- **Q4 (dev remnant of `fichero engine start/stop`):** The ruling kills it for users
  (§5.1e). Does a dev-flagged remnant survive for server/CI development, or is
  `start_backend.sh` the only sanctioned way to run a bare engine?
- **Q5 (provider keys off-Mac):** With the app owning keys on Mac, what owns them for a
  Linux/remote engine — env vars, a server config file? (Same blind spot as Q1; one
  answer should cover both.) Related: I found the #4531 commit ("C1 library-location
  grants + D2 keychain tri-state design") in the reflog but could not locate the spec
  document in this tree (UNVERIFIED) — if it exists, it should own this answer.
