// swiftlint:disable file_length
// V2 inspector views (DisplayAttributesStrip, ArtifactPanel,
// DocumentInspectorContentV2) are appended at the bottom of this file —
// keeping them inline avoids a pbxproj edit (MEMORY: Swift main target not
// file-sync'd). When V2 promotes to default-on (per
// docs/architecture/swiftui/inspector_redesign.md Phase 2), they can be
// split into their own files at that point.
import SwiftUI

// MARK: - Notification Names

extension Notification.Name {
    /// Posted when a claim is selected in the inspector
    static let claimSelectedInInspector = Notification.Name("claimSelectedInInspector")
}

/// Tab selection for document inspector. Order matters — left-to-right is
/// content / knowledge graph / info, per Daniel's mental model:
/// "the document itself" → "the structured world inside it" → "metadata
/// about the document".
enum InspectorTab: String, CaseIterable, Identifiable {
    case content = "Content"
    case annotations = "Annotations"
    case knowledgeGraph = "Knowledge Graph"
    case map = "Map"
    case artifacts = "Artifacts"
    case info = "Info"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .content: return "doc.text"
        case .annotations: return "highlighter"
        case .knowledgeGraph: return "point.3.connected.trianglepath.dotted"
        case .map: return "map"
        case .artifacts: return "shippingbox"
        case .info: return "info.circle"
        }
    }
}

/// Inspector panel showing document metadata and details
struct DocumentInspector: View {
    let document: Document?
    /// Click-through callback for KG entity rows: receives a source page
    /// document id; ContentView resolves it to the parent file and selects
    /// it so the user can read the source. Optional so the previews and
    /// any non-ContentView host still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?

    @SceneStorage("inspectorSelectedTab") private var selectedTab: InspectorTab = .content
    @EnvironmentObject private var entityService: EntityServiceGenerated
    @ObservedObject private var featureManager = FeatureManager.shared
    @ObservedObject private var claimFocusState = ClaimFocusState.shared

    var body: some View {
        Group {
            if let doc = document {
                documentDetail(doc)
            } else {
                emptyState
            }
        }
        .frame(minWidth: 220, maxWidth: .infinity, maxHeight: .infinity)
        .environmentObject(claimFocusState)
        .onReceive(NotificationCenter.default.publisher(for: .ficheroOpenClaimSource)) { note in
            guard let info = note.userInfo else { return }
            if info["claimId"] is String || info["entityId"] is String {
                selectedTab = .knowledgeGraph
            }
        }
    }

    // MARK: - Document Detail

    private func documentDetail(_ doc: Document) -> some View {
        // Tab bar sits at the very top (matching every other pane header).
        // The attribute strip moved below the tabs and now lives *inside* the
        // Content tab only — it described the document, which is the Content
        // tab's concern, and it shouldn't crowd the Knowledge Graph / Map /
        // Artifacts / Info tabs. (#1228)
        VStack(spacing: 0) {
            tabBar
            Divider()
            tabContent(for: doc)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxHeight: .infinity)
    }

    /// Xcode-style icon-only tab bar
    @ViewBuilder
    private var tabBar: some View {
        HStack(spacing: 2) {
            ForEach(InspectorTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Image(systemName: tab.icon)
                        .font(.system(size: 16, weight: .regular))
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(selectedTab == tab
                                ? Color.accentColor.opacity(0.15)
                                : Color.clear)
                )
                .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                .help(tab.rawValue)
                // Stable per-tab XCUITest hook, e.g. "inspectorTab-Content" (#1230).
                .accessibilityIdentifier("inspectorTab-\(tab.rawValue)")
            }
        }
        .padding(.horizontal, 8)
        .frame(height: MiniToolbar<EmptyView>.standardHeight)
        // XCUITest hook for the inspector tab bar (#1230).
        .accessibilityIdentifier("inspectorTabBar")
    }

    /// Tab content for the selected tab
    @ViewBuilder
    private func tabContent(for doc: Document) -> some View {
        switch selectedTab {
        case .content:
            contentTab(for: doc)
        case .annotations:
            DocumentInspectorAnnotationsTab(document: doc)
        case .knowledgeGraph:
            knowledgeGraphTab(for: doc)
        case .map:
            mapTab
        case .artifacts:
            artifactsTab(for: doc)
        case .info:
            infoTab(for: doc)
        }
    }

    @ViewBuilder
    private func contentTab(for doc: Document) -> some View {
        VStack(spacing: 0) {
            DisplayAttributesStrip(document: doc)
            Divider()
            DocumentInspectorContentV2(document: doc, mode: .pageContentOnly)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    @ViewBuilder
    private func knowledgeGraphTab(for doc: Document) -> some View {
        ScrollView {
            KnowledgeGraphInspectorSection(
                documentId: doc.id,
                entityService: entityService,
                onNavigateToSource: onNavigateToSource,
                onClaimSelect: { claimId, claimText, sourceDocId, pageLabel, charStart, charEnd in
                    NotificationCenter.default.post(
                        name: .claimSelectedInInspector,
                        object: nil,
                        userInfo: [
                            "claimId": claimId,
                            "claimText": claimText as Any,
                            "sourceDocumentId": sourceDocId as Any,
                            "pageLabel": pageLabel as Any,
                            "charStart": charStart as Any,
                            "charEnd": charEnd as Any
                        ]
                    )
                }
            )
            .padding()
        }
    }

    private var mapTab: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Page-scoped Knowledge Graph (Map View)")
                    .font(.headline)
                Text("Showing entities and relationships specific to this document.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.gray.opacity(0.1))
                    .frame(height: 300)
                    .overlay(
                        Text("Map tab placeholder - page-scoped graph would appear here")
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding()
                    )
            }
            .padding()
        }
    }

    @ViewBuilder
    private func artifactsTab(for doc: Document) -> some View {
        DocumentInspectorContentV2(document: doc, mode: .artifactsOnly)
    }

    @ViewBuilder
    private func infoTab(for doc: Document) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                DocumentInspectorInfoTab(document: doc)
                if !doc.metadata.isEmpty || doc.path != nil {
                    DocumentInspectorMetadataTab(document: doc)
                }
                Spacer()
            }
            .padding()
        }
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
}

// MARK: - Preview

#Preview("Empty") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    DocumentInspector(document: nil)
        .environmentObject(library.artifactService)
        .environmentObject(library.entityService)
        .frame(width: 280, height: 400)
}

#Preview("With Document") {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    let mockDocument = Document(
        id: UUID().uuidString,
        parentId: nil,
        docType: .file,
        fileType: .pdf,
        name: "Sample Document.pdf",
        path: nil,
        sequence: nil,
        bbox: nil,
        status: .completed,
        metadata: [:],
        pageContent: nil,
        createdAt: Date(),
        updatedAt: Date()
    )

    DocumentInspector(document: mockDocument)
        .environmentObject(library.artifactService)
        .environmentObject(library.entityService)
        .frame(width: 280, height: 400)
}

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
    /// Knowledge-graph summaries the user has surfaced ("entities","claims"),
    /// comma-joined. Opt-in like artifacts (#1246).
    @AppStorage("inspector.attributeStrip.kg") private var shownKGRaw: String = ""
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
        Set(hiddenRaw.split(separator: ",").map(String.init))
    }

    private var shownArtifactTypes: Set<String> {
        Set(shownArtifactsRaw.split(separator: ",").map(String.init))
    }

    private var shownKGItems: Set<String> {
        Set(shownKGRaw.split(separator: ",").map(String.init))
    }

    private var shownMetadataKeys: Set<String> {
        Set(shownMetadataRaw.split(separator: ",").map(String.init))
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
        "transcription", "bookmark"
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
                hiddenRaw = set.sorted().joined(separator: ",")
            }
        )
    }

    private func artifactBinding(for type: String) -> Binding<Bool> {
        Binding(
            get: { shownArtifactTypes.contains(type) },
            set: { show in
                var set = shownArtifactTypes
                if show { set.insert(type) } else { set.remove(type) }
                shownArtifactsRaw = set.sorted().joined(separator: ",")
            }
        )
    }

    private func kgBinding(for item: KGItem) -> Binding<Bool> {
        Binding(
            get: { shownKGItems.contains(item.rawValue) },
            set: { show in
                var set = shownKGItems
                if show { set.insert(item.rawValue) } else { set.remove(item.rawValue) }
                shownKGRaw = set.sorted().joined(separator: ",")
            }
        )
    }

    private func metadataBinding(for key: String) -> Binding<Bool> {
        Binding(
            get: { shownMetadataKeys.contains(key) },
            set: { show in
                var set = shownMetadataKeys
                if show { set.insert(key) } else { set.remove(key) }
                shownMetadataRaw = set.sorted().joined(separator: ",")
            }
        )
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
    /// tab's claim query (include_descendants picks up page-doc claims on a
    /// container); the entity count is the distinct set of every entity any
    /// claim references. Counts only — no per-entity fetch (#1246).
    private func loadKnowledgeGraph() async {
        do {
            let claims = try await entityService.listClaims(
                sourceDocumentId: document.id,
                includeDescendants: true,
                limit: 500
            )
            claimCount = claims.count
            entityCount = Set(claims.flatMap { $0.entityIds ?? [] }).count
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

/// One read-only panel showing a single artifact (transcription, catalogue,
/// summary, etc.) in the V2 inspector. Each artifact gets its own panel —
/// new artifacts append rather than replace, so workflow re-runs never
/// overwrite what's already on screen.
///
/// Phase 1: read-only display. Phase 2 will add per-artifact actions
/// (copy, regenerate, hide). See docs/architecture/swiftui/inspector_redesign.md.
struct ArtifactPanel: View { // swiftlint:disable:this type_body_length
    enum PanelKind {
        case artifact(Artifact)
        /// Special case for showing the document's `page_content` so existing
        /// docs aren't blank in V2 before notes-as-artifact migrates over.
        case pageContent(text: String)
    }

    let kind: PanelKind
    /// Optional delete action. When provided, a trash button shows in the
    /// header on hover. nil hides the button (use for kinds that aren't
    /// individually deletable, like `pageContent` which is a Document field).
    var onDelete: (() -> Void)?
    /// Optional save action. When provided, an edit pencil shows in the
    /// header. The closure receives the new content (RTF source if the
    /// editor produced rich text, plain otherwise) and is responsible for
    /// persisting it. nil hides the edit affordance (read-only panel).
    var onSave: ((String) async -> Void)?

    @AppStorage("editor.rulersVisible") private var rulersVisible = true
    @AppStorage("editor.fontName") private var fontName: String = "System"
    @AppStorage("editor.fontSize") private var fontSize: Double = 14
    @AppStorage("editor.lineSpacing") private var lineSpacing: Double = 4
    @AppStorage("editor.marginHorizontal") private var marginH: Double = 16
    @AppStorage("editor.marginVertical") private var marginV: Double = 12

    /// Whether the panel starts expanded if there's no remembered choice.
    /// `true` for Page Content; `false` for generated artifacts.
    let defaultExpanded: Bool

    /// When true the content editor expands to fill all available vertical
    /// space (top-aligned) rather than sizing to its intrinsic content height.
    /// Set only for the Page Content panel in the Content tab's no-ScrollView
    /// layout, so the editor runs full-height below the attribute strip with no
    /// vertical centring (#1286). Left false elsewhere to preserve the
    /// intrinsic-height sizing the ScrollView path relies on (#960/#1062).
    let fillsHeight: Bool

    @State private var isExpanded: Bool

    /// UserDefaults key for this panel's expansion state, keyed by both
    /// artifact type AND producing provider so two transcriptions on the same
    /// document (Apple Vision + Qwen VL) maintain independent expand/collapse
    /// state across document switches and app launches. Without the provider
    /// in the key, collapsing the Apple Vision transcription on doc A would
    /// also collapse the Qwen transcription on doc B (#765).
    private static func storageKey(for kind: PanelKind) -> String {
        switch kind {
        case .pageContent:
            return "inspector.panel.expanded.pageContent"
        case .artifact(let artifact):
            let providerSuffix = (artifact.provider?.isEmpty == false)
                ? ".\(artifact.provider!)"
                : ""
            return "inspector.panel.expanded.\(artifact.artifactType)\(providerSuffix)"
        }
    }

    init(
        kind: PanelKind,
        defaultExpanded: Bool = true,
        fillsHeight: Bool = false,
        onDelete: (() -> Void)? = nil,
        onSave: ((String) async -> Void)? = nil
    ) {
        self.kind = kind
        self.defaultExpanded = defaultExpanded
        self.fillsHeight = fillsHeight
        self.onDelete = onDelete
        self.onSave = onSave

        // Read remembered choice if any; otherwise fall back to default.
        // `object(forKey:)` distinguishes "never set" (nil) from "set to
        // false" — required so first-run uses the parameter default,
        // not a coerced `false` from `bool(forKey:)`.
        let key = Self.storageKey(for: kind)
        let initial = (UserDefaults.standard.object(forKey: key) as? Bool) ?? defaultExpanded
        self._isExpanded = State(initialValue: initial)
    }
    @State private var confirmingDelete: Bool = false
    @State private var draftAttributedText: NSAttributedString = NSAttributedString(string: "")
    @State private var editorRevision: Int = 0
    @State private var isSaving: Bool = false
    @State private var saveError: String?
    @State private var autoSaveTask: Task<Void, Never>?
    @State private var lastSeededContent: String = ""
    @StateObject private var richTextController = RichTextController()

    /// Page Content is primary content and renders always-expanded with no
    /// collapse chrome; generated artifacts stay collapsable (#1245).
    private var isPageContent: Bool {
        if case .pageContent = kind { return true }
        return false
    }

    var body: some View {
        // Daniel feedback 2026-04-27: drop the rounded-rect box outline (no
        // horizontal lines), let the editor go full panel width (no inner
        // horizontal padding), let separation between panels be just the
        // VStack spacing. Header still gets a little horizontal padding so
        // the title doesn't kiss the inspector edge.
        //
        // Sizing: when expanded, the panel flexes (maxHeight: .infinity) so
        // it fills remaining inspector space — and when there are multiple
        // expanded siblings, SwiftUI's VStack splits space equally. When
        // collapsed, the panel has no flex, so it shrinks to its header
        // height (~30 px) and lets siblings absorb the freed space.
        Group {
            if isPageContent {
                // Page Content is the document's PRIMARY content, not an
                // optional artifact — render it with NO disclosure chrome and
                // NO title row. The title is always "Page Content", so the
                // header is redundant; dropping it reclaims that space and lets
                // the editor start right below the attribute strip (#1286). The
                // content is top-aligned and fills the available height when the
                // panel owns the inspector pane (fillsHeight), so there's no
                // vertical centring / dead space (#1245, #1286).
                contentBody
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .frame(
                        maxWidth: .infinity,
                        maxHeight: fillsHeight ? .infinity : nil,
                        alignment: .top
                    )
            } else {
                VStack(alignment: .leading, spacing: 0) {
                    DisclosureGroup(isExpanded: $isExpanded) {
                        contentBody
                            .padding(.bottom, 6)
                            .padding(.top, 2)
                    } label: {
                        header
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                }
            }
        }
        // Sizing: AttributedTextEditor now reports its layoutManager-used
        // height via sizeThatFits, so an expanded panel matches its actual
        // content. We keep a small min so empty editors don't collapse to
        // a sliver (Daniel 2026-05-05: "the height was 0"); long artifacts
        // grow naturally and the outer ScrollView handles overflow (#960).
        // Collapsed panels have no frame and shrink to header height (~30 px).
        // Page Content is never collapsed, so it always gets the min.
        .frame(minHeight: (isPageContent || isExpanded) ? 60 : nil)
        // Clip so the editor's AppKit text view can't paint outside the panel's
        // SwiftUI frame onto the attribute strip above it (#1245).
        .clipped()
        .onChange(of: isExpanded) { _, newValue in
            // Persist the user's choice so it carries across documents
            // and across app launches. See `storageKey(for:)` for keying.
            UserDefaults.standard.set(newValue, forKey: Self.storageKey(for: kind))
        }
        .confirmationDialog(
            "Delete this artifact?",
            isPresented: $confirmingDelete,
            titleVisibility: .visible
        ) {
            Button("Delete", role: .destructive) { onDelete?() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(deleteMessage)
        }
    }

    // MARK: - Header

    @ViewBuilder
    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: iconName)
                .foregroundStyle(.secondary)
                .font(.system(size: 13))
            Text(title)
                .font(.subheadline)
                .fontWeight(.medium)
            if let subtitle = subtitle {
                Text("·")
                    .foregroundStyle(.tertiary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer()
            // Save indicator (subtle): spinner while saving, green check when
            // idle and saved. No mode toggle — V2 panels are always editable
            // (Daniel feedback 2026-04-27 after preferring V1's always-on
            // behavior). Just type. Auto-saves on the debounce.
            if onSave != nil {
                if isSaving {
                    ProgressView().controlSize(.small)
                } else if saveError == nil {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.green.opacity(0.7))
                        .help("Saved")
                }
            }
            if onDelete != nil {
                Button {
                    confirmingDelete = true
                } label: {
                    Image(systemName: "trash")
                        .font(.system(size: 11))
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                .help("Delete this artifact")
            }
        }
    }

    private var deleteMessage: String {
        switch kind {
        case .artifact(let artifact):
            return "\(title) from \(artifact.provider ?? "unknown") will be removed."
        case .pageContent:
            return "Page content will be cleared."
        }
    }

    // MARK: - Content body
    //
    // Always render via AttributedTextEditor — toggling between a plain
    // Text(read) and an editor(edit) was stripping formatting in the read
    // view (Daniel: "not displaying the rtf, unless I click [edit]") and
    // was responsible for the per-panel layout looking inconsistent. One
    // editor for both modes, isEditable flips the cursor/typing behavior.
    @ViewBuilder
    private var contentBody: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Check if this is a structured output that should be read-only
            if isStructuredOutput {
                structuredOutputView
                    .frame(maxWidth: .infinity)
                    .background(Color(.textBackgroundColor))
                    .cornerRadius(4)
            } else {
                // Format controls live in the AppKit ruler view (Styles / alignment /
                // Spacing / Lists strip that AppKit draws above its numeric ruler)
                // and in the Format menu (bold/italic/underline shortcuts). No
                // separate SwiftUI format bar.
                AttributedTextEditor(
                    text: $draftAttributedText,
                    isEditable: onSave != nil,
                    rulersVisible: rulersVisible,
                    fontName: fontName,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                    marginH: marginH,
                    marginV: marginV,
                    contentRevision: editorRevision,
                    onTextChanged: { scheduleAutoSave() },
                    onEditingChanged: { editing in
                        if !editing { Task { await flushAutoSave() } }
                    },
                    onRulerVisibilityChanged: { visible in
                        if rulersVisible != visible { rulersVisible = visible }
                    },
                    marginLeading: marginH,
                    marginTrailing: 0,
                    controller: richTextController
                )
                // Width stretches; height comes from AttributedTextEditor's
                // sizeThatFits (its layoutManager.usedRect). No maxHeight in the
                // ScrollView path: letting it claim .infinity there made every
                // expanded panel fill the viewport (#960). When fillsHeight is
                // set (Page Content in the no-ScrollView Content tab), the
                // editor DOES claim .infinity so it runs full-height (#1286).
                .frame(maxWidth: .infinity, maxHeight: fillsHeight ? .infinity : nil)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
            }
            if let saveError {
                Text(saveError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
        .task(id: rawArtifactContent) {
            // Re-seed when the artifact content changes externally (workflow
            // re-run, navigation to a different doc). Skip if the change
            // came from our own auto-save echoing back, detected by the
            // lastSeededContent watermark.
            guard lastSeededContent != rawArtifactContent else { return }
            draftAttributedText = decodeArtifactContent(rawArtifactContent)
            lastSeededContent = rawArtifactContent
            editorRevision += 1
        }
    }

    // MARK: - Edit mode helpers

    /// Debounced auto-save. The previous explicit Save button created a
    /// "did my edit save?" anxiety loop — auto-save with a small visible
    /// indicator is calmer. (Daniel feedback 2026-04-26.)
    private func scheduleAutoSave() {
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(800))
            if Task.isCancelled { return }
            await performSave()
        }
    }

    private func flushAutoSave() async {
        autoSaveTask?.cancel()
        autoSaveTask = nil
        await performSave()
    }

    private func performSave() async {
        guard let onSave, !isSaving else { return }
        isSaving = true
        defer { isSaving = false }
        let encoded = encodeArtifactContent(draftAttributedText)
        // Mark the watermark BEFORE the save round-trips. When the engine echoes
        // the new pageContent/artifact content back through `rawArtifactContent`,
        // the `.task(id:)` guard `lastSeededContent != rawArtifactContent` will
        // short-circuit instead of reseeding the editor. Without this, every
        // successful save re-runs decodeArtifactContent on the just-saved RTF,
        // which costs the cursor/selection and looks to the user like the edit
        // didn't take.
        lastSeededContent = encoded
        await onSave(encoded)
    }

    /// Raw content used when seeding the editor — for `.artifact` we use the
    /// content field as the editor source, even if it's RTF, so formatting
    /// round-trips. For `.pageContent` we don't have access to the document's
    /// metadata-stored RTF here (we'd need to plumb it through), so plain
    /// text is the editable surface.
    private var rawArtifactContent: String {
        switch kind {
        case .pageContent(let text): return text
        case .artifact(let artifact): return artifact.content ?? ""
        }
    }

    /// Decode an artifact's stored content into an NSAttributedString. RTF
    /// source (`{\rtf...`) is parsed; plain text becomes a styled run.
    private func decodeArtifactContent(_ content: String) -> NSAttributedString {
        if content.hasPrefix("{\\rtf"),
           let data = content.data(using: .utf8),
           let attr = try? NSAttributedString(
            data: data,
            options: [.documentType: NSAttributedString.DocumentType.rtf],
            documentAttributes: nil
           ) {
            return attr
        }
        return NSAttributedString(string: content)
    }

    /// Encode an NSAttributedString back to a content string. Inline RTF
    /// source (not base64) so the artifact's `content` field stays human-
    /// readable when the artifact is plain text and round-trips losslessly
    /// when the user added formatting.
    ///
    /// Custom paragraph styles (ruler tab stops, indents, line spacing
    /// changes) MUST round-trip through RTF — earlier this function
    /// excluded .paragraphStyle from the formatting check, which made
    /// ruler edits silently lose on save (Daniel feedback 2026-04-26).
    private func encodeArtifactContent(_ attr: NSAttributedString) -> String {
        let fullRange = NSRange(location: 0, length: attr.length)
        let plain = attr.string

        var hasFormatting = false
        let defaultPara = NSParagraphStyle.default
        attr.enumerateAttributes(in: fullRange) { attrs, _, stop in
            for (key, value) in attrs {
                if key == .paragraphStyle {
                    if let para = value as? NSParagraphStyle, para != defaultPara {
                        hasFormatting = true
                    }
                    continue
                }
                hasFormatting = true
            }
            if hasFormatting { stop.pointee = true }
        }

        if !hasFormatting { return plain }

        guard let data = try? attr.data(
            from: fullRange,
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        ), let rtfString = String(data: data, encoding: .utf8) else {
            return plain
        }
        return rtfString
    }

    // MARK: - Computed properties

    private var iconName: String {
        switch kind {
        case .pageContent: return "doc.text"
        case .artifact(let artifact):
            switch artifact.artifactType {
            case "transcription": return "text.quote"
            case "catalogue": return "books.vertical"
            case "summary": return "text.alignleft"
            case "key_people", "people": return "person.2"
            case "timeline", "dates": return "calendar"
            case "keywords": return "tag"
            case "rivers": return "water.waves"
            case "events": return "star"
            case "mines": return "hammer"
            case "properties": return "house"
            case "legal_references": return "scale.3d"
            default: return "sparkles"
            }
        }
    }

    private var title: String {
        switch kind {
        case .pageContent: return "Page Content"
        case .artifact(let artifact):
            return artifact.artifactType
                .split(separator: "_")
                .map { $0.prefix(1).uppercased() + $0.dropFirst() }
                .joined(separator: " ")
        }
    }

    private var subtitle: String? {
        switch kind {
        case .pageContent: return nil
        case .artifact(let artifact):
            var parts: [String] = []
            if let provider = artifact.provider, !provider.isEmpty { parts.append(provider) }
            if let model = artifact.model, !model.isEmpty { parts.append(model) }
            return parts.isEmpty ? nil : parts.joined(separator: " · ")
        }
    }

    private var timestamp: String? {
        switch kind {
        case .pageContent: return nil
        case .artifact(let artifact):
            // RelativeDateTimeFormatter renders <1 minute as "in 0 secs",
            // which Daniel correctly called silly. For fresh artifacts show
            // "just now"; otherwise the abbreviated relative string.
            let interval = abs(Date().timeIntervalSince(artifact.createdAt))
            if interval < 60 { return "just now" }
            let formatter = RelativeDateTimeFormatter()
            formatter.unitsStyle = .abbreviated
            return formatter.localizedString(for: artifact.createdAt, relativeTo: Date())
        }
    }

    private var bodyText: String {
        switch kind {
        case .pageContent(let text):
            return text.isEmpty ? "(empty)" : text
        case .artifact(let artifact):
            guard let content = artifact.content, !content.isEmpty else {
                return "(no text)"
            }
            // If the stored content is RTF source, render the plain string
            // for the read view. The decode→encode round-trip on the editor
            // path preserves the formatting; the read view shows plain so
            // users see what's actually written without RTF chrome.
            if content.hasPrefix("{\\rtf"),
               let data = content.data(using: .utf8),
               let attr = try? NSAttributedString(
                data: data,
                options: [.documentType: NSAttributedString.DocumentType.rtf],
                documentAttributes: nil
               ) {
                return attr.string
            }
            return content
        }
    }

    /// Check if this artifact type should be read-only (structured outputs)
    private var isStructuredOutput: Bool {
        switch kind {
        case .pageContent:
            return false
        case .artifact(let artifact):
            // Structured outputs that shouldn't be edited as RTF
            let structuredTypes: Set<String> = ["entities", "classification", "embedding", "grouping", "segmentation"]
            return structuredTypes.contains(artifact.artifactType)
        }
    }

    /// Formatted view for structured outputs (JSON formatted)
    @ViewBuilder
    private var structuredOutputView: some View {
        switch kind {
        case .pageContent:
            // Shouldn't happen since isStructuredOutput is false for pageContent
            Text("Unsupported content type")
                .foregroundColor(.red)
        case .artifact(let artifact):
            if let content = artifact.content, !content.isEmpty {
                // Try to parse as JSON first for structured data
                if let jsonData = content.data(using: .utf8),
                   let jsonObject = try? JSONSerialization.jsonObject(with: jsonData, options: []),
                   let formattedJSON = try? JSONSerialization.data(
                       withJSONObject: jsonObject, options: [.prettyPrinted]
                   ) {
                    if let formattedString = String(data: formattedJSON, encoding: .utf8) {
                        ScrollView {
                            Text(formattedString)
                                .font(.system(.body, design: .monospaced))
                                .foregroundColor(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding()
                                .cornerRadius(4)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 200)
                    } else {
                        fallbackStructuredView(content: content)
                    }
                } else {
                    fallbackStructuredView(content: content)
                }
            } else {
                Text("(no content)")
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    /// Fallback view for structured content that isn't valid JSON
    @ViewBuilder
    private func fallbackStructuredView(content: String) -> some View {
        ScrollView {
            Text(content)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .cornerRadius(4)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 200)
    }
}

/// V2 inspector Content tab. Tinderbox-style layout:
///   - DisplayAttributesStrip at top (compact key-value).
///   - One ArtifactPanel per artifact below.
///   - The document's `page_content` (if any) renders as one final panel
///     so existing data is visible without a migration.
///
/// Phase 1: read-only. No save logic, no caching, no signature dance —
/// we re-fetch artifacts when the document selection or workflow events
/// change, full stop. See docs/architecture/swiftui/inspector_redesign.md.
struct DocumentInspectorContentV2: View {
    /// Which panels to render. The Content tab shows only the document's
    /// page content (the source text), Artifacts shows only the generated
    /// artifacts. `.all` keeps the original combined behaviour for any
    /// caller that still wants both.
    enum Mode {
        case all
        case pageContentOnly
        case artifactsOnly
    }

    let document: Document
    var mode: Mode = .all

    @EnvironmentObject private var artifactService: ArtifactServiceGenerated
    @EnvironmentObject private var documentService: DocumentServiceGenerated
    @EnvironmentObject private var documentStore: DocumentStore
    @Environment(WorkflowExecutionObserver.self) private var executionObserver

    @State private var artifacts: [Artifact] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var actionError: String?

    var body: some View {
        // Two layout modes:
        //
        // .pageContentOnly — exactly one panel (Page Content). Use a
        // direct flex layout so the editor expands to fill the inspector
        // pane height. No ScrollView (the editor manages its own scroll).
        //
        // .all / .artifactsOnly — many panels (transcription, catalogue,
        // people, places, etc.). Each panel reserves at least 100pt; with
        // 13+ panels the stack overflows the inspector — wrap in
        // ScrollView so the user can scroll through them. Without the
        // wrapper the overflow pushed sibling chrome (the inspector's
        // own tab bar) offscreen.
        Group {
            if mode == .pageContentOnly {
                panelStack(spacing: 8)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            } else {
                ScrollView {
                    panelStack(spacing: 8)
                        .frame(maxWidth: .infinity, alignment: .top)
                }
            }
        }
        .task(id: document.id) {
            await loadArtifacts()
        }
        .onChange(of: executionObserver.fileCompletedCount) { _, _ in
            // Refresh after individual file completions — but don't compete
            // with an in-flight load.
            Task { await loadArtifacts() }
        }
        .onChange(of: executionObserver.workflowCompletedCount) { _, _ in
            Task { await loadArtifacts() }
        }
    }

    // MARK: - Subviews

    @ViewBuilder
    private func panelStack(spacing: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            if let loadError {
                errorBox(loadError)
            }
            if let actionError {
                errorBox(actionError)
            }

            // Page Content panel — only when the mode wants it. The Content
            // tab shows just this so the user can edit / type notes against
            // the source text without artifact noise; the Artifacts tab
            // suppresses it so the panel list is purely workflow output.
            if mode != .artifactsOnly {
                ArtifactPanel(
                    kind: .pageContent(text: document.pageContent ?? ""),
                    // In pageContentOnly there's no outer ScrollView, so the
                    // editor fills the pane top-down instead of centring (#1286).
                    fillsHeight: mode == .pageContentOnly,
                    onSave: { newContent in
                        await savePageContent(newContent)
                    }
                )
                // In pageContentOnly mode there's no outer ScrollView, so
                // the panel can safely claim all remaining inspector height.
                // Top alignment keeps the content pinned just below the
                // attribute strip rather than floating centred (#1062, #1286).
                .frame(
                    maxWidth: .infinity,
                    maxHeight: mode == .pageContentOnly ? .infinity : nil,
                    alignment: .top
                )
            }

            // Generated artifacts — only when the mode wants them. Each one
            // is editable (RTF round-trips, auto-save) and deletable.
            if mode != .pageContentOnly {
                ForEach(sortedArtifacts) { artifact in
                    ArtifactPanel(
                        kind: .artifact(artifact),
                        // Start collapsed so the inspector reads as a list
                        // of headers; users expand the one they want.
                        defaultExpanded: false,
                        onDelete: { Task { await deleteArtifact(artifact) } },
                        onSave: { newContent in
                            await saveArtifact(artifact, content: newContent)
                        }
                    )
                }

                // Hint shown when no generated artifacts exist.
                if !isLoading && sortedArtifacts.isEmpty && loadError == nil {
                    emptyState
                }
            }

            if isLoading && artifacts.isEmpty {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Loading artifacts…").font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "sparkles")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No content yet")
                .font(.callout)
            Text("Run a workflow to generate transcriptions, catalogues, or summaries.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 32)
    }

    @ViewBuilder
    private func errorBox(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Retry") {
                Task { await loadArtifacts() }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .padding(.horizontal, 8)
    }

    // MARK: - Data

    private var sortedArtifacts: [Artifact] {
        // Group raw + cleaned pairs together (people / people_clean,
        // keywords / keywords_clean) by base type, with the *_clean entry
        // first within each pair (the cleaned canonical view is the
        // authoritative one; raw is the per-page substrate that
        // generated it). Within the same exact type, newer first —
        // useful when multiple model runs of the same type exist.
        artifacts.sorted {
            let aBase = baseType(of: $0.artifactType)
            let bBase = baseType(of: $1.artifactType)
            if aBase != bBase { return aBase < bBase }
            let aClean = $0.artifactType.hasSuffix("_clean")
            let bClean = $1.artifactType.hasSuffix("_clean")
            if aClean != bClean { return aClean }
            return $0.createdAt > $1.createdAt
        }
    }

    private func baseType(of artifactType: String) -> String {
        artifactType.hasSuffix("_clean")
            ? String(artifactType.dropLast("_clean".count))
            : artifactType
    }

    private var panelCount: Int {
        var count = sortedArtifacts.count
        if let pageContent = document.pageContent, !pageContent.isEmpty { count += 1 }
        return count
    }

    private func loadArtifacts() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            // V2 wants strict per-document scope — see #696/V2 redesign.
            // The legacy aggregation (parent + children) made delete look
            // broken because deleting one artifact left a sibling in place.
            artifacts = try await artifactService.getArtifacts(
                forDocumentId: document.id,
                forceRefresh: true,
                includeDescendants: false
            )
            loadError = nil
        } catch is CancellationError {
            // Task superseded by a newer page selection — not a load failure.
        } catch {
            loadError = "Couldn't load artifacts: \(error.localizedDescription)"
        }
    }

    private func deleteArtifact(_ artifact: Artifact) async {
        // Optimistic remove (#705 pattern). The artifact panel disappears
        // immediately; rollback if the backend rejects the delete.
        let snapshot = artifacts
        artifacts.removeAll { $0.id == artifact.id }
        do {
            try await artifactService.deleteArtifact(
                id: artifact.id, documentId: document.id
            )
            actionError = nil
        } catch {
            artifacts = snapshot
            actionError = "Couldn't delete: \(error.localizedDescription)"
        }
    }

    private func clearPageContent() async {
        // page_content is a Document field, not an artifact — clearing it
        // means a normal updateDocument call with pageContent: "".
        if let error = await persistPageContent(
            document: document,
            content: "",
            documentService: documentService,
            documentStore: documentStore
        ) {
            actionError = "Couldn't clear page content: \(error)"
        } else {
            actionError = nil
        }
    }

    private func saveArtifact(_ artifact: Artifact, content: String) async {
        do {
            let updated = try await artifactService.updateArtifact(
                id: artifact.id,
                documentId: document.id,
                content: content
            )
            // Replace in local list so the read view picks up the new text
            // immediately; the next loadArtifacts will reconcile if needed.
            if let index = artifacts.firstIndex(where: { $0.id == updated.id }) {
                artifacts[index] = updated
            }
            actionError = nil
        } catch {
            actionError = "Couldn't save: \(error.localizedDescription)"
        }
    }

    private func savePageContent(_ content: String) async {
        actionError = await persistPageContent(
            document: document,
            content: content,
            documentService: documentService,
            documentStore: documentStore
        ).map { "Couldn't save: \($0)" }
    }
}

@MainActor
func persistPageContent(
    document: Document,
    content: String,
    documentService: DocumentServiceGenerated,
    documentStore: DocumentStore
) async -> String? {
    do {
        let updated = try await documentService.updateDocument(
            document.id,
            pageContent: content
        )
        documentStore.refreshLocalContent(updated)
        return nil
    } catch {
        return error.localizedDescription
    }
}
