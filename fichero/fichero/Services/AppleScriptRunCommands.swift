//
//  AppleScriptRunCommands.swift
//  Fichero
//
//  The workflow run-control half of the AppleScript dictionary: run (with a
//  declared document selection, #4414), status, pause, resume, and stop
//  (#4535). Split from AppleScriptCommands.swift for file length only.
//

#if os(macOS)
import Cocoa
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppleScript")

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
        // "on documents {…}" — an EXPLICIT scope. The ids are the selection;
        // the server validates and resolves what they mean (#4396/#4414).
        let selectedDocIds = (evaluatedArguments?["selectedDocIds"] as? [String]) ?? []

        logger.info("AppleScript: run workflow \(workflowId) (selection: \(selectedDocIds.count) ids)")

        do {
            let threadId = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.runWorkflow(
                    workflowId: workflowId,
                    inputs: inputs,
                    selectedDocIds: selectedDocIds
                )
            }
            return threadId
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}

/// Stop (cancel) a workflow run — the missing half of pause/resume (#4535).
@objc(FicheroStopRunCommand)
class FicheroStopRunCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let threadId = directParameter as? String, !threadId.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Thread ID is required"
            return nil
        }

        logger.info("AppleScript: stop run \(threadId)")

        do {
            let outcome = try runAsyncWithoutBlocking {
                try await AppleScriptBridge.shared.stopRun(threadId: threadId)
            }
            return outcome
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

#endif
