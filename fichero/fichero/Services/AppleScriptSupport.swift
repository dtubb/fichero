#if os(macOS)
import Cocoa
#endif
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

#if os(macOS)

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppleScript")

// MARK: - Errors

enum AppleScriptBridgeError: Error {
    case validationError(String)
    case unexpectedResponse(Int)
}

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

    // #4024: run on a DETACHED task, not `Task { @MainActor }`. The caller (an AppleScript
    // command, or the main-thread test) blocks the MainActor by spinning its RunLoop below,
    // so a MainActor-isolated task could never start on that monopolized executor — it hung.
    // A detached task runs off-MainActor immediately; any actor-isolated (e.g. @MainActor
    // AppleScriptBridge) call it awaits hops onto the MainActor, which the RunLoop pump below
    // services, then it stops the caller's run loop.
    Task.detached {
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

/// Bridge to communicate with the Fichero backend API for AppleScript commands.
/// Uses the generated OpenAPI client for typed, pinned, authed transport.
@MainActor
class AppleScriptBridge {
    static let shared = AppleScriptBridge()

    private let client: FicheroClient
    private let workflowExecutionService: WorkflowExecutionService
    private nonisolated(unsafe) var hostChangeObservation: NSObjectProtocol?

    private init() {
        self.client = FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
        self.workflowExecutionService = WorkflowExecutionService(ficheroClient: client)
        // Rebind on a pairing / Settings host change (#2349) — otherwise AppleScript
        // workflow commands keep hitting the launch host (localhost) after the app
        // has moved to a remote engine.
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.client.reconfigure(baseURL: EngineConfig.host)
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    // MARK: - Workflow Operations

    func runWorkflow(workflowId: String, inputs: [String: any Sendable]) async throws -> String {
        let accepted = try await workflowExecutionService.executeAccepted(
            workflowId: workflowId,
            inputs: Dictionary(uniqueKeysWithValues: inputs.map { ($0.key, $0.value as Any) })
        )
        return accepted.threadId
    }

    func getWorkflowStatus(threadId: String) async throws -> String {
        let status = try await workflowExecutionService.getThreadStatus(threadId: threadId)
        return status.status.rawValue
    }

    func pauseWorkflow(threadId: String) async throws -> Bool {
        try await workflowExecutionService.pauseWorkflow(threadId: threadId)
        return true
    }

    func resumeWorkflow(threadId: String) async throws -> String {
        let status = try await workflowExecutionService.resumeWorkflow(threadId: threadId)
        return status.status.rawValue
    }

    func listWorkflows() async throws -> [String] {
        let response = try await client.api.listWorkflowsApiWorkflowsGet(.init())

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map(\.name)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Chain Operations

    func runChain(chainId: String, inputs: [String: any Sendable]) async throws -> String {
        let response = try await client.api.executeChainApiChainsChainIdExecutePost(
            path: .init(chainId: chainId),
            body: .json(.init(
                inputs: .init(additionalProperties: try makeObjectContainer(inputs))
            ))
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.executionId
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Document Operations

    func listDocuments(folderPath: String?, limit: Int) async throws -> [String] {
        // ponytail: legacy AppleScript param was a path string; the generated /api/documents
        // filter is parent_id. Passing the value through preserves the caller contract.
        let response = try await client.api.listDocumentsApiDocumentsGet(
            query: .init(parentId: folderPath, limit: limit)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map(\.name)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    func searchDocuments(query: String, limit: Int) async throws -> [String] {
        let response = try await client.api.enhancedSearchApiSearchPost(
            body: .json(.init(query: query, limit: limit))
        )

        switch response {
        case .ok(let okResponse):
            let results = try okResponse.body.json.results
            return results.map { result in
                result.metadata.additionalProperties.value["name"] as? String ?? result.documentId
            }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    func importFile(filePath: String, folderPath: String?, mode: String) async throws -> String {
        let response = try await client.api.ingestFileApiIngestFilePost(
            body: .json(.init(
                path: filePath,
                parentId: folderPath,
                copyMode: mode.uppercased() == "COPY"
            ))
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.id ?? ""
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    func getDocumentInfo(documentId: String) async throws -> [String: any Sendable] {
        let response = try await client.api.getDocumentApiDocumentsDocIdGet(
            path: .init(docId: documentId)
        )

        switch response {
        case .ok(let okResponse):
            let document = try okResponse.body.json
            return try encodeToSendableDictionary(document)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw AppleScriptBridgeError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw AppleScriptBridgeError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Helpers

    private func makeObjectContainer(_ inputs: [String: any Sendable]) throws -> OpenAPIObjectContainer {
        try OpenAPIObjectContainer(unvalidatedValue: inputs.mapValues { $0 as (any Sendable)? })
    }

    private func encodeToSendableDictionary<T: Encodable>(_ value: T) throws -> [String: any Sendable] {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(value)
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
