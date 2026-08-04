# Design Review: Should `.debugExternal` (the developer-run local engine) survive?

**Date:** 2026-08-04 · **Status:** review, not a decision record · **Asked by:** Daniel
**Question:** Would there be benefits to supporting only **embedded**, **remote**, and **iOS**
engine modes — dropping the developer-run local engine? And should CLI/MCP only ever connect
when the app is running?

**Method note (honesty about tooling):** this review was produced without a shell. Git
evidence comes from reading `.git/logs/refs/heads/integration` reflog subjects directly
(EMPIRICAL, marked below) — commit *bodies* were not searchable, so the defect sweep is a
lower bound. jCodemunch MCP tools were unavailable this session; code claims come from
direct file reads with line numbers. CLI/MCP sources were read from the **main checkout**
(`~/code/fichero/fichero-cli`, `~/code/fichero/fichero-mcp`), which may not be at the same
commit as this worktree — marked where it matters.

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

**Does Daniel's decision (app owns the keychain item, passes the key to the engine) moot
this?** For this bug, **yes** — it removes the engine's code identity from the trust
equation entirely, in *every* mode, including remote (where the engine is on another Mac
and could never read this Mac's keychain anyway). The tri-state read (#4534) remains
worth keeping as defense-in-depth. So: bug 1 is evidence *for* the thesis, but the fix
that actually kills it is the app-owned key, not mode removal. The mode question is not
mooted overall — bugs 2–4 are untouched by it.

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

What would *survive* an embedded-only world: the token file itself still needs a
CLI/MCP-readable location (see §5), and `initialize_token`'s reuse-don't-rotate behavior
(#1110) still protects concurrent pytest/uvicorn instantiations in *engine-alone*
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

1. **Backend iteration speed — the big one.** The developer engine runs under
   `--reload`, so a Python edit is live in seconds with the app still attached. Under
   embedded, a backend change visible *in the app* costs: `briefcase build macOS --app
   server` + an app rebuild + relaunch (`Spawn.swift:141-143` documents exactly this
   recipe). I could not time this without a shell (UNVERIFIED), but the project record is
   unambiguous that builds on this machine are slow, must be serialized, and have pushed
   the machine into process-killing load (AGENTS.md:72-74). Call it minutes-per-iteration
   vs. seconds — a real order-of-magnitude loss **for the specific workflow of iterating
   backend code while watching the result in the live app UI.**
   *Counter-counter:* most backend iteration does not need the app at all — `pytest`,
   `start_backend.sh` + CLI, and contract tests cover engine logic headlessly, and none
   of that depends on `.debugExternal` (an *app* mode). The cost is confined to
   full-stack, UI-visible backend work. It is not zero and should not be waved away.

2. **Headless and CI.** `pytest` runs the engine in-process (TestClient / `#1110`'s
   "concurrent app instantiations" note, `auth.py:317-321`); guardrail scripts and
   contract tests use `start_backend.sh`. **None of this breaks if `.debugExternal` is
   removed**, because none of it involves the Mac app adopting anything. The thing that
   must survive is the *engine-alone developer workflow* — which is orthogonal to which
   provisioning strategies the app supports. Conflating these two would be the expensive
   mistake; the recommendation below keeps them separate.

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

---

## 4. RECOMMENDATION (engine modes)

**Retire `.debugExternal` as a daily-driver mode. Converge the app on
embedded / remote / iOS (+ `.inert` for test hosts). Confidence: medium-high on the
direction; medium on sequencing.**

Reasoning: today's score was 4-for-4; the two-owner arrangement is not merely correlated
with these defects, it is their *mechanism* (two writers of one token file, two
configurators of one socket path, two filesystem views of one `Path.home()`, two code
identities at one keychain item). The steelman survives only on iteration speed — a real
cost, but one that is (a) confined to UI-visible backend iteration and (b) mitigable
without keeping a second engine owner. Daniel has already moved his run target to Dev
Embedded, which is the correct experiment: he is now testing what ships.

**But not yet.** Gate the removal on:

1. **App-owned provider keys land** (the decision already taken). Kills bug 1 in every
   mode; nothing about mode removal should wait on keychain behavior or vice versa.
2. **A decision on the iteration loop** (open question Q2 below). Two candidate answers:
   - *Accept engine-alone iteration:* backend logic loops through pytest/CLI against a
     `start_backend.sh` engine; the app rebuild happens only when you need to see UI.
     Cheapest; costs the live full-stack loop.
   - *App-spawned dev engine:* a Debug-only variant of `.releaseEmbedded` where the app
     spawns the **venv Python with `--reload`** instead of the bundled binary — the app
     still owns the process, mints the token, sets `FICHERO_UDS_PATH`; only the
     executable differs. This keeps one-owner semantics *and* the reload loop.
     **UNVERIFIED and needs a spike:** whether a sandboxed app can spawn an unsigned
     venv interpreter at all (sandbox inheritance normally requires the child to carry
     `com.apple.security.inherit`), and whether the sandbox-confined interpreter can read
     the venv outside the container. If the spike fails, this variant may require the dev
     app to run unsandboxed — which re-opens bug 4 in a different place. Do not assume.
3. **CLI/MCP token discovery reworked first** (see §5) — under embedded-only, the
   sandbox-inherited engine's `Path.home()` is the container, so the home-path `.api-key`
   that `fichero-cli` reads (`client.py:83`, main checkout) would have **no writer**.
   Removing `.debugExternal` before fixing this bricks the CLI for end users.
4. **Keep** `start_backend.sh`, `.inert`, and the pytest in-process path untouched — they
   are the headless/CI story and are not part of this removal.

What to delete when it lands: the `.debugExternal` case and its Debug-no-bundle special
path (`Spawn.swift:138-143`), the Dev Local scheme + pre-action, the sandbox token mirror
machinery (`auth.py:82-146,236-311`) once the CLI story replaces it, and the
`FICHERO_FORCE_UDS` path-free override (`EngineConfig+Launch.swift:49-52`). Each removal
shrinks the auth/transport surface the team has been patching weekly.

---

## 5. RECOMMENDATION (CLI/MCP: "only connect if the app is running")

**Adopt it as the product rule; do not adopt it as a hard technical gate. Confidence:
medium-high.**

Verified current behavior (main checkout — may lag this worktree): `fichero-cli` dials
`http://127.0.0.1:8765` by default and self-discovers the bearer token from the home-path
`.api-key` (`client.py:77,83`); `fichero-mcp` is a thin wrapper over `FicheroClient`
(`server.py:34,46-55`) with `$FICHERO_API_URL` override. Critically, the CLI also ships
`engine_manager.py` — `fichero engine start/stop/restart` with its own PID file
(`~/.fichero/engine.pid`) — i.e., the CLI is a **third potential engine owner**, the same
defect class as `.debugExternal` wearing a different hat.

- **What gating on the app buys:** exactly one engine owner on a user's Mac; CLI/MCP
  become pure clients of the app's engine; the token/socket ambiguity ("which engine am I
  talking to, whose token is live?") disappears; and it matches Daniel's standing
  direction that agents drive the product *through the app* (agent-as-user, app
  scripting). For an end user this is also the honest UX: the engine's data-consistency
  guarantees (single writer to the library) are the app's to own.
- **What a hard gate would cost:** cron/automation on a headless Mac, agent/researcher
  workflows against a long-lived library service, CI and contract tests — all currently
  possible against a bare `start_backend.sh` engine. The test harness does not need the
  concession (pytest is in-process), but developer and future server workflows do.

Concrete shape: (1) **remove or dev-flag `fichero engine start/stop`** — the CLI must
never own an engine in a user install; (2) CLI/MCP connect to the app's engine and fail
absent-engine with an actionable "launch Fichero" message (the transport/token discovery
must be updated for the embedded world: either the app exports a client-visible token +
socket/URL to a stable path outside the container, or CLI/MCP go through a small
app-provided handshake); (3) developers and CI keep `start_backend.sh` + explicit
`$FICHERO_API_URL` as the documented escape hatch — an *explicit* override, not silent
discovery. That yields "CLI/MCP only work when the app is running" for every user-facing
scenario, without amputating headless development.

---

## 6. Open questions for Daniel

- **Q1 (spike):** Can the sandboxed Dev app spawn the venv Python with `--reload` (sandbox
  inheritance / `com.apple.security.inherit` on an unsigned interpreter)? If not, is an
  unsandboxed *dev-only* app configuration acceptable for that loop, or is engine-alone
  iteration (Q2a) good enough?
- **Q2:** Which iteration loop do you accept once Dev Local is gone: (a) engine-alone
  (pytest/CLI, app rebuild only for UI-visible checks), or (b) the app-spawned reload
  engine from Q1? This decides how much tooling has to exist before removal.
- **Q3:** Under embedded-only, who writes the CLI/MCP-readable credential, and where? The
  container-home `.api-key` is invisible to outside processes; options are an app-exported
  token file in real-home Application Support, or a pairing-style handshake. This blocks
  §4 step 3.
- **Q4:** Does `fichero engine start/stop` survive as a dev-only flag, or is it deleted
  outright?
- **Q5:** For the app-owned provider keys: one keychain item per provider under an
  app-owned service, passed per-spawn via env — or pushed to the engine over the
  authenticated channel at runtime (which also serves the remote-engine case)? I found
  the #4531 commit ("C1 library-location grants + D2 keychain tri-state design") in the
  reflog but could not locate the spec document in this tree (UNVERIFIED) — if it exists,
  it should own this answer.
