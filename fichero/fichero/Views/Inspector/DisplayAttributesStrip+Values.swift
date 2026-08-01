import FicheroAPIClient
import SwiftUI

extension DisplayAttributesStrip {
    // MARK: - Artifact helpers

    func displayName(for type: String) -> String {
        artifacts.first { $0.artifactType == type }?.artifactTypeDisplayName
            ?? type.capitalized
    }

    /// Value shown for an artifact row: the most-recent artifact's relative
    /// date, prefixed with a count when several of that type exist.
    func artifactValue(for type: String) -> String {
        let matching = artifacts.filter { $0.artifactType == type }
        guard let latest = matching.max(by: { $0.createdAt < $1.createdAt }) else {
            return "—"
        }
        let date = relativeDateString(latest.createdAt)
        return matching.count > 1 ? "\(matching.count) · \(date)" : date
    }

    func loadArtifacts() async {
        // Scope the shared store to this document (own artifacts only, a page
        // shows just its own); the strip reads `artifactStore.items` reactively
        // and live-updates on artifact.* change events (#3427).
        await artifactStore.setScope(documentId: document.id, includeDescendants: false)
    }

    /// Load KG counts for the opt-in Entities/Claims rows. Mirrors the KG
    /// tab's canonical document KG query so summary counts and KG rows
    /// cannot drift across independent read paths (#1304).
    func loadKnowledgeGraph() async {
        do {
            let response = try await entityService.documentKnowledgeGraph(
                documentId: document.id,
                includeChildren: includeChildren
            )
            claimCount = response.claimCount
            entityCount = response.entityCount
        } catch {
            if error.isCancellationError {
                // Superseded by a newer selection — leave the last counts in place.
                return
            }
            // KG is optional context — clear the counts so the rows show "—"
            // while the toggles stay available.
            claimCount = nil
            entityCount = nil
        }
    }

    // MARK: - Metadata helpers

    /// Title-case a raw metadata key (e.g. "File_Size" → "File Size").
    func metadataLabel(for key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ")
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    /// Render a metadata value for the strip. Byte sizes are formatted, JSON
    /// collections are summarised by shape, everything else stringified — so
    /// the meaningful bit reads cleanly in a one-line row (#1246).
    func metadataValue(for key: String) -> String {
        guard let raw = document.metadata[key]?.value else { return "—" }
        let lower = key.lowercased()
        if lower.contains("size") || lower.contains("bytes") {
            if let intVal = raw as? Int {
                return ByteCountFormatter.string(fromByteCount: Int64(intVal), countStyle: .file)
            }
            if let strVal = raw as? String, let intVal = Int(strVal) {
                return ByteCountFormatter.string(fromByteCount: Int64(intVal), countStyle: .file)
            }
        }
        if let array = raw as? [Any] {
            return array.count == 1 ? "1 item" : "\(array.count) items"
        }
        if let dict = raw as? [String: Any] {
            return dict.count == 1 ? "1 field" : "\(dict.count) fields"
        }
        return String(describing: raw)
    }

    // MARK: - Value computation

    var statusValue: String {
        switch document.status {
        case .pending: return "Pending"
        case .processing: return "Processing"
        case .completed: return "Completed"
        case .failed: return "Failed"
        }
    }

    var statusColor: Color {
        switch document.status {
        case .pending: return .secondary
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }

    var kindValue: String {
        switch document.docType {
        case .folder: return "Folder"
        case .group: return "Group"
        case .file:
            if let fileType = document.fileType {
                return fileType.rawValue.uppercased()
            }
            return "File"
        case .page: return "Page"
        case .chunk: return "Chunk"
        }
    }

    func relativeDateString(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
