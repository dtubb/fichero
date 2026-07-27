import SwiftUI

// MARK: - Artifact Entities View (#519)

/// Surfaces the entity-flavored artifacts (people/places/organizations/
/// events/dates/keywords) for a document row. Both styles observe the shared
/// `ArtifactEntityStore` so the singleLine table-cell and multiLine list-row
/// presentations read ONE fetched+parsed bundle instead of fetching per view.
///
/// Data: `ArtifactEntityStore` keyed by documentId, strict per-document scope
/// ("{id}|own") — matches the V2 convention used by DocumentInspectorContentV2;
/// per-row counts must NOT include descendants, otherwise a parent PDF shows the
/// union of every page-child's artifacts. The store is the single endpoint
/// accessor (#3861 / #1863); views never call getArtifacts() themselves.
struct ArtifactEntitiesView: View {
    enum Style { case singleLine, multiLine }

    let documentId: String
    let style: Style
    /// Entity-type ids ('people' / 'places' / 'organizations' / 'dates'
    /// / 'events' / 'keywords') the caller wants rendered. Defaults to
    /// all six so direct callers don't have to know about filtering;
    /// LibraryView's listVisibleEntityTypes drives this for list rows.
    var visibleTypes: Set<String> = ["people", "places", "organizations", "dates", "events", "keywords"]

    @Environment(ArtifactService.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Shared document-keyed store (#3861) — the single endpoint accessor. Every
    /// row/cell for the same document observes ONE fetch instead of firing its
    /// own `getArtifacts()` in `.onAppear`.
    private var store: ArtifactEntityStore { .shared(for: artifactService) }
    private var bundle: ArtifactEntityBundle? { store.bundle(for: documentId) }

    var body: some View {
        Group {
            if let bundle {
                if bundle.isEmpty {
                    if style == .singleLine {
                        Text("—").font(.caption).foregroundStyle(.secondary)
                    } else {
                        EmptyView()
                    }
                } else {
                    content(bundle)
                }
            } else {
                // Reserve space silently while the first fetch is in flight.
                // multiLine reserved 1pt and then grew by up to six lozenge
                // rows — every list row jumped as artifacts streamed in, and
                // the whole LazyVStack reflowed under the scroll position
                // (#4160 / Every Frame Perfect). Reserve ~two lozenge rows;
                // rows with more or none still shift once, but the common
                // case lands in place. ponytail: fixed 2-row estimate — a
                // measured/persisted per-doc height if this still reads
                // jumpy in real archives.
                Color.clear.frame(height: style == .singleLine ? 14 : 40)
            }
        }
        .onAppear { store.ensureLoaded(documentId) }
        .onChange(of: documentId) { store.ensureLoaded(documentId) }
        // Workflow completion refetches ONLY the documents that run touched —
        // idempotent across the many rows that each observe this counter.
        .onChange(of: executionObserver.workflowCompletedCount) {
            store.reconcileCompletions(executionObserver)
        }
    }

    @ViewBuilder
    private func content(_ bundle: ArtifactEntityBundle) -> some View {
        switch style {
        case .singleLine:
            HStack(spacing: 8) {
                chip(systemName: "person", names: bundle.people, max: 2)
                chip(systemName: "mappin", names: bundle.places, max: 2)
                chip(systemName: "building.2", names: bundle.organizations, max: 1)
                chip(systemName: "calendar", names: bundle.dates, max: 1)
                chip(systemName: "bolt", names: bundle.events, max: 1)
            }
            .font(.caption)
            .lineLimit(1)
            .truncationMode(.tail)
        case .multiLine:
            VStack(alignment: .leading, spacing: 4) {
                if visibleTypes.contains("people") {
                    lozengeRow("People", names: bundle.people)
                }
                if visibleTypes.contains("places") {
                    lozengeRow("Places", names: bundle.places)
                }
                if visibleTypes.contains("organizations") {
                    lozengeRow("Organizations", names: bundle.organizations)
                }
                if visibleTypes.contains("dates") {
                    lozengeRow("Dates", names: bundle.dates)
                }
                if visibleTypes.contains("events") {
                    lozengeRow("Events", names: bundle.events)
                }
                if visibleTypes.contains("keywords") {
                    lozengeRow("Keywords", names: bundle.keywords)
                }
            }
            .font(.caption2)
        }
    }

    @ViewBuilder
    private func chip(systemName: String, names: [String], max: Int) -> some View {
        if !names.isEmpty {
            let shown = Array(names.prefix(max))
            let extra = names.count - shown.count
            let suffix = extra > 0 ? " +\(extra)" : ""
            Label("\(shown.joined(separator: ", "))\(suffix)", systemImage: systemName)
                .foregroundStyle(.secondary)
        }
    }

    /// One row per entity-type with a leading label and a FlowLayout of
    /// blue lozenges that wraps to multiple lines vertically when there
    /// are more names than fit on one row. The maintainer: 'the artefacts should
    /// in the list view stack vertically not just scroll horizontally
    /// when I do two fingers.' Long names truncate with middle ellipsis
    /// (Finder convention) so a single huge entity doesn't spill into
    /// the next column. Each lozenge caps at 180 pt wide.
    @ViewBuilder
    private func lozengeRow(_ label: String, names: [String]) -> some View {
        if !names.isEmpty {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("\(label):")
                    .foregroundStyle(.secondary)
                    .frame(minWidth: 90, alignment: .leading)
                FlowLayout(spacing: 4) {
                    // Dedup: the same name can appear twice in one artifact's
                    // extracted list; `id: \.self` on a raw [String] would then
                    // emit duplicate ForEach IDs (the #1966 warning) and render
                    // the lozenge twice. Order-preserving unique fixes both.
                    ForEach(names.uniqued(), id: \.self) { name in
                        // Pass entityType so the tap fires a scoped query
                        // (e.g. `places:"Quibdó"` instead of free-text).
                        EntityLozenge(name: name, entityType: Self.entityTypeId(for: label))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    /// Map the human-facing row label ("People", "Places", "Organizations",
    /// "Dates", "Events", "Keywords") to the backend's entity_type id.
    /// Used by lozenge taps to fire `<type>:<name>` scoped queries.
    /// Internal so tests can verify the mapping without spinning up a
    /// view hierarchy. (`@testable import Fichero` reaches it.)
    static func entityTypeId(for label: String) -> String {
        switch label.lowercased() {
        case "people": return "people"
        case "places": return "places"
        case "organizations": return "organizations"
        case "dates": return "dates"
        case "events": return "events"
        case "keywords": return "keywords"
        default: return label.lowercased()
        }
    }

}

// MARK: - Artifact Entity Cell — per-type column (#519 table view)

/// Renders just one entity-type's lozenges in a table cell — the maintainer:
/// 'artefacts in the table view should each have their own column, and
/// be rendered as lozenges as well.' Hidden by default; user toggles
/// via the column-header context menu (TableColumnCustomization).
struct ArtifactEntityCell: View {
    let documentId: String
    /// One of: 'people', 'places', 'organizations', 'events', 'dates',
    /// 'keywords'. Rendered as a wrapping FlowLayout of accent-tinted
    /// capsules; "—" when this doc has no artifact of that type.
    let entityType: String

    @Environment(ArtifactService.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    /// Shared document-keyed store (#3861): the six per-type cells of one row now
    /// share ONE fetch with each other and with the row's `ArtifactEntitiesView`.
    private var store: ArtifactEntityStore { .shared(for: artifactService) }
    private var names: [String]? { store.bundle(for: documentId)?.names(for: entityType) }

    var body: some View {
        Group {
            if let names {
                if names.isEmpty {
                    Text("—").font(.caption2).foregroundStyle(.secondary)
                } else {
                    FlowLayout(spacing: 4) {
                        // Same #1966 dedup as lozengeRow — unique IDs, no double render.
                        ForEach(names.uniqued(), id: \.self) { name in
                            EntityLozenge(name: name, entityType: entityType)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                }
            } else {
                // Reserve ~2 lozenge rows while the first fetch is in
                // flight, same rationale as the multiLine reservation
                // (#4160): a 14pt spacer that grows to a multi-line
                // FlowLayout re-pitched the whole table row on load.
                // ponytail: fixed estimate; measured height if still jumpy.
                Color.clear.frame(height: 40)
            }
        }
        // Top-align so cells in the same row don't vertically center —
        // a People column with 30 names sits at top and Places (with 2)
        // shows its lozenges at the top of its cell as well, matching
        // Finder's table-cell behaviour.
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(.vertical, 2)
        .onAppear { store.ensureLoaded(documentId) }
        .onChange(of: documentId) { store.ensureLoaded(documentId) }
        .onChange(of: executionObserver.workflowCompletedCount) {
            store.reconcileCompletions(executionObserver)
        }
    }
}

fileprivate extension Sequence where Element: Hashable {
    /// Order-preserving unique — the stdlib has none. Used so `ForEach(_, id: \.self)`
    /// over an entity-name list can't emit duplicate IDs (#1966). fileprivate: only
    /// this file needs it; promote to a shared extension if a second caller appears.
    func uniqued() -> [Element] {
        var seen = Set<Element>()
        return filter { seen.insert($0).inserted }
    }
}
