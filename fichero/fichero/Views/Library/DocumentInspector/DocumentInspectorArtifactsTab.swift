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
        // Hide the raw extractor artifact when a `<key>_clean` exists on the
        // same doc — the cleaned version is the canonical view, the raw one
        // is just a per-page debug substrate. Show raw only when cleanup
        // hasn't run yet (no _clean present).
        let cleanedTypes = Set(
            artifacts
                .map(\.artifactType)
                .filter { $0.hasSuffix("_clean") }
                .map { String($0.dropLast("_clean".count)) }
        )
        let visibleArtifacts = artifacts.filter {
            !shouldHideArtifactType($0.artifactType)
                && !cleanedTypes.contains($0.artifactType)
        }

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

            // KnowledgeGraphInspectorSection lives in its own top-level
            // inspector tab (Content / Knowledge Graph / Info) since the
            // tab reorder. Removed from here to avoid duplicate rendering.
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

            // Content preview — when the type's section is expanded, render
            // the full text at its natural height so the whole artifact is
            // readable (the parent inspector scrolls). Truncating the
            // narrative to 10 lines or list previews to 3 hides exactly the
            // content the user just clicked to see. RTF source ({\rtf1...})
            // is decoded so the Info tab doesn't dump raw markup.
            if let content = artifact.content, !content.isEmpty {
                Text(plainProjection(of: content))
                    .font(.caption)
                    .foregroundColor(.secondary)
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

    /// Comma-joined raw values of EntityKinds the user has hidden from the
    /// KG list. Persisted across launches so the filter survives restarts.
    /// Default: all kinds visible.
    @AppStorage("inspector.kg.hiddenKinds") private var hiddenKindsCSV: String = ""

    private var hiddenKinds: Set<EntityKind> {
        Set(
            hiddenKindsCSV
                .split(separator: ",")
                .compactMap { EntityKind(rawValue: String($0)) }
        )
    }

    private func setHidden(_ kind: EntityKind, hidden: Bool) {
        var set = hiddenKinds
        if hidden { set.insert(kind) } else { set.remove(kind) }
        hiddenKindsCSV = set.map(\.rawValue).sorted().joined(separator: ",")
    }

    private var grouped: [(EntityKind, [GroupedItem])] {
        var byKind: [EntityKind: [GroupedItem]] = [:]
        // Dedupe within a kind by canonical key. Folder cleanup leaves
        // multiple claims referencing the same canonical entity, plus
        // absorbed entities still carry their old claims — we collapse
        // both into one row per canonical name (or per claim text for
        // date-only claims that have no entity).
        var seenKey: [EntityKind: Set<String>] = [:]
        for claim in claims {
            let entityId = claim.entityIds?.first
            let entity = entityId.flatMap { entitiesById[$0] }

            // Skip absorbed entities — folder_cleanup merged them into a
            // canonical, but the original claims still exist in the DB.
            // The canonical entity's claims will represent them.
            if let merged = entity?.mergedIntoId, !merged.isEmpty {
                continue
            }

            let kind = entity.flatMap { EntityKind(apiType: $0.entityType) } ?? .date
            // claim.text is non-optional in the OpenAPI schema — fall back
            // to it directly without an extra "(untitled)" guard.
            let displayName = entity?.canonicalName ?? claim.text
            // Dedupe key: canonical entity name when present, else claim text.
            let key = displayName
            if seenKey[kind, default: []].contains(key) {
                continue
            }
            seenKey[kind, default: []].insert(key)

            // Prefer the entity's curated description (set by the
            // extractor from `contexto`) over the raw claim source
            // excerpt — it's a one-line role/role-in-document blurb
            // and is what the user wants ("a little bit of information
            // about them"). Falls back to claim.sourceExcerpt then
            // claim.text so date claims (no entity) still render.
            let context = entity?.description?.trimmingCharacters(in: .whitespacesAndNewlines)
                ?? claim.sourceExcerpt
                ?? claim.text
            let item = GroupedItem(
                claimId: claim.id ?? UUID().uuidString,
                displayName: displayName,
                context: context,
                aliases: entity?.aliases ?? []
            )
            byKind[kind, default: []].append(item)
        }
        let hidden = hiddenKinds
        return EntityKind.displayOrder
            .compactMap { kind in
                guard !hidden.contains(kind) else { return nil }
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
        HStack(spacing: 8) {
            Image(systemName: "circle.hexagongrid")
            Text("Knowledge Graph")
                .font(.headline)
            Spacer()
            // Filter Menu — Tinderbox-style "displayed attributes" picker.
            // Each entity kind has its own checkbox; persistence lives in
            // @AppStorage so the choice survives restarts and applies to
            // every doc the user inspects.
            Menu {
                ForEach(EntityKind.displayOrder, id: \.self) { kind in
                    let isHidden = hiddenKinds.contains(kind)
                    Button {
                        setHidden(kind, hidden: !isHidden)
                    } label: {
                        Label(kind.label, systemImage: isHidden ? "" : "checkmark")
                    }
                }
                Divider()
                Button("Show all") { hiddenKindsCSV = "" }
                Button("Hide all") {
                    hiddenKindsCSV = EntityKind.displayOrder
                        .map(\.rawValue)
                        .sorted()
                        .joined(separator: ",")
                }
            } label: {
                Image(systemName: hiddenKinds.isEmpty
                      ? "line.3.horizontal.decrease.circle"
                      : "line.3.horizontal.decrease.circle.fill")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Pick which knowledge-graph kinds to show")
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
        // Keywords (concept) up top — densest summary, scan first.
        // Named entities next; events last (they carry their own dates
        // inside their descriptions, e.g. "Pronunciamiento ... el 23 de
        // julio de 1993"). Bare Dates section is suppressed in the
        // inspector — see body filter — because it duplicates info
        // already visible in event descriptions.
        [.concept, .person, .location, .organization, .event, .other]
    }
}

// MARK: - Per-kind list block

/// Finder Get Info-style block: a DisclosureGroup labelled by entity kind,
/// containing plain selectable rows. No buttons, no copy icons — clicks
/// don't trigger actions, ⌘C copies the standard text selection.
private struct EntityKindBlock: View {
    let kind: EntityKind
    let items: [GroupedItem]

    @AppStorage("inspector.kg.expandedKinds") private var expandedKindsCSV: String = ""

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { isOpen },
            set: { newValue in setOpen(newValue) }
        )
    }

    private var isOpen: Bool {
        expandedKindsCSV
            .split(separator: ",")
            .contains(Substring(kind.rawValue))
            // Default open until the user explicitly collapses something
            || expandedKindsCSV.isEmpty
    }

    private func setOpen(_ open: Bool) {
        var set = Set(
            expandedKindsCSV.split(separator: ",").map(String.init)
        )
        // First explicit toggle: seed with all currently-default-open kinds
        // so collapsing one doesn't collapse them all.
        if set.isEmpty {
            set = Set(EntityKind.displayOrder.map(\.rawValue))
        }
        if open { set.insert(kind.rawValue) } else { set.remove(kind.rawValue) }
        expandedKindsCSV = set.sorted().joined(separator: ",")
    }

    var body: some View {
        DisclosureGroup(isExpanded: isExpanded) {
            if kind == .concept {
                // Keywords as wrapping pale-blue capsule lozenges
                // (Finder tag-pill style). Daniel's call: scan-ability
                // beats single-block selection here. A context menu
                // copies the full list as "; " joined for the rare
                // case the user needs all keywords as text.
                FlowLayout(spacing: 4) {
                    ForEach(items) { item in
                        Text(item.displayName)
                            .font(.caption)
                            .foregroundStyle(.primary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(
                                Capsule().fill(Color.accentColor.opacity(0.18))
                            )
                            .textSelection(.enabled)
                    }
                }
                .padding(.leading, 16)
                .padding(.top, 4)
                .contextMenu {
                    Button("Copy all keywords") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(
                            items.map(\.displayName).joined(separator: "; "),
                            forType: .string
                        )
                    }
                }
            } else {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(items) { item in
                        EntityKindRow(item: item)
                    }
                }
                .padding(.leading, 16)
                .padding(.top, 4)
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: kind.systemImage)
                    .foregroundStyle(.secondary)
                    .font(.caption)
                Text(kind.label)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                Text("(\(items.count))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

/// One row inside an EntityKindBlock. Plain selectable text — name on
/// top, then aliases (if present), then a short context blurb (where
/// the entity carries one). No interactive elements — read + ⌘C only.
private struct EntityKindRow: View {
    let item: GroupedItem

    var body: some View {
        // Two visual rows in ONE selectable Text run:
        //   line 1: name  (aka alias1, alias2)
        //   line 2: context (when non-empty, non-redundant)
        // Because it's one composed Text, triple-click + ⌘C grabs the
        // whole entity as a multi-line block.
        composedText
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 2)
            .textSelection(.enabled)
    }

    private var composedText: Text {
        var text = Text(item.displayName)
            .font(.body)
            .foregroundStyle(.primary)
        if !item.aliases.isEmpty {
            text = text
                + Text("  (aka " + item.aliases.joined(separator: ", ") + ")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
        }
        if !item.context.isEmpty,
           item.context != item.displayName,
           !item.displayName.contains(item.context) {
            text = text
                + Text("\n" + item.context)
                    .font(.body)
                    .foregroundStyle(.secondary)
        }
        return text
    }
}

// MARK: - Previews
//
// Mock data + standalone surfaces so the inspector can iterate in Xcode
// Previews without a running backend. Pure layout work (filter Menu,
// kind ordering, keyword chip row, dedupe rendering, content lineLimits)
// loops in seconds here instead of through a 60s rebuild cycle.

private enum PreviewMocks {
    static let people: [GroupedItem] = [
        GroupedItem(
            claimId: "p1",
            displayName: "Federico W. Leighton",
            context: "is named as engineer of the dredge",
            aliases: ["F. W. Leighton", "Leighton"]
        ),
        GroupedItem(
            claimId: "p2",
            displayName: "Don Mateo Restrepo",
            context: "appears as the lender in the deed",
            aliases: ["Don Mateo", "D. Mateo"]
        ),
        GroupedItem(
            claimId: "p3",
            displayName: "Fenwic P. Caddy",
            context: "is reported to have resigned as captain",
            aliases: []
        )
    ]
    static let places: [GroupedItem] = [
        GroupedItem(
            claimId: "l1",
            displayName: "Río Condoto",
            context: "is named as the site of the dredge sinking",
            aliases: ["Río Conduto"]
        ),
        GroupedItem(
            claimId: "l2",
            displayName: "Bazán",
            context: "is described as the point where the dredge worked",
            aliases: ["Basán"]
        )
    ]
    static let organizations: [GroupedItem] = [
        GroupedItem(
            claimId: "o1",
            displayName: "Compañía Minera Chocó Pacífico",
            context: "is named as operator of the dredge",
            aliases: ["Cía. Minera Chocó Pacífico", "Choco Pacifico"]
        ),
        GroupedItem(
            claimId: "o2",
            displayName: "British Platinum & Gold Corporation Limited",
            context: "is described as the dredge's owner",
            aliases: []
        )
    ]
    static let events: [GroupedItem] = [
        GroupedItem(
            claimId: "e1",
            displayName: "Naufragio de la draga No. 1",
            context: "the file alleges the dredge sank in March 1925",
            aliases: ["sinking of dredge"]
        ),
        GroupedItem(
            claimId: "e2",
            displayName: "Renuncia del capitán",
            context: "Caddy is reported to have resigned",
            aliases: []
        )
    ]
    static let dates: [GroupedItem] = [
        GroupedItem(
            claimId: "d1",
            displayName: "1922-08-24: el naufragio de la draga",
            context: "1922-08-24",
            aliases: []
        ),
        GroupedItem(
            claimId: "d2",
            displayName: "1925-03-15: investigación judicial",
            context: "1925-03-15",
            aliases: []
        )
    ]
    static let keywords: [GroupedItem] = [
        GroupedItem(claimId: "k1", displayName: "minería", context: "", aliases: []),
        GroupedItem(claimId: "k2", displayName: "draga", context: "", aliases: []),
        GroupedItem(claimId: "k3", displayName: "Chocó", context: "", aliases: []),
        GroupedItem(claimId: "k4", displayName: "Condoto", context: "", aliases: []),
        GroupedItem(claimId: "k5", displayName: "naufragio", context: "", aliases: []),
        GroupedItem(claimId: "k6", displayName: "sumario", context: "", aliases: []),
        GroupedItem(claimId: "k7", displayName: "platino", context: "", aliases: []),
        GroupedItem(claimId: "k8", displayName: "British Platinum", context: "", aliases: [])
    ]

    static let allGroups: [(EntityKind, [GroupedItem])] = [
        (.concept, keywords),
        (.person, people),
        (.location, places),
        (.organization, organizations),
        (.event, events),
        (.date, dates)
    ]
}

/// Preview-only surface for the KG section. Takes pre-baked groups so
/// previews can render every entity kind without a running backend.
private struct KnowledgeGraphPreviewSurface: View {
    let groups: [(EntityKind, [GroupedItem])]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "circle.hexagongrid")
                Text("Knowledge Graph")
                    .font(.headline)
                Spacer()
                Image(systemName: "line.3.horizontal.decrease.circle")
                    .foregroundStyle(.secondary)
                Image(systemName: "arrow.clockwise")
                    .foregroundStyle(.secondary)
            }
            .foregroundStyle(.primary)

            ForEach(groups, id: \.0) { kind, items in
                EntityKindBlock(kind: kind, items: items)
            }
        }
        .padding()
        .frame(width: 320)
    }
}

#Preview("KG — full") {
    ScrollView {
        KnowledgeGraphPreviewSurface(groups: PreviewMocks.allGroups)
    }
    .frame(height: 700)
}

#Preview("KG — keywords only (inline row)") {
    KnowledgeGraphPreviewSurface(groups: [(.concept, PreviewMocks.keywords)])
}

#Preview("KG — people row") {
    KnowledgeGraphPreviewSurface(groups: [(.person, PreviewMocks.people)])
}

#Preview("KG — dates (no duplicate context)") {
    KnowledgeGraphPreviewSurface(groups: [(.date, PreviewMocks.dates)])
}

#Preview("KG — empty") {
    VStack(alignment: .leading, spacing: 12) {
        HStack {
            Image(systemName: "circle.hexagongrid")
            Text("Knowledge Graph").font(.headline)
            Spacer()
        }
        Text("No knowledge-graph entries for this document yet.")
            .font(.caption)
            .foregroundStyle(.secondary)
    }
    .padding()
    .frame(width: 320, height: 200)
}
