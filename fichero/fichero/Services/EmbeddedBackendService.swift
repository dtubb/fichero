import FicheroAPIClient
import Foundation
import OSLog

// swiftlint:disable type_body_length

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
    private var backendURL: URL {
        if RemoteAccessConfig.hostingEnabled, let publicBaseURL = RemoteAccessConfig.publicBaseURL {
            return publicBaseURL
        }
        return EngineConfig.host
    }

    enum BackendStatus {
        case stopped
        case starting
        case running
        case failed
    }

    // MARK: - Lifecycle

    /// Start the embedded backend
    func start() async throws {
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
            return
        }

        logger.info("Starting embedded backend...")
        status = .starting

        if EngineConfig.usesCustomHost {
            logger.info("Custom engine host configured: \(EngineConfig.host.absoluteString, privacy: .public)")
            do {
                try await waitForBackend(timeout: 5)
                status = .running
                isExternalBackend = true
                logger.info("Connected to configured external backend")
                return
            } catch {
                status = .failed
                errorMessage = error.localizedDescription
                throw error
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
            return
        } catch {
            logger.info("No external backend found, launching embedded backend...")
            isExternalBackend = false
        }
        #endif

        // Launch embedded backend (macOS only; DEBUG fallback or RELEASE always).
        // Briefcase-bundled engine cold-starts in ~25s on Apple Silicon
        // (heavy ML imports + DB init); 90s gives margin on slower I/O,
        // first-launch caches, and contended startup.
        // iOS cannot spawn a local engine — a configured remote host is required.
        #if os(macOS)
        try launchEmbeddedBackend()
        try await waitForBackend(timeout: 90)
        _ = await AuthTokenMiddleware.waitForToken(timeout: 10)
        status = .running
        logger.info("Embedded backend started successfully")
        #else
        status = .failed
        errorMessage = "No remote engine host configured. Set a custom host in Settings."
        throw BackendError.notRunning
        #endif
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
            logger.error("Build backend with: ./scripts/build_backend_bundle.sh")
            throw BackendError.backendAppNotFound
        }

        // Defensive cleanup ONLY in RELEASE: if a previous Fichero was
        // SIGKILL'd (or crashed without applicationWillTerminate firing),
        // the engine subprocess is an orphan still bound to port 8765.
        // Sweep it before spawning ours, otherwise our spawn will fail
        // with "Address already in use".
        //
        // Skip in DEBUG: the developer often runs the engine externally
        // (uvicorn, briefcase dev, etc.). The `start()` external-probe
        // above should have caught that, but if for any reason we ended
        // up here in DEBUG, we still must not SIGTERM the developer's
        // engine — that would silently kill their workflow runs.
        #if !DEBUG
        Self.terminateOrphanEngines()
        Self.waitForPortToClear(8765, timeout: 3.0)
        #endif

        var remoteAccessMaterial: RemoteAccessTLSMaterial?
        var remoteAccessPublicBaseURL: URL?
        if RemoteAccessConfig.hostingEnabled {
            guard let publicBaseURL = RemoteAccessConfig.publicBaseURL else {
                throw BackendError.launchFailed(
                    NSError(
                        domain: "EmbeddedBackendService",
                        code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "Remote access needs a reachable HTTPS URL."]
                    )
                )
            }
            remoteAccessPublicBaseURL = publicBaseURL
            remoteAccessMaterial = try prepareRemoteAccessTLSMaterial(
                executablePath: executablePath,
                publicBaseURL: publicBaseURL
            )
            if let remoteAccessMaterial {
                try RemoteCertificatePinning.persistHostedBackendSPKIPin(
                    remoteAccessMaterial.spkiPin,
                    hostString: publicBaseURL.absoluteString
                )
            }
        }

        logger.info("Launching backend process: \(executablePath)")

        // Use Process for direct process control - much simpler than NSWorkspace
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = []
        var environment = ProcessInfo.processInfo.environment
        // Engine watches this PID and self-terminates if we die without a
        // chance to call .stop() (e.g., SIGKILL). Belt-and-braces with the
        // applicationWillTerminate path.
        environment["FICHERO_PARENT_PID"] = String(ProcessInfo.processInfo.processIdentifier)
        if let remoteAccessMaterial, let remoteAccessPublicBaseURL {
            environment.merge(
                RemoteAccessConfig.launchEnvironment(
                    for: remoteAccessPublicBaseURL,
                    material: remoteAccessMaterial,
                    bonjourEnabled: RemoteAccessConfig.bonjourEnabled
                ),
                uniquingKeysWith: { _, new in new }
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

        if let tokenURL = AuthTokenMiddleware.bootstrapTokenFileURL() {
            try? FileManager.default.removeItem(at: tokenURL)
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

    private func prepareRemoteAccessTLSMaterial(
        executablePath: String,
        publicBaseURL: URL
    ) throws -> RemoteAccessTLSMaterial {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = [
            "--prepare-remote-access",
            "--public-base-url",
            publicBaseURL.absoluteString
        ]

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
                ?? "Remote access TLS preparation failed."
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

    private func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        let healthURL = backendURL.appendingPathComponent("api/health")
        let session = RemoteCertificatePinning.configuredSession()

        // Poll aggressively at first (100ms) so we catch the backend
        // as soon as it's ready — local FastAPI typically answers
        // within 200-400ms. The previous 1s sleep padded perceived
        // startup time by ~1s on the common path (#619). Back off to
        // 500ms after the first second to avoid log spam if the
        // backend is genuinely slow/stuck.
        var pollInterval: Duration = .milliseconds(100)
        while Date().timeIntervalSince(startTime) < timeout {
            if Task.isCancelled {
                throw CancellationError()
            }

            do {
                let (_, response) = try await session.data(from: healthURL)
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    logger.info("Backend health check passed")
                    return
                }
            } catch {
                // Backend not ready yet, continue waiting
            }

            try await Task.sleep(for: pollInterval)
            if Date().timeIntervalSince(startTime) > 1 {
                pollInterval = .milliseconds(500)
            }
        }

        throw BackendError.timeout
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

    // MARK: - Health Check

    func checkHealth() async -> Bool {
        let healthURL = backendURL.appendingPathComponent("health")
        let session = RemoteCertificatePinning.configuredSession()

        do {
            let (_, response) = try await session.data(from: healthURL)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
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
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        task.arguments = ["-i", ":\(port)", "-sTCP:LISTEN", "-t"]
        let pipe = Pipe()
        task.standardOutput = pipe
        task.standardError = FileHandle.nullDevice
        guard (try? task.run()) != nil else { return false }
        task.waitUntilExit()
        let data = (try? pipe.fileHandleForReading.readToEnd()) ?? Data()
        return !data.isEmpty
    }
    #endif
}

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
            return "Backend app not found in bundle. Build the engine with: " +
                "briefcase build macOS --app engine (in fichero-engine/), then rebuild Fichero in Xcode."
        case .launchFailed(let error):
            return "Failed to launch backend app: \(error.localizedDescription)"
        case .timeout:
            return "Backend failed to start within timeout"
        }
    }
}

// swiftlint:enable type_body_length
