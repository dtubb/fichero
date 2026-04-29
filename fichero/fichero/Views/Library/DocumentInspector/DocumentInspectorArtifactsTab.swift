// swiftlint:disable file_length
import SwiftUI

/// Artifacts tab content for DocumentInspector
struct DocumentInspectorArtifactsTab: View { // swiftlint:disable:this type_body_length
    let documentId: String

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var entityService: EntityServiceGenerated
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
                let hasHiddenTranscription = artifacts.contains { $0.artifactType == "transcription" }
                VStack(spacing: 8) {
                    Image(systemName: hasHiddenTranscription ? "text.quote" : "sparkles")
                        .font(.title2)
                        .foregroundColor(.secondary)
                    Text(hasHiddenTranscription ? "Transcription available" : "No artifacts yet")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(hasHiddenTranscription ? "See the Content tab to view it" : "Run a workflow to generate artifacts")
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

            // Knowledge-graph view: queryable typed entities/claims for this
            // document, written by catalogue extractors alongside markdown
            // artifacts (#728). Both render — markdown above for debug,
            // typed view here for cross-doc search and KG layers.
            Divider().padding(.vertical, 8)
            KnowledgeGraphInspectorSection(
                documentId: documentId,
                entityService: entityService
            )
        }
        .task(id: documentId) {
            await loadArtifacts(for: documentId)
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            // Re-fetch whenever any file completes so artifacts appear mid-run
            Task { await loadArtifacts(for: documentId) }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            // Re-fetch when workflow finishes — reduce-phase nodes (Catalogue)
            // save artifacts after all parallel files complete, so a final
            // refresh is needed after the workflow completes.
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

    // swiftlint:disable:next function_body_length
    private func artifactRow(_ artifact: Artifact) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            // Timestamp and provider
            HStack {
                Text(artifact.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundColor(.secondary)

                if let provider = artifact.provider, !provider.isEmpty {
                    Text("•")
                        .foregroundColor(.secondary)
                    Text(provider)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                // Model is the differentiator when multiple runs of the same
                // tool exist (qwen-vl-3.5 vs qwen-vl-3.6v). Keep it subtle
                // but always visible so users can tell artifacts apart.
                if let model = artifact.model, !model.isEmpty {
                    Text("·")
                        .foregroundColor(.secondary)
                    Text(model)
                        .font(.caption2.monospaced())
                        .foregroundColor(.secondary)
                        .lineLimit(1)
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
                .help("Copy to clipboard")

                Button(
                    action: { exportArtifactToFile(artifact) },
                    label: {
                        Image(systemName: "square.and.arrow.down")
                            .font(.caption2)
                    }
                )
                .buttonStyle(.plain)
                .opacity(artifact.content != nil ? 1 : 0.3)
                .help("Save to file…")
            }

            // Content preview — longer line limit for catalogue-scale artifacts
            // (summary/narrative), tight limit for list-style artifacts where
            // the structured data rendering below carries the real content.
            // RTF source ({\rtf1...}) is decoded to its plain projection so
            // the Info tab doesn't dump raw markup at the user.
            if let content = artifact.content, !content.isEmpty {
                Text(plainProjection(of: content))
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .lineLimit(lineLimitForArtifactType(artifact.artifactType))
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
                    .textSelection(.enabled)
            }

            // Structured data preview — each catalogue artifact type
            // (people, dates, rivers, etc.) renders the structured items
            // list as a clean table so researchers can browse without
            // parsing JSON or markdown.
            if let data = artifact.data {
                structuredPreview(for: artifact.artifactType, data: data)
            }
        }
        .padding(.vertical, 4)
    }

    /// Strip raw RTF source for the Info tab preview. When the artifact's
    /// content was stored as inline RTF ({\rtf1...} from the V2 editor),
    /// rendering it as plain Text dumps the markup at the user. Decode and
    /// return .string instead. Plain content passes through unchanged.
    private func plainProjection(of content: String) -> String {
        guard content.hasPrefix("{\\rtf"),
              let data = content.data(using: .utf8),
              let attr = try? NSAttributedString(
                  data: data,
                  options: [.documentType: NSAttributedString.DocumentType.rtf],
                  documentAttributes: nil
              ) else {
            return content
        }
        return attr.string
    }

    private func lineLimitForArtifactType(_ type: String) -> Int {
        switch type {
        case "catalogue", "summary":
            return 10  // narrative — give it room
        case "people", "dates", "rivers", "events",
             "legal_references", "mines", "properties":
            return 3   // preview; structured view below carries the real list
        default:
            return 4
        }
    }

    // MARK: - Structured Preview Router

    @ViewBuilder
    private func structuredPreview(for type: String, data: [String: AnyCodable]) -> some View {
        switch type {
        case "entities":
            entitiesPreview(data)
        case "people", "mines", "properties", "legal_references":
            CatalogueArtifactPreviews.nameContext(data, primaryKey: "nombre")
        case "events":
            CatalogueArtifactPreviews.nameContext(data, primaryKey: "evento")
        case "dates":
            CatalogueArtifactPreviews.dates(data)
        case "rivers":
            CatalogueArtifactPreviews.rivers(data)
        case "keywords":
            CatalogueArtifactPreviews.keywords(data)
        default:
            EmptyView()
        }
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
            // Strict per-document scope — the legacy aggregation
            // (`include_descendants=true`, the API default) returns the
            // doc's artifacts PLUS its children's PLUS its parent's, which
            // makes container-scoped artifacts (folder Catalogue, folder
            // Dates) bleed onto every child page's inspector. V2 wants
            // each page to show only its own artifacts. (#721)
            artifacts = try await artifactService.getArtifacts(
                forDocumentId: documentId,
                includeDescendants: false
            )
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

    private static let iconByType: [String: String] = [
        "transcription": "text.quote",
        "entities": "person.3",
        "catalogue": "books.vertical",
        "summary": "doc.text",
        "summary_file": "doc.text",
        "summary_folder": "doc.text",
        "summary_collection": "doc.text",
        "keywords": "tag",
        "people": "person.2",
        "dates": "calendar",
        "legal_references": "scale.3d",
        "rivers": "water.waves",
        "events": "star",
        "mines": "pickaxe",
        "properties": "building.columns",
        "description": "eye"
    ]

    private static let displayNameByType: [String: String] = [
        "transcription": "Transcription",
        "entities": "Entities",
        "catalogue": "Catalogue",
        "summary": "Summary",
        "summary_file": "Summary",
        "summary_folder": "Folder Summary",
        "summary_collection": "Collection Summary",
        "keywords": "Keywords",
        "people": "People",
        "dates": "Dates",
        "legal_references": "Legal References",
        "rivers": "Rivers",
        "events": "Events",
        "mines": "Mines",
        "properties": "Properties",
        "description": "Description"
    ]

    private func iconForArtifactType(_ type: String) -> String {
        Self.iconByType[type] ?? "doc"
    }

    private func displayNameForArtifactType(_ type: String) -> String {
        Self.displayNameByType[type]
            ?? type.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func shouldHideArtifactType(_ type: String) -> Bool {
        let normalized = type.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        // Transcription artifacts are shown — when multiple runs exist (e.g.
        // qwen-vl-3.5 and qwen-vl-3.6v), each provider/model combination
        // produces its own artifact and researchers need to compare them.
        // The Content tab still holds the latest run's editable copy.
        return normalized == "page_content_rtf" || normalized == "rtf"
    }

    // MARK: - Clipboard

    private func copyToClipboard(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    private func exportArtifactToFile(_ artifact: Artifact) {
        guard let content = artifact.content else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText, .json]
        let modelSlug = (artifact.model ?? "unknown")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: ":", with: "_")
        panel.nameFieldStringValue = "\(artifact.artifactType)-\(modelSlug).txt"
        panel.canCreateDirectories = true
        panel.begin { response in
            guard response == .OK, let url = panel.url else { return }
            do {
                try content.write(to: url, atomically: true, encoding: .utf8)
            } catch {
                NSLog("Failed to save artifact: \(error)")
            }
        }
    }
}

// MARK: - Catalogue Artifact Previews
//
// Lives in this file (not a standalone one) because the Xcode main target
// isn't file-system-synchronized — new .swift files under fichero/
// require a pbxproj edit to be picked up. Appending to an existing file in
// the target is the reliable path. See MEMORY.md's "Swift main target not
// file-sync'd" note.

/// Structured previews for the per-section artifacts produced by the
/// Catalogue workflow (people, dates, rivers, events, mines, properties,
/// keywords). Each catalogue-section artifact stores its structured items
/// in `artifact.data["items"]` as an array of dicts; these views render
/// them as compact tables the inspector can show without a separate sheet.
enum CatalogueArtifactPreviews {

    static func items(from data: [String: AnyCodable]) -> [[String: Any]] {
        guard let value = data["items"]?.value,
              let array = value as? [[String: Any]] else {
            return []
        }
        return array
    }

    @ViewBuilder
    static func nameContext(
        _ data: [String: AnyCodable],
        primaryKey: String
    ) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if let name = item[primaryKey] as? String {
                        HStack(alignment: .top, spacing: 6) {
                            Text(name)
                                .font(.caption.weight(.medium))
                                .foregroundColor(.primary)
                                .frame(minWidth: 100, alignment: .leading)
                            if let context = item["contexto"] as? String, !context.isEmpty {
                                Text(context)
                                    .font(.caption2)
                                    .foregroundColor(.secondary)
                                    .lineLimit(3)
                            }
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func dates(_ data: [String: AnyCodable]) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let normalized = (item["fecha_normalizada"] as? String) ?? ""
                    let raw = (item["fecha"] as? String) ?? ""
                    let context = (item["contexto"] as? String) ?? ""
                    HStack(alignment: .top, spacing: 6) {
                        Text(normalized.isEmpty ? raw : normalized)
                            .font(.caption.monospacedDigit())
                            .foregroundColor(.primary)
                            .frame(minWidth: 100, alignment: .leading)
                        if !context.isEmpty {
                            Text(context)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(3)
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func rivers(_ data: [String: AnyCodable]) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let name = (item["nombre"] as? String) ?? ""
                    let alts = (item["ortografias_alternativas"] as? [String]) ?? []
                    let context = (item["contexto"] as? String) ?? ""
                    VStack(alignment: .leading, spacing: 1) {
                        Text(name)
                            .font(.caption.weight(.medium))
                            .foregroundColor(.primary)
                        if !alts.isEmpty {
                            Text("Alt: \(alts.joined(separator: ", "))")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        if !context.isEmpty {
                            Text(context)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func keywords(_ data: [String: AnyCodable]) -> some View {
        if let value = data["keywords"]?.value,
           let keywords = value as? [String],
           !keywords.isEmpty {
            Text(keywords.joined(separator: " • "))
                .font(.caption2)
                .foregroundColor(.primary)
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.accentColor.opacity(0.1))
                .cornerRadius(4)
                .textSelection(.enabled)
        }
    }
}
// swiftlint:enable file_length
import FicheroAPIClient

/// Inspector section that shows knowledge-graph entities and claims for
/// the currently selected document. Reads from `/api/claims` filtered
/// by `source_document_id`, dereferences `entity_ids` against
/// `/api/entities`, and groups by `EntityType` for display (#728).
///
/// This is the typed-view counterpart to the existing markdown-artifact
/// previews in `DocumentInspectorArtifactsTab`. Both render side-by-side
/// for now (dual-write era) — markdown for debug, typed view for query.
struct KnowledgeGraphInspectorSection: View {
    let documentId: String
    let entityService: EntityServiceGenerated

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var entitiesById: [String: Components.Schemas.KnowledgeEntity] = [:]
    @State private var isLoading = false
    @State private var loadError: String?

    private var grouped: [(EntityKind, [GroupedItem])] {
        var byKind: [EntityKind: [GroupedItem]] = [:]
        for claim in claims {
            let entityId = claim.entityIds?.first
            let entity = entityId.flatMap { entitiesById[$0] }
            let kind = entity.flatMap { EntityKind(apiType: $0.entityType) } ?? .date
            let item = GroupedItem(
                claimId: claim.id ?? UUID().uuidString,
                displayName: entity?.canonicalName ?? claim.text ?? "(untitled)",
                context: claim.sourceExcerpt ?? claim.text ?? "",
                aliases: entity?.aliases ?? []
            )
            byKind[kind, default: []].append(item)
        }
        return EntityKind.displayOrder
            .compactMap { kind in
                guard let items = byKind[kind], !items.isEmpty else { return nil }
                return (kind, items)
            }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader

            if isLoading {
                ProgressView().padding(.vertical, 8)
            } else if let err = loadError {
                Label(err, systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.orange)
            } else if grouped.isEmpty {
                Text("No knowledge-graph entries for this document yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(grouped, id: \.0) { kind, items in
                    EntityKindBlock(kind: kind, items: items)
                }
            }
        }
        .task(id: documentId) { await load() }
    }

    private var sectionHeader: some View {
        HStack {
            Image(systemName: "circle.hexagongrid")
            Text("Knowledge Graph")
                .font(.headline)
            Spacer()
            Button {
                Task { await load() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload knowledge-graph entities for this document")
        }
        .foregroundStyle(.primary)
    }

    private func load() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let docClaims = try await entityService.listClaims(
                sourceDocumentId: documentId,
                limit: 500
            )
            claims = docClaims

            // Resolve referenced entities. Bounded: max one per claim.
            let entityIds = Set(docClaims.compactMap { $0.entityIds?.first })
            var fetched: [String: Components.Schemas.KnowledgeEntity] = [:]
            for id in entityIds {
                if let entity = try? await entityService.getEntity(id) {
                    fetched[id] = entity
                }
            }
            entitiesById = fetched
        } catch {
            loadError = "Couldn't load: \(error.localizedDescription)"
            claims = []
            entitiesById = [:]
        }
    }
}

// MARK: - Models for the section's local rendering state

private struct GroupedItem: Identifiable {
    let claimId: String
    let displayName: String
    let context: String
    let aliases: [String]
    var id: String { claimId }
}

/// Local enum mirroring the API EntityType plus a "date" bucket for
/// claim-only date entries (those have no entity at all).
private enum EntityKind: String, Hashable, CaseIterable {
    case person, location, organization, event, concept, date, other

    init?(apiType: Components.Schemas.EntityTypeOutput?) {
        guard let apiType else { return nil }
        switch apiType {
        case .person:       self = .person
        case .location:     self = .location
        case .organization: self = .organization
        case .event:        self = .event
        case .concept:      self = .concept
        case .other:        self = .other
        }
    }

    var label: String {
        switch self {
        case .person:       return "People"
        case .location:     return "Places"
        case .organization: return "Organizations"
        case .event:        return "Events"
        case .concept:      return "Keywords"
        case .date:         return "Dates"
        case .other:        return "Other"
        }
    }

    var systemImage: String {
        switch self {
        case .person:       return "person.2"
        case .location:     return "mappin.and.ellipse"
        case .organization: return "building.2"
        case .event:        return "star"
        case .concept:      return "tag"
        case .date:         return "calendar"
        case .other:        return "questionmark.circle"
        }
    }

    static var displayOrder: [EntityKind] {
        [.person, .location, .organization, .event, .date, .concept, .other]
    }
}

// MARK: - Per-kind list block

private struct EntityKindBlock: View {
    let kind: EntityKind
    let items: [GroupedItem]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Image(systemName: kind.systemImage)
                    .foregroundStyle(.secondary)
                Text("\(kind.label) (\(items.count))")
                    .font(.subheadline)
                    .foregroundStyle(.primary)
            }
            ForEach(items) { item in
                EntityKindRow(item: item, kind: kind)
            }
        }
    }
}

private struct EntityKindRow: View {
    let item: GroupedItem
    let kind: EntityKind

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            // Tappable entity name. Clicking copies the canonical name to
            // the pasteboard so the user can paste into the search bar to
            // find every doc mentioning it. Proper cross-doc navigation
            // (click-to-search) needs a global dispatcher and is a 0.0.3
            // task — this is the cheap affordance for now.
            Button(action: copyName) {
                HStack(spacing: 4) {
                    Text(item.displayName)
                        .font(.body)
                        .foregroundStyle(.primary)
                    Image(systemName: "doc.on.clipboard")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .opacity(0.6)
                }
            }
            .buttonStyle(.plain)
            .help("Copy '\(item.displayName)' — paste in search to find all sources")

            if !item.aliases.isEmpty {
                Text("Also: \(item.aliases.joined(separator: ", "))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if !item.context.isEmpty, item.context != item.displayName {
                Text(item.context)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.leading, 18)
        .padding(.vertical, 2)
        .contextMenu {
            Button("Copy name") { copyName() }
            Button("Copy with context") {
                let combined = item.context.isEmpty
                    ? item.displayName
                    : "\(item.displayName) — \(item.context)"
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(combined, forType: .string)
            }
        }
    }

    private func copyName() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(item.displayName, forType: .string)
    }
}

// MARK: - Preview

#Preview {
    Text("KnowledgeGraphInspectorSection — preview requires a backend")
        .padding()
}
