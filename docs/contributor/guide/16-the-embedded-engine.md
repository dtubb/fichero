# 16. The Embedded Engine


How the engine ships inside the app, in one page. (This replaces the older bundling/setup pages, which described a superseded arrangement.)

**Packaging.** The engine is packaged by **Briefcase** into a nested app bundle named **“Fichero Server.app”** inside the Fichero app bundle (`EmbeddedBackendService+Spawn.swift` looks for it under `Contents/Helpers/Fichero Server.app`, falling back to `Contents/Resources/Fichero Server.app`). The build step is `fichero-server/scripts/build_backend_bundle.sh`; Xcode’s Embed phase copies the produced bundle into the app. Briefcase declares one platform, so the embedded engine is macOS-only — iOS and iPadOS always talk to a remote engine.

**Provisioning is scheme-based, not** `#if DEBUG`**.** The decision of who owns the engine is made by `EngineConfig.engineProvisioningStrategy()` (`EngineConfig+Launch.swift`), resolved from the running scheme’s build configuration. Schemes come in tiers (Dev, Alpha, Beta, Release) × flavors (Embedded, Local):

- **Embedded** schemes (including “Fichero (Dev Embedded)”, whose build configuration is `Dev Embedded` and does *not* define `DEBUG`) resolve to the embedded strategy: **the app spawns and owns the bundled engine**, binding it to the app’s Unix-socket path. Stop any hand-started engine first — two engines, one socket.
- **Local** schemes (e.g. “Fichero (Dev Local)”, configuration `Debug`) resolve to the external strategy: the app never spawns and *requires* a developer-run engine (`start_backend.sh`) to adopt. The engine is deliberately not bundled in Debug builds.

The two flavors differ in who owns the engine process, not in speed — Swift optimization is `-Onone` in both Dev variants.

**Health and readiness.** Readiness is probed at `GET /api/health` over the pinned transport (UDS locally, pinned HTTPS otherwise) — `EngineReadinessProbe` requires a 200 plus matching identity fields (including the launch nonce the spawn passed), so the app cannot adopt a stale or foreign engine. The general engine-ownership model has two axes: the app owns the *process* (spawn, lifecycle, teardown), and the library owns the *connection* (which engine a given library window talks to).
