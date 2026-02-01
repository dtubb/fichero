import Foundation
import Cocoa
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "AppleScript")

// MARK: - Async Helper

/// Thread-safe result box for runAsyncWithoutBlocking
private final class ResultBox<T>: @unchecked Sendable {
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
private struct SendableCFRunLoop: @unchecked Sendable {
    let runLoop: CFRunLoop
}

/// Helper to run async code from synchronous AppleScript commands without blocking the main thread.
/// Uses RunLoop to process events while waiting for the async operation to complete.
private func runAsyncWithoutBlocking<T: Sendable>(_ operation: @escaping @Sendable () async throws -> T) throws -> T {
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

// MARK: - Script Object Classes

/// Scriptable document representation
@objc(FicheroScriptDocument)
class FicheroScriptDocument: NSObject {
    @objc let id: String
    @objc let name: String
    @objc let path: String
    @objc let mimeType: String
    @objc let size: Int
    @objc let createdDate: Date
    @objc let modifiedDate: Date

    init(id: String, name: String, path: String, mimeType: String, size: Int, createdDate: Date, modifiedDate: Date) {
        self.id = id
        self.name = name
        self.path = path
        self.mimeType = mimeType
        self.size = size
        self.createdDate = createdDate
        self.modifiedDate = modifiedDate
    }
}

/// Scriptable workflow representation
@objc(FicheroScriptWorkflow)
class FicheroScriptWorkflow: NSObject {
    @objc let id: String
    @objc var name: String
    @objc var workflowDescription: String
    @objc let nodeCount: Int
    @objc var isEnabled: Bool

    init(id: String, name: String, description: String, nodeCount: Int, isEnabled: Bool) {
        self.id = id
        self.name = name
        self.workflowDescription = description
        self.nodeCount = nodeCount
        self.isEnabled = isEnabled
    }
}

/// Scriptable workflow chain representation
@objc(FicheroScriptWorkflowChain)
class FicheroScriptWorkflowChain: NSObject {
    @objc let id: String
    @objc var name: String
    @objc let stepCount: Int

    init(id: String, name: String, stepCount: Int) {
        self.id = id
        self.name = name
        self.stepCount = stepCount
    }
}

/// Scriptable execution thread representation
@objc(FicheroScriptExecutionThread)
class FicheroScriptExecutionThread: NSObject {
    @objc let id: String
    @objc let workflowId: String
    @objc let status: String

    init(id: String, workflowId: String, status: String) {
        self.id = id
        self.workflowId = workflowId
        self.status = status
    }
}

// MARK: - Script Commands

/// Run a workflow via AppleScript
@objc(FicheroRunWorkflowCommand)
class FicheroRunWorkflowCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let workflowId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Workflow ID is required"
            return nil
        }

        let inputs = evaluatedArguments?["inputs"] as? [String: any Sendable] ?? [:]

        logger.info("AppleScript: run workflow \(workflowId)")

        do {
            let threadId = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.runWorkflow(workflowId: workflowId, inputs: inputs)
            }
            return threadId
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}

/// Get workflow execution status
@objc(FicheroGetWorkflowStatusCommand)
class FicheroGetWorkflowStatusCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let threadId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Thread ID is required"
            return nil
        }

        logger.info("AppleScript: get workflow status \(threadId)")

        do {
            let status = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.getWorkflowStatus(threadId: threadId)
            }
            return status
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}

/// Pause a workflow
@objc(FicheroPauseWorkflowCommand)
class FicheroPauseWorkflowCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let threadId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Thread ID is required"
            return nil
        }

        logger.info("AppleScript: pause workflow \(threadId)")

        do {
            let success = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.pauseWorkflow(threadId: threadId)
            }
            return success
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return false
        }
    }
}

/// Resume a workflow
@objc(FicheroResumeWorkflowCommand)
class FicheroResumeWorkflowCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let threadId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Thread ID is required"
            return nil
        }

        logger.info("AppleScript: resume workflow \(threadId)")

        do {
            _ = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.resumeWorkflow(threadId: threadId)
            }
            return true
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return false
        }
    }
}

/// Run a workflow chain
@objc(FicheroRunChainCommand)
class FicheroRunChainCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let chainId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Chain ID is required"
            return nil
        }

        let inputs = evaluatedArguments?["inputs"] as? [String: any Sendable] ?? [:]

        logger.info("AppleScript: run chain \(chainId)")

        do {
            let executionId = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.runChain(chainId: chainId, inputs: inputs)
            }
            return executionId
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}

/// List all workflows
@objc(FicheroListWorkflowsCommand)
class FicheroListWorkflowsCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        logger.info("AppleScript: list workflows")

        do {
            let workflows = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.listWorkflows()
            }
            return workflows
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return []
        }
    }
}

/// List documents
@objc(FicheroListDocumentsCommand)
class FicheroListDocumentsCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        let folderPath = evaluatedArguments?["folderPath"] as? String
        let limit = evaluatedArguments?["limit"] as? Int ?? 100

        logger.info("AppleScript: list documents (folder: \(folderPath ?? "/"), limit: \(limit))")

        do {
            let documents = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.listDocuments(folderPath: folderPath, limit: limit)
            }
            return documents
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return []
        }
    }
}

/// Search documents
@objc(FicheroSearchDocumentsCommand)
class FicheroSearchDocumentsCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let query = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Search query is required"
            return nil
        }

        let limit = evaluatedArguments?["limit"] as? Int ?? 50

        logger.info("AppleScript: search documents '\(query)' (limit: \(limit))")

        do {
            let results = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.searchDocuments(query: query, limit: limit)
            }
            return results
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return []
        }
    }
}

/// Import a file
@objc(FicheroImportFileCommand)
class FicheroImportFileCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let filePath = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "File path is required"
            return nil
        }

        let folderPath = evaluatedArguments?["folderPath"] as? String
        let mode = evaluatedArguments?["mode"] as? String ?? "link"

        logger.info("AppleScript: import file '\(filePath)' (mode: \(mode))")

        do {
            let documentId = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.importFile(
                    filePath: filePath,
                    folderPath: folderPath,
                    mode: mode
                )
            }
            return documentId
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}

/// Get document info
@objc(FicheroGetDocumentInfoCommand)
class FicheroGetDocumentInfoCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let documentId = directParameter as? String else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Document ID is required"
            return nil
        }

        logger.info("AppleScript: get document info '\(documentId)'")

        do {
            let info = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.getDocumentInfo(documentId: documentId)
            }
            return info
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return [:]
        }
    }
}

// MARK: - AppleScript Bridge

/// Bridge to communicate with the Fichero backend API for AppleScript commands
@MainActor
class AppleScriptBridge {
    static let shared = AppleScriptBridge()

    private let baseURL = URL(string: "http://127.0.0.1:8765/api")!
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

        let body: [String: any Sendable] = [
            "workflow_id": workflowId,
            "inputs": inputs,
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["thread_id"] as? String ?? ""
    }

    func getWorkflowStatus(threadId: String) async throws -> String {
        let url = baseURL.appendingPathComponent("workflow-execution/threads/\(threadId)/status")
        let (data, _) = try await session.data(from: url)
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
        request.httpBody = "{}".data(using: .utf8)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["status"] as? String ?? "unknown"
    }

    func listWorkflows() async throws -> [String] {
        let url = baseURL.appendingPathComponent("workflows")
        let (data, _) = try await session.data(from: url)
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

        let body: [String: any Sendable] = [
            "inputs": inputs,
            "input_files": [] as [String],
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await session.data(for: request)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        return result?["execution_id"] as? String ?? ""
    }

    // MARK: - Document Operations

    func listDocuments(folderPath: String?, limit: Int) async throws -> [String] {
        var urlComponents = URLComponents(url: baseURL.appendingPathComponent("documents"), resolvingAgainstBaseURL: false)!
        urlComponents.queryItems = [
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        if let folder = folderPath {
            urlComponents.queryItems?.append(URLQueryItem(name: "folder_path", value: folder))
        }

        let (data, _) = try await session.data(from: urlComponents.url!)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let documents = result?["documents"] as? [[String: Any]] ?? []
        return documents.compactMap { $0["name"] as? String }
    }

    func searchDocuments(query: String, limit: Int) async throws -> [String] {
        var urlComponents = URLComponents(url: baseURL.appendingPathComponent("search"), resolvingAgainstBaseURL: false)!
        urlComponents.queryItems = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: String(limit)),
        ]

        let (data, _) = try await session.data(from: urlComponents.url!)
        let result = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let documents = result?["documents"] as? [[String: Any]] ?? []
        return documents.compactMap { $0["name"] as? String }
    }

    func importFile(filePath: String, folderPath: String?, mode: String) async throws -> String {
        let url = baseURL.appendingPathComponent("ingest/file")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        var body: [String: Any] = [
            "source_path": filePath,
            "mode": mode.uppercased(),
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
        let (data, _) = try await session.data(from: url)
        return try JSONSerialization.jsonObject(with: data) as? [String: any Sendable] ?? [:]
    }
}
