# iOS/iPad Engine Embed — Re-Review (2026-07-13)

Status: COMPLETE. Re-review of the Fabel decision (#3275 review → #3278 decision: ADOPT
Substrate C thin client, PARK Substrate B in-process CPython behind spike #3291) in light of
PEP 730 / official CPython iOS support. Researcher agent; research only, no source modified.

Evidence classes used throughout: **(a)** documented (Apple/PSF/upstream docs, read today),
**(b)** reported developer experience, **(c)** researcher inference. Every per-package wheel claim
below was verified against the package's live PyPI files listing on **2026-07-13** unless marked
otherwise.

Access limitation, stated up front: this session had no `gh` access and the repo is private, so
issues #3275, #3278, #3291, #2865, #2579, #2584, #2663, #2620, #1093 could not be read directly.
Their content is taken from the task brief's summary plus the local design doc
`docs/contributor/design/ios-ipad-embedding-plan.md` (2026-07-06) and the shipping code
(`EngineConfig.swift` `iosCompanion`, verified in source today). Flagged again in Open Questions.

---

## VERDICT UP FRONT

**Is in-process CPython on iOS (Substrate B) viable today? NO — not for Fichero's engine.**
More precisely: **YES for the interpreter, NO for the stack.** PEP 730 makes embedding CPython
inside an iOS app process officially supported (Tier 3, Python 3.13+), and Apple's App Store rules
do not prohibit it. But Fichero's engine cannot be *installed* on that interpreter: as of today
**`pydantic-core` (the foundation of FastAPI/pydantic v2), `duckdb` (the library store),
`cryptography`, `PyMuPDF`, `onnxruntime`, `pylance`/`pyarrow` (LanceDB), `tiktoken`, `jiter`,
`tokenizers`, and `ormsgpack` all lack iOS wheels** (each verified on PyPI today). The minimal
"engine-slim" core — FastAPI + pydantic v2 + DuckDB — cannot even import, let alone the AI lane.

**Does the prior decision (#3278, Substrate C) still stand? YES — CONFIRM IT.** The prior review's
headline objection ("iOS has no subprocess API") was aimed at the subprocess architecture and is
irrelevant to in-process embedding, but its *dependency* objection was and remains decisive — and it
is broader than the three packages (#3275 called `lancedb`/`onnxruntime`/`mlx` RED): the wall now
verifiably includes the web framework's own compiled core and the database itself. PEP 730 changes
the *official-support* picture, not the *packaging* picture. Substrate C (thin remote client +
Swift-native local capability layer) also remains the architecturally better answer for reasons
independent of packaging (§Q4). **Keep #3291 parked**, with a sharper, cheaper re-open trigger
defined in the Recommendation.

---

## What changed since #3275 — and what did not

**Changed (or under-weighted at review time):**

1. **In-process CPython on iOS is officially supported.** PEP 730 (Final) landed in Python 3.13
   (Oct 2024), Tier 3, ABIs `arm64-apple-ios` / `arm64-apple-ios-simulator`; the official docs at
   https://docs.python.org/3/using/ios.html treat iOS as a first-class embedded-only platform. (a)
   So "no subprocess API" kills only Substrate A. Substrate B is not blocked *at the interpreter
   level*.
2. **CPython upstream actively engineers for App Store review.** CPython ships an
   `app-store-compliance.patch` applied automatically to iOS builds (removing stdlib code that trips
   Apple's automated review) and documents the 2025 privacy-manifest requirement. (a) Policy risk on
   iOS is therefore *lower* than the prior review may have assumed.
3. **mobile-forge is dead.** As of ~Aug 2025 BeeWare stopped developing mobile-forge: no new
   recipes, no version bumps, no Python 3.14+ recipes; the sanctioned path for missing binary wheels
   is now `cibuildwheel --platform=ios` run by *each upstream project* (or by you, locally). (a,
   https://github.com/beeware/mobile-forge README + https://beeware.org/mobile-wheels/). **This
   invalidates the premise of #2579** ("build missing iOS wheels via Briefcase mobile-forge") as
   written — the tool it names is frozen pre-3.13. The replacement path exists but shifts the burden
   to per-package cross-compilation that someone must maintain release-over-release.
4. **A real but small official-iOS-wheel ecosystem now exists.** Verified today: **Pillow 12.3.0**,
   **aiohttp 3.14.1**, **cffi 2.1.0** publish official `ios_13_0_arm64_iphoneos` wheels on PyPI. (a)
   The aio-libs C-accelerated deps (`multidict` etc.) publish pure-Python fallback wheels, so that
   family installs. The trend line is positive — the coverage is nowhere near Fichero's needs.

**NOT changed — the parts that decide the question:**

- **No subprocess, ever, on iOS**: `subprocess`, `os.fork()`, `os.spawn*()` raise; PEP 730 notes
  that if invoked, "the invoking iOS process stops, and the new process doesn't start."
  `multiprocessing` is likewise unavailable. (a) Substrate A stays dead; anything in the engine that
  shells out (fm-bridge, MLX venv provisioning, TLS material minting via self-exec) has no iOS
  analogue.
- **The data layer has no iOS wheels** — duckdb, pylance, pyarrow, onnxruntime: all still absent
  (verified today, table below). #3275's RED on `lancedb`/`onnxruntime`/`mlx` stands.
- **PyObjC is macOS-only**; the Apple Vision OCR path, security-scoped-bookmark LINK mode, fm-bridge
  and the MLX runtime remain macOS-shaped seams (per the local embedding plan doc, re-confirmed by
  `pyproject.toml`'s `[tool.briefcase.app.engine.macOS]` block). (a)
- **The thin client is not hypothetical** — `EngineConfig.EngineProvisioningStrategy.iosCompanion`
  is in shipping source with tests asserting "iOS never runs a local engine," and an iOS TestFlight
  release went out this cycle. Substrate C is the incumbent, not a proposal. (a, repo)

---

## Q1. Is in-process CPython on iOS officially supported today?

**Yes — officially, Tier 3, embedded-mode only.** All category (a):

- **PEP 730 (Final, Python 3.13)** — https://peps.python.org/pep-0730/ — iOS is a PEP 11 Tier-3
  platform; core-team contact Ned Deily; buildbot hardware from Anaconda. Tier 3 = best-effort:
  a failing iOS buildbot does not block a CPython release. Officially supported ≠ Tier-1 solid.
- **Embedded mode only** — https://docs.python.org/3/using/ios.html — iOS has no console, REPL, or
  python.exe; "Python must be used in embedded mode only," via `libPython` (framework build; static
  linking unsupported) and the embedding API, with documented mandatory `PyConfig` settings. This is
  exactly Substrate B's shape: CPython inside the app process, Swift calling in directly — no
  loopback HTTP server process, because there is no second process.
- **Documented restrictions**: no `subprocess`/`fork`/`spawn`/`multiprocessing` (raise on use); every
  binary extension module must be repackaged as a **standalone signed `.framework`** (one dylib per
  framework + `Info.plist`) in the app's `Frameworks/` folder, with the original `.so` replaced by a
  `.fwork` marker loaded through `importlib.machinery.AppleFrameworkLoader`; wheels use iOS platform
  tags (`ios_13_0_arm64_iphoneos`). `dlopen` of arbitrary unsigned dylibs is not part of the model —
  loadable code is embedded, signed frameworks. JIT: not documented as available on iOS; Apple does
  not permit writable+executable memory for App Store apps, so assume the CPython interpreter runs
  fine (it does not require a JIT) but nothing that needs executable-memory tricks does. (last
  sentence: c, inference from Apple's long-standing W^X policy; the CPython docs simply never offer
  JIT on iOS.)
- **Briefcase/BeeWare** supports iOS packaging end-to-end (Xcode project generation, framework
  conversion, `cleanup_paths` for App Store-offending files) —
  https://briefcase.beeware.org/en/latest/reference/platforms/iOS/xcode.html. Two package sources:
  PyPI (iOS-tagged or pure-Python wheels only — **"Briefcase cannot install packages published as
  source tarballs into an iOS app"**) and the legacy `anaconda.org/beeware` channel, which is frozen
  and incomplete. (a)

**Bottom line for Q1**: the *mechanism* the prior review said didn't exist (a supported way to run
the engine on iOS) does exist — in-process, not subprocess. Q3 is where it dies.

## Q2. App Store Guideline 2.5.2 on iOS

**Embedding a Python interpreter that runs bundled scripts does not violate 2.5.2 on iOS**, for the
same textual reason as the macOS finding in the sibling report
(`docs/superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md`, read today): 2.5.2 prohibits
code that is **downloaded/installed after review** or that changes the app from what was reviewed —
not a bundled, signed interpreter executing bundled, signed scripts. The iOS reasoning is the same
guideline text (one guidelines document covers all Apple platforms), and is actually **stronger**
on iOS:

- **CPython upstream ships an App Store compliance patch specifically for iOS builds** and documents
  privacy-manifest handling — the PSF explicitly engineers for App Store distribution. (a,
  https://docs.python.org/3/using/ios.html)
- **PEP 730's framework-packaging design exists *because of* App Store rules** ("The iOS App Store
  requires that all binary modules… be dynamic libraries, contained in a framework with appropriate
  metadata"). (a)
- **Precedent**: full Python interpreters have shipped on the iOS App Store for a decade
  (Pythonista 3 — https://apps.apple.com/us/app/pythonista-3/id1085978097 — and Pyto); BeeWare/Kivy
  apps are routinely approved. (b)

**Where iOS differs from the macOS analysis** — none of it rescues Substrate B, and one point cuts
against it:

1. **No escape hatch.** On macOS the DMG channel exists if App Review balks; on iOS the App Store
   (or TestFlight) is the only distribution path, so any 2.5.2 friction is fatal rather than
   annoying. (a)
2. **The macOS report's hard conditions get easier**: no Sparkle on iOS anyway; no nested-app
   placement question (frameworks, not a nested .app); no `pgrep`/`lsof` process-poking (impossible);
   no hardened-runtime `cs.*` entitlement questions (iOS signing model differs).
3. **The zero-runtime-code-download rule binds harder**: no pip at runtime, no venv provisioning —
   which independently kills the engine's MLX runtime path (`mlx_runtime.py` provisions a venv and
   installs `mlx-lm` dynamically; that is both mechanically impossible and policy-prohibited on
   iOS). (a + repo)
4. **2.4.5 (the macOS-specific chapter) doesn't apply on iOS** — the subprocess/update questions from
   the sibling report are moot here.

**Conclusion**: App Store policy is NOT the blocker for Substrate B on iOS. Packaging is.

## Q3. THE DEPENDENCY WALL — per-dependency table

Method: for each entry in `fichero-server/pyproject.toml` `[tool.briefcase.app.engine].requires`
(read today) plus load-bearing transitive deps, the live PyPI "Download files" page was checked for
`ios_*` wheel tags on **2026-07-13**. "❌ none" = latest release publishes no iOS wheels. Note
Briefcase cannot fall back to sdists on iOS, so ❌ + no pure wheel = uninstallable without
self-built wheels.

| Dependency | Role | iOS status today | Evidence | Workaround |
|---|---|---|---|---|
| `fastapi`, `starlette` | API framework | 🟢 pure Python | (c) pure per upstream packaging; no compiled core | n/a — but see pydantic-core |
| `pydantic` v2 → **`pydantic-core`** | ALL models/validation | **❌ none** (2.47.0: win/mac/linux/wasm only) | PyPI files page (a) | Self-build via maturin/cibuildwheel (Rust cross-compiles to iOS); recurring maintenance forever. **Blocks the entire FastAPI stack as shipped.** |
| **`duckdb`** | **the library store** | **❌ none** (1.5.4). Nuance: DuckDB's *C++ engine* advertises iOS ("runs on Linux, macOS, Windows, Android, iOS") and an official `duckdb/duckdb-swift` SPM package exists with no platform exclusions | PyPI files page; PyPI project description; Package.swift (a) | Python wheel: self-build (heavy C++, feasible-in-principle since core supports iOS; nobody publishes it). Swift-native DuckDB is the *Substrate C-compatible* route to local DuckDB. |
| `lancedb` → **`pylance`**, **`pyarrow`** | vector store / FTS | **❌ none** (pylance: mac/linux/win only; pyarrow 25.0.0: no ios) | PyPI files pages (a) | None realistic: Rust lance + Arrow C++ + protobuf toolchain; not a self-build project, a porting program. #3275's RED stands. |
| `fastembed` → **`onnxruntime`** | local embeddings | fastembed pure, but **onnxruntime ❌ none** (1.27.0) | PyPI files page (a) | onnxruntime ships iOS *via CocoaPods/Swift*, not Python (b). Native route = Substrate C's CoreML/NL-embedding layer, not a Python wheel. |
| **`PyMuPDF`** | PDF render/extract | **❌ none** (1.28.0; has wasm before iOS) | PyPI files page (a) | Swift-native PDFKit on iOS (Substrate C direction). |
| `Pillow` | image IO | **✅ official iOS wheels** (12.3.0, cp313–cp315 `ios_13_0_arm64_iphoneos`) | PyPI files page (a) | — |
| `aiohttp` | async HTTP | **✅ official iOS + Android wheels** (3.14.1) | PyPI files page (a) | — |
| `cffi` | FFI (cryptography dep &c.) | **✅ official iOS wheels** (2.1.0) | PyPI files page (a) | — |
| **`cryptography`** | TLS/tokens | **❌ none** (49.0.0, checked Jun-2026 release) | PyPI files page (a) | Ironically its dep cffi has wheels but it doesn't. In-process embed wouldn't need loopback TLS, so possibly droppable (c); frozen beeware channel may hold ancient builds (unverified). |
| `zeroconf` | Bonjour | ❌ none, and **no pure wheel** (0.150.0, all platform-specific) | PyPI files page (a) | Moot: on iOS discovery belongs to `NWBrowser`/Network.framework in Swift (c). |
| `watchdog` | FS watching | ❌ none (6.0.0) | PyPI files page (a) | No iOS FSEvents-equivalent for third parties; drop on iOS (c). |
| `websockets` | WS | 🟢 pure wheel `py3-none-any` exists (16.1) | PyPI files page (a) | — |
| `uvicorn` | ASGI server | 🟢 base is pure; `[standard]` extras (uvloop/httptools) native, no iOS | (c) | In-process embed wouldn't run a socket server at all — call ASGI directly (c). |
| `langchain*`, `langgraph`, `litellm`, `mcp` | orchestration | wrappers pure, BUT: **`ormsgpack` ❌** (1.12.2; langgraph hard dep), **`tiktoken` ❌** (0.13.0; langchain-openai, litellm), **`jiter` ❌** (0.16.0; openai+anthropic SDKs), **`tokenizers` ❌** (0.23.1) | PyPI files pages (a); dep-edges (c, not re-verified today) | All four are Rust/C and individually self-buildable via cibuildwheel — but that's 4+ more wheels you own forever. |
| `kreuzberg` | doc extraction | unverified; pulls a broader native doc stack | (c) | Needs its own spike; assume partial ❌. |
| `pyobjc-framework-{Vision,Quartz,Cocoa}` | Apple Vision OCR | ❌ macOS-only by definition | (a) | Substrate C: Vision.framework directly from Swift on iOS. |
| `mlx`/`mlx-lm` + venv provisioning | local LLM | ❌ dead twice: no iOS wheels AND the venv/subprocess provisioning path is impossible + policy-prohibited on iOS | (a) PEP 730 + repo `mlx_runtime.py` | Apple Foundation Models / CoreML from Swift (Substrate C). |
| `numpy` | transitive | ❌ no official iOS wheels (2.5.1); stale builds exist on frozen beeware channel | PyPI files page (a); Briefcase docs mention numpy `cleanup_paths` (a) | Upstream iOS support is plausible eventually (b); not today. |

**Is #2579 (build missing wheels via mobile-forge) realistic?** **No, as written** — mobile-forge is
explicitly no-longer-developed, frozen at pre-3.13 recipes (a). Restated as "build missing wheels via
cibuildwheel," it is realistic **only** for the Rust singletons (pydantic-core, ormsgpack, tiktoken,
jiter, possibly tokenizers) and *maybe* duckdb (large C++ but upstream already compiles for iOS). It
is **not** realistic for pyarrow/pylance/onnxruntime. Even the realistic subset means Fichero owns a
private wheel farm — rebuilt for every dependency release, every Python bump, every Xcode/SDK bump,
on a Tier-3 platform — to reach an engine that still lacks vectors, embeddings, PDF, and OCR.

**What would "engine-slim" actually have to drop, and is it still Fichero?** Drop: vector search +
embeddings (lancedb/fastembed/onnxruntime), PDF processing (PyMuPDF), OCR (PyObjC), all local AI
(MLX/fm-bridge), FS watching, Bonjour, TLS/auth as shipped, plus every LLM SDK with a native dep
unless self-built. Keep (after self-building pydantic-core + duckdb): FastAPI-shaped CRUD over
DuckDB with a change stream. **That is not Fichero; it is a database with opinions** — and every
dropped capability has a *better* iOS-native replacement (PDFKit, Vision, CoreML/NL, Network.framework)
which is precisely Substrate C's local capability layer. Engine-slim converges on rebuilding
Substrate C the expensive way. (c)

## Q4. Does the architecture even want this?

**No.** Independent of packaging, Substrate B is a worse architecture for this product:

- **Substrate C is shipping, not aspirational.** `iosCompanion` is in source with guard tests
  ("iOS never runs a local engine"), and an iOS TestFlight build shipped this cycle. (a, repo)
- **Second source of truth.** #3278's core principle (per brief): the iPad is "never a second source
  of truth." An embedded engine with its own DuckDB *is exactly that* — it reintroduces the
  multi-master sync problem the accounts/authz architecture (engine = host authority) was designed
  to avoid. (c, grounded in repo architecture)
- **iOS process lifecycle fights a long-running engine.** The app (and thus the in-process engine)
  is suspended in background and jetsam-killed under memory pressure; batch imports, OCR runs, and
  workflow executions — the engine's whole point — don't fit a foreground-only, memory-capped,
  single-process budget shared with SwiftUI. (b/c — platform behavior is common knowledge; no
  specific Apple page was fetched for it in this session, flagged in Open Questions.)
- **What would a user actually gain offline over cache + outbox?** Offline *writes against a local
  authoritative library* and offline *derived-data computation*. The first is the second-source-of-
  truth trap. The second is better served natively: Vision OCR, PDFKit rendering, CoreSpotlight
  search, NLEmbedding — on-device Apple frameworks Substrate C already names. The honest residual
  gain of B is "create and fully own a library on an iPad with no Mac" — a real product idea, but it
  is a *different product posture* (iPad-primary Fichero), and if Daniel ever wants it, the
  Swift-native DuckDB route (official `duckdb-swift` supports Apple platforms) is more plausible
  than a Python engine embed. (c)

**The strongest reading**: Substrate C isn't the fallback — it's simply correct, and B is a
distraction that PEP 730 makes *look* newly viable without changing the economics.

## Q5. Does the macOS MAS sandbox finding change anything for iOS?

**No — it grants nothing.** The macOS finding (sibling report) is that a sandboxed MAS app may spawn
a bundled helper via `Process`/`NSTask` with `com.apple.security.app-sandbox` +
`com.apple.security.inherit`. That is macOS App Sandbox machinery. On iOS: there is no
`Process`/`NSTask` for third-party apps, no sandbox-inherit concept exposed, and PEP 730 documents
that `fork`/`spawn` attempts kill the invoking process. (a) The two platforms' conclusions are
consistent, not transferable: macOS = subprocess architecture viable under conditions; iOS =
subprocess architecture impossible, in-process architecture legal-but-uninstallable.

---

## Recommendation (no hedging)

**CONFIRM #3278. Substrate C stands. Do not overturn.** Specifically:

1. **Keep iPhone/iPad as thin remote client + Swift-native local capability layer** (cache, outbox,
   on-device Vision/PDFKit/CoreML), never a second source of truth.
2. **Keep Substrate B (#2865) parked and keep spike #3291 unscheduled** — but *re-scope its trigger*:
   the question is no longer "can CPython embed on iOS?" (answered upstream: yes) but "do
   **official** iOS wheels exist for `duckdb` AND `pydantic-core`?" Those two are the cheap quarterly
   tripwire (one PyPI files-page check each; beeware.org/mobile-wheels as a dashboard). Until both
   flip, any spike is spending days to rediscover this table.
3. **Close or re-title #2579** — its mobile-forge premise is dead upstream; if kept, restate as
   "cibuildwheel-built private wheels" and record that this path means owning a permanent wheel farm
   for, at minimum: pydantic-core, duckdb, ormsgpack, tiktoken, jiter (+ tokenizers), on a Tier-3
   CPython — and still yields no vectors/embeddings/PDF/OCR.
4. **If iPad-local libraries ever become a product goal**, evaluate **Swift-native DuckDB**
   (`duckdb/duckdb-swift`) inside the Substrate C capability layer — not a Python engine embed. That
   preserves one action layer and one source-of-truth policy while making "library on an iPad" at
   least discussable.

## Open questions

1. **Could not read the GitHub issues** (#3275, #3278, #3291, #2865, #2579, #2584, #2663, #2620,
   #1093) — private repo, no `gh` in this session. This report's characterization of the prior
   decision comes from the task brief and local docs. If #3275's dependency analysis already covered
   pydantic-core/duckdb, the "under-weighted" framing in §What-changed should be softened.
2. **iOS background-execution limits** for a hypothetical in-process engine are asserted from general
   platform knowledge (b/c), not from a fetched Apple doc — verify against Apple's
   background-execution documentation if this ever matters.
3. **kreuzberg's** transitive native chain on iOS is unverified (assumed partially blocked).
4. **litellm→tiktoken and langgraph→ormsgpack dependency edges** were not re-verified today (c);
   the package wheel statuses themselves were.
5. **The frozen `anaconda.org/beeware` channel's exact contents** (e.g., whether an old cryptography
   or numpy build exists there) was not enumerated; irrelevant to the verdict since it is frozen
   pre-3.13.
6. **Whether pydantic-core/duckdb upstreams have open iOS-wheel issues or CI plans** was not
   established — worth one look before setting the quarterly tripwire cadence.

## Sources

**Standards / official docs (fetched and read 2026-07-13):**
- PEP 730 — iOS support for CPython (Final, 3.13, Tier 3): https://peps.python.org/pep-0730/
- Using Python on iOS (embedded-only, framework packaging, App Store compliance patch, privacy
  manifests): https://docs.python.org/3/using/ios.html
- Briefcase iOS platform docs (no sdists on iOS, PyPI + frozen beeware channel, cleanup_paths):
  https://briefcase.beeware.org/en/latest/reference/platforms/iOS/xcode.html
- cibuildwheel platforms (iOS: macOS host + Xcode, xbuild-tools for Rust/CMake, simulator-only
  testing): https://cibuildwheel.pypa.io/en/stable/platforms/
- BeeWare Mobile Wheels + mobile-forge deprecation: https://beeware.org/mobile-wheels/ and
  https://github.com/beeware/mobile-forge

**PyPI files pages checked 2026-07-13 (latest release each; `ios_*` tag presence):**
- ✅ has iOS wheels: pillow 12.3.0, aiohttp 3.14.1, cffi 2.1.0
- ❌ no iOS wheels: duckdb 1.5.4, pydantic-core 2.47.0, pyarrow 25.0.0, pylance, onnxruntime 1.27.0,
  cryptography 49.0.0, pymupdf 1.28.0, numpy 2.5.1, tiktoken 0.13.0, jiter 0.16.0,
  tokenizers 0.23.1, ormsgpack 1.12.2, watchdog 6.0.0, zeroconf 0.150.0
- pure-Python fallback wheels confirmed: websockets 16.1 (`py3-none-any`), multidict 6.7.1
  (`py3-none-any`)
  (all via https://pypi.org/project/NAME/#files)

**Other:**
- DuckDB iOS claims: PyPI duckdb project description ("runs on Linux, macOS, Windows, Android,
  iOS…"); official Swift API: https://github.com/duckdb/duckdb-swift (Package.swift declares no
  platform exclusions)
- Pythonista 3 (bundled-interpreter iOS App Store precedent):
  https://apps.apple.com/us/app/pythonista-3/id1085978097

**Repo files read (2026-07-13):**
- `fichero-server/pyproject.toml` (full dependency manifest)
- `docs/contributor/design/ios-ipad-embedding-plan.md` (2026-07-06 survey; feasibility matrix)
- `docs/superpowers/specs/2026-07-13-mac-app-store-sandbox-research.md` (sibling macOS report)
- `fichero/fichero/Services/EngineConfig.swift`, `EmbeddedBackendService.swift`,
  `fichero-tests/EngineProvisioningStrategyTests.swift` (iosCompanion posture, via grep)
