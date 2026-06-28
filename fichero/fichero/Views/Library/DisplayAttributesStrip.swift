// swiftlint:disable file_length
import SwiftUI

/// Compact key-value strip at the top of the V2 inspector — modeled on
/// Tinderbox's "Displayed Attributes" panel. Read-only in Phase 1.
///
/// Shows the few fields a researcher checks most often when scanning a
/// document: status, kind, ingest mode, timestamps. The list is intentionally
/// short — anything more belongs in the Info tab. See
/// docs/architecture/swiftui/inspector_redesign.md.
struct DisplayAttributesStrip: View { // swiftlint:disable:this type_body_length
    let document: Document

    // Artifacts are loaded lazily so the user can opt to surface them as rows
    // (#1229 part 2). The same per-document, non-descendant scope the Artifacts
    // tab uses (#721) — a page shows only its own artifacts.
    @EnvironmentObject private var artifactService: ArtifactServiceGenerated

    /// Which fixed attributes the user has *hidden*, comma-joined raw values.
    /// Persisted as a global display preference (not per-window scene state) —
    /// the visible set is user-editable, never hardcoded (MEMORY: don't
    /// hardcode user-editable things). Default empty → every fixed attribute
    /// shows, matching pre-#1229 behaviour.
    @AppStorage("inspector.attributeStrip.hidden") private var hiddenRaw: String = ""
    /// Artifact types the user has chosen to surface, comma-joined. Default
    /// empty → no artifacts shown; they are opt-in.
    @AppStorage("inspector.attributeStrip.artifacts") private var shownArtifactsRaw: String = ""
    /// Knowledge-graph summaries surfaced at the top of the Content pane,
    /// comma-joined. Defaults to "entities" so the inspector reflects what's
    /// actually been extracted on the page — the entities row appears as the
    /// page gains entities (gated on a non-zero count in `rows`) — instead of
    /// staying blank by default (#2696). Claims remain opt-in. Still
    /// user-editable via the filter menu (#1246). Per-kind people/places rows
    /// are the larger design pass.
    @AppStorage("inspector.attributeStrip.kg") private var shownKGRaw: String = "entities"
    /// Scope for KG summaries. Defaults to the item's OWN records so a
    /// folder/PDF shows what belongs to it, not its children's mixed in
    /// (#2697); children are opt-in via the "Include children" toggle.
    @AppStorage("inspector.scope.includeChildren") private var includeChildren: Bool = false
    /// Document-metadata keys the user has surfaced, comma-joined. File
    /// metadata/info and any imported JSON all live in `document.metadata`,
    /// so this one bucket covers both. Opt-in (#1246).
    @AppStorage("inspector.attributeStrip.metadata") private var shownMetadataRaw: String = ""

    /// Knowledge-graph reads come from the same service the KG tab uses.
    @EnvironmentObject private var entityService: EntityServiceGenerated

    @State private var artifacts: [Artifact] = []
    /// KG counts for this document, nil until loaded (or on load failure).
    /// Drives the opt-in Entities/Claims rows (#1246).
    @State private var entityCount: Int?
    @State private var claimCount: Int?

    /// The fixed document attributes the strip can show. Case order is the
    /// display order. `path` is additionally gated on the document having one.
    enum DisplayAttribute: String, CaseIterable, Identifiable {
        case status, kind, ingest, path, created, modified
        var id: String { rawValue }
        var label: String {
            switch self {
            case .status: return "Status"
            case .kind: return "Kind"
            case .ingest: return "Ingest"
            case .path: return "Path"
            case .created: return "Created"
            case .modified: return "Modified"
            }
        }
    }

    /// Knowledge-graph summaries the strip can surface — peers to artifacts,
    /// each an opt-in count row (#1246).
    enum KGItem: String, CaseIterable, Identifiable {
        case entities, claims
        var id: String { rawValue }
        var label: String {
            switch self {
            case .entities: return "Entities"
            case .claims: return "Claims"
            }
        }
    }

    /// A single rendered line in the strip — a fixed attribute, a KG summary,
    /// a surfaced artifact type, or a document-metadata key. Unifying them lets
    /// one `ForEach` interleave the divider logic without an index-vs-data
    /// mismatch. (#1229, extended for KG + metadata in #1246.)
    private enum StripRow: Identifiable {
        case attribute(DisplayAttribute)
        case knowledge(KGItem)
        case artifact(String)
        case metadata(String)
        var id: String {
            switch self {
            case .attribute(let attr): return "attr:\(attr.rawValue)"
            case .knowledge(let item): return "kg:\(item.rawValue)"
            case .artifact(let type): return "art:\(type)"
            case .metadata(let key): return "meta:\(key)"
            }
        }
    }

    private var hiddenAttributes: Set<String> {
        csvSet(hiddenRaw)
    }

    private var shownArtifactTypes: Set<String> {
        csvSet(shownArtifactsRaw)
    }

    private var shownKGItems: Set<String> {
        csvSet(shownKGRaw)
    }

    private var shownMetadataKeys: Set<String> {
        csvSet(shownMetadataRaw)
    }

    /// Distinct artifact types available for this document, sorted for a stable
    /// menu + row order.
    private var availableArtifactTypes: [String] {
        Array(Set(artifacts.map(\.artifactType))).sorted()
    }

    /// Internal/derived metadata keys that aren't useful as surfaced rows —
    /// hashes, MIME guts, the raw page-content blobs, and the LINK bookmark.
    /// Matches the noise filter the Info tab's Technical Metadata uses.
    private static let noisyMetadataKeys: Set<String> = [
        "checksum", "hash", "md5", "sha256",
        "mime_type", "mimetype", "content_type",
        "page_content", "page_content_rtf",
        "transcription", "bookmark",
        // #1369: internal timeline extraction bucket shouldn't surface as a
        // top-strip facet.
        "dates"
    ]

    /// Document-metadata keys worth surfacing (file metadata/info + any
    /// imported JSON), noise filtered out, sorted for a stable menu order.
    private var availableMetadataKeys: [String] {
        document.metadata.keys
            .filter { !Self.noisyMetadataKeys.contains($0.lowercased()) }
            .sorted()
    }

    /// The ordered rows to render: visible fixed attributes, then the
    /// knowledge-graph summaries, artifact types, and metadata keys the user
    /// has switched on. Every source is opt-in past the fixed attributes, so
    /// the Content tab can surface *everything* available for the selection
    /// without crowding the default view (#1246).
    private var rows: [StripRow] {
        var result = DisplayAttribute.allCases
            .filter { shouldRender($0) }
            .map { StripRow.attribute($0) }
        result += KGItem.allCases
            .filter { shownKGItems.contains($0.rawValue) }
            // Entities surface "as they're added" — only when the page actually
            // has some — so a fresh/empty page isn't cluttered with "Entities —"
            // (#2696). Claims (opt-in) keep their explicit count/dash.
            .filter { $0 != .entities || (entityCount ?? 0) > 0 }
            .map { StripRow.knowledge($0) }
        result += availableArtifactTypes
            .filter { shownArtifactTypes.contains($0) }
            .map { StripRow.artifact($0) }
        result += availableMetadataKeys
            .filter { shownMetadataKeys.contains($0) }
            .map { StripRow.metadata($0) }
        return result
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            ForEach(Array(rows.enumerated()), id: \.element.id) { index, item in
                if index > 0 {
                    Divider()
                }
                rowView(for: item)
            }
        }
        .padding(.vertical, 6)
        .background(Color(.controlBackgroundColor))
        .task(id: document.id) {
            // Artifacts and KG counts are independent reads — fetch them
            // concurrently so the strip populates without serial latency.
            async let artifactLoad: Void = loadArtifacts()
            async let knowledgeLoad: Void = loadKnowledgeGraph()
            _ = await (artifactLoad, knowledgeLoad)

            // Normalize persisted CSV payloads so malformed/empty tokens from older
            // builds don't keep toggles in an inconsistent state across launches.
            hiddenRaw = csvString(hiddenAttributes)
            shownArtifactsRaw = csvString(shownArtifactTypes)
            shownKGRaw = csvString(shownKGItems)
            shownMetadataRaw = csvString(shownMetadataKeys)
        }
    }

    // MARK: - Header + filter menu

    private var header: some View {
        HStack(spacing: 6) {
            Text("Attributes")
                .font(.caption2)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            filterMenu
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 4)
    }

    private var filterMenu: some View {
        Menu {
            Section("Attributes") {
                ForEach(DisplayAttribute.allCases) { attr in
                    Toggle(attr.label, isOn: binding(for: attr))
                }
            }
            Section("Scope") {
                Button {
                    includeChildren = false
                } label: {
                    HStack {
                        Text("This item only")
                        Spacer(minLength: 0)
                        if !includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
                Button {
                    includeChildren = true
                } label: {
                    HStack {
                        Text("Include children")
                        Spacer(minLength: 0)
                        if includeChildren {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
            Section("Knowledge Graph") {
                ForEach(KGItem.allCases) { item in
                    Toggle(item.label, isOn: kgBinding(for: item))
                }
            }
            if !availableArtifactTypes.isEmpty {
                Section("Artifacts") {
                    ForEach(availableArtifactTypes, id: \.self) { type in
                        Toggle(displayName(for: type), isOn: artifactBinding(for: type))
                    }
                }
            }
            if !availableMetadataKeys.isEmpty {
                Section("Metadata") {
                    ForEach(availableMetadataKeys, id: \.self) { key in
                        Toggle(metadataLabel(for: key), isOn: metadataBinding(for: key))
                    }
                }
            }
        } label: {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .font(.caption)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Choose which attributes, knowledge graph, artifacts, and metadata to show")
    }

    // MARK: - Visibility + bindings

    /// A fixed attribute renders when the user hasn't hidden it — and, for
    /// `path`, only when the document actually has one (matching pre-#1229).
    private func shouldRender(_ attr: DisplayAttribute) -> Bool {
        guard !hiddenAttributes.contains(attr.rawValue) else { return false }
        if attr == .path {
            return !(document.path?.isEmpty ?? true)
        }
        return true
    }

    private func binding(for attr: DisplayAttribute) -> Binding<Bool> {
        Binding(
            get: { !hiddenAttributes.contains(attr.rawValue) },
            set: { show in
                var set = hiddenAttributes
                if show { set.remove(attr.rawValue) } else { set.insert(attr.rawValue) }
                hiddenRaw = csvString(set)
            }
        )
    }

    private func artifactBinding(for type: String) -> Binding<Bool> {
        Binding(
            get: { shownArtifactTypes.contains(type) },
            set: { show in
                var set = shownArtifactTypes
                if show { set.insert(type) } else { set.remove(type) }
                shownArtifactsRaw = csvString(set)
            }
        )
    }

    private func kgBinding(for item: KGItem) -> Binding<Bool> {
        Binding(
            get: { shownKGItems.contains(item.rawValue) },
            set: { show in
                var set = shownKGItems
                if show { set.insert(item.rawValue) } else { set.remove(item.rawValue) }
                shownKGRaw = csvString(set)
            }
        )
    }

    private func metadataBinding(for key: String) -> Binding<Bool> {
        Binding(
            get: { shownMetadataKeys.contains(key) },
            set: { show in
                var set = shownMetadataKeys
                if show { set.insert(key) } else { set.remove(key) }
                shownMetadataRaw = csvString(set)
            }
        )
    }

    // MARK: - Persistence helpers

    private func csvSet(_ raw: String) -> Set<String> {
        Set(raw.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty })
    }

    private func csvString(_ values: Set<String>) -> String {
        values
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted()
            .joined(separator: ",")
    }

    // MARK: - Row rendering

    @ViewBuilder
    private func rowView(for item: StripRow) -> some View {
        switch item {
        case .attribute(let attr):
            attributeRow(attr)
        case .knowledge(let kgItem):
            kgRow(kgItem)
        case .artifact(let type):
            row(displayName(for: type), value: artifactValue(for: type))
        case .metadata(let key):
            row(metadataLabel(for: key), value: metadataValue(for: key))
        }
    }

    /// A KG summary row. The count is the meaningful bit, so it's emphasised
    /// (primary, semibold) rather than rendered as flat secondary text — the
    /// "intelligently highlighted" treatment Daniel asked for (#1246).
    private func kgRow(_ item: KGItem) -> some View {
        let count: Int? = (item == .entities) ? entityCount : claimCount
        return row(item.label, value: count.map(String.init) ?? "—", emphasis: true)
    }

    @ViewBuilder
    private func attributeRow(_ attr: DisplayAttribute) -> some View {
        switch attr {
        case .status: row(attr.label, value: statusValue, color: statusColor)
        case .kind: row(attr.label, value: kindValue)
        case .ingest: row(attr.label, value: ingestValue)
        case .path: row(attr.label, value: document.path ?? "", monospaced: true)
        case .created: row(attr.label, value: relativeDateString(document.createdAt))
        case .modified: row(attr.label, value: relativeDateString(document.updatedAt))
        }
    }

    // MARK: - Artifact helpers

    private func displayName(for type: String) -> String {
        artifacts.first { $0.artifactType == type }?.artifactTypeDisplayName
            ?? type.capitalized
    }

    /// Value shown for an artifact row: the most-recent artifact's relative
    /// date, prefixed with a count when several of that type exist.
    private func artifactValue(for type: String) -> String {
        let matching = artifacts.filter { $0.artifactType == type }
        guard let latest = matching.max(by: { $0.createdAt < $1.createdAt }) else {
            return "—"
        }
        let date = relativeDateString(latest.createdAt)
        return matching.count > 1 ? "\(matching.count) · \(date)" : date
    }

    private func loadArtifacts() async {
        do {
            artifacts = try await artifactService.getArtifacts(
                forDocumentId: document.id,
                includeDescendants: false
            )
        } catch {
            // Artifacts are optional context — fall back to an empty list so
            // the fixed attribute rows still render.
            artifacts = []
        }
    }

    /// Load KG counts for the opt-in Entities/Claims rows. Mirrors the KG
    /// tab's canonical document KG query so summary counts and KG rows
    /// cannot drift across independent read paths (#1304).
    private func loadKnowledgeGraph() async {
        do {
            let response = try await entityService.documentKnowledgeGraph(
                documentId: document.id,
                includeChildren: includeChildren
            )
            claimCount = response.claimCount
            entityCount = response.entityCount
        } catch is CancellationError {
            // Superseded by a newer selection — leave the last counts in place.
        } catch {
            // KG is optional context — clear the counts so the rows show "—"
            // while the toggles stay available.
            claimCount = nil
            entityCount = nil
        }
    }

    // MARK: - Metadata helpers

    /// Title-case a raw metadata key (e.g. "File_Size" → "File Size").
    private func metadataLabel(for key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ")
            .split(separator: " ")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }

    /// Render a metadata value for the strip. Byte sizes are formatted, JSON
    /// collections are summarised by shape, everything else stringified — so
    /// the meaningful bit reads cleanly in a one-line row (#1246).
    private func metadataValue(for key: String) -> String {
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

    // MARK: - Row helpers

    @ViewBuilder
    private func row(
        _ label: String,
        value: String,
        color: Color = .primary,
        monospaced: Bool = false,
        emphasis: Bool = false
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 64, alignment: .leading)
            Text(value)
                .font(monospaced ? .caption.monospaced() : .caption)
                // Emphasised rows (e.g. KG counts) get semibold weight so the
                // meaningful value stands out from the flat secondary label.
                .fontWeight(emphasis ? .semibold : .regular)
                .foregroundStyle(color)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 3)
    }

    // MARK: - Value computation

    private var statusValue: String {
        switch document.status {
        case .pending: return "Pending"
        case .processing: return "Processing"
        case .completed: return "Completed"
        case .failed: return "Failed"
        }
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .secondary
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }

    private var kindValue: String {
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

    private var ingestValue: String {
        document.isLinked ? "LINK" : "COPY"
    }

    private func relativeDateString(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .abbreviated
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}
