import Foundation
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "EmbeddedBackend")

/// Manages the embedded Python backend lifecycle
@MainActor
final class EmbeddedBackendService: ObservableObject {
    @Published var status: BackendStatus = .stopped
    @Published var errorMessage: String?

    private var process: Process?
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
        // Development mode: expect external backend
        logger.info("DEBUG mode: Checking for external backend on port 8765")
        logger.info("Start backend with: PYTHONPATH=src uvicorn fichero.api.main:app --reload --port 8765")

        do {
            try await waitForBackend(timeout: 3)
            status = .running
            logger.info("Connected to external backend")
        } catch {
            status = .failed
            errorMessage = """
            Backend not running. Please start it with:
            cd \(FileManager.default.currentDirectoryPath)
            PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --reload --port 8765
            """
            throw BackendError.notRunning
        }
        #else
        // Production mode: launch embedded backend
        try launchEmbeddedBackend()
        try await waitForBackend(timeout: 30)
        status = .running
        logger.info("Embedded backend started successfully")
        #endif
    }

    /// Stop the embedded backend
    func stop() {
        guard let process = process else { return }

        logger.info("Stopping embedded backend...")

        // Graceful shutdown
        if process.isRunning {
            process.terminate()

            // Wait up to 5 seconds for graceful shutdown
            DispatchQueue.global().async {
                for _ in 0..<50 {
                    if !process.isRunning {
                        break
                    }
                    Thread.sleep(forTimeInterval: 0.1)
                }

                // Force kill if still running
                if process.isRunning {
                    kill(process.processIdentifier, SIGKILL)
                }
            }
        }

        self.process = nil
        status = .stopped
    }

    // MARK: - Private Helpers

    private func launchEmbeddedBackend() throws {
        guard let resourcePath = Bundle.main.resourcePath else {
            throw BackendError.bundleNotFound
        }

        let pythonPath = "\(resourcePath)/python/bin/python3"
        let scriptPath = "\(resourcePath)/python/start_backend.py"

        // Check if files exist
        guard FileManager.default.fileExists(atPath: pythonPath) else {
            logger.error("Python executable not found at: \(pythonPath)")
            throw BackendError.pythonNotFound
        }

        guard FileManager.default.fileExists(atPath: scriptPath) else {
            logger.error("Backend script not found at: \(scriptPath)")
            throw BackendError.scriptNotFound
        }

        // Create process
        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath]

        // Set up environment
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONHOME"] = "\(resourcePath)/python"
        environment["PYTHONPATH"] = "\(resourcePath)/python/lib/python3.10/site-packages"
        environment["TOKENIZERS_PARALLELISM"] = "false"
        process.environment = environment

        // Set up output pipes for logging
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        process.standardOutput = outputPipe
        process.standardError = errorPipe

        // Log backend output
        outputPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                logger.info("[Backend] \(output.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        errorPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if let output = String(data: data, encoding: .utf8), !output.isEmpty {
                logger.error("[Backend] \(output.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        // Launch
        logger.info("Launching Python backend at: \(pythonPath)")
        try process.run()

        self.process = process
    }

    private func waitForBackend(timeout: TimeInterval) async throws {
        let startTime = Date()
        let healthURL = backendURL.appendingPathComponent("health")

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
    case pythonNotFound
    case scriptNotFound
    case timeout

    var errorDescription: String? {
        switch self {
        case .notRunning:
            return "Backend is not running"
        case .bundleNotFound:
            return "App bundle resources not found"
        case .pythonNotFound:
            return "Python interpreter not found in bundle"
        case .scriptNotFound:
            return "Backend script not found in bundle"
        case .timeout:
            return "Backend failed to start within timeout"
        }
    }
}
