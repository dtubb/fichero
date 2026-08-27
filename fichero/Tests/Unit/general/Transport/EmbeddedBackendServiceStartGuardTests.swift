//
//  EmbeddedBackendServiceStartGuardTests.swift
//  FicheroTests
//
//  One poller + one retry entry point (#3108): the re-entrancy guard on
//  `start()` is the invariant that keeps N rapid retries from spawning a second
//  engine or racing the first readiness probe. Because `start()` is @MainActor,
//  the guard is deterministic — MainActor's serial executor runs the first
//  call's synchronous guard-check + flag-set uninterrupted before its first
//  `await`, so every concurrent sibling observes the flag and bounces.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
@Suite("EmbeddedBackendService start guard (#3108)")
struct EmbeddedBackendServiceStartGuardTests {

    @Test("N concurrent retries pass the start guard exactly once — one spawn attempt")
    func oneSpawnUnderRapidRetries() async {
        let service = EmbeddedBackendService()
        #expect(service.startAttemptsPassedGuard == 0)
        #expect(service.isStarting == false)

        // Fire eight retries at once. On the XCTest host `start()` takes the
        // safe "connect-to-external-if-up, else no-op" branch (it never spawns a
        // real engine), so this exercises the guard, not process launch.
        await withTaskGroup(of: Void.self) { group in
            for _ in 0..<8 {
                group.addTask { @MainActor in try? await service.start() }
            }
        }

        // Only the first call got past the guard; the other seven bounced.
        #expect(service.startAttemptsPassedGuard == 1)
        // The in-flight flag resets once the call completes (defer).
        #expect(service.isStarting == false)
    }

    @Test("guard is re-entrant across sequential retries, not a one-shot latch")
    func guardResetsBetweenAttempts() async {
        let service = EmbeddedBackendService()

        try? await service.start()
        #expect(service.startAttemptsPassedGuard == 1)
        #expect(service.isStarting == false)

        // A later retry (after the first finished) must pass the guard again —
        // otherwise a genuine reconnect could never re-probe.
        try? await service.start()
        #expect(service.startAttemptsPassedGuard == 2)
        #expect(service.isStarting == false)
    }
}

/// A new window/tab's connect trigger must reuse the app-level connection rather
/// than reprovision the backend (#3394/#3407).
@Suite("Window-lifecycle connection reuse (#3394)")
@MainActor
struct ConnectionReuseDecisionTests {

    @Test("a new window on a running+ready backend attaches — no reconnect")
    func newWindowReusesRunningConnection() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }

    @Test("the first/not-yet-connected window proceeds to connect")
    func firstWindowConnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .stopped, isBackendReady: false) == false)
    }

    @Test("an explicit Retry always re-runs, even when running")
    func retryAlwaysReconnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: true, status: .running, isBackendReady: true) == false)
    }

    @Test("running but not-yet-ready does not short-circuit the readiness probe")
    func runningButNotReadyStillConnects() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: false) == false)
    }

    @Test("a failed/starting backend never counts as reusable")
    func failedOrStartingNotReused() {
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .failed, isBackendReady: true) == false)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .starting, isBackendReady: true) == false)
    }

    // MARK: - Native tab + split lifecycle (#3407)

    @Test("opening a native TAB reuses the connection — tabs open the same guarded scene")
    func nativeTabReusesConnection() {
        // WindowOpener.open(asTab: true) calls openWindow(id: "main"), the same
        // scene a new window opens, whose `.task` runs connectBackend(restart:
        // false). So a tab hits the identical reuse decision as a new window —
        // no re-auth, no backend restart. `addTabbedWindow` never touches the
        // backend. (#3407, narrowed scope of #3394.)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }

    @Test("a window SPLIT never reprovisions — it is an in-window view, not a scene")
    func windowSplitDoesNotReprovision() {
        // A SplittablePane triggers no connect at all (no new scene, no
        // openWindow). This documents that the ONLY paths reaching connectBackend
        // are window/tab scene mounts (restart: false → reuse) and explicit Retry
        // (restart: true). There is no restart:false-on-a-connected-backend path
        // that reprovisions, so a split can't either. (#3407)
        #expect(EmbeddedBackendService.shouldReuseExistingConnection(
            restart: false, status: .running, isBackendReady: true) == true)
    }
}

/// The spawned engine's security posture (auth on/off, bind surface) must come
/// only from the FICHERO_* the app sets — never from a stray FICHERO_* inherited
/// from the shell that launched the app (#3933). `childEnvironmentBase` strips
/// every inherited FICHERO_* before the app layers its own on top.
@Suite("Spawned-engine environment sanitisation (#3933)")
@MainActor
struct SpawnedEngineEnvironmentTests {

    @Test("inherited FICHERO_* keys are stripped from the child's base env")
    func inheritedFicheroVarsAreStripped() {
        let inherited = [
            // The two the issue calls out: auth kill-switch + LAN bind widening.
            "FICHERO_DISABLE_AUTH": "1",
            "FICHERO_LAN_HOST": "0.0.0.0",
            "FICHERO_ALLOW_NON_LOOPBACK_BIND": "I_UNDERSTAND_SHARED_SECRET_RISK",
            // A not-yet-invented FICHERO_* must fail closed too.
            "FICHERO_SOME_FUTURE_FLAG": "danger",
            // Non-FICHERO vars the interpreter needs must survive untouched.
            "PATH": "/usr/bin:/bin",
            "HOME": "/Users/test",
            "LANG": "en_US.UTF-8"
        ]

        let base = EmbeddedBackendService.childEnvironmentBase(inheriting: inherited)

        // No FICHERO_* survives inheritance — the app is the only source.
        #expect(base.keys.allSatisfy { !$0.hasPrefix("FICHERO_") })
        #expect(base["FICHERO_DISABLE_AUTH"] == nil)
        #expect(base["FICHERO_LAN_HOST"] == nil)
        #expect(base["FICHERO_ALLOW_NON_LOOPBACK_BIND"] == nil)
        #expect(base["FICHERO_SOME_FUTURE_FLAG"] == nil)

        // Everything else passes through so the bundled interpreter still runs.
        #expect(base["PATH"] == "/usr/bin:/bin")
        #expect(base["HOME"] == "/Users/test")
        #expect(base["LANG"] == "en_US.UTF-8")
    }

    @Test("an env with no FICHERO_* is returned unchanged")
    func nonFicheroEnvIsUntouched() {
        let inherited = ["PATH": "/bin", "TMPDIR": "/tmp", "USER": "test"]
        #expect(EmbeddedBackendService.childEnvironmentBase(inheriting: inherited) == inherited)
    }
}

/// The engine's `terminationHandler` must decode `terminationReason`: for
/// `.uncaughtSignal` the `terminationStatus` is the SIGNAL NUMBER, so a SIGPIPE
/// (13) must read as "signal 13 SIGPIPE", never the false "exit code 13" that
/// the old status-only path reported. For `.exit` it is a real exit code.
@Suite("Engine termination decoding (SIGPIPE vs exit code)")
struct EngineTerminationDecodingTests {

    @Test("SIGPIPE (signal 13) is decoded as a signal, not exit code 13")
    func sigpipeDecodesAsSignal() {
        let described = EmbeddedBackendService.describeTermination(
            status: SIGPIPE, reason: .uncaughtSignal
        )
        #expect(described == "signal 13 SIGPIPE")
        // The regression we are guarding against: it must NOT read as an exit code.
        #expect(!described.contains("exit code"))
    }

    @Test("a real non-zero exit code is decoded as an exit code")
    func nonZeroExitDecodesAsExit() {
        #expect(EmbeddedBackendService.describeTermination(
            status: 1, reason: .exit) == "exit code 1")
        #expect(EmbeddedBackendService.describeTermination(
            status: 13, reason: .exit) == "exit code 13")
    }

    @Test("other known signals decode to their mnemonics")
    func otherSignalsDecode() {
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGKILL, reason: .uncaughtSignal) == "signal 9 SIGKILL")
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGTERM, reason: .uncaughtSignal) == "signal 15 SIGTERM")
        #expect(EmbeddedBackendService.describeTermination(
            status: SIGSEGV, reason: .uncaughtSignal) == "signal 11 SIGSEGV")
    }

    @Test("a clean exit (code 0) is still described as an exit code")
    func cleanExitDecodes() {
        #expect(EmbeddedBackendService.describeTermination(
            status: 0, reason: .exit) == "exit code 0")
    }
}

/// The TLS-material cache key must be STABLE across rebuilds (keyed on the engine
/// bundle VERSION, not the executable mtime) so the ~2.74s prep subprocess isn't
/// re-paid on every dev launch (#4038) — while still changing on a version bump or
/// a different argument set.
@Suite("TLS-prep cache key (#4038 stable across rebuilds)")
struct TLSCacheKeyTests {

    /// Build a throwaway `Fichero Server.app/Contents/{MacOS/exe, Info.plist}` and
    /// return the executable path. version==nil writes no Info.plist (fallback path).
    private func makeEngineBundle(version: String?) throws -> (exe: String, root: URL) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("tlskey-\(UUID().uuidString)", isDirectory: true)
        let contents = root.appendingPathComponent("Fichero Server.app/Contents", isDirectory: true)
        let macos = contents.appendingPathComponent("MacOS", isDirectory: true)
        try FileManager.default.createDirectory(at: macos, withIntermediateDirectories: true)
        let exe = macos.appendingPathComponent("Fichero Server")
        try Data("binary".utf8).write(to: exe)
        if let version {
            let data = try PropertyListSerialization.data(
                fromPropertyList: ["CFBundleShortVersionString": version],
                format: .xml, options: 0
            )
            try data.write(to: contents.appendingPathComponent("Info.plist"))
        }
        return (exe.path, root)
    }

    @Test("key is unchanged when only the executable mtime/size changes (the fix)")
    func stableAcrossRebuild() throws {
        let (exe, root) = try makeEngineBundle(version: "2026.07.22")
        defer { try? FileManager.default.removeItem(at: root) }
        let key1 = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: ["--host", "127.0.0.1"])
        try Data("rebuilt-binary-larger".utf8).write(to: URL(fileURLWithPath: exe))  // simulate rebuild
        let key2 = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: ["--host", "127.0.0.1"])
        #expect(key1 != nil)
        #expect(key1 == key2)  // version-keyed → cache HITS across the rebuild
    }

    @Test("key changes on a version bump")
    func changesOnVersionBump() throws {
        let (exe, root) = try makeEngineBundle(version: "2026.07.22")
        defer { try? FileManager.default.removeItem(at: root) }
        let k1 = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: [])
        let plist = URL(fileURLWithPath: exe).deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("Info.plist")
        let data = try PropertyListSerialization.data(
            fromPropertyList: ["CFBundleShortVersionString": "2026.07.23"], format: .xml, options: 0)
        try data.write(to: plist)
        let k2 = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: [])
        #expect(k1 != k2)
    }

    @Test("key changes when the arguments differ")
    func changesOnArguments() throws {
        let (exe, root) = try makeEngineBundle(version: "2026.07.22")
        defer { try? FileManager.default.removeItem(at: root) }
        let a = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: ["--host", "127.0.0.1"])
        let b = EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: ["--host", "0.0.0.0"])
        #expect(a != b)
    }

    @Test("falls back to a fingerprint when no Info.plist version is present")
    func fingerprintFallback() throws {
        let (exe, root) = try makeEngineBundle(version: nil)
        defer { try? FileManager.default.removeItem(at: root) }
        #expect(EmbeddedBackendService.engineBundleVersion(forExecutableAt: exe) == nil)
        #expect(EmbeddedBackendService.tlsCacheKey(executablePath: exe, arguments: []) != nil)
    }
}

/// The `.api-key` clobber fix (live find 2026-08-04): the app's engine spawn
/// used to write its freshly minted bootstrap token to the shared token file
/// BEFORE `process.run()`, unconditionally. A spawn that never took the port
/// over (an external engine still serving, a child aborting pre-bind) left
/// the file holding a token the serving engine never adopted — every
/// file-reading client (CLI, MCP, diagnostics curl) then 401'd while the app
/// hummed along on its in-memory token. The rule: only an absent or empty
/// file may be pre-written; a live token is never clobbered from the launch
/// path. The engine-side launcher has the mirror-image guard
/// (`prepare_app_bootstrap_token_for_launch`).
struct BootstrapTokenPreWriteGuardTests {

    private func temporaryFileURL() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("api-key-guard-\(UUID().uuidString)")
    }

    @Test("an absent token file may be pre-written")
    func absentFileAllowsPreWrite() {
        #expect(EmbeddedBackendService.shouldPreWriteBootstrapTokenFile(at: temporaryFileURL()))
    }

    @Test("an empty or whitespace token file may be pre-written")
    func emptyFileAllowsPreWrite() throws {
        let url = temporaryFileURL()
        defer { try? FileManager.default.removeItem(at: url) }
        try "  \n".write(to: url, atomically: true, encoding: .utf8)
        #expect(EmbeddedBackendService.shouldPreWriteBootstrapTokenFile(at: url))
    }

    @Test("a live token is never clobbered from the launch path")
    func liveTokenBlocksPreWrite() throws {
        let url = temporaryFileURL()
        defer { try? FileManager.default.removeItem(at: url) }
        try "existing-serving-engine-token".write(to: url, atomically: true, encoding: .utf8)
        #expect(!EmbeddedBackendService.shouldPreWriteBootstrapTokenFile(at: url))
    }

    @Test("the spawn path consults the guard before writing")
    func spawnConsultsTheGuard() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Services/EmbeddedBackendService+Spawn.swift"),
            encoding: .utf8
        )
        #expect(
            source.contains("shouldPreWriteBootstrapTokenFile(at: tokenURL)"),
            "the unconditional pre-write is back — it clobbers a live engine's token"
        )
    }
}
