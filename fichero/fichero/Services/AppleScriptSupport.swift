#if os(macOS)
import Cocoa
#endif
import Foundation
import OSLog

#if os(macOS)

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppleScript")

// MARK: - Async Helper

/// Thread-safe result box for runAsyncWithoutBlocking
final class ResultBox<T>: @unchecked Sendable {
    private var result: Result<T, Error>?
    private let lock = NSLock()

    func set(_ newValue: Result<T, Error>) {
        lock.lock()
        defer { lock.unlock() }
        result = newValue
    }

    func get() -> Result<T, Error>? {
        lock.lock()
        defer { lock.unlock() }
        return result
    }
}

/// Sendable wrapper for CFRunLoop
struct SendableCFRunLoop: @unchecked Sendable {
    let runLoop: CFRunLoop
}

/// Helper to run async code from synchronous AppleScript commands without blocking the main thread.
/// Uses RunLoop to process events while waiting for the async operation to complete.
func runAsyncWithoutBlocking<T: Sendable>(_ operation: @escaping @Sendable () async throws -> T) throws -> T {
    let resultBox = ResultBox<T>()
    let runLoop = RunLoop.current
    let sendableRunLoop = SendableCFRunLoop(runLoop: runLoop.getCFRunLoop())

    Task { @MainActor in
        do {
            let value = try await operation()
            resultBox.set(.success(value))
        } catch {
            resultBox.set(.failure(error))
        }
        CFRunLoopStop(sendableRunLoop.runLoop)
    }

    // Process events until the async operation completes
    // This allows the main thread to remain responsive
    while resultBox.get() == nil {
        runLoop.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
    }

    switch resultBox.get()! {
    case .success(let value):
        return value
    case .failure(let error):
        throw error
    }
}

// MARK: - AppleScript Bridge

/// Bridge to communicate with the Fichero backend API for AppleScript commands
@MainActor
class AppleScriptBridge {
    static let shared = AppleScriptBridge()

    private var baseURL: URL { EngineConfig.apiBaseURL }

    /// GET request with engine Bearer token (#742). Replaces former
    /// `session.data(from: url)` callsites which strip headers.
    private func authedGet(_ url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.addEngineAuth()
        return request
    }
    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = 120
        self.session = URLSession(configuration: config)
    }

    // MARK: - Workflow Operations

    func runWorkflow(workflowId: String, inputs: [String: any Sendable]) async throws -> String {
        let url = baseURL.appendingPathComponent("workflow-execution/execute")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()

        let body: [String: any Sendable] = [
            "workflow_id": workflowId,
            "inputs": inputs
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["thread_id"] as? String ?? ""
    }

    func getWorkflowStatus(threadId: String) async throws -> String {
        let url = baseURL.appendingPathComponent("workflow-execution/threads/\(threadId)/status")
        let (data, _) = try await session.data(for: authedGet(url))
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["status"] as? String ?? "unknown"
    }

    func pauseWorkflow(threadId: String) async throws -> Bool {
        // Note: Pause endpoint not implemented - workflows use interrupt_before/after for checkpointing
        // This returns false until pause functionality is added
        return false
    }

    func resumeWorkflow(threadId: String) async throws -> String {
        let url = baseURL.appendingPathComponent("workflow-execution/threads/\(threadId)/resume")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()
        request.httpBody = Data("{}".utf8)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["status"] as? String ?? "unknown"
    }

    func listWorkflows() async throws -> [String] {
        let url = baseURL.appendingPathComponent("workflows")
        let (data, _) = try await session.data(for: authedGet(url))
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let workflows = result?["workflows"] as? [[String: Any]] ?? []
        return workflows.compactMap { $0["name"] as? String }
    }

    // MARK: - Chain Operations

    func runChain(chainId: String, inputs: [String: any Sendable]) async throws -> String {
        let url = baseURL.appendingPathComponent("chains/\(chainId)/execute")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()

        let body: [String: any Sendable] = [
            "inputs": inputs,
            "input_files": [] as [String]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["execution_id"] as? String ?? ""
    }

    // MARK: - Document Operations

    func listDocuments(folderPath: String?, limit: Int) async throws -> [String] {
        var urlComponents = URLComponents(
            url: baseURL.appendingPathComponent("documents"),
            resolvingAgainstBaseURL: false
        )!
        urlComponents.queryItems = [
            URLQueryItem(name: "limit", value: String(limit))
        ]
        if let folder = folderPath {
            urlComponents.queryItems?.append(URLQueryItem(name: "folder_path", value: folder))
        }

        let (data, _) = try await session.data(for: authedGet(urlComponents.url!))
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let documents = result?["documents"] as? [[String: Any]] ?? []
        return documents.compactMap { $0["name"] as? String }
    }

    func searchDocuments(query: String, limit: Int) async throws -> [String] {
        var urlComponents = URLComponents(
            url: baseURL.appendingPathComponent("search"),
            resolvingAgainstBaseURL: false
        )!
        urlComponents.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: String(limit))
        ]

        let (data, _) = try await session.data(for: authedGet(urlComponents.url!))
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let documents = result?["documents"] as? [[String: Any]] ?? []
        return documents.compactMap { $0["name"] as? String }
    }

    func importFile(filePath: String, folderPath: String?, mode: String) async throws -> String {
        let url = baseURL.appendingPathComponent("ingest/file")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addEngineAuth()

        var body: [String: Any] = [
            "source_path": filePath,
            "mode": mode.uppercased()
        ]
        if let folder = folderPath {
            body["parent_id"] = folder
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["id"] as? String ?? ""
    }

    func getDocumentInfo(documentId: String) async throws -> [String: any Sendable] {
        let url = baseURL.appendingPathComponent("documents/\(documentId)")
        let (data, _) = try await session.data(for: authedGet(url))
        return try JSONSerialization.jsonObject(with: data) as? [String: any Sendable] ?? [:]
    }
}
#else

// iOS stub: AppleScript bridge is macOS-only. These symbols are only referenced
// from AppleScriptCommands.swift, which is also gated, so minimal no-op stubs
// keep the module interface consistent on iOS.

final class ResultBox<T>: @unchecked Sendable {
    private var result: Result<T, Error>?
    private let lock = NSLock()

    func set(_ newValue: Result<T, Error>) {
        lock.lock()
        defer { lock.unlock() }
        result = newValue
    }

    func get() -> Result<T, Error>? {
        lock.lock()
        defer { lock.unlock() }
        return result
    }
}

struct SendableCFRunLoop: @unchecked Sendable {
    let runLoop: CFRunLoop
}

func runAsyncWithoutBlocking<T: Sendable>(_ operation: @escaping @Sendable () async throws -> T) throws -> T {
    let sem = DispatchSemaphore(value: 0)
    let resultBox = ResultBox<T>()
    Task { @MainActor in
        do {
            resultBox.set(.success(try await operation()))
        } catch {
            resultBox.set(.failure(error))
        }
        sem.signal()
    }
    sem.wait()
    switch resultBox.get()! {
    case .success(let value): return value
    case .failure(let error): throw error
    }
}

@MainActor
class AppleScriptBridge {
    static let shared = AppleScriptBridge()
    private init() {}

    func runWorkflow(workflowId: String, inputs: [String: any Sendable]) async throws -> String { "" }
    func getWorkflowStatus(threadId: String) async throws -> String { "unknown" }
    func pauseWorkflow(threadId: String) async throws -> Bool { false }
    func resumeWorkflow(threadId: String) async throws -> String { "unknown" }
    func listWorkflows() async throws -> [String] { [] }
    func runChain(chainId: String, inputs: [String: any Sendable]) async throws -> String { "" }
    func listDocuments(folderPath: String?, limit: Int) async throws -> [String] { [] }
    func searchDocuments(query: String, limit: Int) async throws -> [String] { [] }
    func importFile(filePath: String, folderPath: String?, mode: String) async throws -> String { "" }
    func getDocumentInfo(documentId: String) async throws -> [String: any Sendable] { [:] }
}

#endif
