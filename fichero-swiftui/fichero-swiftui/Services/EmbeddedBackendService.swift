import AppKit
import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "EmbeddedBackend")

/// Manages the embedded Python backend lifecycle
@MainActor
final class EmbeddedBackendService: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var errorMessage: String?

    private var backendPID: pid_t?
    private var isExternalBackend = false  // Track if using external vs embedded backend
    private let backendURL = URL(string: "http://127.0.0.1:8765")!

    enum BackendStatus {
        case stopped
        case starting
        case running
        case failed
    }

    // MARK: - Lifecycle

    /// Start the embedded backend
    func start() async throws {
        logger.info("Starting embedded backend...")
        status = .starting

        #if DEBUG
        // Development mode: Try external backend first, fall back to embedded
        logger.info("DEBUG mode: Checking for external backend on port 8765")

        do {
            try await waitForBackend(timeout: 2)
            let supportsWorkflows = await backendSupportsWorkflowRoutes()
            if supportsWorkflows {
                status = .running
                isExternalBackend = true
                logger.info("✅ Connected to external backend (will not manage lifecycle)")
                logger.warning("⚠️  External backend will NOT be stopped when app quits (user-managed)")
                return
            }

            logger.warning(
                "⚠️ External backend lacks /api/workflows routes (404); launching embedded dev-tier backend instead"
            )
            isExternalBackend = false
        } catch {
            logger.info("No external backend found, launching embedded backend...")
            isExternalBackend = false
        }
        #endif

        // Launch embedded backend (DEBUG fallback or RELEASE always)
        try launchEmbeddedBackend()
        try await waitForBackend(timeout: 30)
        status = .running
        logger.info("Embedded backend started successfully")
    }

    /// Stop the embedded backend
    func stop() {
        // Don't stop external backends (user-managed)
        if isExternalBackend {
            logger.info("🔌 Using external backend - leaving it running (user-managed)")
            status = .stopped
            return
        }

        guard let pid = backendPID else {
            logger.info("ℹ️  No embedded backend PID tracked (may not have launched yet or using external)")
            status = .stopped
            return
        }

        logger.info("🛑 Stopping embedded backend (PID: \(pid))...")

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
                logger.info("✅ Backend stopped gracefully after \(attempt * 100)ms")
                return
            }
            // Sleep for 100ms
            Thread.sleep(forTimeInterval: 0.1)
        }

        // Force kill if still running after 5 seconds
        if kill(pid, 0) == 0 {
            logger.warning("⚠️ Backend didn't shut down gracefully after 5s, force killing...")
            kill(pid, SIGKILL)

            // Give it one more second to die
            Thread.sleep(forTimeInterval: 1.0)

            if kill(pid, 0) == 0 {
                logger.error("❌ Failed to kill backend process (PID: \(pid))")
            } else {
                logger.info("✅ Backend force-killed successfully")
            }
        }
    }

    deinit {
        // Clean up backend on service deallocation (shouldn't happen in normal app lifecycle)
        if let pid = backendPID, !isExternalBackend {
            logger.warning("⚠️  EmbeddedBackendService deinit - terminating backend (PID: \(pid))")
            logger.warning("⚠️  This shouldn't happen in normal app lifecycle - backend should be stopped via stop()")
            kill(pid, SIGTERM)
        }
    }

    // MARK: - Private Helpers

    private func launchEmbeddedBackend() throws {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BackendError.bundleNotFound
        }

        // Path to nested Briefcase backend app's executable
        let backendAppPath = "\(resourcePath)/FicheroBackend.app"
        let executablePath = "\(backendAppPath)/Contents/MacOS/FicheroBackend"

        // Check if backend executable exists
        guard FileManager.default.fileExists(atPath: executablePath) else {
            logger.error("Backend executable not found at: \(executablePath)")
            logger.error("Build backend with: ./scripts/build_backend_bundle.sh")
            throw BackendError.backendAppNotFound
        }

        logger.info("Launching backend process: \(executablePath)")

        // Use Process for direct process control - much simpler than NSWorkspace
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executablePath)
        process.arguments = []
        var environment = ProcessInfo.processInfo.environment
        #if DEBUG
        // Ensure workflow/provider routes are available for debug UI surfaces.
        environment["FICHERO_FEATURE_TIER"] = environment["FICHERO_FEATURE_TIER"] ?? "dev"
        #endif
        process.environment = environment

        // Redirect output to /dev/null (or we could log it)
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        // Launch the process
        try process.run()

        let pid = process.processIdentifier
        logger.info("✅ Backend process launched successfully (PID: \(pid))")

        // Store PID and process reference
        backendPID = pid
        isExternalBackend = false
        logger.info("📍 Tracking embedded backend PID: \(pid)")
    }

    private func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        let healthURL = backendURL.appendingPathComponent("api/health")

        while Date().timeIntervalSince(startTime) < timeout {
            if Task.isCancelled {
                throw CancellationError()
            }

            do {
                let (_, response) = try await URLSession.shared.data(from: healthURL)
                if let httpResponse = response as? HTTPURLResponse,
                   httpResponse.statusCode == 200 {
                    logger.info("Backend health check passed")
                    return
                }
            } catch {
                // Backend not ready yet, continue waiting
            }

            try await Task.sleep(for: .seconds(1))
        }

        throw BackendError.timeout
    }

    private func backendSupportsWorkflowRoutes() async -> Bool {
        let workflowsURL = backendURL.appendingPathComponent("api/workflows")
        var request = URLRequest(url: workflowsURL)
        request.httpMethod = "GET"

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            // Missing library header may return 422; route absence returns 404.
            return httpResponse.statusCode != 404
        } catch {
            return false
        }
    }

    // MARK: - Health Check

    func checkHealth() async -> Bool {
        let healthURL = backendURL.appendingPathComponent("health")

        do {
            let (_, response) = try await URLSession.shared.data(from: healthURL)
            return (response as? HTTPURLResponse)?.statusCode == 200
        } catch {
            return false
        }
    }
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
            return "Backend app not found in bundle. Run: ./scripts/build_backend_bundle.sh"
        case .launchFailed(let error):
            return "Failed to launch backend app: \(error.localizedDescription)"
        case .timeout:
            return "Backend failed to start within timeout"
        }
    }
}
