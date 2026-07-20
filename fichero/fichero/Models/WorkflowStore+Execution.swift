import FicheroAPIClient
import OSLog

extension WorkflowStore {
    // MARK: - Workflow Execution

    /// Execute a saved workflow by ID
    func executeWorkflow(
        _ workflowId: String,
        inputs: [String: Any] = [:],
        interruptBefore: [String] = [],
        interruptAfter: [String] = []
    ) async throws -> ExecutionThread {
        do {
            let thread = try await executionService.executeWorkflow(
                workflowId: workflowId,
                inputs: inputs,
                interruptBefore: interruptBefore,
                interruptAfter: interruptAfter
            )
            logger.info("Started execution of workflow \(workflowId), thread: \(thread.threadId)")
            return thread
        } catch {
            self.error = error
            logger.error("Failed to execute workflow \(workflowId): \(String(describing: error))")
            throw error
        }
    }

    /// Get the status of an execution thread
    func getExecutionStatus(_ threadId: String) async throws -> ExecutionThread {
        do {
            return try await executionService.getThreadStatus(threadId: threadId)
        } catch {
            self.error = error
            throw error
        }
    }

    /// Resume a paused workflow
    func resumeExecution(_ threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionThread {
        do {
            let thread = try await executionService.resumeWorkflow(threadId: threadId, inputs: inputs)
            logger.info("Resumed workflow thread: \(threadId)")
            return thread
        } catch {
            self.error = error
            logger.error("Failed to resume workflow thread \(threadId): \(String(describing: error))")
            throw error
        }
    }

    /// List all execution threads
    func listExecutionThreads(limit: Int = 100) async throws -> [ExecutionThread] {
        do {
            return try await executionService.listThreads(limit: limit)
        } catch {
            self.error = error
            throw error
        }
    }

    /// Delete an execution thread
    func deleteExecutionThread(_ threadId: String) async throws {
        do {
            try await executionService.deleteThread(threadId: threadId)
            logger.info("Deleted execution thread: \(threadId)")
        } catch {
            self.error = error
            throw error
        }
    }
}
