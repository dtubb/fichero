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

            if let content = artifact.content, !content.isEmpty {
                ArtifactContentView(content: content)
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
            CatalogueArtifactPreviews.nameContext(data, primaryKey: "nombre", entityType: type)
        case "events":
            CatalogueArtifactPreviews.nameContext(data, primaryKey: "evento", entityType: type)
        case "dates":
            CatalogueArtifactPreviews.dates(data, entityType: type)
        case "rivers":
            CatalogueArtifactPreviews.rivers(data)
        case "keywords":
            CatalogueArtifactPreviews.keywords(data, entityType: type)
        case "places", "organizations":
            CatalogueArtifactPreviews.nameContext(data, primaryKey: "nombre", entityType: type)
        default:
            GenericJSONInspector(anyCodable: data)
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
        "mines": "hammer",     // 'pickaxe' doesn't exist as an SF Symbol on macOS 15 (#1015)
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
        primaryKey: String,
        entityType: String? = nil
    ) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            // Render each entity name as a blue lozenge — matches the
            // list-view convention so the visual language is consistent
            // across views. Daniel: 'for the document inspector, you
            // should also render as blue lozenges all of the artefacts.'
            // Tooltip carries the per-item context so the original
            // detail isn't lost.
            FlowLayout(spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if let name = item[primaryKey] as? String {
                        let context = item["contexto"] as? String ?? item["context"] as? String
                        EntityLozenge(name: name, tooltip: context, entityType: entityType)
                    }
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }

    @ViewBuilder
    static func dates(_ data: [String: AnyCodable], entityType: String? = nil) -> some View {
        let items = items(from: data)
        if !items.isEmpty {
            FlowLayout(spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    let normalized = (item["fecha_normalizada"] as? String)
                        ?? (item["date_normalized"] as? String) ?? ""
                    let raw = (item["fecha"] as? String)
                        ?? (item["date"] as? String) ?? ""
                    let context = (item["contexto"] as? String)
                        ?? (item["context"] as? String) ?? ""
                    let label = normalized.isEmpty ? raw : normalized
                    if !label.isEmpty {
                        EntityLozenge(
                            name: label,
                            tooltip: context.isEmpty ? nil : context,
                            entityType: entityType
                        )
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
    static func keywords(_ data: [String: AnyCodable], entityType: String? = "keywords") -> some View {
        if let value = data["keywords"]?.value,
           let keywords = value as? [String],
           !keywords.isEmpty {
            FlowLayout(spacing: 4) {
                ForEach(Array(keywords.enumerated()), id: \.offset) { _, keyword in
                    EntityLozenge(name: keyword, entityType: entityType)
                }
            }
            .padding(6)
            .background(Color(.textBackgroundColor))
            .cornerRadius(4)
        }
    }
}

// MARK: - Entity Lozenge (#519 follow-up)

/// Shared blue capsule for entity names. Same style as the list-view
/// lozenges so the visual language is consistent across the library
/// and the document inspector. Tooltip carries the per-item context
/// (e.g. role, date raw form) so the detail isn't lost when the
/// long-form context cell is replaced by a compact pill.
struct EntityLozenge: View {
    let name: String
    var tooltip: String?
    /// Optional entity type ('people', 'places', 'organizations',
    /// 'dates', 'events', 'keywords'). When set, lozenge taps fire an
    /// entity-scoped search like `keywords:"social license"` instead of
    /// a plain text search — so clicking the 'social license' tag finds
    /// docs whose KEYWORDS artifact contains that term, not docs whose
    /// page_content happens to mention it. Daniel's "if I click on a
    /// name, it should find other documents with that person's name"
    /// requirement.
    var entityType: String?
    /// Cap so a single super-long name (e.g. 'Canadian Association of
    /// Latin American and Caribbean Studies') doesn't push the lozenge
    /// past its column boundary. Truncated with middle-ellipsis like
    /// Finder filename truncation. (Daniel: 'elipses in the middle')
    var maxWidth: CGFloat = 180

    var body: some View {
        Button {
            // Lozenge tap → fire a global entity-search request. ContentView
            // listens and routes the name into runToolbarSearch so we get
            // the same path as typing into the toolbar (creates a saved
            // search, switches sidebar to search mode, runs the query).
            // NotificationCenter avoids prop-drilling a closure through
            // ArtifactEntitiesView → MailStyleRow → LibraryView →
            // ContentView (5 levels deep).
            var userInfo: [String: Any] = ["name": name]
            if let entityType {
                userInfo["entityType"] = entityType
            }
            NotificationCenter.default.post(
                name: .ficheroEntitySearchRequested,
                object: nil,
                userInfo: userInfo
            )
        } label: {
            Text(name)
                .font(.caption2)
                .foregroundStyle(Color.accentColor)
                .lineLimit(1)
                .truncationMode(.middle)
                .padding(.horizontal, 8)
                .padding(.vertical, 2)
                .background(
                    Capsule()
                        .fill(Color.accentColor.opacity(0.12))
                )
                .overlay(
                    Capsule()
                        .stroke(Color.accentColor.opacity(0.25), lineWidth: 0.5)
                )
                .frame(maxWidth: maxWidth, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
        }
        .buttonStyle(.plain)
        .help(tooltip ?? "Search for \"\(name)\"")
    }
}

extension Notification.Name {
    /// Posted when the user taps an entity lozenge anywhere in the UI.
    /// `userInfo["name"]: String` carries the entity name to search for.
    /// ContentView listens and routes via `runToolbarSearch`.
    static let ficheroEntitySearchRequested = Notification.Name(
        "ficheroEntitySearchRequested"
    )
    /// Posted after a claim is deleted from the KG UI (right-click →
    /// Delete in ClaimSummaryCard). `object` is the deleted claim ID
    /// (String) or nil on error (in which case userInfo["error"]
    /// carries the message). EntityDetailView listens to refresh its
    /// claim list.
    static let ficheroClaimDeleted = Notification.Name("ficheroClaimDeleted")

    /// Posted when the user taps a source-doc citation on a claim card
    /// (or anywhere else that wants to navigate to a claim's source).
    /// userInfo carries:
    /// - "documentId": String (required)
    /// - "pageLabel": String? (optional)
    /// - "charStart": Int? / "charEnd": Int? (optional span)
    /// - "claimId": String? (so the consumer can highlight downstream)
    /// ContentView listens and selects the document + navigates the
    /// preview to the span when populated. (#978/#979/#982)
    static let ficheroOpenClaimSource = Notification.Name("ficheroOpenClaimSource")

    /// Forwarded from `ficheroOpenClaimSource` after ContentView
    /// selects the target document. The PDF preview view listens for
    /// this to scroll to the requested page + position. userInfo is
    /// the same dict as `ficheroOpenClaimSource` (documentId,
    /// pageLabel, charStart, charEnd, claimId). Separate name so the
    /// listener split is explicit — ContentView owns the doc-select
    /// path, the preview owns the page-scroll path.
    static let ficheroNavigateToPage = Notification.Name("ficheroNavigateToPage")
}

// MARK: - Artifact Content View

/// Renders artifact `content` string as a structured JSON inspector when
/// the content is valid JSON, or as plain text otherwise.
/// Owns the "View Raw" toggle independently per artifact.
private struct ArtifactContentView: View {
    let content: String

    @State private var showRaw = false

    var body: some View {
        if let parsed = parseJSON(content) {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Spacer()
                    Button(showRaw ? "Structured" : "Raw") { showRaw.toggle() }
                        .font(.caption2)
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                }
                if showRaw {
                    Text(content)
                        .font(.caption2.monospaced())
                        .foregroundColor(.secondary)
                        .padding(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                        .background(Color(.textBackgroundColor))
                        .cornerRadius(4)
                        .textSelection(.enabled)
                } else {
                    GenericJSONInspector(value: parsed)
                }
            }
        } else {
            Text(plainText)
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(6)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
                .textSelection(.enabled)
        }
    }

    private var plainText: String {
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

    private func parseJSON(_ string: String) -> Any? {
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("{") || trimmed.hasPrefix("["),
              let data = string.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) else {
            return nil
        }
        return obj
    }
}

// MARK: - Generic JSON Inspector

/// Renders a JSON value (dict or array) as a compact structured panel.
/// Used for artifact `data` dicts of unknown types and parsed JSON content.
struct GenericJSONInspector: View {
    let value: Any

    init(value: Any) {
        self.value = value
    }

    init(anyCodable: [String: AnyCodable]) {
        self.value = anyCodable.reduce(into: [String: Any]()) { $0[$1.key] = $1.value.value }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let dict = value as? [String: Any] {
                ForEach(Array(dict.keys.sorted()), id: \.self) { key in
                    if let val = dict[key] {
                        GenericJSONRow(label: key, value: val)
                    }
                }
            } else if let arr = value as? [Any] {
                GenericJSONValueView(value: arr)
            }
        }
        .padding(6)
        .background(Color(.textBackgroundColor))
        .cornerRadius(4)
    }
}

private struct GenericJSONRow: View {
    let label: String
    let value: Any

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Text(label.replacingOccurrences(of: "_", with: " ").capitalized + ":")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(minWidth: 70, alignment: .leading)
            GenericJSONValueView(value: value)
        }
    }
}

struct GenericJSONValueView: View {
    let value: Any

    var body: some View {
        if let strArr = value as? [String] {
            FlowLayout(spacing: 3) {
                ForEach(Array(strArr.enumerated()), id: \.offset) { _, item in
                    Text(item)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.accentColor.opacity(0.10))
                        .foregroundStyle(Color.accentColor)
                        .cornerRadius(3)
                }
            }
        } else if let arr = value as? [Any] {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(arr.prefix(10).enumerated()), id: \.offset) { _, item in
                    if let dict = item as? [String: Any] {
                        let preview = dict.values.compactMap { $0 as? String }.first
                            ?? String(describing: item)
                        Text("• \(preview)")
                            .font(.caption2)
                            .foregroundStyle(.primary)
                    } else {
                        Text("• \(String(describing: item))")
                            .font(.caption2)
                            .foregroundStyle(.primary)
                    }
                }
                if arr.count > 10 {
                    Text("+ \(arr.count - 10) more")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        } else if let dict = value as? [String: Any] {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(dict.keys.sorted().prefix(5)), id: \.self) { key in
                    HStack(spacing: 4) {
                        Text(key + ":")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        Text(String(describing: dict[key]!))
                            .font(.caption2)
                            .foregroundStyle(.primary)
                            .textSelection(.enabled)
                    }
                }
                if dict.count > 5 {
                    Text("+ \(dict.count - 5) more keys")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        } else {
            Text(String(describing: value))
                .font(.caption2)
                .foregroundStyle(.primary)
                .textSelection(.enabled)
        }
    }
}
import FicheroAPIClient

/// Inspector section that shows knowledge-graph entities and claims for
/// the currently selected document. Reads from `/api/claims` filtered
/// by `source_document_id`, dereferences `entity_ids` against
/// `/api/entities`, and groups by `EntityType` for display (#728).
///
/// This is the typed-view counterpart to the existing markdown-artifact
/// previews in `DocumentInspectorArtifactsTab`. Both render side-by-side
/// for now (dual-write era) — markdown for debug, typed view for query.
struct KnowledgeGraphInspectorSection: View { // swiftlint:disable:this type_body_length
    let documentId: String
    let entityService: EntityServiceGenerated
    /// Called when the user clicks the source-page arrow on an entity row.
    /// Receives the source page document id; ContentView decides how to
    /// navigate (typically: select the parent file in the grid). Optional
    /// so previews and standalone uses still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?
    /// Called when the user clicks on a claim to select it for highlighting
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var entitiesById: [String: Components.Schemas.KnowledgeEntity] = [:]
    @State private var isLoading = false
    @State private var loadError: String?
    @EnvironmentObject private var claimFocusState: ClaimFocusState

    /// Comma-joined raw values of EntityKinds the user has hidden from the
    /// KG list. Persisted across launches so the filter survives restarts.
    /// Default: all kinds visible.
    @AppStorage("inspector.kg.hiddenKinds") private var hiddenKindsCSV: String = ""

    /// Text = dense semicolon prose per entity; List = grouped disclosure rows.
    @AppStorage("inspector.kg.displayMode") private var displayMode: KGDisplayMode = .text

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
        // Index into byKind so extra claims can be appended to existing rows.
        var kindItemIndex: [EntityKind: [String: Int]] = [:]
        // Dedupe within a kind by canonical key. Folder cleanup leaves
        // multiple claims referencing the same canonical entity, plus
        // absorbed entities still carry their old claims — we collapse
        // both into one row per canonical name (or per claim text for
        // date-only claims that have no entity).
        // When the same entity has multiple DISTINCT substantive claims,
        // accumulate them in extraClaims so all SVOs are visible (#1109).
        for claim in claims {
            let entityId = claim.entityIds?.first
            let entity = entityId.flatMap { entitiesById[$0] }

            // Skip absorbed entities — folder_cleanup merged them into a
            // canonical, but the original claims still exist in the DB.
            // The canonical entity's claims will represent them.
            if let merged = entity?.mergedIntoId, !merged.isEmpty {
                continue
            }

            // Skip tautological "is a [entity_type]" claims emitted by
            // the NER step to assert entity kind — they carry no
            // knowledge content and pollute the inspector (#1109).
            let predVerb = (claim.predicateVerb ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let objPhrase = (claim.objectPhrase ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if predVerb == "is" && (objPhrase.hasPrefix("a ") || objPhrase.hasPrefix("an ")) {
                continue
            }

            let kind = entity.flatMap { EntityKind(apiType: $0.entityType) } ?? .date
            let displayName = entity?.canonicalName ?? claim.text
            let key = displayName

            let excerpt = claim.sourceExcerpt?.trimmingCharacters(in: .whitespacesAndNewlines)
            let context = entity?.description?.trimmingCharacters(in: .whitespacesAndNewlines)
                ?? excerpt
                ?? claim.text

            if let existingIdx = kindItemIndex[kind]?[key] {
                // Entity already has a row — accumulate as extra SVO (#1109).
                let extra = GroupedItem.ExtraClaim(
                    claimId: claim.id ?? UUID().uuidString,
                    context: context,
                    sourceDocumentId: claim.sourceDocumentId,
                    sourcePageLabel: claim.sourcePageLabel,
                    sourceExcerpt: excerpt
                )
                byKind[kind]![existingIdx].extraClaims.append(extra)
            } else {
                // Prefer the entity's curated description (set by the
                // extractor from `contexto`) over the raw claim source
                // excerpt — it's a one-line role/role-in-document blurb
                // and is what the user wants ("a little bit of information
                // about them"). Falls back to claim.sourceExcerpt then
                // claim.text so date claims (no entity) still render.
                let item = GroupedItem(
                    claimId: claim.id ?? UUID().uuidString,
                    displayName: displayName,
                    context: context,
                    aliases: entity?.aliases ?? [],
                    sourceDocumentId: claim.sourceDocumentId,
                    sourcePageLabel: claim.sourcePageLabel,
                    sourceExcerpt: excerpt
                )
                let idx = byKind[kind, default: []].count
                byKind[kind, default: []].append(item)
                kindItemIndex[kind, default: [:]][key] = idx
            }
        }
        let hidden = hiddenKinds
        return EntityKind.displayOrder
            .compactMap { kind in
                guard !hidden.contains(kind) else { return nil }
                guard let items = byKind[kind], !items.isEmpty else { return nil }
                return (kind, items)
            }
    }

    // MARK: - Text digest data

    private struct TextDigestEntry {
        let displayName: String
        let kind: EntityKind
        // Each element is "verb objectPhrase" or bare claim text.
        let svoLines: [String]
    }

    private struct EntityAccumulator {
        let kind: EntityKind
        let displayName: String
        var svoLines: [String]
    }

    private var textDigest: [(EntityKind, [TextDigestEntry])] {
        var byEntity: [String: EntityAccumulator] = [:]
        let hidden = hiddenKinds

        for claim in claims {
            let entityId = claim.entityIds?.first
            let entity = entityId.flatMap { entitiesById[$0] }

            if let merged = entity?.mergedIntoId, !merged.isEmpty { continue }

            let predVerb = (claim.predicateVerb ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let objPhrase = (claim.objectPhrase ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if predVerb == "is" && (objPhrase.hasPrefix("a ") || objPhrase.hasPrefix("an ")) { continue }

            let kind = entity.flatMap { EntityKind(apiType: $0.entityType) } ?? .date
            guard !hidden.contains(kind) else { continue }

            let displayName = entity?.canonicalName ?? claim.text
            let key = entityId ?? displayName

            let svo: String
            if !predVerb.isEmpty && !objPhrase.isEmpty {
                svo = "\(predVerb) \(objPhrase)"
            } else if !predVerb.isEmpty {
                svo = predVerb
            } else if !claim.text.isEmpty {
                svo = claim.text
            } else {
                continue
            }

            if byEntity[key] == nil {
                byEntity[key] = EntityAccumulator(kind: kind, displayName: displayName, svoLines: [svo])
            } else {
                byEntity[key]!.svoLines.append(svo)
            }
        }

        var byKind: [EntityKind: [TextDigestEntry]] = [:]
        for (_, accumulator) in byEntity {
            let entry = TextDigestEntry(displayName: accumulator.displayName, kind: accumulator.kind, svoLines: accumulator.svoLines)
            byKind[accumulator.kind, default: []].append(entry)
        }

        return EntityKind.displayOrder.compactMap { kind in
            guard !hidden.contains(kind) else { return nil }
            guard let entries = byKind[kind], !entries.isEmpty else { return nil }
            return (kind, entries.sorted { $0.displayName < $1.displayName })
        }
    }

    // MARK: - Text digest view

    @ViewBuilder
    private var textDigestView: some View {
        VStack(alignment: .leading, spacing: 10) {
            if textDigest.isEmpty {
                Text("No knowledge-graph entries for this document yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(textDigest, id: \.0) { kind, entries in
                    VStack(alignment: .leading, spacing: 4) {
                        Label(kind.label.uppercased(), systemImage: kind.systemImage)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.secondary)

                        ForEach(entries, id: \.displayName) { entry in
                            let prose = entry.svoLines.joined(separator: "; ")
                            // SwiftUI markdown bold for the entity name.
                            let raw = "**\(entry.displayName)** \(prose)"
                            if let attributed = try? AttributedString(markdown: raw) {
                                Text(attributed)
                                    .font(.caption)
                                    .fixedSize(horizontal: false, vertical: true)
                            } else {
                                Text(raw)
                                    .font(.caption)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
            }
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
            } else if displayMode == .text {
                textDigestView
            } else {
                ForEach(grouped, id: \.0) { kind, items in
                    EntityKindBlock(
                        kind: kind,
                        items: items,
                        onNavigateToSource: onNavigateToSource,
                        onClaimSelect: onClaimSelect
                    )
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
            // Text / List mode toggle
            Button {
                displayMode = .text
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .text ? Color.accentColor : Color.secondary)
            .help("Text digest")
            Button {
                displayMode = .list
            } label: {
                Image(systemName: "list.bullet")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .list ? Color.accentColor : Color.secondary)
            .help("List view")
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
            // include_descendants=true picks up the page-doc claims that
            // extract_all writes when this doc is a folder/group container
            // (#826). For leaf docs the BFS just returns the doc itself,
            // so the result is identical to the non-descendant query —
            // no extra cost to always pass it.
            let docClaims = try await entityService.listClaims(
                sourceDocumentId: documentId,
                includeDescendants: true,
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
        } catch is CancellationError {
            // Task superseded by a newer page selection — not a load failure.
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
    /// First source page document id for this entity. Multiple sources are
    /// not surfaced yet — folder-cleanup merges retain the first claim's
    /// source, which is good enough for click-through provenance. (#833)
    /// Defaults to nil so existing #Preview fixtures and any non-claim
    /// callers compile without modification.
    var sourceDocumentId: String?
    /// Page label as recorded on the claim (e.g. "page 4", "folio 12r").
    /// Rendered as inline parenthetical when present.
    var sourcePageLabel: String?
    /// Verbatim quote the LLM lifted the claim from (#893). Shown as
    /// an italicised tappable citation underneath the curated context
    /// when distinct from both the displayName and the context. Tap
    /// runs a library search for the exact text — same path as the
    /// OntologyBrowser ClaimSummaryCard.
    var sourceExcerpt: String?
    /// Additional SVO claims for this same entity (#1109). When an entity
    /// has multiple substantive claims, the first lands in context/sourceExcerpt
    /// above; the rest accumulate here and render as secondary rows.
    struct ExtraClaim {
        let claimId: String
        let context: String
        let sourceDocumentId: String?
        let sourcePageLabel: String?
        let sourceExcerpt: String?
    }
    var extraClaims: [ExtraClaim] = []
    var id: String { claimId }
}

/// Toggle between dense prose digest and grouped disclosure list.
private enum KGDisplayMode: String {
    case text
    case list
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

    /// Backend entity-type id used when firing a scoped search from a
    /// tap. Matches `entityTypeId(for:)` in LibraryView+ColumnConfig
    /// (the table-view keyword column uses the same ids).
    var searchScope: String {
        switch self {
        case .person:       return "people"
        case .location:     return "places"
        case .organization: return "organizations"
        case .event:        return "events"
        case .concept:      return "keywords"
        case .date:         return "dates"
        case .other:        return "keywords"  // best-effort fallback
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
    var onNavigateToSource: ((String) -> Void)?
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

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
                // Keywords as wrapping lozenges. Use the same EntityLozenge
                // component as the inspector + list-view so tap-to-search
                // works consistently and styling is uniform across all
                // entity rendering paths in the app. EntityKind.concept
                // maps to the 'keywords' artifact type — pass that so
                // taps fire `keywords:"<term>"` scoped queries.
                FlowLayout(spacing: 4) {
                    ForEach(items) { item in
                        EntityLozenge(name: item.displayName, entityType: "keywords")
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
                        EntityKindRow(
                            item: item,
                            kind: kind,
                            onNavigateToSource: onNavigateToSource,
                            onClaimSelect: onClaimSelect
                        )
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

/// One row inside an EntityKindBlock. The **name** is tappable —
/// clicking fires a scoped entity search (e.g. `person:"…"`) via the
/// `.ficheroEntitySearchRequested` notification, same path Keyword
/// lozenges use. Aliases / page reference / context render as plain
/// selectable text below for ⌘C. (#882)
private struct EntityKindRow: View {
    let item: GroupedItem
    let kind: EntityKind
    var onNavigateToSource: ((String) -> Void)?
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @EnvironmentObject private var claimFocusState: ClaimFocusState

    var body: some View {
        // Layout:
        //   line 1: [name button]  (aka alias1, alias2)  (p. label)   → arrow  [select claim]
        //   line 2: context  (when non-empty, non-redundant)
        // Name is its own Button so a tap doesn't have to compete with
        // textSelection on the rest of the row.
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Button(action: fireEntitySearch) {
                    Text(item.displayName)
                        .font(.body)
                        .foregroundStyle(claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.primary)
                }
                .buttonStyle(.plain)
                .help("Search for \"\(item.displayName)\"")
                .accessibilityHint("Searches for this \(kind.label.lowercased())")

                trailingText
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)

                // Claim selection button for bidirectional sync
                if let onClaimSelect = onClaimSelect {
                    Button(action: {
                        onClaimSelect(
                            item.claimId,
                            item.sourceExcerpt,
                            item.sourceDocumentId,
                            item.sourcePageLabel,
                            nil,
                            nil
                        )
                    }, label: {
                        Image(systemName: claimFocusState.isClaimSelected(item.claimId) ? "star.fill" : "star")
                            .font(.system(size: 12))
                            .foregroundStyle(claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.secondary)
                    })
                    .buttonStyle(.plain)
                    .help(
                        claimFocusState.isClaimSelected(item.claimId)
                            ? "Claim selected for highlighting"
                            : "Select claim for highlighting"
                    )
                }

                if let sourceId = item.sourceDocumentId,
                   let navigate = onNavigateToSource {
                    Button {
                        navigate(sourceId)
                    } label: {
                        Image(systemName: "arrow.right.circle")
                            .font(.body)
                            .foregroundStyle(Color.accentColor)
                    }
                    .buttonStyle(.plain)
                    .help("Go to source")
                }
            }

            if !item.context.isEmpty,
               item.context != item.displayName,
               !item.displayName.contains(item.context) {
                Text(item.context)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            // Verbatim source quote — only when distinct from both the
            // displayName and the curated context. Tap runs a library
            // search for the exact text (#893).
            if let excerpt = item.sourceExcerpt,
               !excerpt.isEmpty,
               excerpt != item.displayName,
               excerpt != item.context {
                Button {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": excerpt]
                    )
                } label: {
                    Text("\u{201C}\(excerpt)\u{201D}")
                        .font(.caption)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help("Search the library for this quote")
            }

            // Additional SVO claims for the same entity (#1109).
            // Each renders as an indented context + excerpt pair, visually
            // subordinate to the primary claim above.
            if !item.extraClaims.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(item.extraClaims, id: \.claimId) { extra in
                        if !extra.context.isEmpty,
                           extra.context != item.displayName,
                           extra.context != item.context {
                            Text(extra.context)
                                .font(.body)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                        if let excerpt = extra.sourceExcerpt,
                           !excerpt.isEmpty,
                           excerpt != extra.context,
                           excerpt != item.displayName {
                            Button {
                                NotificationCenter.default.post(
                                    name: .ficheroEntitySearchRequested,
                                    object: nil,
                                    userInfo: ["name": excerpt]
                                )
                            } label: {
                                Text("\u{201C}\(excerpt)\u{201D}")
                                    .font(.caption)
                                    .italic()
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .buttonStyle(.plain)
                            .help("Search the library for this quote")
                        }
                    }
                }
                .padding(.leading, 8)
            }
        }
        .padding(.vertical, 2)
    }

    private func fireEntitySearch() {
        NotificationCenter.default.post(
            name: .ficheroEntitySearchRequested,
            object: nil,
            userInfo: [
                "name": item.displayName,
                "entityType": kind.searchScope
            ]
        )
    }

    /// Aliases + page reference rendered as one selectable text run,
    /// sitting beside the tappable name on line 1.
    private var trailingText: Text {
        var text = Text("")
            .font(.caption)
            .foregroundStyle(.secondary)
        if !item.aliases.isEmpty {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text(" (aka " + item.aliases.joined(separator: ", ") + ")")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        if let pageRef = pageReference {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text("  (\(pageRef))")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        return text
    }

    /// Scholarly-style page reference: prefer the recorded label
    /// (e.g. "page 4", "folio 12r"); strip a leading "page " so we can
    /// abbreviate it to "p. 4". Returns nil when no label is available
    /// (don't fabricate a reference from nothing).
    private var pageReference: String? {
        guard let raw = item.sourcePageLabel?.trimmingCharacters(in: .whitespaces),
              !raw.isEmpty
        else { return nil }
        let lower = raw.lowercased()
        if lower.hasPrefix("page "), let numericPart = lower.split(separator: " ").last {
            return "p. \(numericPart)"
        }
        return raw
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
