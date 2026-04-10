import AppKit
import Foundation
import OSLog

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "WorkflowExporter")

/// Utility for importing/exporting workflows to files via backend API
enum WorkflowExporter {

    /// Export a workflow to a JSON file via save panel (calls backend API)
    @MainActor
    static func exportToFile(_ workflowId: String, name: String, using service: WorkflowServiceGenerated) async {
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

    /// Import a workflow from a JSON file via open panel (calls backend API)
    /// Returns the imported workflow ID on success, nil on cancel/failure
    @MainActor
    static func importFromFile(using service: WorkflowServiceGenerated) async -> String? {
        // Show open panel
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.message = "Select a workflow JSON file to import"

        guard panel.runModal() == .OK, let url = panel.url else {
            return nil
        }

        do {
            // Read file data
            let data = try Data(contentsOf: url)

            // Parse JSON
            guard let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                logger.error("Invalid JSON format in workflow file")
                return nil
            }

            // Convert to AnyCodable for the API
            let workflowData = json.mapValues { AnyCodable($0) }

            // Extract name from filename if not in JSON
            let fileName = url.deletingPathExtension().lastPathComponent
            let name = (json["name"] as? String) ?? fileName
            let description = (json["description"] as? String) ?? ""

            // Import via backend
            let response = try await service.importWorkflow(
                name: name,
                description: description,
                workflowData: workflowData
            )

            logger.info("Imported workflow '\(name)' with ID: \(response.id)")
            return response.id
        } catch {
            logger.error("Failed to import workflow: \(error.localizedDescription)")
            return nil
        }
    }
}
