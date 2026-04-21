import SwiftUI

/// Artifacts tab content for DocumentInspector
struct DocumentInspectorArtifactsTab: View {
    let documentId: String

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @Environment(WorkflowExecutionObserver.self) private var executionObserver
    @State private var artifacts: [Artifact] = []
    @State private var isLoadingArtifacts = false
    @State private var expandedArtifactTypes: Set<String> = []

    var body: some View {
        let visibleArtifacts = artifacts.filter { !shouldHideArtifactType($0.artifactType) }

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

            if visibleArtifacts.isEmpty && !isLoadingArtifacts {
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
                let groupedArtifacts = Dictionary(grouping: visibleArtifacts) { $0.artifactType }

                ForEach(groupedArtifacts.keys.sorted(), id: \.self) { artifactType in
                    if let typeArtifacts = groupedArtifacts[artifactType] {
                        artifactTypeSection(type: artifactType, artifacts: typeArtifacts)
                    }
                }
            }
        }
        .task(id: documentId) {
            await loadArtifacts(for: documentId)
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            // Re-fetch whenever any file completes so artifacts appear mid-run
            Task { await loadArtifacts(for: documentId) }
        }
    }

    // MARK: - Artifact Type Section

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

    // MARK: - Artifact Row

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

    // MARK: - Entities Preview

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

    // MARK: - Load Artifacts

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

    // MARK: - Artifact Type Helpers

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

    private func shouldHideArtifactType(_ type: String) -> Bool {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "transcription"
            || normalized == "page_content_rtf"
            || normalized == "rtf"
    }

    // MARK: - Clipboard

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}
