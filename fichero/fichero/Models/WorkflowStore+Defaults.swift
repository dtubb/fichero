import FicheroAPIClient

extension WorkflowStore {
    // MARK: - Default Templates

    /// Install built-in default workflows if they are missing.
    @discardableResult
    func installDefaultWorkflowTemplates() async throws -> [WorkflowSidebarItem] {
        try await syncDefaultWorkflowTemplates(resetExisting: false)
    }

    /// Remove and recreate built-in default workflows.
    @discardableResult
    func resetDefaultWorkflowTemplates() async throws -> [WorkflowSidebarItem] {
        try await syncDefaultWorkflowTemplates(resetExisting: true)
    }

    @discardableResult
    private func syncDefaultWorkflowTemplates(resetExisting: Bool) async throws -> [WorkflowSidebarItem] {
        // The Swift-side `DefaultWorkflowTemplate` enum used to define
        // a few simple Transcribe templates here, but those overlapped
        // with backend-shipped defaults (Catalogue, Transcribe,
        // Catalogue (composable), Apple variants) and just created
        // duplicates. Source of truth is now backend JSON in
        // fichero-server/src/fichero_server/resources/default_workflows/. (#722 part 1)
        //
        // The reset path delegates to `reinstallDefaults` which deletes
        // existing presets server-side and re-seeds from the backend's
        // canonical JSON. Install is a no-op because `loadWorkflows`
        // already re-seeds defaults on every session start (see line 59).
        if resetExisting {
            try await workflowService.reinstallDefaults()
        }
        await loadWorkflows()

        // Return the system-default workflows that exist after the
        // operation so callers (e.g., the "Reset Defaults" button) can
        // surface a "Reinstalled N workflows" message.
        return workflows.filter(\.isSystem)
    }
}
