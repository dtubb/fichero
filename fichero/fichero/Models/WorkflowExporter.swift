#if canImport(AppKit)
import AppKit
#endif
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "WorkflowExporter")

/// Utility for importing/exporting workflows to files via backend API
#if os(macOS)

enum WorkflowExporter {
    enum ImportError: LocalizedError {
        case invalidTopLevelObject

        var errorDescription: String? {
            switch self {
            case .invalidTopLevelObject:
                return "Workflow import file must contain a JSON object."
            }
        }
    }

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
    static func importFromFile(using service: WorkflowServiceGenerated) async throws -> String? {
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
                throw ImportError.invalidTopLevelObject
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
            throw error
        }
    }
}

#else

// iOS stub: workflow import/export uses document picker on iOS; these methods no-op.
enum WorkflowExporter {
    @MainActor
    static func exportToFile(_ workflowId: String, name: String, using service: WorkflowServiceGenerated) async {
        // No-op on iOS.
    }

    @MainActor
    static func importFromFile(using service: WorkflowServiceGenerated) async throws -> String? {
        // iOS: import would be handled via UIDocumentPickerViewController.
        return nil
    }
}

#endif
