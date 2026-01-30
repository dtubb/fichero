import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ArtifactsBrowserView")

/// View for browsing all artifacts in the library
struct ArtifactsBrowserView: View {
    @EnvironmentObject var artifactService: ArtifactServiceGenerated
    @EnvironmentObject var apiClient: APIClient

    @State private var artifacts: [Artifact] = []
    @State private var isLoading = false
    @State private var error: String?
    @State private var selectedArtifactType: String?
    @State private var searchText = ""
    @State private var sortOrder: ArtifactSortOrder = .newest

    enum ArtifactSortOrder: String, CaseIterable {
        case newest = "Newest"
        case oldest = "Oldest"
        case type = "Type"
        case document = "Document"
    }

    /// All unique artifact types from loaded artifacts
    private var artifactTypes: [String] {
        Array(Set(artifacts.map { $0.artifactType })).sorted()
    }

    /// Filtered and sorted artifacts
    private var displayedArtifacts: [Artifact] {
        var filtered = artifacts

        // Filter by type
        if let type = selectedArtifactType {
            filtered = filtered.filter { $0.artifactType == type }
        }

        // Filter by search
        if !searchText.isEmpty {
            filtered = filtered.filter { artifact in
                artifact.content?.localizedCaseInsensitiveContains(searchText) ?? false ||
                artifact.artifactType.localizedCaseInsensitiveContains(searchText) ||
                artifact.documentId.localizedCaseInsensitiveContains(searchText)
            }
        }

        // Sort
        switch sortOrder {
        case .newest:
            filtered.sort { $0.createdAt > $1.createdAt }
        case .oldest:
            filtered.sort { $0.createdAt < $1.createdAt }
        case .type:
            filtered.sort { $0.artifactType < $1.artifactType }
        case .document:
            filtered.sort { $0.documentId < $1.documentId }
        }

        return filtered
    }

    /// Group artifacts by type for the grouped view
    private var groupedArtifacts: [(String, [Artifact])] {
        let grouped = Dictionary(grouping: displayedArtifacts) { $0.artifactType }
        return grouped.sorted { $0.key < $1.key }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            toolbarView

            Divider()

            // Content
            if isLoading && artifacts.isEmpty {
                loadingView
            } else if let error = error {
                errorView(error)
            } else if artifacts.isEmpty {
                emptyView
            } else {
                artifactsContent
            }
        }
        .task {
            guard !Task.isCancelled else { return }
            await loadArtifacts()
        }
    }

    // MARK: - Toolbar

    @ViewBuilder
    private var toolbarView: some View {
        HStack(spacing: 12) {
            // Search field
            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField("Search artifacts...", text: $searchText)
                    .textFieldStyle(.plain)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(6)
            .background(Color(nsColor: .textBackgroundColor))
            .cornerRadius(6)

            // Type filter
            Picker("Type", selection: $selectedArtifactType) {
                Text("All Types").tag(nil as String?)
                Divider()
                ForEach(artifactTypes, id: \.self) { type in
                    Text(displayNameForType(type)).tag(type as String?)
                }
            }
            .frame(width: 150)

            // Sort order
            Picker("Sort", selection: $sortOrder) {
                ForEach(ArtifactSortOrder.allCases, id: \.self) { order in
                    Text(order.rawValue).tag(order)
                }
            }
            .frame(width: 120)

            Spacer()

            // Refresh button
            Button {
                Task { await loadArtifacts() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .disabled(isLoading)

            // Stats
            Text("\(displayedArtifacts.count) artifacts")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Content Views

    @ViewBuilder
    private var artifactsContent: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(groupedArtifacts, id: \.0) { type, artifacts in
                    artifactTypeSection(type: type, artifacts: artifacts)
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private func artifactTypeSection(type: String, artifacts: [Artifact]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Section header
            HStack {
                Image(systemName: iconForType(type))
                    .foregroundStyle(colorForType(type))
                Text(displayNameForType(type))
                    .font(.headline)
                Spacer()
                Text("\(artifacts.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Artifact cards
            LazyVGrid(columns: [
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12),
                GridItem(.flexible(), spacing: 12)
            ], spacing: 12) {
                ForEach(artifacts) { artifact in
                    artifactCard(artifact)
                }
            }
        }
    }

    @ViewBuilder
    private func artifactCard(_ artifact: Artifact) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack {
                Image(systemName: iconForType(artifact.artifactType))
                    .foregroundStyle(colorForType(artifact.artifactType))

                VStack(alignment: .leading, spacing: 2) {
                    Text(displayNameForType(artifact.artifactType))
                        .font(.caption)
                        .fontWeight(.medium)

                    if let provider = artifact.provider {
                        Text(provider)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Spacer()

                // Copy button
                if artifact.content != nil {
                    Button {
                        copyToClipboard(artifact.content ?? "")
                    } label: {
                        Image(systemName: "doc.on.doc")
                            .font(.caption)
                    }
                    .buttonStyle(.plain)
                }
            }

            Divider()

            // Content preview
            if let content = artifact.content, !content.isEmpty {
                Text(content)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
                    .textSelection(.enabled)
            } else if let data = artifact.data, !data.isEmpty {
                // Show structured data preview
                dataPreview(data)
            } else {
                Text("No content")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .italic()
            }

            Spacer(minLength: 0)

            // Footer
            HStack {
                Text("Doc: \(String(artifact.documentId.prefix(8)))...")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

                Spacer()

                Text(artifact.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(12)
        .frame(minHeight: 120)
        .background(Color(nsColor: .controlBackgroundColor))
        .cornerRadius(8)
    }

    @ViewBuilder
    private func dataPreview(_ data: [String: AnyCodable]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(data.keys.sorted().prefix(4)), id: \.self) { key in
                if let value = data[key] {
                    HStack(alignment: .top, spacing: 4) {
                        Text("\(key):")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .fontWeight(.medium)

                        Text(formatValue(value.value))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
            }

            if data.count > 4 {
                Text("+ \(data.count - 4) more fields...")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - State Views

    @ViewBuilder
    private var loadingView: some View {
        VStack(spacing: 16) {
            ProgressView()
            Text("Loading artifacts...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    @ViewBuilder
    private func errorView(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Error Loading Artifacts", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Retry") {
                Task { await loadArtifacts() }
            }
        }
    }

    @ViewBuilder
    private var emptyView: some View {
        ContentUnavailableView {
            Label("No Artifacts", systemImage: "sparkles")
        } description: {
            Text("Run workflows on documents to generate artifacts like transcriptions, summaries, and entity extractions.")
        }
    }

    // MARK: - Helpers

    private func loadArtifacts() async {
        isLoading = true
        error = nil
        defer { isLoading = false }

        do {
            artifacts = try await artifactService.getAllArtifacts(limit: 500)
            logger.info("Loaded \(artifacts.count) artifacts")
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load artifacts: \(error.localizedDescription)")
        }
    }

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    private func iconForType(_ type: String) -> String {
        switch type {
        case "transcription": return "text.quote"
        case "entities": return "person.3"
        case "summary_file", "summary_folder", "summary_collection", "summary": return "doc.text"
        case "description": return "eye"
        case "keywords": return "tag"
        case "sentiment": return "face.smiling"
        default: return "doc"
        }
    }

    private func colorForType(_ type: String) -> Color {
        switch type {
        case "transcription": return .blue
        case "entities": return .purple
        case "summary_file", "summary_folder", "summary_collection", "summary": return .orange
        case "description": return .green
        case "keywords": return .cyan
        case "sentiment": return .pink
        default: return .secondary
        }
    }

    private func displayNameForType(_ type: String) -> String {
        switch type {
        case "transcription": return "Transcription"
        case "entities": return "Entities"
        case "summary_file": return "File Summary"
        case "summary_folder": return "Folder Summary"
        case "summary_collection": return "Collection Summary"
        case "summary": return "Summary"
        case "description": return "Description"
        case "keywords": return "Keywords"
        case "sentiment": return "Sentiment"
        default: return type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func formatValue(_ value: Any) -> String {
        if let array = value as? [Any] {
            if array.count <= 3 {
                return array.map { String(describing: $0) }.joined(separator: ", ")
            } else {
                return "\(array.prefix(3).map { String(describing: $0) }.joined(separator: ", "))..."
            }
        }
        return String(describing: value)
    }
}

#Preview {
    ArtifactsBrowserView()
        .environmentObject(APIClient())
        .frame(width: 900, height: 600)
}
