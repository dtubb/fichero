# Mac App Store / App Sandbox Research for Fichero (2026-07-13)

Status: COMPLETE. Researcher agent; all Apple-rule claims carry citations; (a)=Apple-documented, (b)=widely-reported developer experience, (c)=inference are marked throughout.

## VERDICT UP FRONT

**YES — WITH CONDITIONS.** The embedded-Python-subprocess architecture is viable on the Mac App Store *as a matter of Apple's rules*:

- **Policy (a, Apple-documented):** A sandboxed app spawning a bundled helper with `Process`/`NSTask` is an Apple-documented, DTS-endorsed pattern (`com.apple.security.inherit`). Guideline 2.5.2 prohibits code that is **downloaded or installed** or that **changes the app from what was reviewed** — a bundled interpreter executing bundled, signed .py files does neither (full quoted-text analysis below). Bundled-interpreter apps (Python, Lua, JS/Electron) ship on Apple's stores routinely, and Briefcase — the exact tool packaging Fichero's engine — documents MAS distribution as a supported path.
- **The conditions:** (1) the engine must itself be sandboxed with exactly `app-sandbox` + `inherit`; (2) the user's library folder must be handed to the engine via **security-scoped bookmarks** (dynamic file grants do NOT inherit — this is the #3340 plumbing, and it's real work in CPython); (3) zero runtime code download, ever, in the MAS SKU; (4) Sparkle compiled out at the *link* level (separate target); (5) move the nested engine app out of `Contents/Resources`; (6) replace the `pgrep`/`ps`/`lsof`/`kill` process-poking with own-child-only lifecycle management.
- **The honest caveat (c):** the rules allow it, but **nobody has yet proven Fichero's specific CPython+800-wheels engine runs inside an inherited sandbox**. That empirical spike — not App Review policy — is the real go/no-go, and it costs ~1–2 days to run.

## Recommendation: Option A (one app) vs Option B (two apps)

**Recommendation: pursue Option A (embedded engine, one app), gated on a short sandbox spike; keep Option B as the designed fallback, not the plan.**

| | Rejection risk | Engineering cost |
|---|---|---|
| **A: one app, embedded engine** | **Low-moderate** — policy is on our side (2.5.2/2.4.5 analysis + precedent); residual risk is reviewer variance + ingestion-validation friction (nested-code layout, cs.* entitlements) | **Moderate-high** — engine sandboxing, bookmark plumbing into CPython, lifecycle rework, target split |
| **B: two apps, MAS client only** | **Moderate** — the 4.2.3(i) "should work on its own" question is the one guideline where we'd argue precedent (Sequel Ace, Plex) rather than text | **Low** — `configuredRemote` mode, pairing UI, and BackendConnectionView already exist; mostly compile-out + demo-mode work |

Reasoning (c): Option A's risks are mostly *engineering certainties with known fixes*, while Option B's risk is a *judgment call by a reviewer* on minimum functionality — and Option B also delivers a worse product (a MAS app that's inert until the user installs the DMG build anyway). If the sandbox spike (Open Question #1) fails badly — e.g., CPython/duckdb fundamentally misbehaves in an inherited sandbox — Option B is a genuinely cheap fallback because the client-only mode already exists in the codebase. Sequencing: spike first; decide A vs B on its result, not on guesswork.

## Current state of the repo (verified by reading source)

All claims in this section are verified by reading files in `~/code/fichero` on 2026-07-13.

### The four entitlements files

**1. `fichero/fichero/FicheroAppStore.entitlements`** — the MAS profile (#3340). Grants:
- `com.apple.security.app-sandbox = true` (App Sandbox on)
- `com.apple.security.network.client = true` (outbound connections, incl. loopback client)
- `com.apple.security.network.server = true` (listen on a port — for the engine's loopback bind)
- `com.apple.security.files.user-selected.read-write = true` (read/write files the user picks)
- `com.apple.security.files.bookmarks.app-scope = true` and `...document-scope = true` (create/resolve security-scoped bookmarks so library access persists across launches)

The header comment records two important facts already known to the team: (a) MAS upload is rejected (ITMS error 90296) unless *every nested executable* is sandboxed, and (b) sandboxing the shared Briefcase engine build is deliberately **not wired yet** — held (#3340) because it risks the DMG engine and needs security-scoped-bookmark plumbing to hand library access to the sandboxed engine.

**2. `fichero/fichero/FicheroRelease.entitlements`** — the DMG / Developer ID profile. Grants only:
- `com.apple.security.files.user-selected.read-write = true`

No sandbox key → the DMG build is **not sandboxed** (this entitlement is effectively cosmetic outside the sandbox; kept presumably for parity/hardened-runtime contexts).

**3. `fichero/fichero/FicheroEngine.entitlements`** — applied when the release DMG re-signs `Fichero Engine.app` with Developer ID + hardened runtime. Grants (all hardened-runtime *exception* entitlements, each mapped in the file's comments to a real CPython failure mode):
- `com.apple.security.cs.disable-library-validation` (load ~800 third-party native wheels not signed with our Team ID: duckdb, numpy, PyMuPDF, …)
- `com.apple.security.cs.allow-unsigned-executable-memory` (cffi/ctypes trampolines create W+X memory)
- `com.apple.security.cs.allow-dyld-environment-variables` (Briefcase launcher sets `DYLD_*` to find bundled libs)
- `com.apple.security.cs.allow-jit` (defensive, for native deps that JIT)

Note: **none of these is a sandbox entitlement** — they are hardened-runtime opt-outs for notarization. Several of them (esp. `disable-library-validation` and `allow-dyld-environment-variables`) are the kind of thing App Review scrutinizes; see risk section.

**4. `fichero/fichero/Fichero.entitlements`** — an **empty dict**. Grants nothing (development/default profile).

### Embedded engine spawn (Release) — how it works today

From `fichero/fichero/Services/EmbeddedBackendService.swift` (the #2611/#2862/#2863 code):

- Strategy enum (#3109): `inert` (tests/previews), `configuredRemote` / `iosCompanion` (connect to explicit or paired host, never spawn), `debugExternal` (Debug ⌘R adopts developer-run engine on :8765), `releaseEmbedded` (the ONLY strategy that spawns).
- `launchEmbeddedBackend()` uses **`Foundation.Process`** directly: executable is `Bundle.main.resourcePath + "/Fichero Engine.app/Contents/MacOS/Fichero Engine"` — a **Briefcase-packaged CPython app nested inside the app's Resources**. Arguments pass TLS cert/key; env passes `FICHERO_PARENT_PID`, `FICHERO_BOOTSTRAP_TOKEN`, `FICHERO_LAUNCH_NONCE`, TLS material, `FICHERO_BIND_HOST`, feature tier.
- The app is token-authoritative (#2862): it mints the bootstrap token, writes it to the `.api-key` file itself (mode 0600) via `AuthTokenMiddleware.bootstrapTokenFileURL()`, and probes readiness with an authenticated request + launch-nonce echo.
- Engine stdout/stderr are captured to `~/Library/Logs/Fichero/engine.log`.
- Additional helper subprocesses spawned by the app (all sandbox-relevant): the engine binary itself is also run synchronously with `--prepare-local-access` / `--prepare-remote-access` to mint TLS material; orphan sweep runs **`/usr/bin/pgrep`**, **`/bin/ps -E`** (reads other processes' environments), and **`/usr/sbin/lsof`**; conflict resolution sends `kill(pid, SIGTERM/SIGKILL)` to processes that may not be our children.
- Transport: HTTPS on loopback with SPKI pinning; loopback-only bind is a HARD invariant guarded by `scripts/check_swift_transport.py`.

### Sparkle usage sites

- `fichero/fichero/App/SparkleUpdater.swift` — the whole class is **already wrapped in `#if canImport(Sparkle)`** with a no-Sparkle fallback path (alert "Sparkle framework is not linked in this build") and an iOS stub. So the *source* is already conditional; what remains is per-configuration **linking**.
- `fichero/fichero/FicheroApp.swift:338-345` — menu item calling `SparkleUpdater.shared.checkForUpdates()`; the comment already states the intent: "Mac App Store forbids Sparkle's helpers… App-Store config (which doesn't link Sparkle) hides this item (#3340)."
- `fichero/fichero/Models/WorkflowStore.swift:76` — a comment only ("Updated presets after a Sparkle update reach old libraries"); no code dependency.

## Required entitlement changes for MAS

**App target:** `FicheroAppStore.entitlements` is already substantively correct — `app-sandbox`, `network.client`, `network.server`, `files.user-selected.read-write`, `files.bookmarks.app-scope`, `files.bookmarks.document-scope`. No changes identified. (If Unix-domain sockets were ever used app↔engine, an app-group container would be required — they aren't; TCP loopback is used.)

**Engine (`Fichero Engine.app`) — the missing piece.** For the MAS build the engine needs a *new, different* entitlements profile containing **exactly**:

```xml
<key>com.apple.security.app-sandbox</key><true/>
<key>com.apple.security.inherit</key><true/>
```

per Apple's documented rule ("a child target must use exactly two App Sandbox entitlement keys… If you specify any other App Sandbox entitlement, the system aborts the child process"). Every executable nested in the app must be sandboxed or upload fails with ITMS-90296 (already recorded in the entitlements file's comment). That includes the Briefcase launcher/binary — Briefcase's macOS docs expose an `entitlement` setting in `pyproject.toml` for this (https://briefcase.beeware.org/en/latest/reference/platforms/macOS/index.html).

- The four `com.apple.security.cs.*` keys in `FicheroEngine.entitlements` are **hardened-runtime** exceptions needed for *notarization* (DMG channel). MAS distribution does not go through notarization; whether these keys are needed or even permitted at MAS ingestion is **unverified** (see Open Questions). Plan for a separate MAS engine entitlements file without them, and add them back only if signing/ingestion demands it.
- Also set `CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO` for the helper in dev builds: Xcode's injected `get-task-allow` is incompatible with `com.apple.security.inherit` (from Apple's embedding doc, as surfaced in the doc search results).

**Keep the two profiles strictly separate** (as the repo already does): DMG = not sandboxed + hardened runtime + cs.* exceptions; MAS = sandboxed + inherit, no Sparkle.

## The subprocess question, in depth

**Bottom line: yes — a sandboxed Mac App Store app may spawn a bundled executable (including a bundled Python interpreter) as a child process with `Foundation.Process`/`NSTask`, provided the child inherits the parent's sandbox.** This is not a gray area at the mechanism level: Apple documents it and Apple DTS (Quinn "The Eskimo!") explicitly confirms it. XPC services or `SMAppService` are *alternatives*, not requirements.

### (a) What Apple documents

Apple's Entitlement Key Reference ("Enabling App Sandbox") says, verbatim:

> "If your app employs a child process created with either the `posix_spawn` function or the `NSTask` class, you can configure the child process to inherit the sandbox of its parent."

> "To enable sandbox inheritance, a child target must use exactly two App Sandbox entitlement keys: `com.apple.security.app-sandbox` and `com.apple.security.inherit`."

> "If you specify any other App Sandbox entitlement, the system aborts the child process."

> "This property causes the child process to inherit *only* the static rights defined in the main app's entitlements file, *not* any rights added to your sandbox after launch (such as PowerBox access to files)."

Source: https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html (archived but still the canonical wording; the modern equivalent is "Embedding a command-line tool in a sandboxed app", https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app, which Apple DTS still points developers to as of 2024–2025).

Apple DTS (Quinn "The Eskimo!") on the developer forums:

> "The sandbox is called the *App* Sandbox, and that's for a reason. As far as public API is concerned, you can only sandbox apps (and app-like things, like app extensions, system extensions, and XPC Services). Things that aren't apps always inherit the sandbox from the parent process." — https://developer.apple.com/forums/thread/123873

> "It *is* possible for sandbox apps to run child processes, but it's a bit tricky." (pointing at the embedding-a-command-line-tool doc) — https://developer.apple.com/forums/thread/763498

Also relevant from thread 763498 (Quinn): for a sandboxed helper doing local sockets, "stick with localhost (127.0.0.1 or ::1)"; Unix domain sockets would require an app-group container.

### Consequences of sandbox inheritance for Fichero's engine

1. **Same container, same static rights.** The engine sees exactly the app's static entitlements (network client+server, user-selected files, bookmark entitlements) and shares the app's sandbox container. `~/Library/Application Support/Fichero/.api-key` (the path `AuthTokenMiddleware.bootstrapTokenFileURL()` computes via `.applicationSupportDirectory`) resolves *inside the container* for both processes — so the prior ".sandboxed app couldn't read the engine's .api-key" pain largely dissolves in a MAS build where **both** processes are sandbox-mates. (Inference from documented behavior; verify empirically.)
2. **Dynamic rights do NOT flow to the child.** The user picks a library folder via NSOpenPanel → that grant is a *dynamic* Powerbox extension to the app's sandbox and is **not inherited**. Apple's documented options: pass the data, or pass a **security-scoped bookmark** to the child, which the child resolves and calls `startAccessingSecurityScopedResource()` on. This is precisely the "security-scoped-bookmark plumbing" the `FicheroAppStore.entitlements` HOLD note (#3340) anticipates: the app must hand the engine an app-scoped bookmark for the library folder (e.g., via env var/argument/API call), and the engine must resolve it before touching DuckDB files. **This is real engineering work on the Python side** (PyObjC or a small helper to resolve `NSURL` bookmarks — CPython can't do it with plain `open()`).
3. **The engine must be signed with exactly `app-sandbox` + `inherit` and no other *sandbox* entitlements.** The current `FicheroEngine.entitlements` keys (`cs.disable-library-validation`, `cs.allow-unsigned-executable-memory`, `cs.allow-dyld-environment-variables`, `cs.allow-jit`) are **hardened-runtime** entitlements, not App Sandbox entitlements, so they don't trip the documented "system aborts the child" rule — and MAS builds don't require the hardened runtime at all (notarization does; MAS ingestion is a separate trust path). *(Inference: widely reported that MAS apps don't need hardened runtime; I could not find a current Apple page stating this explicitly — flagged in Open Questions.)*
4. **The orphan-sweep / port-conflict machinery will likely break.** `EmbeddedBackendService` shells out to `/usr/bin/pgrep`, `/bin/ps -E` (reading *other* processes' environments), `/usr/sbin/lsof`, and sends `kill()` to processes that are not its children. Under App Sandbox, visibility into and signaling of unrelated processes is restricted (sandboxed processes can't inspect or signal arbitrary PIDs). Expect `terminateOrphanEngines()`, `engineParentPID()`, `pidOnPort()` and the "Stop it" kill path to silently return nothing or fail in a MAS build. *(This is (c) inference from sandbox semantics plus widely-reported behavior; needs empirical testing. The safe MAS design: track only your own child via the `Process` object, and treat "port in use" as a hard error with a Retry.)*
5. **2.4.5(iii) compliance is already satisfied by design:** "nor spawn processes that continue to run without consent after a user has quit the app" — `stop()` SIGTERMs the engine synchronously in `applicationWillTerminate`, and the engine watches `FICHERO_PARENT_PID` and self-terminates. Keep it that way.
6. **Nested-code placement.** The engine currently lives at `Contents/Resources/Fichero Engine.app`. Apple's code-signing rules (TN2206 "macOS Code Signing In Depth") require nested executable code to live in the designated code locations (`Contents/MacOS`, `Contents/Frameworks`, `Contents/Helpers`, `Contents/PlugIns`, `Contents/XPCServices`, `Contents/Library/...`), **not** `Contents/Resources`. App Store ingestion validation is stricter than notarization; an executable `.app` under `Resources` is a plausible ITMS validation error. *(Widely-reported + TN2206; the DMG channel getting away with it under notarization does not prove MAS will. Recommend moving the nested app to `Contents/Helpers/` or `Contents/Library/` for the MAS target.)*

### `Process`/`NSTask` vs XPC vs `SMAppService`

- **`Process`/`NSTask` + inherit**: documented, supported, sufficient. This is what Fichero already does.
- **XPC service**: Apple's *preferred* helper architecture (lifecycle managed by launchd, per-service sandbox), but an XPC service hosting a full CPython + FastAPI server is awkward (XPC services are on-demand, message-oriented; Fichero needs a long-lived HTTP listener). Not required.
- **`SMAppService`**: for login items/daemons/agents that outlive the app — the *opposite* of what 2.4.5(iii) wants for this design. Not applicable.

## Guideline 2.5.2 analysis (quoted text)

Full verbatim text (fetched 2026-07-13 from https://developer.apple.com/app-store/review/guidelines/):

> **2.5.2** "Apps should be self-contained in their bundles, and may not read or write data outside the designated container area, nor may they download, install, or execute code which introduces or changes features or functionality of the app, including other apps. Educational apps designed to teach, develop, or allow students to test executable code may, in limited circumstances, download code provided that such code is not used for other purposes. Such apps must make the source code provided by the app completely viewable and editable by the user."

**What it actually prohibits vs. what developers assume.** The operative clause is "download, install, or execute code **which introduces or changes features or functionality of the app**." Read carefully:

- The prohibition targets code that **arrives after review** (downloaded/installed) or that **changes what the reviewer approved**. Code that ships **inside the reviewed bundle** — .py files signed into the app, executed by an interpreter also signed into the app — introduces nothing and changes nothing relative to what App Review saw. The reviewed artifact *is* the behavior.
- The educational-apps exception is about **downloading** code; it is irrelevant to bundled scripts.
- The companion Mac rule is 2.4.5(iv): "They may not **download or install** standalone apps, kexts, additional code, or resources to add functionality or significantly change the app from what we see during the review process." Again: *download or install*. Executing bundled code is not in the prohibited verb set.

**Where the real line is:** if the app ever fetches .py files (or workflow definitions that are effectively code) from a server and executes them, *that* is squarely prohibited. Fichero's engine must ship frozen: no pip-install-at-runtime, no plugin download, no "update engine scripts" path outside the App Store. Also note 2.4.5(vii): "They must use the Mac App Store to distribute updates; other update mechanisms are not allowed" — this kills Sparkle *and* any engine-only self-update.

**Precedent (category b — widely reported, not Apple-documented):**
- **BeeWare Briefcase** (the exact packaging tool Fichero uses for the engine) documents Mac App Store distribution of Briefcase-built Python apps as a supported path, and Python-app developers report successful MAS approvals (see Sources). The engine here is Briefcase-built.
- Bundled interpreters have shipped on Apple's stores for over a decade: **Pythonista** and **Pyto** (iOS, full Python interpreters), games embedding Lua, Electron/JS apps (a bundled V8/JavaScriptCore executing bundled JS is structurally identical to a bundled CPython executing bundled .py). Electron apps (Slack, 1Password 7-era, WhatsApp) have long been accepted on the Mac App Store.
- Guideline 2.5.1 ("Apps may only use public APIs…") is not offended by an interpreter: CPython uses POSIX/libSystem public API. The historical 2.5.1 flashpoint for Electron apps was accidental **private API usage** inside Chromium (widely-reported MAS rejections circa 2019 for `CAContext`/private symbols) — that risk class exists for any large native dependency but is about *which symbols get linked*, not about interpretation.

**My assessment (clearly marked as inference):** a bundled CPython executing only bundled, signed .py files does **not** violate 2.5.2 as written, and there is strong precedent of approval. The residual risk is reviewer variance (a reviewer misreading "execute code" broadly), which historically has been low for bundled-interpreter apps and is appealable with the guideline text.

## Sparkle removal: concrete Xcode mechanism

**Why it must go (Apple citation):** Guideline 2.4.5(vii): "They must use the Mac App Store to distribute updates; other update mechanisms are not allowed." (https://developer.apple.com/app-store/review/guidelines/). Sparkle also ships helper executables (`Autoupdate`, `Updater.app`, XPC services) inside the framework — leaving the framework in the bundle, even unused, leaves prohibited updater machinery in a reviewed MAS binary. So it must be **not linked and not embedded**, not merely dormant.

**What the repo already has:** `SparkleUpdater.swift` is fully wrapped in `#if canImport(Sparkle)` with a no-Sparkle fallback, and `FicheroApp.swift` hides the menu item when Sparkle isn't linked (#3340). So the *source-level* compile-out already exists; the remaining mechanism is *link-level*.

**The mechanism (in order of robustness):**
1. **Separate app target** ("Fichero App Store") that simply does not list the Sparkle SPM product under General → Frameworks, Libraries, and Embedded Content. With the package product absent, `canImport(Sparkle)` is false, all Sparkle code compiles out, and no Sparkle binary/XPC service is embedded. This is the widely-used pattern for dual MAS/Developer-ID distribution (e.g. SwiftLee's write-up, https://www.avanderlee.com/xcode/sparkle-distribution-apps-in-and-out-of-the-mac-app-store/). Given a distinct `FicheroAppStore.entitlements` already exists, a distinct target (or at minimum a distinct scheme+configuration pair) is the natural home.
2. **Per-configuration linking with one target** is the fragile route: SPM does **not** support conditional product dependencies per build *configuration* (only per *platform*, via `.when(platforms:)`). Workarounds (`OTHER_LDFLAGS` per config + `EXCLUDED_SOURCE_FILE_NAMES` + a config-gated `SWIFT_ACTIVE_COMPILATION_CONDITIONS` like `APPSTORE` with `#if !APPSTORE`) can stop the *reference*, but Xcode will still embed the package product it thinks the target depends on — you would need an extra "strip Sparkle" build phase. Not recommended; use a target. *(Category (b)/(c): SPM limitation is widely reported; I did not find an Apple doc stating it.)*
3. Whichever route: keep `#if canImport(Sparkle)` as the source gate (already done) rather than sprinkling `#if APPSTORE` — it is self-maintaining.

Note the `SWIFT_ACTIVE_COMPILATION_CONDITIONS`/`#if` machinery is still useful for *other* MAS divergences (e.g., hiding the "Check for Updates…" menu, disabling the remote-access hosting UI if desired).

## Loopback networking in the sandbox

**Answer: loopback counts as network under the App Sandbox; you need `network.client` to connect to 127.0.0.1 and `network.server` to bind/listen on it. Fichero's MAS entitlements file already has both.**

- Apple's entitlement reference (verbatim): client — "To enable your app to connect to a server process running on another machine **(or on the same machine)**, enable outgoing network connections." server — "To enable opening a network listening socket so that other computers can connect to your app, allow incoming network connections." (https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html). The "(or on the same machine)" wording is Apple explicitly including loopback in the client entitlement's scope.
- Because the engine (child) inherits the app's **static** entitlements, the engine's loopback **bind** is covered by the app's `network.server`, and the app's requests to `https://127.0.0.1:8765` are covered by `network.client`. No extra keys.
- Apple DTS (Quinn), on sandboxed helper + sockets: stick with "localhost (127.0.0.1 or ::1)"; TCP loopback avoids both the Unix-socket app-group requirement and the macOS 15+ **Local Network privacy** prompt, which applies to LAN peers, not loopback (https://developer.apple.com/forums/thread/763498). Note: the *remote-access/Bonjour hosting* feature, if enabled in a MAS build, WOULD touch Local Network privacy and the LAN — that's about usage description keys/prompts, not entitlements.

## File access / security-scoped bookmarks

The library folder (DuckDB + files) is user-chosen, so under the sandbox:

- **Grant**: `com.apple.security.files.user-selected.read-write` + NSOpenPanel gives read/write to whatever the user picks (Powerbox). Already present in `FicheroAppStore.entitlements`. Apple: "Read/write access to files the user has selected using an Open or Save dialog." Drag-in and Open Recent expand the sandbox automatically.
- **Persistence across launches**: requires security-scoped bookmarks. Apple: "If you want to provide your sandboxed app with persistent access to file system resources, you must enable security-scoped bookmark and URL access." The entitlements `com.apple.security.files.bookmarks.app-scope` (app-scoped bookmarks — "recent libraries" style, right fit for Fichero) and `...document-scope` are both already present.
- **API flow** (standard, category (a) API reference — pointers: https://developer.apple.com/documentation/foundation/nsurl/1417795-bookmarkdata and https://developer.apple.com/documentation/foundation/nsurl/1413736-startaccessingsecurityscopedreso): create with `url.bookmarkData(options: .withSecurityScope, …)` at pick time; persist the blob; on next launch `URL(resolvingBookmarkData:options:[.withSecurityScope]…)`, then `startAccessingSecurityScopedResource()` before touching the tree, `stopAccessing…` when done (kernel resources leak if you never stop).
- **The hard part is the engine.** The Powerbox grant and a `startAccessing…` call extend the *app's* dynamic sandbox — and Apple explicitly documents that dynamic rights are **not inherited** by the child. The engine must be handed the bookmark itself (env var / API call at startup / on library-open), resolve it, and call `startAccessingSecurityScopedResource` **in the engine process** before opening DuckDB/files. In CPython that means PyObjC (`NSURL.URLByResolvingBookmarkData_options_relativeTo_bookmarkDataIsStale_error_` + `startAccessingSecurityScopedResource`) or a tiny compiled shim. This is the "security-scoped-bookmark plumbing" the #3340 HOLD note names, and it is the single largest engineering item for Option A.
- Everything not user-chosen (app-support, logs, caches, `.api-key`, TLS material) lives in the app container, which the inheriting engine shares — no bookmarks needed there. `~/Library/Logs/Fichero/engine.log` will silently relocate to `~/Library/Containers/<bundle-id>/Data/Library/Logs/Fichero/` in a sandboxed build; docs/support flows that tell users where the log lives need updating. *(Inference from standard container path mapping.)*

## Option B: two apps (client-only MAS app + full DMG app)

**The repo is already most of the way to a client-only mode.** Verified in source: `EngineConfig.EngineProvisioningStrategy` has `configuredRemote` and `iosCompanion` cases that connect to an explicit/paired host and *never spawn*; the iOS build already IS the client-only app (`#else` branch: "iOS never runs a local engine"). Supporting UI exists: `Views/Components/BackendConnectionView.swift`, `Views/Settings/LibraryAccess/MacRemoteClientPairingSection.swift`, `Models/PairedHostEndpoints.swift`, `PairingCardView.swift` (QR pairing / Bonjour / tailscale-serve story). Option B's MAS app ≈ the macOS build with `releaseEmbedded` compiled out — engineering cost is genuinely low.

**1. Is a client-only MAS app acceptable to App Review?** Yes, as a category — with the 4.2 caveat below. This is category (b) precedent, not an Apple statement: **Sequel Ace** is a sandboxed MySQL/MariaDB client on the Mac App Store (https://apps.apple.com/us/app/sequel-ace/id1518036000) that is useless without a database server the user runs themselves (locally or remotely) — architecturally identical to Fichero-as-client. **Plex** ships its client on Apple's stores while the media server is downloaded from plex.tv (https://apps.apple.com/us/app/plex-watch-live-tv-and-movies/id383457673). And Guideline 4.2.7 (remote-desktop clients to a "user-owned host device") shows Apple explicitly contemplates client-to-user's-own-machine apps, albeit in an iOS streaming context.

**2. Entitlements the client needs:** `com.apple.security.app-sandbox`, `com.apple.security.network.client` (outbound to the engine — loopback, LAN, or Tailscale), and the file-access keys only if the client itself still opens local files (drag-in import → `files.user-selected.read-write`; persistent recents → `files.bookmarks.app-scope`). `network.server` is **not** needed unless the client listens (check whether the pairing flow ever opens a listening socket — Bonjour *browsing* is outbound; Bonjour *advertising* would need server). Connecting to LAN peers (not loopback) triggers macOS 15+ **Local Network privacy** — needs an `NSLocalNetworkUsageDescription`-style disclosure and the user prompt, not an entitlement.

**3. Guideline 4.2 / 4.2.3 — Option B's main rejection risk.** Quoted verbatim:

> **4.2** "Your app should include features, content, and UI that elevate it beyond a repackaged website. If your app is not particularly useful, unique, or 'app-like,' it doesn't belong on the App Store. …"

> **4.2.3(i)** "Your app should work on its own without requiring installation of another app to function."

Honest read: a Fichero client that shows only a "connect to your engine" screen on first launch, with the engine obtainable *only* from GitHub, sits close to 4.2.3(i). Mitigating factors, honestly weighed: (a) precedent — DB clients, SSH clients, MQTT clients, VNC clients all "require" a separately-obtained server and are approved routinely; reviewers treat *servers* differently from *companion apps*; (b) the wording is "another app" — a network service (possibly on another machine) is not obviously "another app" on the reviewing device; (c) the client is not a thin wrapper — it has substantial native UI. Risk is real but moderate; it can be reduced by shipping a built-in demo library / read-only sample mode so the app demonstrably "works on its own", and by review notes explaining the self-hosted-server model. Note also 4.2.7(e) "Thin clients for cloud-based apps are not appropriate for the App Store" — Fichero-client is a rich native client to the user's OWN server, which is the distinguishing argument to make in review notes. *(All weighting here is inference; the quoted text is Apple's.)*

**4. Prior art:** Sequel Ace (verified on MAS, sandboxed, needs user-run server), Plex client (verified on App Store; server off-store), plus the general class of DB/SSH/remote-admin clients. I did not find a documented *rejection* of a Mac client app for requiring a self-hosted server.

**Option B costs (product, not review):** two SKUs to explain; MAS users get a confusing first-run unless a demo mode ships; the "one Mac, one app" user must install the DMG build anyway (at which point the MAS app is redundant); iCloud/App Store reviewers may still ask "what does this do without the server?" Every one of these is manageable, none is fatal.

## Risks ranked, with rejection-likelihood calls

Ranked by (probability × cost). "Rejection likelihood" = my judgment call, category (c), grounded in the cited material.

1. **Engineering risk, not rejection: CPython under an inherited sandbox may hit runtime walls.** Briefcase's engine + ~800 wheels has never been run sandboxed by this team (the #3340 HOLD note says exactly this). Failure modes to expect: file access outside the container (temp dirs, `~/.cache`, wheel-internal paths), multiprocessing semaphores, `ps`/`lsof` shell-outs, port pre-flight, anything touching other processes. **Likelihood of *some* breakage: high. This is the gating unknown for Option A** — a 1–2 day spike (sandbox the engine, run the test suite inside it) answers it cheaply. Not a review risk per se; a review risk only if worked around with sandbox escapes.
2. **Security-scoped-bookmark plumbing to the engine is mandatory and non-trivial** (dynamic rights don't inherit — Apple-documented). Without it the engine cannot open the user's library folder at all. Engineering: medium (PyObjC or shim in the engine + handoff protocol). Rejection likelihood if done right: low; if skipped via `files.all`-style temporary-exception entitlements: **high** (temporary exceptions are heavily scrutinized and routinely rejected — category (b)).
3. **Nested `Fichero Engine.app` under `Contents/Resources`** violates nested-code placement rules (TN2206); MAS ingestion validation is stricter than notarization. Likelihood of ITMS validation failure: medium-high; fix cost: low (move to `Contents/Helpers` or `Contents/Library`, adjust the path in `EmbeddedBackendService`). *(Category (b) + inference.)*
4. **Orphan-sweep / port-conflict machinery** (`pgrep`/`ps -E`/`lsof`/`kill` of non-children) will degrade or fail under sandbox; if App Review notices process-poking behavior it also reads badly against 2.4.5. Likelihood it *breaks functionally*: high; rejection likelihood: low. Fix: MAS build trusts its own `Process` handle only; port-in-use → in-window error + Retry (UI already exists, #3111).
5. **Reviewer misreads 2.5.2 against the bundled interpreter.** The guideline text and precedent (Briefcase's supported MAS path, Pythonista/Pyto, Electron apps) are on Fichero's side, provided **zero runtime code download**. Rejection likelihood: low, and appealable. **BUT** audit the workflow/preset system: if workflows (or AI-generated actions) can introduce *executable* behavior fetched from outside the bundle, that flips to high. Also ensure the engine never pip-installs or downloads models that are code (downloading *data*/ML weights is fine under 4.2.3(ii) with disclosure).
6. **Sparkle remnants in the MAS bundle** (framework, `Autoupdate`, XPC services) → 2.4.5(vii) rejection or ingestion error. Likelihood if the separate-target compile-out is done: near zero; if only source-gated but still linked: high. Fix cost: low (target split; source is already `#if canImport`-gated).
7. **`cs.*` hardened-runtime exception entitlements in the MAS engine signature** (esp. `disable-library-validation`, `allow-dyld-environment-variables`). Unclear if MAS ingestion accepts them or whether they're even needed without hardened runtime. Likelihood of friction: medium; unresolved (Open Questions #2).
8. **Remote-access / Bonjour / tailscale-serve hosting features in a MAS build**: hosting a LAN-visible server from a sandboxed app is entitlement-compatible (`network.server`) but adds Local Network privacy prompts and review questions about account/invite flows (2.4.5(iii) background behavior, 4.8 login rules if accounts ship). Consider compiling hosting OFF in the MAS SKU initially. Rejection likelihood if shipped: low-medium; if deferred: zero.
9. **Option B-specific: 4.2.3(i) minimum functionality** — see Option B section. Rejection likelihood: moderate, mitigable with demo content + review notes.

## Open questions

1. **Empirical: does the Briefcase engine actually run under `app-sandbox`+`inherit`?** Nobody has tried (per #3340 HOLD). Highest-value next step; everything else in Option A is contingent on it.
2. **Are hardened-runtime `cs.*` entitlements needed/permitted in a MAS build?** MAS apps are re-signed by Apple at distribution; how library validation and W^X apply to the bundled CPython + unsigned-wheel dylibs in that trust path is something I could not find current Apple documentation for. (Widely reported that MAS ingestion re-signs nested code, which would moot `disable-library-validation`, but I could not verify with an Apple source.)
3. **Does MAS ingestion accept an executable nested `.app` under `Contents/Resources`,** or must it move? I found the TN2206 placement rule but no current Apple page stating ingestion-validation behavior for this exact layout.
4. **`ps -E` / `pgrep` / `lsof` behavior under App Sandbox** — I did not find explicit Apple documentation of process-info restrictions; my "will likely break" call is inference. Needs the same empirical spike as #1.
5. **Does the QR-pairing flow ever open a listening socket on the client?** Determines whether Option B's client needs `network.server`.
6. **Workflow system audit**: can any user-authored or downloaded workflow introduce executable code into the engine? If yes, 2.5.2 exposure exists in *both* options' server, but only the MAS SKU is reviewed against it.
7. **Apple's modern JS-rendered docs** ("Embedding a command-line tool in a sandboxed app", "Accessing files from the macOS App Sandbox") could not be fetched by tooling; quotes above come from the archived Entitlement Key Reference and Apple DTS forum posts. Wording should be re-checked against the live pages in a browser before implementation.

## Sources

**Apple (fetched and read):**
- App Store Review Guidelines (2.5.1, 2.5.2, 2.5.3, 2.4.5 i–ix, 4.2, 4.2.3, 4.2.7): https://developer.apple.com/app-store/review/guidelines/
- Entitlement Key Reference — Enabling App Sandbox (inherit, network.client/server, bookmarks, user-selected): https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html
- Apple DTS (Quinn) — how child processes are sandboxed: https://developer.apple.com/forums/thread/123873
- Apple DTS (Quinn) — sandboxed app + helper process + sockets/loopback: https://developer.apple.com/forums/thread/763498
- Apple doc pointer (title verified, body JS-blocked): Embedding a command-line tool in a sandboxed app: https://developer.apple.com/documentation/xcode/embedding-a-helper-tool-in-a-sandboxed-app

**Third-party (read via search results / fetch):**
- Briefcase macOS platform docs (App Store distribution, entitlements in pyproject.toml): https://briefcase.beeware.org/en/latest/reference/platforms/macOS/index.html
- Sparkle documentation (sandboxing guide, XPC services): https://sparkle-project.org/documentation/
- SwiftLee — Sparkle: distributing apps in- and out of the Mac App Store (separate-target pattern): https://www.avanderlee.com/xcode/sparkle-distribution-apps-in-and-out-of-the-mac-app-store/
- Sequel Ace on the Mac App Store (client-to-user-run-server precedent; sandbox socket workaround): https://apps.apple.com/us/app/sequel-ace/id1518036000 and https://sequel-ace.com/get-started/local-connection.html
- Plex client on the App Store (server distributed off-store): https://apps.apple.com/us/app/plex-watch-live-tv-and-movies/id383457673
- Pythonista 3 on the App Store (bundled Python interpreter precedent): https://apps.apple.com/us/app/pythonista-3/id1085978097
- Timac — Mac App Store: embedding a command-line tool: https://blog.timac.org/2021/0516-mac-app-store-embedding-a-command-line-tool-using-paths-as-arguments/

**Repo files read (2026-07-13, `~/code/fichero`):**
- `fichero/fichero/FicheroAppStore.entitlements`, `FicheroRelease.entitlements`, `FicheroEngine.entitlements`, `Fichero.entitlements`
- `fichero/fichero/Services/EmbeddedBackendService.swift` (full)
- `fichero/fichero/App/SparkleUpdater.swift`, `FicheroApp.swift` (Sparkle sites, via grep)
- `fichero/fichero-api-client/Sources/FicheroAPIClient/AuthTokenMiddleware.swift` (token path)
- Existence checks: `Views/Components/BackendConnectionView.swift`, `Views/Settings/LibraryAccess/MacRemoteClientPairingSection.swift`, `Models/PairedHostEndpoints.swift`
