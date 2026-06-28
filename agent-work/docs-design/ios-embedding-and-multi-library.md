# iOS/iPad Embedding & Multi-Library — Feasibility + Architecture

Status: **research / proposal** (read-only investigation, no product code changed).
Milestone: *iOS/iPad Embedding & Multi-Library*. Base branch: `0.0.2`.
Author: planning worker, 2026-06-23.

This document answers two coupled questions and stages the work. Every claim is
grounded in a cited file/symbol or in the dependency manifest. **Wheel-availability
claims for binary packages are unverified** (they are reasoned from each package's
build nature) and are flagged `NEEDS BUILD TEST` where a real `briefcase create iOS`
attempt is the only way to know. Treat those as hypotheses, not facts.

---

## TL;DR

- **Part A — embedding on iOS is gated by a handful of *native* (C/C++/Rust)
  wheels, not by the app code.** The pure-Python AI stack (langchain / langgraph /
  litellm / fastapi / pydantic-ish) is fine. The blockers are the binary
  dependencies — and the **single biggest one is `lancedb` / `pylance` (Rust)**:
  it is *core* (the vector-search substrate, so it can't be gated off) and has no
  published iOS wheel. `torch` (pulled only by `pykeen`) is the biggest *gateable*
  blocker — `pykeen` is used in exactly 3 source files and is trivially excluded.
  `opencv` is already effectively mac-only and is used in only 2 files.
- **Part B — multi-library is largely already built and is doable.** The macOS app
  is already genuinely multi-library (`LibraryManager.openLibraries: [LibraryReference]`),
  the engine already serves N libraries via a per-request library-path header plus a
  known-libraries registry, and iOS already connects to a Mac engine over paired
  TLS. The **gap** is two-fold: (1) every `LibraryReference` is hardwired to the
  single global `EngineConfig.host`, so it can't hold a *per-library* host; and (2) on
  iOS the paired remote library is adopted *into* the global slot (it **replaces**
  the local library instead of sitting **alongside** it). Closing those two gaps is
  the bulk of the work, and Part B's "own local library" leg depends on Part A.

---

# PART A — Embedding the engine on iPad/iPhone

## A.1 How the engine is bundled today

The engine is a Briefcase app defined in `fichero-engine/pyproject.toml`:

- `[tool.briefcase.app.engine]` (lines 37–97) — `console_app = true` (headless
  FastAPI), `sources = ["src/fichero", "src/engine"]`, and a `requires = [...]`
  list that is the **bundled** dependency set.
- `[tool.briefcase.app.engine.macOS]` (lines 99–114) — `universal_build = false`
  (arm64-only), `min_os_version = "15.0"`, `python_version = "3.12"`, plus a
  **macOS-only `requires` block** (lines 110–114) that adds the PyObjC Vision /
  Quartz / Cocoa frameworks for the Apple Vision OCR path.
- There is **no `[tool.briefcase.app.engine.iOS]` section today** (verified: a
  search for `briefcase.app.engine.iOS` returns nothing). So iOS embedding has
  never been attempted.

The macOS-only `requires` block (lines 110–114) is the **existing precedent for a
per-platform manifest** — Briefcase already merges a platform-specific `requires`
on top of the base list. The proposed iOS mechanism (A.4) is exactly this pattern,
inverted to *subtract*.

A second precedent worth noting: the base `requires` block is **already a curated
subset** of `[project].dependencies`. `rdflib`, `spacy`, and `splink` appear in
`[project].dependencies` (lines 192–194) but are **deliberately absent** from the
Briefcase `requires` (lines 47–97). So the codebase already ships a slimmer bundle
than the dev install, and the code that imports those packages
(`kg/triples.py` → rdflib, `kg/spacy_ner.py` → spacy) must already tolerate their
absence in the bundle via lazy/guarded import. That guard pattern is the same one
iOS gating (A.3) will lean on.

The embed lifecycle on macOS lives in
`fichero/fichero/Services/EmbeddedBackendService.swift`: `launchEmbeddedBackend()`
(line 208, wrapped in `#if os(macOS)`) spawns the nested
`Fichero Engine.app/Contents/MacOS/Fichero Engine` as a child process. The
**non-macOS branch of `start()` (lines 136–140) already hard-fails** with
"No remote engine host configured" — i.e. iOS deliberately has no local engine
today and is a thin client. Embedding on iOS means giving that branch a real
local engine to launch (or, on iOS, to load in-process — see A.5).

## A.2 Per-dependency audit

Legend — **iOS wheel?**: `pure` = pure-Python (works anywhere a Python runtime
runs); `BeeWare` = a binary package BeeWare/`mobile-forge` is known to support;
`build` = native, no published iOS wheel, would need a custom iOS arm64 build;
`none` = native with no realistic iOS story today. All non-`pure` rows are
`NEEDS BUILD TEST`.

| Dep | iOS wheel? | mac-only? | Used by (cited) | Removable / bloat | Verdict |
|---|---|---|---|---|---|
| `fastapi` | pure | no | API core | keep | ✅ ship |
| `uvicorn[standard]` | pure (but `[standard]` pulls `uvloop`/`httptools`, native) | no | server entrypoint | trim `[standard]` → plain `uvicorn` on iOS | ✅ ship, drop uvloop |
| `websockets<14` | pure (optional C ext) | no | uvicorn ws | keep | ✅ ship |
| `python-multipart`, `python-dotenv`, `aiofiles` | pure | no | API/uploads/config | keep | ✅ ship |
| `aiohttp` | build (C accelerators, pure fallback exists) | no | provider/HTTP calls | keep | ⚠️ build test; pure fallback likely OK |
| `httpx` | pure | no | HTTP client | keep | ✅ ship |
| `defusedxml` | pure | no | XML hardening | keep | ✅ ship |
| `cryptography` | BeeWare (Rust+OpenSSL; BeeWare supports it) | no | TLS, pairing, tokens | keep (core) | ⚠️ build test, expected OK |
| `zeroconf` | pure | no | Bonjour advertise/discover | keep on Mac; iOS uses NWBrowser anyway | ✅ ship (or drop on iOS) |
| `pydantic`, `pydantic-settings` | build (`pydantic-core` is Rust; BeeWare has built it) | no | **every model** (god-node) | keep (core) | ⚠️ build test, expected OK |
| `duckdb` | build (C++; compiles for iOS, no PyPI iOS wheel) | no | **library DB** (god-node `Database`) | keep (core) | ⚠️ build test — core, must succeed |
| `lancedb` + `pylance`(`lance`) | none/build (Rust + heavy deps; no iOS wheel) | no | vector + FTS search (`db_embeddings.py`, `api/main.py`) | keep (core) | 🔴 **biggest blocker** — core & hardest |
| `langchain*` (core, openai, anthropic, google-genai, aws, cohere, mistralai, openrouter, community, ollama, mcp-adapters) | pure | no | workflows / LLM routing | keep | ✅ ship |
| `mcp` | pure | no | MCP tool adapters | keep | ✅ ship |
| `langgraph` | pure | no | workflow graph engine | keep (core) | ✅ ship |
| `litellm` | pure (heavy dep tree) | no | provider routing | keep | ✅ ship |
| `apscheduler` | pure | no | scheduled jobs | keep (or disable on iOS) | ✅ ship |
| `watchdog` | build (FSEvents/inotify C; polling fallback) | no | folder watch | iOS bg-fs is sandboxed → likely disable | ⚠️ gate/disable on iOS |
| `kreuzberg` | build (text-extraction; pulls native sub-deps) | no | document text extraction | keep if buildable, else server-side | ⚠️ build test |
| `fastembed` | none/build (`onnxruntime` + Rust `tokenizers`; desktop onnxruntime wheel) | no | default local embeddings (`local_models.py`, `db_embeddings.py`, `api/main.py`) | gateable — embeddings can be remote | 🔴 high-risk; gate or do embeddings remotely on iOS |
| `pykeen` | none (depends on `torch`; no iOS torch wheel) | effectively yes | KG link prediction (`kg/pykeen_predictor.py`, `pykeen_inference.py`, `api/routes/kg_predictions.py`) | **gate off** — 3 files only | 🔴 biggest *gateable* blocker — exclude on iOS |
| `torch` (transitive via pykeen) | none (no iOS Python wheel; only C++ LibTorch/ExecuTorch) | effectively yes | only via pykeen (`torch` refs: kg_predictions, pykeen_predictor, pykeen_inference) | drop with pykeen | 🔴 exclude on iOS |
| `PyMuPDF` | build (MuPDF compiles for iOS; no PyPI iOS wheel) | no | PDF render/extract | keep if buildable | ⚠️ build test |
| `Pillow>=12.2.0` | BeeWare (supported binary package) | no | image handling | keep | ⚠️ build test, expected OK |
| `opencv-python-headless` | none (huge C++; no iOS wheel) | effectively yes | `api/routes/image_editing.py`, `workflows/tools/remove_background_images.py` (2 files) | **gate off** | 🔴 exclude on iOS — mac-only |
| `rdflib` | pure (already NOT in bundle) | n/a | `kg/triples.py` | already excluded from bundle | ✅ ship if wanted |
| `spacy` | build (cython + models; NOT in bundle) | n/a | `kg/spacy_ner.py` | already excluded from bundle | ⚠️ keep excluded on iOS |
| `splink` | pure-ish (heavy; NOT in bundle) | n/a | record linkage | already excluded | ⚠️ keep excluded |
| `mlx` | n/a | n/a | **0 references in code** — not a dependency | already absent | ✅ confirmed not needed (matches Daniel) |
| PyObjC Vision/Quartz/Cocoa | macOS-only (already in `engine.macOS.requires`) | **yes** | Apple Vision OCR path | mac-only by design | ✅ stays mac-only; iOS has its own Vision via Swift |

Notes:
- **`mlx` is not in the dependency tree at all** (`find_references mlx` → 0). Daniel's
  "MLX-embedded not needed on iOS" is already the status quo; nothing to exclude.
- **`opencv` and `pykeen`/`torch` are already isolated** to a tiny number of files,
  so gating them is cheap (A.3).
- The pure-Python AI core (`langchain*`, `langgraph`, `litellm`, `mcp`) is the bulk
  of the "intelligence" and ships cleanly. The risk is entirely in the storage /
  embeddings / vision binaries.

## A.3 Code gating — what mac-only code needs guarding

The native deps that must be excluded on iOS are reached from a small, enumerable
set of modules. Each needs a runtime/import guard so the engine boots without them:

- **opencv** (`cv2`): `api/routes/image_editing.py`,
  `workflows/tools/remove_background_images.py`. Guard: lazy-import `cv2` inside the
  handler and return a 501/feature-unavailable when absent; do not import at module
  top. (Swift side already has the `#if os(macOS)` + `EngineConfig.engineIsLocal`
  machinery to hide local-only affordances — `EngineConfig.engineIsLocal`,
  `EngineConfig.swift:179`.)
- **pykeen / torch**: `kg/pykeen_predictor.py`, `pykeen_inference.py`,
  `api/routes/kg_predictions.py`. Guard: lazy-import; the KG-prediction route
  reports "unavailable on this engine" when torch is missing. This mirrors the
  existing precedent where `rdflib`/`spacy` are absent from the bundle yet their
  modules (`kg/triples.py`, `kg/spacy_ner.py`) exist — the same lazy-import
  discipline applies.
- **fastembed**: `local_models.py`, `db_embeddings.py`, `api/main.py`. This is the
  default *local* embedding provider, so gating it changes behaviour: on iOS,
  embeddings must come from a remote provider (litellm) or be deferred to the paired
  Mac. Decision needed (see A.5 "Embeddings on iOS").

This relates directly to the existing platform-shim issues **#2097 (platform shims)**
and **#2098 (macOS-gating)** — the Python side needs the same conditional-capability
discipline the Swift side already has via `#if os(macOS)` and `EngineConfig.engineIsLocal`.

## A.4 KEY ASK — a programmatic per-platform inclusion manifest

Briefcase already supports this; we just have not used it for iOS. Two layers:

**1. Build-time (which wheels ship).** Add an `[tool.briefcase.app.engine.iOS]`
section mirroring the existing `[tool.briefcase.app.engine.macOS]` one, but with its
**own slimmer `requires`**. Briefcase merges platform `requires` onto the base list;
to *exclude* a base dep cleanly, the most maintainable shape is to invert the
manifest: move the optional native deps out of the base `requires` into
platform-specific blocks, leaving the base list as the minimal cross-platform core.

Proposed shape:

```toml
[tool.briefcase.app.engine]
requires = [ ...minimal cross-platform CORE only:
  fastapi, uvicorn, websockets<14, python-multipart, python-dotenv,
  aiofiles, httpx, defusedxml, cryptography, pydantic, pydantic-settings,
  duckdb, lancedb, pylance,
  langchain*, langgraph, litellm, mcp, apscheduler, PyMuPDF, Pillow ]

[tool.briefcase.app.engine.macOS]
requires = [ pyobjc-framework-Vision, pyobjc-framework-Quartz, pyobjc-framework-Cocoa,
  opencv-python-headless, pykeen, fastembed, kreuzberg, watchdog, aiohttp, zeroconf ]

[tool.briefcase.app.engine.iOS]
requires = [ fastembed-or-omit, ...only what builds for iOS ]
```

**2. Run-time (which features turn on).** Introduce a single
`engine/capabilities.py` feature-matrix that the engine consults at startup and
exposes over an endpoint (e.g. extend `/api/health` or add `/api/capabilities`).
It declares, per capability, whether the optional module imported successfully:

```
capabilities = {
  "vision_ocr":      _can_import("Vision"),       # mac PyObjC
  "image_editing":   _can_import("cv2"),          # opencv
  "kg_link_predict": _can_import("torch"),        # pykeen/torch
  "local_embeddings":_can_import("fastembed"),
  ...
}
```

Routes that need an optional capability check the matrix and 501 cleanly; the Swift
client reads `/api/capabilities` and hides the corresponding affordances (it already
hides local-only UI via `EngineConfig.engineIsLocal`). This is the programmatic,
declared inclusion mechanism Daniel asked for: **one place declares what's included
per platform at build time, one place declares what's active at run time, and both
the bundle and the UI follow it.** It also makes the *remote* case fall out for free
— a thin iOS client talking to a full Mac engine simply reads the Mac's richer
capability matrix.

## A.5 Recommended path to a minimal iOS-embeddable engine

Two embedding strategies for iOS exist; they are not exclusive:

- **In-process Python (BeeWare/`Python-Apple-support`).** iOS forbids spawning child
  processes, so the macOS `Process()`-spawn model in `EmbeddedBackendService`
  (line 208, `#if os(macOS)`) **cannot** be reused. On iOS the engine must run
  **in-process** via an embedded CPython (the BeeWare iOS runtime), with the FastAPI
  app served on `127.0.0.1` inside the app, or called in-process without a socket.
  This is the largest *new* piece of engineering and is the real "embedding" work.
- **Defer hard features to the paired Mac.** Anything that won't build for iOS
  (KG link-prediction, opencv image editing, possibly local embeddings / heavy OCR)
  routes to a connected Mac engine when one is paired (Part B makes this natural —
  the iOS device can hold *both* its own local library and a remote Mac library).

Recommended staging:

1. **Prove the core builds.** `briefcase create iOS` against the minimal core list
   (duckdb, lancedb/pylance, pydantic, cryptography, Pillow, PyMuPDF + the pure
   stack). This single experiment resolves most `NEEDS BUILD TEST` rows. Expect
   `lancedb` and `fastembed` to be the failures.
2. **Gate the optional natives** (opencv, pykeen/torch, fastembed) behind lazy
   imports + the capability matrix (A.3/A.4) so the engine boots without them.
3. **Resolve the vector-store blocker** (lancedb): either (a) get a Rust iOS build of
   `lance`, or (b) ship a degraded iOS mode where vector/FTS search is delegated to a
   paired Mac and duckdb alone backs the local library, or (c) evaluate a
   pure/embeddable vector index for the on-device library.
4. **Decide embeddings-on-iOS**: remote provider via litellm, or delegate to Mac.
5. **In-process serving**: stand up the FastAPI app inside the iOS app process and
   point the existing `LibraryReference` machinery at it (Part B).

**Single biggest blocker: `lancedb`/`pylance` (Rust vector+FTS store).** It is core
(can't be gated off without losing search), Rust-native with a heavy dependency tree,
and has no published iOS wheel. `torch`-via-`pykeen` is the biggest *gateable*
blocker but is trivially excluded (3 files). If lancedb cannot be built for iOS, the
fallback is a duckdb-only on-device library with search delegated to a paired Mac —
which Part B's architecture supports directly.

---

# PART B — Multi-library architecture (own + shared, cross-device)

## B.1 What exists today

**The app is already multi-library on macOS.**
`fichero/fichero/Models/LibraryManager.swift`:

- `LibraryManager.openLibraries: [LibraryReference]` (line 17) — an **array** of open
  libraries, "Global is always last" — so the multi-library container already exists.
- `LibraryManager.globalLibraryId` (line 14) — a fixed UUID for the always-present
  "Local/Global" library, created on init via `loadGlobalLibrary()` (line 307), stored
  at `~/Library/Application Support/Fichero/global.fichero`.
- `LibraryReference` (line 54) is a full per-library service bundle: its own
  `apiClient`, `ficheroClient`, and ~25 domain stores, **one set per library, shared
  across that library's windows** (the comment at line 51–52). Each library has its
  own SSE `changeStream` (line 182).

**The engine already serves N libraries.** Library selection is **per-request**, by
path, not global engine state:

- `LibraryReference.init` sets `apiClient.currentLibraryPath = url.path` (line 237)
  and constructs `FicheroClient(baseURL: EngineConfig.host, libraryPath: url.path)`
  (line 240). The library path travels as a request header
  (`APIClient.swift` has registry-endpoint handling at line 121).
- The engine has a **known-libraries registry**:
  `api/routes/library_registry.py` — `list_known_libraries`, `add_known_library`,
  `update_library_access`, `remove_known_library`, backed by the global DB
  (`get_global_database`, line 37) and the `known_libraries` table
  (`db_migrations.py::migrate_known_libraries_table`, line 409). The Swift side
  mirrors it with `KnownLibraryRegistryStore` (`FileMenuCommands.swift`) and
  `FicheroClient.list_known_libraries` / `remove_known_library`.

**iOS already connects to a Mac engine.** `FicheroApp_iOS.swift`:

- It is a **thin remote client**: no embedded engine (`EngineConfig.host` on non-macOS
  returns the paired remote host, never localhost — `EngineConfig.swift:89–96`,
  `#2465`). Startup requires `EngineConfig.hasConfiguredHost` and
  `RemoteAccessConfig.hasPairedLibraryPath` (lines 42, 63), else it shows
  `RemoteConnectionSetupView` (QR-pair with the Mac, line 230).
- Pairing is built: QR scan → `RemoteClientPairing.pairAndPersistHost(...)` with
  `remoteURL`, `pairCode`, `spkiPin`, `libraryPath` (lines 210–217); Bonjour discovery
  exists (`BonjourDiscoveryService`, line 706, browses `_fichero._tcp.`).
- After pairing, `libraryManager.adoptPairedRemoteLibrary()` runs.

**Why iOS can't see a Mac's libraries as *additional* today — the two real gaps:**

1. **`adoptPairedRemoteLibrary()`** (`LibraryManager+Helpers.swift`) inserts the
   paired remote library **into the `globalLibraryId` slot** — it does
   `openLibraries.removeAll { $0.id == globalLibraryId }` then inserts the remote at
   index 0. So the remote library **replaces** the local/global library rather than
   being **added alongside** it. iOS therefore has exactly one library (the Mac's),
   not "its own + the Mac's".
2. **Every `LibraryReference` is hardwired to the single global `EngineConfig.host`**
   (`LibraryManager.swift:240`, `FicheroClient(baseURL: EngineConfig.host, ...)`).
   There is no per-library host. So even though `openLibraries` is an array, all
   entries point at the *same* engine. A device cannot simultaneously hold a
   library on its *own* engine and a library on a *remote* engine, because the host
   is global, not per-`LibraryReference`.

These two are the entire architectural delta between "one device, one engine" and
"my device + connected remote libraries". Everything else (registry, per-request
library path, pairing, TLS pinning, Bonjour, per-library service bundles, multi-window
fan-out) already exists.

## B.2 Proposed model

Daniel's target: **every device always has its own internal library, AND can connect
to others' shared libraries.** Map onto what exists:

- The existing always-present `globalLibraryId` library becomes the device's **own
  local library**, served by the device's **own local engine** (Part A on iOS; the
  already-embedded engine on macOS).
- Each **remote** library is a *separate* `LibraryReference` whose host is a **paired
  remote engine's** base URL (over `tailscale serve` / paired TLS), carrying that
  remote's `libraryPath`. `openLibraries` becomes `[own-local] + [remote, remote, …]`.

The one required change to make `LibraryReference` carry mixed hosts: **give
`LibraryReference` a `host: URL` (or a `connection` value) instead of reading the
global `EngineConfig.host`.** The local library's host is the local engine; each
remote library's host is its paired engine. `reconfigureBackendHost()`
(`LibraryManager.swift:293`) already exists to re-point a library's client — it just
needs to take a per-library host rather than always `EngineConfig.host`.

## B.3 Is it architecturally doable? — Yes

The hard substrate is already there:

- **Transport:** engine binds loopback + `tailscale serve` for tailnet-private HTTPS
  (per the remote-access work / MEMORY "loopback + tailscale serve transport"); the
  Swift client pins the SPKI (`RemoteCertificatePinning`) and validates remote URLs
  (`validatedRemoteURL`, `EngineConfig.swift:399`).
- **Pairing & per-device tokens:** `PairingService` (`EngineConfig.swift:580`),
  `RemoteClientPairing.pairAndPersistHost`, `/api/pair` device-token exchange
  (`#2155+`), per-host token persistence (`AuthTokenMiddleware.persistRemoteToken`).
- **Per-library addressing:** the library-path header + known-libraries registry
  (B.1) already lets one engine expose many libraries and a client pick one per
  request.
- **Multi-user / ACL:** `fichero/authz.py` per-library/folder authz enforced at
  `registry.invoke` + read path behind `FICHERO_MULTIUSER`, actor attribution from
  session (`#2021/#2022/#2023/#2024`, MEMORY "ACL choke-point shipped"). A *shared*
  library on a Mac is exactly the multi-PERSON case those guards were built for.

**The gap** (B.1): per-library host on `LibraryReference`, and stop letting the remote
adoption clobber the local slot. Plus, on iOS, Part A must deliver a real local engine
for the "own library" leg (until then, iOS can still do "connect to a Mac's library",
which is what it does now).

## B.4 Proposed architecture

```
Device (mac / iPad / iPhone)
├── LibraryManager.openLibraries: [LibraryReference]
│   ├── [0] OWN LOCAL library  → host = local engine (loopback / in-process)
│   │                            libraryPath = <device>/global.fichero
│   ├── [1] REMOTE "Daniel's Mac — Archive"  → host = mac.tailnet:8765 (paired TLS)
│   │                                          libraryPath = /…/Archive.fichero
│   └── [n] REMOTE …            → host = other paired engine, its libraryPath
│
├── per LibraryReference: own apiClient/ficheroClient(host, libraryPath),
│   own ~25 domain stores, own SSE changeStream  (already true today)
│
└── Library picker/switcher: choose active library; sets currentLibraryId
    (already exists: currentLibraryId, LibraryWorkspaceSelection.activeLibrary)
```

- A **library picker/switcher** drives `currentLibraryId`
  (`LibraryManager.swift:20`); the active-library resolution already exists
  (`LibraryWorkspaceSelection.activeLibrary`, used in `FicheroApp_iOS.swift:96`).
- A **remote library** = a paired device's engine + a `libraryPath` it exposes. The
  known-libraries registry on each engine enumerates what that engine can serve; the
  client lists them via `list_known_libraries` and adds chosen ones as
  `LibraryReference`s with that engine's host.
- **Direction:** iOS↔Mac both ways is doable *once iOS embeds an engine* (Part A): a
  Mac could then connect to an iPad's served library identically. Until then it is
  one-directional (iOS connects to Mac).

## B.5 Hard parts (flagged)

- **A Mac engine must be running and serving** for its library to be reachable.
  Today the engine is a child of the app (`EmbeddedBackendService`), so it dies when
  the app quits. Sharing a library cross-device implies a **serve-even-when-app-closed**
  mode (a LaunchAgent / always-on engine), or accepting "reachable only while the host
  app is open". This is a product decision, not just code.
- **Per-library host plumbing**: threading a `host` through `LibraryReference` and the
  generated clients touches the god-ish `LibraryReference` init — do it as an additive
  parameter (default `EngineConfig.host`) to honour the "iterate, never replace" rule.
- **Auth per remote library**: tokens are per-host today
  (`AuthTokenMiddleware.persistRemoteToken(_, hostString:)`). N remote engines = N
  tokens; the token store must key by host (it already does) and the picker must
  surface "not paired / expired" per remote.
- **Discovery**: Bonjour works on-LAN (`BonjourDiscoveryService`); off-LAN relies on
  tailscale + a saved host. A unified "available libraries" list must merge
  local-registry + Bonjour + saved remotes.
- **Offline behaviour**: a remote library must degrade gracefully when its engine is
  unreachable (the local library keeps working). The existing `ConnectionBanner`
  (`Views/Library/ConnectionBanner.swift`) and the iOS `needsConnectionSetup` gate are
  the seams for per-library offline state.
- **iOS "own library" depends on Part A**: no embeddable engine ⇒ no own local
  library on iOS ⇒ iOS stays connect-only. This is the explicit Part A → Part B
  dependency.

## B.6 Staged plan

1. **Per-library host (foundational, macOS-only, no iOS needed).** Add an additive
   `host: URL = EngineConfig.host` to `LibraryReference`; route `ficheroClient`/
   `apiClient` through it; make `reconfigureBackendHost(_ host:)` per-library. Ship a
   library picker that can hold the local library + one remote library on macOS
   (connect a second Mac). This delivers cross-device shared libraries **without any
   iOS work** and de-risks the model.
2. **Stop clobbering the local slot on iOS.** Change `adoptPairedRemoteLibrary()` to
   **add** the remote as a *new* `LibraryReference` (new id) alongside whatever local
   library exists, instead of replacing the `globalLibraryId` slot. On iOS pre-Part-A
   there is no local engine yet, so the remote can stay the primary — but it should no
   longer be hardwired to *the* global id.
3. **Multi-remote.** Let the picker add N remote libraries (N paired engines), each
   its own `LibraryReference`. Surface per-remote pairing/expiry/offline state.
4. **iOS own library (depends on Part A).** Once the iOS engine embeds (A.5), create
   the device's own local library on the in-process engine and make it `openLibraries[0]`.
5. **Bidirectional + visionOS/tvOS.** With an embeddable engine on more platforms,
   any device can both serve its own library and connect to others.

---

## Appendix — primary sources

- `fichero-engine/pyproject.toml` — Briefcase app + base/macOS `requires`, `[project].dependencies`.
- `fichero/fichero/Services/EmbeddedBackendService.swift` — macOS engine spawn (`#if os(macOS)`), iOS hard-fail branch.
- `fichero/fichero/Services/EngineConfig.swift` — host resolution, iOS = remote-only, pairing types, remote-URL validation.
- `fichero/fichero/FicheroApp_iOS.swift` — iOS thin-client app, QR pairing, `adoptPairedRemoteLibrary` wiring, Bonjour.
- `fichero/fichero/Models/LibraryManager.swift` — `openLibraries`, `LibraryReference`, global library, per-library service bundle.
- `fichero/fichero/Models/LibraryManager+Helpers.swift` — `adoptPairedRemoteLibrary()` (replaces global slot — the gap).
- `fichero-engine/src/fichero/api/routes/library_registry.py` — known-libraries registry CRUD.
- `fichero-engine/src/fichero/db_migrations.py::migrate_known_libraries_table` — registry table.
- opencv usage: `api/routes/image_editing.py`, `workflows/tools/remove_background_images.py`.
- pykeen/torch usage: `kg/pykeen_predictor.py`, `pykeen_inference.py`, `api/routes/kg_predictions.py`.
- fastembed usage: `local_models.py`, `db_embeddings.py`, `api/main.py`.
</content>
