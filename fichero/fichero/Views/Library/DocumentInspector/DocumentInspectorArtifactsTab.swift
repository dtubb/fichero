// swiftlint:disable file_length
import SwiftUI

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
    /// Posted after a claim is edited via EditClaimSheet (#1135). `object`
    /// is the claim ID (String). userInfo["claim"] carries the updated
    /// KnowledgeClaim value so observers can refresh in place.
    static let ficheroClaimUpdated = Notification.Name("ficheroClaimUpdated")

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

import FicheroAPIClient

/// Inspector section that shows knowledge-graph entities and claims for
/// the currently selected document. Reads from `/api/claims` filtered
/// by `source_document_id`, dereferences `entity_ids` against
/// `/api/entities`, and groups by `EntityType` for display (#728).
///
/// The legacy markdown-artifact previews (the old `DocumentInspectorArtifactsTab`
/// struct and its JSON helpers) were removed in #1507 once routing moved to
/// `DocumentInspectorContentV2`; this typed section is now the sole KG surface.
// swiftlint:disable:next type_body_length
struct KnowledgeGraphInspectorSection: View {
    let documentId: String
    let entityService: EntityServiceGenerated
    let artifactService: ArtifactServiceGenerated
    /// Called when the user clicks the source-page arrow on an entity row.
    /// Receives the source page document id; ContentView decides how to
    /// navigate (typically: select the parent file in the grid). Optional
    /// so previews and standalone uses still compile. (#833)
    var onNavigateToSource: ((String) -> Void)?
    /// Called when the user clicks on a claim to select it for highlighting
    var onClaimSelect: ((String, String?, String?, String?, Int?, Int?) -> Void)?

    @StateObject private var loadState = KnowledgeGraphInspectorLoadState()
    private var claims: [Components.Schemas.KnowledgeClaim] {
        get { loadState.claims }
        nonmutating set { loadState.claims = newValue }
    }
    private var canonicalGroups: [Components.Schemas.KGEntityGroup] {
        get { loadState.canonicalGroups }
        nonmutating set { loadState.canonicalGroups = newValue }
    }
    private var isLoading: Bool {
        get { loadState.isLoading }
        nonmutating set { loadState.isLoading = newValue }
    }
    private var loadError: String? {
        get { loadState.loadError }
        nonmutating set { loadState.loadError = newValue }
    }
    @EnvironmentObject private var claimFocusState: ClaimFocusState

    /// Comma-joined raw values of EntityKinds the user has hidden from the
    /// KG list. Persisted across launches so the filter survives restarts.
    /// Default: all kinds visible.
    @AppStorage("inspector.kg.hiddenKinds") private var hiddenKindsCSV: String = ""

    /// Text = dense semicolon prose per entity; List = grouped disclosure rows.
    @AppStorage("inspector.kg.displayMode") private var displayMode: KGDisplayMode = .text
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13

    private var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    private var typeLabelFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 2, 9)), weight: .semibold)
    }

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
        var claimById: [String: Components.Schemas.KnowledgeClaim] = [:]
        for claim in claims {
            if let id = claim.id {
                claimById[id] = claim
            }
        }
        let hidden = hiddenKinds
        return canonicalGroups.compactMap { group -> (EntityKind, [GroupedItem])? in
            guard let kind = EntityKind(groupKind: group.kind), !hidden.contains(kind) else { return nil }
            var items: [GroupedItem] = []
            for item in group.items {
                guard let firstClaimId = item.claimIds.first else { continue }
                let firstClaim = claimById[firstClaimId]
                let primaryContext = (item.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let excerpt = (item.sourceExcerpt ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                let context = !primaryContext.isEmpty
                    ? primaryContext
                    : (!excerpt.isEmpty ? excerpt : (firstClaim?.text ?? item.canonicalName))
                let extraClaims: [GroupedItem.ExtraClaim] = item.claimIds.dropFirst().compactMap { claimId in
                    let claim = claimById[claimId]
                    return GroupedItem.ExtraClaim(
                        claimId: claimId,
                        context: claim?.text ?? context,
                        sourceDocumentId: claim?.sourceDocumentId ?? item.sourceDocumentId,
                        sourcePageLabel: claim?.sourcePageLabel ?? item.sourcePageLabel,
                        sourceExcerpt: claim?.sourceExcerpt ?? item.sourceExcerpt
                    )
                }
                items.append(GroupedItem(
                    entityId: item.entityId,
                    claimId: firstClaimId,
                    displayName: item.canonicalName,
                    context: context,
                    aliases: item.aliases,
                    confidence: firstClaim?.confidence,
                    sourceDocumentId: item.sourceDocumentId,
                    sourcePageLabel: item.sourcePageLabel,
                    sourceExcerpt: item.sourceExcerpt,
                    extraClaims: extraClaims
                ))
            }
            guard !items.isEmpty else { return nil }
            let sorted = items.sorted { lhs, rhs in
                let leftConfidence = lhs.confidence ?? 0
                let rightConfidence = rhs.confidence ?? 0
                if leftConfidence == rightConfidence {
                    return lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
                }
                return leftConfidence > rightConfidence
            }
            return (kind, sorted)
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
        grouped.map { kind, items in
            let entries = items.map { item in
                let lines = [item.context] + item.extraClaims.map(\.context)
                return TextDigestEntry(displayName: item.displayName, kind: kind, svoLines: lines)
            }
            return (kind, entries)
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
                            .font(typeLabelFont)
                            .foregroundStyle(.secondary)

                        ForEach(entries, id: \.displayName) { entry in
                            let prose = entry.svoLines.joined(separator: "; ")
                            // SwiftUI markdown bold for the entity name.
                            let raw = "**\(entry.displayName)** \(prose)"
                            if let attributed = try? AttributedString(markdown: raw) {
                                Text(attributed)
                                    .font(bodyTextFont)
                                    .fixedSize(horizontal: false, vertical: true)
                            } else {
                                Text(raw)
                                    .font(bodyTextFont)
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

            Divider()
                .padding(.vertical, 4)
            KGCurationHistorySection(entityService: entityService)
            Divider()
                .padding(.vertical, 4)
            DocumentInterpretationsSection(
                documentId: documentId,
                entityService: entityService
            )
        }
        .task(id: documentId) { await loadStatements() }
    }

    private var sectionHeader: some View {
        // No "Knowledge Graph" title/icon — the inspector tab already names
        // this surface, so the in-pane label was redundant (#1244). The header
        // is now just the filter + view-mode + reload controls, right-aligned.
        HStack(spacing: 8) {
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
            .help("Filter — choose which entity kinds (people, places, organizations…) appear in this list")
            // Text / List mode toggle
            Button {
                displayMode = .text
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .text ? Color.accentColor : Color.secondary)
            .help("Text digest — entities as a dense prose summary, one paragraph per kind")
            Button {
                displayMode = .list
            } label: {
                Image(systemName: "list.bullet")
            }
            .buttonStyle(.plain)
            .foregroundStyle(displayMode == .list ? Color.accentColor : Color.secondary)
            .help("List view — entities as grouped, expandable rows you can click through to the source")
            Button {
                Task { await loadStatements() }
            } label: {
                Image(systemName: "arrow.clockwise")
            }
            .buttonStyle(.plain)
            .help("Reload — re-fetch the knowledge-graph entities for this document")
        }
        .foregroundStyle(.primary)
    }

    private func loadStatements() async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        do {
            let response = try await entityService.documentKnowledgeGraph(
                documentId: documentId,
                includeChildren: true
            )
            claims = response.claims
            canonicalGroups = response.groups
        } catch is CancellationError {
            // Task superseded by a newer page selection — not a load failure.
        } catch {
            loadError = "Couldn't load: \(error.localizedDescription)"
            claims = []
            canonicalGroups = []
        }
    }
}

// MARK: - Models for the section's local rendering state

@MainActor
private final class KnowledgeGraphInspectorLoadState: ObservableObject {
    @Published var claims: [Components.Schemas.KnowledgeClaim] = []
    @Published var canonicalGroups: [Components.Schemas.KGEntityGroup] = []
    @Published var isLoading = false
    @Published var loadError: String?
}

private struct GroupedItem: Identifiable {
    var entityId: String?
    let claimId: String
    let displayName: String
    let context: String
    let aliases: [String]
    let confidence: Double?
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

    init(
        entityId: String? = nil,
        claimId: String,
        displayName: String,
        context: String,
        aliases: [String],
        confidence: Double? = nil,
        sourceDocumentId: String? = nil,
        sourcePageLabel: String? = nil,
        sourceExcerpt: String? = nil,
        extraClaims: [ExtraClaim] = []
    ) {
        self.entityId = entityId
        self.claimId = claimId
        self.displayName = displayName
        self.context = context
        self.aliases = aliases
        self.confidence = confidence
        self.sourceDocumentId = sourceDocumentId
        self.sourcePageLabel = sourcePageLabel
        self.sourceExcerpt = sourceExcerpt
        self.extraClaims = extraClaims
    }
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
        case .citation:     self = .other
        case .other:        self = .other
        }
    }

    init?(groupKind: String) {
        self.init(rawValue: groupKind.lowercased())
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
        // Named entities next; events then dates (events carry their own dates
        // inside their descriptions, e.g. "Pronunciamiento ... el 23 de
        // julio de 1993"). Dates are included here so they get their own filter
        // toggle AND are covered by "Hide all" — previously .date was omitted,
        // so the Dates facet ignored the filter and could not be hidden (#1468).
        [.concept, .person, .location, .organization, .event, .date, .other]
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

    @SceneStorage("inspector.kg.expandedKinds") private var expandedKindsCSV: String = ""
    @SceneStorage("inspector.kg.showAllKinds") private var showAllKindsCSV: String = ""

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

    private var isShowingAll: Bool {
        KnowledgeGraphInspectorSection.isKindStored(kind, in: showAllKindsCSV)
    }

    private func setShowingAll(_ show: Bool) {
        var set = Set(
            showAllKindsCSV.split(separator: ",").map(String.init)
        )
        if show { set.insert(kind.rawValue) } else { set.remove(kind.rawValue) }
        showAllKindsCSV = set.sorted().joined(separator: ",")
    }

    private var visibleItems: [GroupedItem] {
        KnowledgeGraphInspectorSection.visibleItems(items, showingAll: isShowingAll)
    }

    var body: some View {
        DisclosureGroup(isExpanded: isExpanded) {
            VStack(alignment: .leading, spacing: 0) {
                if kind == .concept {
                    // Keywords as wrapping lozenges. Use the same EntityLozenge
                    // component as the inspector + list-view so tap-to-search
                    // works consistently and styling is uniform across all
                    // entity rendering paths in the app. EntityKind.concept
                    // maps to the 'keywords' artifact type — pass that so
                    // taps fire `keywords:"<term>"` scoped queries.
                    FlowLayout(spacing: 4) {
                        ForEach(visibleItems) { item in
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
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(visibleItems) { item in
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
                if let title = KnowledgeGraphInspectorSection.showAllButtonTitle(
                    itemCount: items.count,
                    showingAll: isShowingAll
                ) {
                    bottomLoadMoreButton(title: title) {
                        setShowingAll(!isShowingAll)
                    }
                }
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

    @ViewBuilder
    private func bottomLoadMoreButton(title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack {
                Text(title)
                    .font(.caption)
                Spacer()
                Image(systemName: isShowingAll ? "chevron.up" : "chevron.down")
                    .font(.caption2)
            }
            .foregroundStyle(Color.accentColor)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 4)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 16)
        .padding(.top, 4)
    }
}

extension KnowledgeGraphInspectorSection {
    static let groupVisibleCap = 10

    static func visibleItems<T>(_ items: [T], showingAll: Bool, cap: Int = groupVisibleCap) -> [T] {
        if showingAll || items.count <= cap { return items }
        return Array(items.prefix(cap))
    }

    static func showAllButtonTitle(itemCount: Int, showingAll: Bool, cap: Int = groupVisibleCap) -> String? {
        guard itemCount > cap else { return nil }
        return showingAll ? "Show less" : "Show all (\(itemCount))"
    }

    fileprivate static func isKindStored(_ kind: EntityKind, in csv: String) -> Bool {
        csv.split(separator: ",").contains(Substring(kind.rawValue))
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
    @Environment(KGFocusState.self) private var kgFocusState
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13
    @State private var claimForEditing: Components.Schemas.KnowledgeClaim?
    @State private var showDeleteConfirmation = false
    @State private var rowError: String?

    private var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    private var secondaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 1, 10)))
    }

    var body: some View {
        // Layout:
        //   line 1: [name button]  (aka alias1, alias2)  (p. label)   → arrow  [select claim]
        //   line 2: context  (when non-empty, non-redundant)
        // Name is its own Button so a tap doesn't have to compete with
        // textSelection on the rest of the row.
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Button(action: focusPrimaryClaim) {
                    Text(item.displayName)
                        .font(bodyTextFont)
                        .fontWeight(.medium)
                        .foregroundStyle(
                            claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.primary
                        )
                }
                .buttonStyle(.plain)
                .help("Focus \"\(item.displayName)\"")
                .accessibilityHint("Focuses this \(kind.label.lowercased())")

                trailingText
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)

                if let confidence = item.confidence {
                    Text(String(format: "%.2f", confidence))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.12))
                        .clipShape(Capsule())
                        .help("Claim confidence")
                }

                // Claim selection button for bidirectional sync
                if let onClaimSelect = onClaimSelect {
                    Button(action: {
                        focusPrimaryClaim()
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
                            .foregroundStyle(
                                claimFocusState.isClaimSelected(item.claimId) ? Color.accentColor : Color.secondary
                            )
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
                    .font(bodyTextFont)
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
                        .font(secondaryTextFont)
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
                                .font(bodyTextFont)
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
                                    .font(secondaryTextFont)
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

            if let rowError {
                Text(rowError)
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .onTapGesture {
            focusPrimaryClaim()
        }
        .contextMenu {
            Button("Edit claim…") {
                loadClaimForEditing()
            }
            Button("Delete claim…", role: .destructive) {
                showDeleteConfirmation = true
            }
        }
        .alert("Delete claim?", isPresented: $showDeleteConfirmation) {
            Button("Delete", role: .destructive) { deleteClaim() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes the claim from the knowledge graph. Related entities stay in place.")
        }
        .sheet(isPresented: Binding(
            get: { claimForEditing != nil },
            set: { if !$0 { claimForEditing = nil } }
        )) {
            if let claimForEditing {
                EditClaimSheet(claim: claimForEditing) { updated in
                    self.claimForEditing = nil
                    NotificationCenter.default.post(
                        name: .ficheroClaimUpdated,
                        object: updated.id,
                        userInfo: ["claim": updated]
                    )
                }
            }
        }
    }

    private func focusPrimaryClaim() {
        kgFocusState.focusClaim(
            claimId: item.claimId,
            entityId: item.entityId,
            sourceDocumentId: item.sourceDocumentId,
            sourcePageLabel: item.sourcePageLabel
        )
    }

    /// Aliases + page reference rendered as one selectable text run,
    /// sitting beside the tappable name on line 1.
    private var trailingText: Text {
        var text = Text("")
            .font(secondaryTextFont)
            .foregroundStyle(.secondary)
        if !item.aliases.isEmpty {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text(" (aka " + item.aliases.joined(separator: ", ") + ")")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
        if let pageRef = pageReference {
            // swiftlint:disable:next shorthand_operator
            text = text
                + Text("  (\(pageRef))")
                .font(secondaryTextFont)
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

    private func loadClaimForEditing() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        rowError = nil
        Task {
            do {
                claimForEditing = try await library.entityService.getClaim(item.claimId)
            } catch {
                rowError = error.localizedDescription
            }
        }
    }

    private func deleteClaim() {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        rowError = nil
        Task {
            do {
                try await library.entityService.deleteClaim(item.claimId)
                NotificationCenter.default.post(name: .ficheroClaimDeleted, object: item.claimId)
            } catch {
                rowError = error.localizedDescription
            }
        }
    }
}

// MARK: - KG Curation History (#1434)

/// Collapsible "Curation History" panel at the bottom of the KG tab.
/// Shows recent entity merge/split audit records from
/// `/api/kg/entity-curation/audit` with per-row Undo buttons.
/// Only rendered when there are audit records — keeps the panel tight
/// for the common case where no curation has happened.
struct KGCurationHistorySection: View {
    let entityService: EntityServiceGenerated

    @State private var audits: [Components.Schemas.EntityAuditResponse] = []
    @State private var isLoading = false
    @State private var undoingId: String?
    @State private var statusMessage: String?
    @State private var isExpanded = false
    @State private var loadTrigger = 0

    var body: some View {
        if !audits.isEmpty || isLoading {
            DisclosureGroup(
                isExpanded: $isExpanded,
                content: {
                    if isLoading {
                        HStack(spacing: 6) {
                            ProgressView().scaleEffect(0.6)
                            Text("Loading…").font(.caption).foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    } else {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(audits, id: \.id) { audit in
                                auditRow(audit)
                            }
                            if let msg = statusMessage {
                                Text(msg)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .padding(.top, 2)
                            }
                        }
                    }
                },
                label: {
                    HStack(spacing: 4) {
                        Image(systemName: "clock.arrow.trianglehead.counterclockwise.rotate.90")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Curation History (\(audits.count))")
                            .font(.caption.bold())
                            .foregroundStyle(.secondary)
                    }
                }
            )
            .task(id: loadTrigger) { await load() }
        }
    }

    private func auditRow(_ audit: Components.Schemas.EntityAuditResponse) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: auditIcon(audit.operationType))
                .foregroundStyle(auditTint(audit.operationType))
                .font(.caption)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 2) {
                Text(auditLabel(audit))
                    .font(.caption)
                Text(audit.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Spacer(minLength: 0)
            if canUndo(audit) {
                Button {
                    Task { await undo(audit.id) }
                } label: {
                    if undoingId == audit.id {
                        ProgressView().controlSize(.mini)
                    } else {
                        Text("Undo")
                            .font(.caption2)
                    }
                }
                .buttonStyle(.borderless)
                .disabled(undoingId != nil)
            }
        }
        .padding(.vertical, 2)
    }

    private func canUndo(_ audit: Components.Schemas.EntityAuditResponse) -> Bool {
        switch audit.operationType {
        case .merge, .split: return audit.reversalId == nil
        case .undoMerge, .undoSplit: return false
        }
    }

    private func auditIcon(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> String {
        switch mergeOp {
        case .merge: return "arrow.triangle.merge"
        case .split: return "arrow.triangle.branch"
        case .undoMerge, .undoSplit: return "arrow.uturn.backward.circle"
        }
    }

    private func auditTint(_ mergeOp: Components.Schemas.EntityMergeOperationType) -> Color {
        switch mergeOp {
        case .merge: return .blue
        case .split: return .orange
        case .undoMerge, .undoSplit: return .gray
        }
    }

    private func auditLabel(_ audit: Components.Schemas.EntityAuditResponse) -> String {
        switch audit.operationType {
        case .merge:
            let cnt = audit.sourceEntityIds.count
            return "Merged \(cnt) entr\(cnt == 1 ? "y" : "ies")"
        case .split:
            return "Split entity"
        case .undoMerge:
            return "Undid merge"
        case .undoSplit:
            return "Undid split"
        }
    }

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        audits = (try? await entityService.listEntityAudits(limit: 20)) ?? []
    }

    private func undo(_ auditId: String) async {
        undoingId = auditId
        defer { undoingId = nil }
        do {
            _ = try await entityService.undoEntityAudit(auditId)
            statusMessage = "Undo complete"
            loadTrigger += 1
        } catch {
            statusMessage = "Undo failed"
        }
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
        .environmentObject(ClaimFocusState.shared)
        .environment(KGFocusState.shared)
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

// MARK: - Hermeneutics interpretations panel

/// Shows interpretations for this document + inline "New Interpretation" form.
/// Always visible so the user can create the first interpretation even when none exist.
struct DocumentInterpretationsSection: View { // swiftlint:disable:this type_body_length
    let documentId: String
    let entityService: EntityServiceGenerated

    @State private var interpretations: [Components.Schemas.Interpretation] = []
    @State private var isExpanded = false
    @State private var isLoading = false

    // Create form
    @State private var showingCreateForm = false
    @State private var frameworks: [Components.Schemas.InterpretiveFramework] = []
    @State private var selectedFrameworkId: String = ""
    @State private var selectedAct: Components.Schemas.InterpretiveActType = .reading
    @State private var newInterpretationText: String = ""
    @State private var newConfidence: Double = 0.8
    @State private var isSubmitting = false
    @State private var submitError: String?

    // Edit form (one row expanded at a time)
    @State private var editingInterpId: String?
    @State private var editText: String = ""
    @State private var editConfidence: Double = 0.8
    @State private var isSavingEdit = false
    @State private var editError: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header row — always visible
            HStack(spacing: 6) {
                if isLoading {
                    ProgressView().scaleEffect(0.55)
                } else {
                    Image(systemName: "text.magnifyingglass")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(interpretations.isEmpty
                     ? "Interpretations"
                     : "Interpretations (\(interpretations.count))")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.12)) {
                        showingCreateForm.toggle()
                        if showingCreateForm && frameworks.isEmpty {
                            Task { await loadFrameworks() }
                        }
                    }
                } label: {
                    Image(systemName: showingCreateForm ? "xmark.circle" : "plus.circle")
                        .font(.caption)
                        .foregroundStyle(Color.accentColor)
                }
                .buttonStyle(.borderless)
                .help(showingCreateForm ? "Cancel" : "Add interpretation")
                if !interpretations.isEmpty {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.caption2).foregroundStyle(.tertiary)
                        .onTapGesture { withAnimation { isExpanded.toggle() } }
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
            .onTapGesture {
                if !interpretations.isEmpty {
                    withAnimation { isExpanded.toggle() }
                }
            }

            // Interpretation list (collapsed by default until loaded)
            if isExpanded && !isLoading {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(interpretations.prefix(8), id: \.id) { interp in
                        interpretationRow(interp)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.bottom, 6)
            }

            // Inline create form
            if showingCreateForm {
                createForm
                    .padding(.horizontal, 12)
                    .padding(.bottom, 8)
            }
        }
        .task(id: documentId) { await load() }
    }

    // MARK: - Create form

    @ViewBuilder
    private var createForm: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()

            // Framework picker — required for the backend
            if frameworks.isEmpty {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.55)
                    Text("Loading frameworks…").font(.caption2).foregroundStyle(.secondary)
                }
            } else {
                Picker("Framework", selection: $selectedFrameworkId) {
                    ForEach(frameworks, id: \.id) { framework in
                        Text(framework.name).tag(framework.id ?? "")
                    }
                }
                .pickerStyle(.menu)
                .font(.caption)
                .labelsHidden()
            }

            // Act picker
            Picker("Act", selection: $selectedAct) {
                ForEach(Components.Schemas.InterpretiveActType.allCases, id: \.self) { act in
                    Text(actLabel(act)).tag(act)
                }
            }
            .pickerStyle(.menu)
            .font(.caption)
            .labelsHidden()

            // Interpretation text
            TextEditor(text: $newInterpretationText)
                .font(.caption)
                .frame(minHeight: 60)
                .padding(4)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(.separatorColor), lineWidth: 0.5)
                )
                .overlay(alignment: .topLeading) {
                    if newInterpretationText.isEmpty {
                        Text("Interpretation text…")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .padding(.horizontal, 8)
                            .padding(.top, 8)
                            .allowsHitTesting(false)
                    }
                }

            // Confidence slider
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Confidence").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Text(String(format: "%.0f%%", newConfidence * 100))
                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
                Slider(value: $newConfidence, in: 0...1, step: 0.05)
            }

            if let err = submitError {
                Text(err).font(.caption2).foregroundStyle(.red)
            }

            HStack {
                Spacer()
                Button("Cancel") {
                    withAnimation { showingCreateForm = false }
                    resetForm()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)

                Button("Save") {
                    Task { await submitInterpretation() }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(
                    newInterpretationText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || selectedFrameworkId.isEmpty
                    || isSubmitting
                )
            }
        }
        .font(.caption)
    }

    // MARK: - Rows

    @ViewBuilder
    private func interpretationRow(_ interp: Components.Schemas.Interpretation) -> some View {
        let isEditing = editingInterpId == interp.id
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                Text(actLabel(interp.act))
                    .font(.caption2)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.accentColor.opacity(0.12))
                    .foregroundStyle(Color.accentColor)
                    .clipShape(Capsule())
                Spacer()
                if let conf = interp.confidence {
                    Text(String(format: "%.0f%%", conf * 100))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                Button {
                    if isEditing {
                        editingInterpId = nil
                        editError = nil
                    } else {
                        editText = interp.interpretationText
                        editConfidence = interp.confidence ?? 0.8
                        editingInterpId = interp.id
                        editError = nil
                    }
                } label: {
                    Image(systemName: isEditing ? "xmark.circle" : "pencil.circle")
                        .font(.caption)
                        .foregroundStyle(isEditing ? Color.secondary : Color.accentColor)
                }
                .buttonStyle(.borderless)
                .help(isEditing ? "Cancel edit" : "Edit interpretation")
            }
            if isEditing {
                editForm(for: interp)
            } else {
                Text(interp.interpretationText)
                    .font(.caption)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
                if let insights = interp.keyInsights, !insights.isEmpty {
                    VStack(alignment: .leading, spacing: 1) {
                        ForEach(insights.prefix(2), id: \.self) { insight in
                            HStack(alignment: .top, spacing: 4) {
                                Text("•").font(.caption2).foregroundStyle(.secondary)
                                Text(insight).font(.caption2).foregroundStyle(.secondary).lineLimit(2)
                            }
                        }
                    }
                }
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func editForm(for interp: Components.Schemas.Interpretation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            TextEditor(text: $editText)
                .font(.caption)
                .frame(minHeight: 56)
                .padding(4)
                .background(Color(.textBackgroundColor))
                .cornerRadius(4)
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color(.separatorColor), lineWidth: 0.5)
                )
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text("Confidence").font(.caption2).foregroundStyle(.secondary)
                    Spacer()
                    Text(String(format: "%.0f%%", editConfidence * 100))
                        .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
                Slider(value: $editConfidence, in: 0...1, step: 0.05)
            }
            if let err = editError {
                Text(err).font(.caption2).foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel") {
                    editingInterpId = nil
                    editError = nil
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                Button("Save") {
                    Task { await saveEdit(for: interp) }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(editText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSavingEdit)
            }
        }
        .font(.caption)
        .padding(.top, 4)
    }

    private func actLabel(_ act: Components.Schemas.InterpretiveActType) -> String {
        switch act {
        case .reading: return "Reading"
        case .translating: return "Translating"
        case .contextualizing: return "Contextualizing"
        case .synthesizing: return "Synthesizing"
        case .critiquing: return "Critiquing"
        case .applying: return "Applying"
        }
    }

    // MARK: - Load / Submit

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        interpretations = (try? await entityService.listDocumentInterpretations(documentId: documentId)) ?? []
        if !interpretations.isEmpty { isExpanded = true }
    }

    private func loadFrameworks() async {
        let loaded = (try? await entityService.listFrameworks()) ?? []
        frameworks = loaded
        if let first = loaded.first, let fwId = first.id {
            selectedFrameworkId = fwId
        }
    }

    private func submitInterpretation() async {
        let text = newInterpretationText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !selectedFrameworkId.isEmpty else { return }
        isSubmitting = true
        submitError = nil
        defer { isSubmitting = false }
        do {
            let created = try await entityService.createInterpretation(
                frameworkId: selectedFrameworkId,
                documentId: documentId,
                act: selectedAct,
                interpretationText: text,
                confidence: newConfidence
            )
            interpretations.insert(created, at: 0)
            isExpanded = true
            withAnimation { showingCreateForm = false }
            resetForm()
        } catch {
            submitError = error.localizedDescription
        }
    }

    private func saveEdit(for interp: Components.Schemas.Interpretation) async {
        let text = editText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let interpId = interp.id else { return }
        isSavingEdit = true
        editError = nil
        defer { isSavingEdit = false }
        do {
            let updated = try await entityService.updateInterpretation(
                interpretationId: interpId,
                interpretationText: text,
                confidence: editConfidence
            )
            if let idx = interpretations.firstIndex(where: { $0.id == interp.id }) {
                interpretations[idx] = updated
            }
            editingInterpId = nil
        } catch {
            editError = error.localizedDescription
        }
    }

    private func resetForm() {
        newInterpretationText = ""
        selectedAct = .reading
        newConfidence = 0.8
        submitError = nil
    }
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
