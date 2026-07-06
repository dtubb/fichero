import SwiftUI

// MARK: - Artifact Entities View (#519)

/// Surfaces the entity-flavored artifacts (people/places/organizations/
/// events/dates/keywords) for a document row. Two styles share one data
/// path so the singleLine table-cell and multiLine list-row presentations
/// fetch + parse identically.
///
/// Cache: reads ArtifactServiceGenerated.artifactsByDocument["{id}|own"]
/// (matches the V2 strict-scope convention used by DocumentInspectorContentV2 —
/// per-row counts shouldn't include descendants, otherwise a parent PDF
/// shows the union of every page-child's artifacts).
struct ArtifactEntitiesView: View {
    enum Style { case singleLine, multiLine }

    let documentId: String
    let style: Style
    /// Entity-type ids ('people' / 'places' / 'organizations' / 'dates'
    /// / 'events' / 'keywords') the caller wants rendered. Defaults to
    /// all six so direct callers don't have to know about filtering;
    /// LibraryView's listVisibleEntityTypes drives this for list rows.
    var visibleTypes: Set<String> = ["people", "places", "organizations", "dates", "events", "keywords"]

    @Environment(ArtifactServiceGenerated.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    @State private var people: [String] = []
    @State private var places: [String] = []
    @State private var organizations: [String] = []
    @State private var events: [String] = []
    @State private var dates: [String] = []
    @State private var keywords: [String] = []
    @State private var loaded = false

    var body: some View {
        Group {
            if !loaded {
                // Reserve space silently while the first fetch is in flight.
                Color.clear.frame(height: style == .singleLine ? 14 : 1)
            } else if isEmpty {
                if style == .singleLine {
                    Text("—").font(.caption).foregroundStyle(.secondary)
                } else {
                    EmptyView()
                }
            } else {
                content
            }
        }
        .onAppear { Task { await loadEntities() } }
        .onChange(of: documentId) {
            Task { await loadEntities(forceRefresh: true) }
        }
        .onChange(of: executionObserver.workflowCompletedCount) {
            Task { await loadEntities(forceRefresh: true) }
        }
    }

    @ViewBuilder
    private var content: some View {
        switch style {
        case .singleLine:
            HStack(spacing: 8) {
                chip(systemName: "person", names: people, max: 2)
                chip(systemName: "mappin", names: places, max: 2)
                chip(systemName: "building.2", names: organizations, max: 1)
                chip(systemName: "calendar", names: dates, max: 1)
                chip(systemName: "bolt", names: events, max: 1)
            }
            .font(.caption)
            .lineLimit(1)
            .truncationMode(.tail)
        case .multiLine:
            VStack(alignment: .leading, spacing: 4) {
                if visibleTypes.contains("people") {
                    lozengeRow("People", names: people)
                }
                if visibleTypes.contains("places") {
                    lozengeRow("Places", names: places)
                }
                if visibleTypes.contains("organizations") {
                    lozengeRow("Organizations", names: organizations)
                }
                if visibleTypes.contains("dates") {
                    lozengeRow("Dates", names: dates)
                }
                if visibleTypes.contains("events") {
                    lozengeRow("Events", names: events)
                }
                if visibleTypes.contains("keywords") {
                    lozengeRow("Keywords", names: keywords)
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
    /// are more names than fit on one row. Daniel: 'the artefacts should
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
                    ForEach(names, id: \.self) { name in
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

    private var isEmpty: Bool {
        people.isEmpty && places.isEmpty && organizations.isEmpty
            && events.isEmpty && dates.isEmpty && keywords.isEmpty
    }

    @MainActor
    private func loadEntities(forceRefresh: Bool = false) async {
        let cacheKey = "\(documentId)|own"
        let artifacts: [Artifact]
        people = []
        places = []
        organizations = []
        events = []
        dates = []
        keywords = []

        if !forceRefresh, let cached = artifactService.artifactsByDocument[cacheKey] {
            artifacts = cached
        } else if let fetched = try? await artifactService.getArtifacts(
            forDocumentId: documentId,
            forceRefresh: forceRefresh,
            includeDescendants: false
        ) {
            artifacts = fetched
        } else {
            loaded = true
            return
        }
        for artifact in artifacts {
            switch artifact.artifactType {
            case "people":
                people = extractNames(artifact, key: "name")
            case "places":
                places = extractNames(artifact, key: "name")
            case "organizations":
                organizations = extractNames(artifact, key: "name")
            case "events":
                events = extractNames(artifact, key: "event")
            case "keywords":
                keywords = extractKeywords(artifact)
            case "dates":
                dates = extractDates(artifact)
            default:
                break
            }
        }
        loaded = true
    }

    private func extractNames(_ artifact: Artifact, key: String) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { $0[key] as? String }
    }

    private func extractKeywords(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["keywords"]?.value,
              let array = value as? [String] else { return [] }
        return array
    }

    private func extractDates(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { item in
            (item["date_normalized"] as? String) ?? (item["date"] as? String)
        }
    }
}

// MARK: - Artifact Entity Cell — per-type column (#519 table view)

/// Renders just one entity-type's lozenges in a table cell — Daniel:
/// 'artefacts in the table view should each have their own column, and
/// be rendered as lozenges as well.' Hidden by default; user toggles
/// via the column-header context menu (TableColumnCustomization).
struct ArtifactEntityCell: View {
    let documentId: String
    /// One of: 'people', 'places', 'organizations', 'events', 'dates',
    /// 'keywords'. Rendered as a wrapping FlowLayout of accent-tinted
    /// capsules; "—" when this doc has no artifact of that type.
    let entityType: String

    @Environment(ArtifactServiceGenerated.self) var artifactService
    @Environment(WorkflowExecutionObserver.self) var executionObserver

    @State private var names: [String] = []
    @State private var loaded = false

    var body: some View {
        Group {
            if !loaded {
                Color.clear.frame(height: 14)
            } else if names.isEmpty {
                Text("—").font(.caption2).foregroundStyle(.secondary)
            } else {
                FlowLayout(spacing: 4) {
                    ForEach(names, id: \.self) { name in
                        EntityLozenge(name: name, entityType: entityType)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
        }
        // Top-align so cells in the same row don't vertically center —
        // a People column with 30 names sits at top and Places (with 2)
        // shows its lozenges at the top of its cell as well, matching
        // Finder's table-cell behaviour.
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(.vertical, 2)
        .onAppear { Task { await load() } }
        .onChange(of: executionObserver.workflowCompletedCount) {
            Task { await load(forceRefresh: true) }
        }
    }

    @MainActor
    private func load(forceRefresh: Bool = false) async {
        let cacheKey = "\(documentId)|own"
        let artifacts: [Artifact]
        if !forceRefresh, let cached = artifactService.artifactsByDocument[cacheKey] {
            artifacts = cached
        } else if let fetched = try? await artifactService.getArtifacts(
            forDocumentId: documentId, forceRefresh: forceRefresh, includeDescendants: false
        ) {
            artifacts = fetched
        } else {
            loaded = true
            return
        }
        for artifact in artifacts where artifact.artifactType == entityType {
            switch entityType {
            case "people", "places", "organizations":
                names = extractNames(artifact, key: "name")
            case "events":
                names = extractNames(artifact, key: "event")
            case "keywords":
                names = extractKeywords(artifact)
            case "dates":
                names = extractDates(artifact)
            default:
                break
            }
        }
        loaded = true
    }

    private func extractNames(_ artifact: Artifact, key: String) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { $0[key] as? String }
    }

    private func extractKeywords(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["keywords"]?.value,
              let array = value as? [String] else { return [] }
        return array
    }

    private func extractDates(_ artifact: Artifact) -> [String] {
        guard let data = artifact.data,
              let value = data["items"]?.value,
              let items = value as? [[String: Any]] else { return [] }
        return items.compactMap { item in
            (item["date_normalized"] as? String) ?? (item["date"] as? String)
        }
    }
}
