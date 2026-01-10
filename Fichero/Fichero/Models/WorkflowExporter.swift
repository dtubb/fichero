import Foundation
import AppKit
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowExporter")

/// Utility for exporting workflows to files via backend API
enum WorkflowExporter {

    /// Export a workflow to a JSON file via save panel (calls backend API)
    @MainActor
    static func exportToFile(_ workflowId: String, name: String, using service: WorkflowService) async {
        do {
            // Get export data from backend
            let exportData = try await service.exportWorkflow(workflowId)

            // Show save panel
            let panel = NSSavePanel()
            panel.allowedContentTypes = [.json]
            panel.nameFieldStringValue = "\(name).json"

            if panel.runModal() == .OK, let url = panel.url {
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
                let data = try encoder.encode(exportData)
                try data.write(to: url)
                logger.info("Exported workflow to: \(url.path)")
            }
        } catch {
            logger.error("Failed to export workflow: \(error.localizedDescription)")
        }
    }
}
