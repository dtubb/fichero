import Foundation
import Cocoa
import OSLog

let appleScriptCommandsLogger = Logger(subsystem: "ca.tubb.Fichero", category: "AppleScript")

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

        appleScriptCommandsLogger.info("AppleScript: run workflow \(workflowId)")

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

        appleScriptCommandsLogger.info("AppleScript: get workflow status \(threadId)")

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

        appleScriptCommandsLogger.info("AppleScript: pause workflow \(threadId)")

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

        appleScriptCommandsLogger.info("AppleScript: resume workflow \(threadId)")

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

        appleScriptCommandsLogger.info("AppleScript: run chain \(chainId)")

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
        appleScriptCommandsLogger.info("AppleScript: list workflows")

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

        appleScriptCommandsLogger.info("AppleScript: list documents (folder: \(folderPath ?? "/"), limit: \(limit))")

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

        appleScriptCommandsLogger.info("AppleScript: search documents '\(query)' (limit: \(limit))")

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

        appleScriptCommandsLogger.info("AppleScript: import file '\(filePath)' (mode: \(mode))")

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

        appleScriptCommandsLogger.info("AppleScript: get document info '\(documentId)'")

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
