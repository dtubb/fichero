import SwiftUI

// TODO: Refactor DocumentInspector - extract artifacts section to separate view component
// Type body is 438 lines, target <350. See: ai/inbox/document-inspector-refactor.md

/// Tab selection for document inspector
enum InspectorTab: String, CaseIterable, Identifiable {
    case info = "Info"
    case metadata = "Metadata"
    case artifacts = "Artifacts"
    case content = "Content"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .info: return "info.circle"
        case .metadata: return "tag"
        case .artifacts: return "sparkles"
        case .content: return "doc.text"
        }
    }
}

/// Inspector panel showing document metadata and details
// swiftlint:disable:next type_body_length
struct DocumentInspector: View {
    let document: Document?

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @State private var artifacts: [Artifact] = []
    @State private var isLoadingArtifacts = false
    @State private var expandedArtifactTypes: Set<String> = []
    @State private var selectedTab: InspectorTab = .info

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 250, maxWidth: 300)
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        VStack(spacing: 0) {
            // Tab Picker
            Picker("Inspector Tab", selection: $selectedTab) {
                ForEach(InspectorTab.allCases) { tab in
                    Label(tab.rawValue, systemImage: tab.icon)
                        .tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider()

            // Tab Content
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    switch selectedTab {
                    case .info:
                        infoTab(doc)
                    case .metadata:
                        metadataTab(doc)
                    case .artifacts:
                        artifactsTab
                    case .content:
                        contentTab(doc)
                    }

                    Spacer()
                }
                .padding()
            }
        }
        .task(id: doc.id) {
            await loadArtifacts(for: doc.id)
        }
    }

    // MARK: - Info Tab

    private func infoTab(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header with thumbnail
            headerSection(doc)

            Divider()

            // Status
            statusSection(doc)

            Divider()

            // Basic file info
            basicFileInfo(doc)
        }
    }

    // MARK: - Metadata Tab

    private func metadataTab(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Technical Metadata")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let path = doc.path {
                LabeledContent("Path") {
                    Text(path)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                .textSelection(.enabled)
            }

            // Dynamic metadata fields
            ForEach(Array(doc.metadata.keys.sorted()), id: \.self) { key in
                if let value = doc.metadata[key] {
                    LabeledContent(formatMetadataKey(key)) {
                        Text(String(describing: value.value))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .textSelection(.enabled)
                }
            }

            if doc.metadata.isEmpty && doc.path == nil {
                Text("No metadata available")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    // MARK: - Artifacts Tab

    private var artifactsTab: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Workflow Artifacts")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if isLoadingArtifacts {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            if artifacts.isEmpty && !isLoadingArtifacts {
                VStack(spacing: 8) {
                    Image(systemName: "sparkles")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    Text("No artifacts yet")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("Run a workflow to generate artifacts")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
            } else {
                // Group artifacts by type
                let groupedArtifacts = Dictionary(grouping: artifacts) { $0.artifactType }

                ForEach(groupedArtifacts.keys.sorted(), id: \.self) { artifactType in
                    if let typeArtifacts = groupedArtifacts[artifactType] {
                        artifactTypeSection(type: artifactType, artifacts: typeArtifacts)
                    }
                }
            }
        }
    }

    // MARK: - Content Tab

    private func contentTab(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Extracted Content")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if let content = doc.pageContent, !content.isEmpty {
                    Button(
                        action: { copyToClipboard(content) },
                        label: {
                            Image(systemName: "doc.on.doc")
                        }
                    )
                    .buttonStyle(.plain)
                    .help("Copy to clipboard")
                }
            }

            if let content = doc.pageContent, !content.isEmpty {
                Text(content)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(6)
                    .textSelection(.enabled)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "doc.text")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    Text("No content extracted")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("Run transcription or OCR workflow")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 32)
            }
        }
    }

    // MARK: - Basic File Info

    private func basicFileInfo(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("File Information")
                .font(.subheadline)
                .fontWeight(.semibold)

            if let fileType = doc.fileType {
                LabeledContent("Type") {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption)
                }
            }

            if let fileSize = doc.metadata["File_Size"]?.value as? Int {
                LabeledContent("Size") {
                    Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                        .font(.caption)
                }
            }

            if let width = doc.metadata["Width"]?.value as? Int,
               let height = doc.metadata["Height"]?.value as? Int {
                LabeledContent("Dimensions") {
                    Text("\(width) × \(height)")
                        .font(.caption)
                }
            }
        }
    }

    // MARK: - Header Section

    private func headerSection(_ doc: Document) -> some View {
        VStack(alignment: .center, spacing: 12) {
            // Thumbnail from backend
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 80, height: 100)

                LibraryImageView(documentId: doc.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 80, height: 100)
                    .clipped()
            }
            .frame(width: 80, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            // Name
            Text(doc.name)
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)

            // Type badge
            HStack(spacing: 4) {
                Text(doc.docType.rawValue.capitalized)
                    .font(.caption)
                    .foregroundColor(.secondary)

                if let fileType = doc.fileType {
                    Text("•")
                        .foregroundColor(.secondary)
                    Text(fileType.rawValue.capitalized)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Status Section

    private func statusSection(_ doc: Document) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Status")
                .font(.subheadline)
                .fontWeight(.semibold)

            HStack {
                StatusBadge(status: doc.status)
                Spacer()

                if doc.status == .processing {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            // Dates
            LabeledContent("Created") {
                Text(doc.createdAt, style: .date)
                    .font(.caption)
            }

            LabeledContent("Modified") {
                Text(doc.updatedAt, style: .relative)
                    .font(.caption)
            }
        }
    }

    // MARK: - Helper Functions

    private func formatMetadataKey(_ key: String) -> String {
        // Convert "Exif_Make" to "Make", "File_Size" to "Size", etc.
        key.replacingOccurrences(of: "_", with: " ")
           .components(separatedBy: " ")
           .map { $0.capitalized }
           .joined(separator: " ")
    }

    // MARK: - Empty State

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "sidebar.right")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No Selection")
                .font(.headline)

            Text("Select a document to view details")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Helpers

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    // MARK: - Artifacts Section

    private var artifactsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Artifacts")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                if isLoadingArtifacts {
                    ProgressView()
                        .scaleEffect(0.7)
                }
            }

            if artifacts.isEmpty && !isLoadingArtifacts {
                Text("No artifacts yet")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .italic()
            } else {
                // Group artifacts by type
                let groupedArtifacts = Dictionary(grouping: artifacts) { $0.artifactType }

                ForEach(groupedArtifacts.keys.sorted(), id: \.self) { artifactType in
                    if let typeArtifacts = groupedArtifacts[artifactType] {
                        artifactTypeSection(type: artifactType, artifacts: typeArtifacts)
                    }
                }
            }
        }
    }

    private func artifactTypeSection(type: String, artifacts: [Artifact]) -> some View {
        DisclosureGroup(
            isExpanded: Binding(
                get: { expandedArtifactTypes.contains(type) },
                set: { isExpanded in
                    if isExpanded {
                        expandedArtifactTypes.insert(type)
                    } else {
                        expandedArtifactTypes.remove(type)
                    }
                }
            )
        ) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(artifacts) { artifact in
                    artifactRow(artifact)
                }
            }
            .padding(.leading, 8)
        } label: {
            HStack(spacing: 6) {
                Image(systemName: iconForArtifactType(type))
                    .foregroundColor(.secondary)
                Text(displayNameForArtifactType(type))
                    .font(.caption)
                    .fontWeight(.medium)
                Text("(\(artifacts.count))")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func artifactRow(_ artifact: Artifact) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            // Timestamp and provider
            HStack {
                Text(artifact.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundColor(.secondary)

                if let provider = artifact.provider {
                    Text("•")
                        .foregroundColor(.secondary)
                    Text(provider)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }

                Spacer()

                Button(
                    action: {
                        if let content = artifact.content {
                            copyToClipboard(content)
                        }
                    },
                    label: {
                        Image(systemName: "doc.on.doc")
                            .font(.caption2)
                    }
                )
                .buttonStyle(.plain)
                .opacity(artifact.content != nil ? 1 : 0.3)
            }

            // Content preview
            if let content = artifact.content, !content.isEmpty {
                Text(content)
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(4)
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
            }

            // Structured data preview for entities
            if let data = artifact.data, artifact.artifactType == "entities" {
                entitiesPreview(data)
            }
        }
        .padding(.vertical, 4)
    }

    private func entitiesPreview(_ data: [String: AnyCodable]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(data.keys.sorted()), id: \.self) { key in
                if let value = data[key],
                   let array = value.value as? [String],
                   !array.isEmpty {
                    HStack(alignment: .top, spacing: 4) {
                        Text("\(key.capitalized):")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .frame(width: 80, alignment: .leading)

                        Text(array.joined(separator: ", "))
                            .font(.caption2)
                            .foregroundColor(.primary)
                            .lineLimit(2)
                    }
                }
            }
        }
        .padding(6)
        .background(Color(.textBackgroundColor))
        .cornerRadius(4)
    }

    private func loadArtifacts(for documentId: String) async {
        guard !Task.isCancelled else { return }
        isLoadingArtifacts = true
        defer { isLoadingArtifacts = false }

        do {
            artifacts = try await artifactService.getArtifacts(forDocumentId: documentId)
            // Auto-expand if there's only one type
            if Set(artifacts.map(\.artifactType)).count == 1,
               let firstType = artifacts.first?.artifactType {
                expandedArtifactTypes = [firstType]
            }
        } catch {
            // Silently fail - artifacts are optional
            artifacts = []
        }
    }

    private func iconForArtifactType(_ type: String) -> String {
        switch type {
        case "transcription": return "text.quote"
        case "entities": return "person.3"
        case "summary_file", "summary_folder", "summary_collection": return "doc.text"
        case "description": return "eye"
        default: return "doc"
        }
    }

    private func displayNameForArtifactType(_ type: String) -> String {
        switch type {
        case "transcription": return "Transcription"
        case "entities": return "Entities"
        case "summary_file": return "Summary"
        case "summary_folder": return "Folder Summary"
        case "summary_collection": return "Collection Summary"
        case "description": return "Description"
        default: return type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

// MARK: - Preview

#Preview("Empty") {
    DocumentInspector(document: nil)
        .frame(width: 280, height: 400)
}
