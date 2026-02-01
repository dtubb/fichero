import Foundation
import AppKit
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "EmbeddedBackend")

/// Manages the embedded Python backend lifecycle
@MainActor
final class EmbeddedBackendService: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var errorMessage: String?

    private var backendPID: pid_t?
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
            status = .running
            logger.info("Connected to external backend")
            return
        } catch {
            logger.info("No external backend found, launching embedded backend...")
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
        guard let pid = backendPID else {
            logger.info("No backend PID tracked, nothing to stop")
            return
        }

        logger.info("Stopping embedded backend (PID: \(pid))...")

        // Clear state immediately
        backendPID = nil
        status = .stopped

        // Graceful shutdown - send SIGTERM
        kill(pid, SIGTERM)

        // Wait up to 5 seconds for graceful shutdown in background
        Task.detached {
            for _ in 0..<50 {
                // Check if process is still running
                if kill(pid, 0) != 0 {
                    // Process no longer exists
                    break
                }
                try? await Task.sleep(for: .milliseconds(100))
            }

            // Force kill if still running
            if kill(pid, 0) == 0 {
                logger.warning("Backend didn't shut down gracefully, force killing...")
                kill(pid, SIGKILL)
            }
        }
    }

    deinit {
        // Clean up backend on service deallocation
        if let pid = backendPID {
            logger.info("EmbeddedBackendService deinit - terminating backend (PID: \(pid))")
            kill(pid, SIGTERM)
        }
    }

    // MARK: - Private Helpers

    private func launchEmbeddedBackend() throws {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BackendError.bundleNotFound
        }

        // Path to nested Briefcase backend app (arm64)
        let backendAppPath = "\(resourcePath)/FicheroBackend.app"

        // Check if backend app exists
        guard FileManager.default.fileExists(atPath: backendAppPath) else {
            logger.error("Backend app not found at: \(backendAppPath)")
            logger.error("Build backend with: ./scripts/build_backend_bundle.sh")
            throw BackendError.backendAppNotFound
        }

        let backendAppURL = URL(fileURLWithPath: backendAppPath)

        logger.info("Launching nested backend app at: \(backendAppPath)")

        // Launch the nested Briefcase app using modern NSWorkspaceOpenConfiguration
        // activates: false - Don't bring to front
        // hides: true - Hide from Dock
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        configuration.hides = true

        NSWorkspace.shared.openApplication(at: backendAppURL, configuration: configuration) { [weak self] app, error in
            Task { @MainActor in
                if let error = error {
                    logger.error("Failed to launch backend app: \(error)")
                    return
                }

                if let app = app {
                    logger.info("Backend app launched successfully (PID: \(app.processIdentifier))")
                    self?.backendPID = app.processIdentifier
                }
            }
        }
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
