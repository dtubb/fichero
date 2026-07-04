#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import Foundation
import OSLog
import Security

// swiftlint:disable file_length type_body_length

private let logger = Logger(subsystem: "app.fichero.fichero", category: "EmbeddedBackend")

/// True when this process is hosting an XCTest bundle. Detected via the XCTest
/// runtime class, which is loaded into the host the moment the test bundle is
/// injected (before `main`), so it's reliable regardless of how the host was
/// launched — unlike the `XCTest*` env vars, which don't always propagate.
///
/// Used to neutralize app-boot side effects during tests: the host must not
/// launch a backend (it would race / fatally terminate via showBackendError)
/// or open the user's real libraries. The integration harness (EngineHarness)
/// owns engine lifecycle and seeds its own disposable library.
func isRunningXCTests() -> Bool {
    if NSClassFromString("XCTestCase") != nil { return true }
    let env = ProcessInfo.processInfo.environment
    return env["XCTestConfigurationFilePath"] != nil || env["XCTestBundlePath"] != nil
}

// `isUITesting()` / `uiTestSupportDirectory()` live in UITestSupport.swift (#1230).

/// Manages the embedded Python backend lifecycle
@MainActor
final class EmbeddedBackendService: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var errorMessage: String?

    private var backendPID: pid_t?
    private var isExternalBackend = false  // Track if using external vs embedded backend
    var isUsingExternalBackend: Bool { isExternalBackend }
    /// The FICHERO_LAUNCH_NONCE we passed to the engine we spawned (#2862).
    /// Readiness verifies /api/health echoes this exact value, proving the
    /// responder is the child we launched — not a stale process on the port.
    /// nil when we adopted an external engine (we didn't spawn it, so there's
    /// no nonce to match).
    private(set) var expectedLaunchNonce: String?
    private var backendURL: URL {
        // Own-engine traffic stays on loopback, never the advertised public URL (#2604).
        EngineConfig.host
    }

    enum BackendStatus {
        case stopped
        case starting
        case running
        case failed
    }

    /// Outcome of an authenticated readiness probe (#2862) — now the shared
    /// `EngineReadiness` (#3106), verified by the one `EngineReadinessProbe`.
    typealias ReadinessResult = EngineReadiness

    /// The most recent readiness outcome, for #2864's diagnosis UI.
    private(set) var lastReadiness: ReadinessResult?

    /// Set true when WE initiate a stop (stop()), so the process
    /// terminationHandler doesn't misread an intentional shutdown as a crash
    /// and flip status to .failed (#2863).
    private var intentionalStop = false

    /// True while a start()/respawn is in flight. Guards against a second
    /// `retry()` spawning a duplicate engine or racing the first probe (#3108):
    /// a retry while starting is a no-op. Because `start()` is @MainActor, the
    /// guard+set at the top run without interleaving up to the first `await`,
    /// so concurrent retries deterministically see this true and bounce.
    private(set) var isStarting = false

    /// How many `start()` calls passed the re-entrancy guard — the spawn-attempt
    /// counter the concurrency-stress test asserts stays at 1 under N rapid
    /// retries (#3108).
    private(set) var startAttemptsPassedGuard = 0

    /// How the port pre-flight resolved (#2863).
    private enum PortResolution { case spawnOurs, adoptExisting }

    // MARK: - Lifecycle

    /// Start the embedded backend
    func start() async throws {
        // One spawn per host at a time (#3108): a retry fired while a start is
        // already in flight is a no-op, so N rapid retries never spawn a second
        // engine or race the first readiness probe.
        guard !isStarting else {
            logger.info("start() ignored — a start/retry is already in flight (#3108)")
            return
        }
        isStarting = true
        startAttemptsPassedGuard += 1
        defer { isStarting = false }

        if await useExistingBackendIfAvailable() {
            return
        }

        logger.info("Starting embedded backend...")
        status = .starting

        // Launch embedded backend (macOS only; DEBUG fallback or RELEASE always).
        // Briefcase-bundled engine cold-starts in ~25s on Apple Silicon
        // (heavy ML imports + DB init); 90s gives margin on slower I/O,
        // first-launch caches, and contended startup.
        // iOS cannot spawn a local engine — a configured remote host is required.
        #if os(macOS)
        // Pre-flight the port (#2863). Sweep our own orphans, then if the port
        // is STILL held by a process we can't claim, ask the user (Stop it /
        // Use it / Quit) rather than silently adopting an engine that may
        // reject our token and leave a blank window.
        switch await resolvePortConflict() {
        case .adoptExisting:
            isExternalBackend = true
            expectedLaunchNonce = nil
            // Adoption is gated on the authenticated probe: if the existing
            // engine rejects our token, waitForBackend throws and we surface
            // failure instead of a blank window.
            try await waitForBackend(timeout: 30)
            status = .running
            logger.info("Adopted user-approved existing engine on port 8765")
        case .spawnOurs:
            try launchEmbeddedBackend()
            try await waitForBackend(timeout: 90)
            _ = await AuthTokenMiddleware.waitForToken(timeout: 10)
            status = .running
            logger.info("Embedded backend started successfully")
        }
        #else
        status = .failed
        errorMessage = "No remote engine host configured. Set a custom host in Settings."
        throw BackendError.notRunning
        #endif
    }

    private func useExistingBackendIfAvailable() async -> Bool {
        // Clear any nonce from a prior spawn — an adopted external engine is
        // not our child, so readiness must not try to match a stale nonce.
        expectedLaunchNonce = nil
        // SwiftUI Previews / Xcode canvas: never spawn the embedded engine.
        // Previews launch the full app to render a view — orphan-cleanup
        // would SIGTERM the developer's external engine, and the briefcase
        // cold-start (~25s) blows past the 30s preview launch timeout.
        // Try a quick connect to a developer-managed external engine; if
        // one is up, use it; otherwise mark as running (with no backend)
        // so preview rendering doesn't block. Mocked previews don't hit
        // the API anyway.
        let env = ProcessInfo.processInfo.environment
        let isPreview = env["XCODE_RUNNING_FOR_PREVIEWS"] == "1"
            || env["XCODE_RUNNING_FOR_PLAYGROUNDS"] == "1"
        // XCTest host: a test run launches the full app as its host, so this
        // boot path runs *before* any test code. The integration harness
        // (EngineHarness) manages its own disposable engine and drives the
        // services with its own client, so the host app must NEITHER launch
        // the (often unbuilt) bundled engine NOR fatally terminate when it's
        // missing — `showBackendError` calls NSApplication.terminate, which
        // kills the test runner before a single test executes.
        if isPreview || isRunningXCTests() || isUITesting() {
            logger.info("Preview / playground / XCTest host / UI-test — connecting to external if up, else no-op")
            do {
                try await waitForBackend(timeout: 1.5)
                status = .running
                isExternalBackend = true
                logger.info("Connected to external backend")
            } catch {
                logger.info("No external backend; host runs without managing one")
                status = .running
                isExternalBackend = true
            }
            return true
        }

        if EngineConfig.usesCustomHost {
            logger.info("Custom engine host configured: \(EngineConfig.host.absoluteString, privacy: .public)")
            do {
                try await waitForBackend(timeout: 5)
                status = .running
                isExternalBackend = true
                logger.info("Connected to configured external backend")
                return true
            } catch {
                status = .failed
                errorMessage = error.localizedDescription
                logger.error("Configured external backend did not respond: \(error.localizedDescription, privacy: .public)")
                return false
            }
        }

        #if DEBUG
        // Development mode: connect to external backend if running, skip
        // embedded launch. 5s window because a freshly-started external
        // engine may still be in cold-start when Fichero.app launches in
        // a paired-debug session — 2s was tight enough to miss it and
        // fall through to embedded launch (which kills the developer's
        // engine on the way up).
        logger.info("DEBUG mode: Checking for external backend on port 8765")

        do {
            try await waitForBackend(timeout: 5)
            status = .running
            isExternalBackend = true
            logger.info("Connected to external backend (will not manage lifecycle)")
            return true
        } catch {
            logger.info("No external backend found, launching embedded backend...")
            isExternalBackend = false
        }
        #endif
        return false
    }

    /// Stop the embedded backend
    func stop() {
        // Don't stop external backends (user-managed)
        if isExternalBackend {
            logger.info("Using external backend - leaving it running (user-managed)")
            status = .stopped
            return
        }

        guard let pid = backendPID else {
            logger.info("ℹ️  No embedded backend PID tracked (may not have launched yet or using external)")
            status = .stopped
            return
        }

        logger.info("Stopping embedded backend (PID: \(pid))...")

        // Mark intentional so the terminationHandler doesn't flip .failed.
        intentionalStop = true

        // Clear state immediately
        backendPID = nil
        status = .stopped

        // Graceful shutdown - send SIGTERM
        kill(pid, SIGTERM)

        // Wait up to 5 seconds for graceful shutdown (synchronous)
        // This must be synchronous so applicationWillTerminate waits for it
        for attempt in 0..<50 {
            // Check if process is still running
            if kill(pid, 0) != 0 {
                // Process no longer exists
                logger.info("Backend stopped gracefully after \(attempt * 100)ms")
                return
            }
            // Sleep for 100ms
            Thread.sleep(forTimeInterval: 0.1)
        }

        // Force kill if still running after 5 seconds
        if kill(pid, 0) == 0 {
            logger.warning("Backend didn't shut down gracefully after 5s, force killing...")
            kill(pid, SIGKILL)

            // Give it one more second to die
            Thread.sleep(forTimeInterval: 1.0)

            if kill(pid, 0) == 0 {
                logger.error("Failed to kill backend process (PID: \(pid))")
            } else {
                logger.info("Backend force-killed successfully")
            }
        }
    }

    deinit {
        // Clean up backend on service deallocation (shouldn't happen in normal app lifecycle)
        if let pid = backendPID, !isExternalBackend {
            logger.warning("EmbeddedBackendService deinit - terminating backend (PID: \(pid))")
            logger.warning("This shouldn't happen in normal app lifecycle - backend should be stopped via stop()")
            kill(pid, SIGTERM)
        }
    }

    // MARK: - Private Helpers

    #if os(macOS)
    // swiftlint:disable:next function_body_length
    private func launchEmbeddedBackend() throws {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BackendError.bundleNotFound
        }

        // Path to nested Briefcase backend app's executable. Bundle is named
        // "Fichero Engine.app" (briefcase formal_name = "Fichero Engine"),
        // bundle ID app.fichero.fichero.engine (#renamed today).
        let backendAppPath = "\(resourcePath)/Fichero Engine.app"
        let executablePath = "\(backendAppPath)/Contents/MacOS/Fichero Engine"

        // Check if backend executable exists
        guard FileManager.default.fileExists(atPath: executablePath) else {
            logger.error("Backend executable not found at: \(executablePath)")
            // Debug builds skip the "Embed Fichero Engine" phase (it only runs in
            // Release), so in a Debug ⌘R the engine is expected to be running
            // externally on :8765. If it isn't, that's this path.
            logger.error("Debug: start the engine first — fichero-engine/scripts/start_backend.sh. Release: briefcase build macOS --app engine (in fichero-engine/), then rebuild.")
            throw BackendError.backendAppNotFound
        }

        // Port pre-flight (orphan sweep + user decision on a foreign holder)
        // already ran in resolvePortConflict() before we got here — including
        // in DEBUG (#2863). By this point the port is ours to bind.

        let accessMaterial: RemoteAccessTLSMaterial
        let publicBaseURL: URL?
        if RemoteAccessConfig.hostingEnabled {
            guard let url = RemoteAccessConfig.publicBaseURL else {
                throw BackendError.launchFailed(
                    NSError(
                        domain: "EmbeddedBackendService",
                        code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "Remote access needs a reachable HTTPS URL."]
                    )
                )
            }
            publicBaseURL = url
            accessMaterial = try prepareRemoteAccessTLSMaterial(
                executablePath: executablePath,
                publicBaseURL: url
            )
        } else {
            publicBaseURL = nil
            accessMaterial = try prepareLocalAccessTLSMaterial(executablePath: executablePath)
        }

        // Persist the SPKI pin for every host the engine binds to. The
        // remote-access cert is also served on loopback, so pins match (#2611).
        try RemoteCertificatePinning.persistHostedBackendSPKIPin(
            accessMaterial.spkiPin,
            hostString: EngineConfig.defaultHostString
        )
        if let publicBaseURL {
            try RemoteCertificatePinning.persistHostedBackendSPKIPin(
                accessMaterial.spkiPin,
                hostString: publicBaseURL.absoluteString
            )
        }

        logger.info("Launching backend process: \(executablePath)")

        // Use Process for direct process control - much simpler than NSWorkspace
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        // Mirror start_backend.sh HTTPS args (#2603/#2604/#2611).
        process.arguments = [
            "--ssl-certfile", accessMaterial.certificatePath,
            "--ssl-keyfile", accessMaterial.keyPath
        ]
        // Mint the bootstrap token and a launch nonce HERE, in the app, and
        // pass both to the spawn (#2862). The app is authoritative: it writes
        // the token file itself (below) instead of racing to read whatever the
        // engine mints, and it can issue an authenticated readiness probe the
        // instant the engine binds. The nonce lets readiness prove the engine
        // answering /api/health is the child we launched.
        let bootstrapToken = Self.generateSecret()
        let launchNonce = Self.generateSecret()
        expectedLaunchNonce = launchNonce

        var environment = ProcessInfo.processInfo.environment
        // Engine watches this PID and self-terminates if we die without a
        // chance to call .stop() (e.g., SIGKILL). Belt-and-braces with the
        // applicationWillTerminate path.
        environment["FICHERO_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        environment["FICHERO_BOOTSTRAP_TOKEN"] = bootstrapToken
        environment["FICHERO_LAUNCH_NONCE"] = launchNonce
        environment["FICHERO_TLS_CERTFILE"] = accessMaterial.certificatePath
        environment["FICHERO_TLS_KEYFILE"] = accessMaterial.keyPath
        environment["FICHERO_TLS_SPKI_HASH"] = accessMaterial.spkiPin
        environment["FICHERO_BIND_HOST"] = accessMaterial.bindHost
        if let publicBaseURL {
            // Reuse the same env contract as RemoteAccessConfig so the
            // remote-access launch path cannot drift from the helper (#2611).
            environment.merge(
                RemoteAccessConfig.launchEnvironment(
                    for: publicBaseURL,
                    material: accessMaterial,
                    bonjourEnabled: RemoteAccessConfig.bonjourEnabled
                ),
                uniquingKeysWith: { $1 }
            )
        }
        #if DEBUG
        // Ensure workflow/provider routes are available for debug UI surfaces.
        environment["FICHERO_FEATURE_TIER"] = environment["FICHERO_FEATURE_TIER"] ?? "dev"
        #endif
        process.environment = environment

        // Diagnostic (#757): capture engine stdout/stderr to a tail-able file
        // in ~/Library/Logs/ so Release-build engine failures surface instead
        // of getting silently swallowed.
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        try? FileManager.default.createDirectory(
            at: logURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let logHandle = try FileHandle(forWritingTo: logURL)
        process.standardOutput = logHandle
        process.standardError = logHandle

        // Write the token file the app minted (#2862/#2863). We NEVER pre-delete
        // it: an empty/absent .api-key would make every request 401 until the
        // engine got around to writing one — the blank-window-with-401s bug.
        // Writing our own token (mode 0600) means the app and the engine agree
        // from the first request, with no window where the two disagree.
        if let tokenURL = AuthTokenMiddleware.bootstrapTokenFileURL() {
            Self.writeBootstrapTokenFile(bootstrapToken, at: tokenURL)
        }

        // If the engine dies on its own (crash, import error, port lost), flip
        // to .failed with the tail of engine.log instead of leaving the UI
        // stuck on a spinner or a blank window (#2863). Skipped when WE asked
        // it to stop. terminationHandler runs off the main actor, so hop back.
        intentionalStop = false
        process.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            Task { @MainActor [weak self] in
                guard let self, !self.intentionalStop else { return }
                let tail = Self.tailEngineLog(lines: 20)
                self.status = .failed
                self.errorMessage = "The engine exited unexpectedly (code \(code))."
                    + (tail.isEmpty ? "" : "\n\n\(tail)")
                logger.error("Engine terminated unexpectedly (code \(code))")
            }
        }

        // Launch the process
        try process.run()

        let pid = process.processIdentifier
        logger.info("Backend process launched successfully (PID: \(pid))")

        // Store PID and process reference
        backendPID = pid
        isExternalBackend = false
        logger.info("Tracking embedded backend PID: \(pid)")
    }

    private func prepareLocalAccessTLSMaterial(executablePath: String) throws -> RemoteAccessTLSMaterial {
        try prepareTLSMaterial(
            executablePath: executablePath,
            arguments: ["--prepare-local-access"],
            failureMessage: "Local engine TLS preparation failed."
        )
    }

    private func prepareRemoteAccessTLSMaterial(
        executablePath: String,
        publicBaseURL: URL
    ) throws -> RemoteAccessTLSMaterial {
        try prepareTLSMaterial(
            executablePath: executablePath,
            arguments: [
                "--prepare-remote-access",
                "--public-base-url",
                publicBaseURL.absoluteString
            ],
            failureMessage: "Remote access TLS preparation failed."
        )
    }

    private func prepareTLSMaterial(
        executablePath: String,
        arguments: [String],
        failureMessage: String
    ) throws -> RemoteAccessTLSMaterial {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = arguments

        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        let outputData = stdout.fileHandleForReading.readDataToEndOfFile()
        let errorData = stderr.fileHandleForReading.readDataToEndOfFile()
        guard process.terminationStatus == 0 else {
            let message = String(data: errorData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
                ?? failureMessage
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: Int(process.terminationStatus),
                    userInfo: [NSLocalizedDescriptionKey: message]
                )
            )
        }

        do {
            return try JSONDecoder().decode(RemoteAccessTLSMaterial.self, from: outputData)
        } catch {
            throw BackendError.launchFailed(
                NSError(
                    domain: "EmbeddedBackendService",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Could not decode remote access TLS material."]
                )
            )
        }
    }
    #endif

    /// Poll until the engine is genuinely READY (#2862): not just answering
    /// health-200, but the instance we spawned (nonce echo) AND accepting the
    /// app's token (authenticated /api/registry 200). Throws `.timeout` if it
    /// never reaches `.ready`. The last probe result is stored in
    /// `lastReadiness` for #2864's diagnosis.
    private func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        // Poll aggressively at first (100ms) so we catch the backend as soon as
        // it's ready — local FastAPI typically answers within 200-400ms. Back
        // off to 500ms after the first second to avoid log spam if the backend
        // is genuinely slow/stuck.
        var pollInterval: Duration = .milliseconds(100)
        while Date().timeIntervalSince(startTime) < timeout {
            if Task.isCancelled {
                throw CancellationError()
            }

            let result = await probeReadiness()
            lastReadiness = result
            if result == .ready {
                logger.info("Backend readiness passed (health 200 + identity + authenticated probe)")
                return
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }

        throw BackendError.timeout
    }

    /// One authenticated readiness probe — delegates to the shared
    /// `EngineReadinessProbe` (#3106), the single home for the readiness contract.
    func probeReadiness() async -> ReadinessResult {
        await EngineReadinessProbe(hostURL: backendURL, expectedNonce: expectedLaunchNonce).probe()
    }

    private func backendSupportsWorkflowRoutes() async -> Bool {
        let workflowsURL = backendURL.appendingPathComponent("api/workflows")
        var request = URLRequest(url: workflowsURL)
        request.httpMethod = "GET"
        request.addEngineAuth()
        let session = RemoteCertificatePinning.configuredSession()

        do {
            let (_, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            // Missing library header may return 422; route absence returns 404.
            // 401 means engine present but token mismatch — treat as supported
            // so we don't double-launch.
            return httpResponse.statusCode != 404
        } catch {
            return false
        }
    }

    // MARK: - Token & identity helpers (#2862)

    /// 32 cryptographically-random bytes, base64url without padding — same
    /// shape as the engine's `secrets.token_urlsafe(32)`. Used for both the
    /// bootstrap token and the launch nonce.
    static func generateSecret() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    /// Write the bootstrap token to `url` with 0600 perms (owner-only), matching
    /// the engine's write. The app is authoritative for the token it minted.
    static func writeBootstrapTokenFile(_ token: String, at url: URL) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try token.data(using: .utf8)?.write(to: url, options: .atomic)
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o600], ofItemAtPath: url.path
            )
        } catch {
            logger.error("Failed to write bootstrap token file: \(error.localizedDescription, privacy: .public)")
        }
    }

    // MARK: - Orphan-engine cleanup

    #if os(macOS)
    /// SIGTERM a "Fichero Engine" subprocess left over from a previous run of
    /// **this** app that didn't get a chance to call .stop() (e.g. SIGKILL,
    /// crash, or force-quit). Called before spawning a new engine so the new
    /// spawn can bind port 8765 cleanly.
    ///
    /// SAFETY (#2079): a host can BOTH serve a shared engine (for remote users)
    /// AND run the app. Killing local engines by name pattern would SIGTERM that
    /// shared engine out from under its users. We therefore never kill by name
    /// alone — only engines that provably belong to this app's lineage. The rule,
    /// in priority order, per candidate engine PID:
    ///   • configured to use a custom/remote host  → we own NO local engine;
    ///     skip the whole sweep (early return below).
    ///   • engine has no recorded `FICHERO_PARENT_PID`  → started independently
    ///     of any app (a shared/manually-run engine) — SPARE it.
    ///   • recorded parent is still alive and isn't us  → a DIFFERENT live owner
    ///     is using it — SPARE it.
    ///   • recorded parent is us, or is dead  → a genuine orphan of a Fichero
    ///     app run that no longer exists — KILL it.
    ///
    /// Correctness over aggressiveness: it is better to leave a real orphan
    /// running (the user can kill it) than to SIGTERM a shared engine others
    /// depend on. When in doubt we spare.
    static func terminateOrphanEngines() {
        if EngineConfig.usesCustomHost {
            logger.info("Custom/remote engine host configured — skipping orphan sweep (no local engine is ours to kill)")
            return
        }

        let thisAppPID = ProcessInfo.processInfo.processIdentifier

        let pgrep = Process()
        pgrep.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        pgrep.arguments = ["-f", "Fichero Engine.app/Contents/MacOS"]
        let pipe = Pipe()
        pgrep.standardOutput = pipe
        pgrep.standardError = FileHandle.nullDevice
        guard (try? pgrep.run()) != nil else { return }
        pgrep.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        guard let output = String(data: data, encoding: .utf8) else { return }
        for line in output.split(separator: "\n") {
            guard let pid = pid_t(line.trimmingCharacters(in: .whitespaces)) else { continue }

            guard let parent = engineParentPID(pid) else {
                logger.info("Engine PID \(pid) has no FICHERO_PARENT_PID — not app-spawned, sparing")
                continue
            }
            if parent != thisAppPID, isProcessAlive(parent) {
                logger.info("Engine PID \(pid) owned by live app PID \(parent) — sparing")
                continue
            }
            logger.info("Terminating orphan engine PID \(pid) (parent \(parent) is this app or dead)")
            kill(pid, SIGTERM)
        }
    }

    /// Read the `FICHERO_PARENT_PID` recorded in a candidate engine's
    /// environment (set by `launchEmbeddedBackend` on spawn). `ps -E` appends a
    /// process's environment to its command-line output, so we can recover the
    /// owner without a pidfile. Returns nil when the var is absent (engine
    /// started independently of any app) or the environment can't be read.
    private static func engineParentPID(_ pid: pid_t) -> pid_t? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/ps")
        task.arguments = ["-E", "-ww", "-o", "command=", "-p", String(pid)]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return nil }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        guard let output = String(data: data, encoding: .utf8),
              let range = output.range(of: "FICHERO_PARENT_PID=") else { return nil }
        let digits = output[range.upperBound...].prefix { $0.isNumber }
        return pid_t(digits)
    }

    /// True if `pid` names a live process — exists, even if owned by another
    /// user we lack permission to signal. `kill(_, 0)` returns 0 when the
    /// process exists and is signalable, or fails with EPERM when it exists but
    /// belongs to a different owner. Both mean "alive" for orphan-kill purposes.
    private static func isProcessAlive(_ pid: pid_t) -> Bool {
        if pid <= 0 { return false }
        return kill(pid, 0) == 0 || errno == EPERM
    }

    static func waitForPortToClear(_ port: UInt16, timeout: TimeInterval) {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if !portInUse(port) { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    private static func portInUse(_ port: UInt16) -> Bool {
        pidOnPort(port) != nil
    }

    /// PID of the process LISTENing on `port`, or nil if the port is free.
    private static func pidOnPort(_ port: UInt16) -> pid_t? {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-i", ":\(port)", "-sTCP:LISTEN", "-t"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return nil }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        let first = String(data: data, encoding: .utf8)?
            .split(separator: "\n").first
            .map(String.init)?
            .trimmingCharacters(in: .whitespaces)
        return first.flatMap { pid_t($0) }
    }

    /// Port pre-flight (#2863). Sweep our own orphans; if the port is then
    /// STILL held by a process we can't claim, ask the user rather than
    /// silently adopting or silently killing. Never returns without the port
    /// being ours (`.spawnOurs`) or the user having chosen to adopt
    /// (`.adoptExisting`); "Quit" terminates the app.
    private func resolvePortConflict() async -> PortResolution {
        Self.terminateOrphanEngines()
        Self.waitForPortToClear(8765, timeout: 3.0)
        guard let pid = Self.pidOnPort(8765) else { return .spawnOurs }

        switch Self.presentPortConflictDecision(pid: pid) {
        case .stopIt:
            kill(pid, SIGTERM)
            Self.waitForPortToClear(8765, timeout: 5.0)
            if Self.portInUse(8765) {
                kill(pid, SIGKILL)
                Self.waitForPortToClear(8765, timeout: 2.0)
            }
            return .spawnOurs
        case .useIt:
            return .adoptExisting
        case .quit:
            NSApplication.shared.terminate(nil)
            return .adoptExisting  // unreachable; terminate() ends the process
        }
    }

    private enum PortConflictChoice { case stopIt, useIt, quit }

    /// Modal decision when port 8765 is held by a process we didn't spawn.
    /// Explicit user intent replaces silent adoption (#2863).
    private static func presentPortConflictDecision(pid: pid_t) -> PortConflictChoice {
        let alert = NSAlert()
        alert.messageText = "Port 8765 is already in use"
        alert.informativeText = """
            Another process (PID \(pid)) is already listening on port 8765, \
            where the Fichero engine runs.

            • Stop it — quit that process and start Fichero's own engine.
            • Use it — connect to the existing engine (only works if it \
            accepts this app's credentials).
            • Quit — leave the other process alone and quit Fichero.
            """
        alert.alertStyle = .warning
        alert.addButton(withTitle: "Stop it")   // .alertFirstButtonReturn
        alert.addButton(withTitle: "Use it")    // .alertSecondButtonReturn
        alert.addButton(withTitle: "Quit")      // .alertThirdButtonReturn
        switch alert.runModal() {
        case .alertFirstButtonReturn: return .stopIt
        case .alertSecondButtonReturn: return .useIt
        default: return .quit
        }
    }

    /// Last `lines` lines of the engine log, for surfacing a real cause when
    /// the engine dies (#2863). Empty string if the log can't be read.
    static func tailEngineLog(lines: Int) -> String {
        let logURL = FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero/engine.log")
        guard let contents = try? String(contentsOf: logURL, encoding: .utf8) else {
            return ""
        }
        let tail = contents.split(separator: "\n", omittingEmptySubsequences: false).suffix(lines)
        return tail.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }
    #endif
}

// MARK: - Readiness probe payload

// MARK: - Errors

enum BackendError: LocalizedError {
    case notRunning
    case bundleNotFound
    case backendAppNotFound
    case launchFailed(Error)
    case timeout

    var errorDescription: String? {
        switch self {
        case .notRunning:
            return "Backend is not running"
        case .bundleNotFound:
            return "App bundle resources not found"
        case .backendAppNotFound:
            // Debug builds don't embed the engine (the embed phase is Release-only),
            // so the usual cause in a Debug ⌘R is simply no engine running on :8765.
            #if DEBUG
            return "The Fichero Engine isn't running. In a Debug build the engine is "
                + "not bundled — start it first with fichero-engine/scripts/start_backend.sh "
                + "(or briefcase dev), then Retry."
            #else
            return "Backend app not found in bundle. Build the engine with: "
                + "briefcase build macOS --app engine (in fichero-engine/), then rebuild Fichero in Xcode."
            #endif
        case .launchFailed(let error):
            return "Failed to launch backend app: \(error.localizedDescription)"
        case .timeout:
            return "Backend failed to start within timeout"
        }
    }
}

// swiftlint:enable type_body_length
