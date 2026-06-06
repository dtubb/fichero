import FicheroAPIClient
import SwiftUI

// Inspector section that shows knowledge-graph entities and claims for
// the currently selected document. Reads from `/api/claims` filtered
// by `source_document_id`, dereferences `entity_ids` against
// `/api/entities`, and groups by `EntityType` for display (#728).
//
// The legacy markdown-artifact previews (the old `DocumentInspectorArtifactsTab`
// struct and its JSON helpers) were removed in #1507 once routing moved to
// `DocumentInspectorContentV2`; this typed section is now the sole KG surface.
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

// MARK: - KnowledgeGraphInspectorSection utilities

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

    static func isKindStored(_ kind: EntityKind, in csv: String) -> Bool {
        csv.split(separator: ",").contains(Substring(kind.rawValue))
    }
}
