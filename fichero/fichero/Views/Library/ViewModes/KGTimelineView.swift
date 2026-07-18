import Charts
import FicheroAPIClient
import SwiftUI

/// Timeline visualization of claims on a time axis (#1267). Each claim that
/// carries a parseable `timeStart` is plotted at its date; claims with a
/// distinct `timeEnd` render as a span (a bar from start to end). Marks are
/// laid out in six entity-kind swimlanes and coloured by the shared KG
/// palette, so a glance lines up with the Graph, Chart, and Map views.
///
/// Asserted vs inferred dates are distinguished visually (see `KGProvenance`):
/// asserted dates are solid filled circles, inferred dates are dimmed open
/// diamonds. Tapping a mark selects its entity, which cross-filters the
/// entity list, detail pane, and the focus-neighborhood Graph view via the
/// shared `selectedEntityId` binding.
///
/// Scope: the view honours the upstream entity-kind filter (claims are kept
/// only when their subject resolves to an entity in `entities`). When an
/// entity is selected, a "Focus" toggle narrows the timeline to just that
/// entity's claims — the temporal analogue of the focus-neighborhood graph.
/// Degrades to an explanatory empty state when no claim has temporal data
/// yet (e.g. before the #1266 extractor enrichment has run).
struct KGTimelineView: View {
    let entities: [Components.Schemas.KnowledgeEntity]
    @Binding var selectedEntityId: String?
    var sourceDocumentId: String?

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var focusOnSelection = false

    /// Fixed lane order so the y-axis reading order matches the filter menu
    /// and the Chart-view legend. One lane per entity kind.
    private static let laneOrder = [
        "People", "Places", "Organizations", "Events", "Concepts", "Other"
    ]

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.controlBackgroundColor))
        .task { await load() }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 12) {
            Text("Timeline")
                .font(.headline)
            Text("\(datedClaims.count) dated · \(undatedInScopeCount) undated")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            provenanceLegend
            if selectedEntityId != nil {
                Toggle("Focus", isOn: $focusOnSelection)
                    .toggleStyle(.switch)
                    .controlSize(.mini)
                    .help("Show only the selected entity's dated claims")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var provenanceLegend: some View {
        HStack(spacing: 10) {
            HStack(spacing: 4) {
                Image(systemName: "circle.fill").font(.caption2).foregroundStyle(.secondary)
                Text("Asserted").font(.caption2).foregroundStyle(.secondary)
            }
            HStack(spacing: 4) {
                Image(systemName: "diamond").font(.caption2).foregroundStyle(.secondary)
                Text("Inferred").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Content states

    @ViewBuilder
    private var content: some View {
        if isLoading {
            ProgressView("Loading timeline…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let loadError {
            errorState(loadError)
        } else if datedClaims.isEmpty {
            emptyState
        } else {
            chart
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No dated claims", systemImage: "calendar.badge.clock")
        } description: {
            Text(claims.isEmpty
                    ? "Claims will appear here once extraction has run"
                    : "Claims need a start date (timeStart) to plot on the timeline")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Couldn't load timeline", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Chart

    private var chart: some View {
        Chart(datedClaims) { row in
            if row.isSpan {
                BarMark(
                    xStart: .value("Start", row.start),
                    xEnd: .value("End", row.end),
                    y: .value("Kind", row.lane),
                    height: .fixed(row.isSelected ? 10 : 6)
                )
                .foregroundStyle(row.color)
                .opacity(row.provenance == .inferred ? 0.45 : 0.9)
            } else {
                PointMark(
                    x: .value("Date", row.start),
                    y: .value("Kind", row.lane)
                )
                .foregroundStyle(row.color)
                .opacity(row.provenance == .inferred ? 0.5 : 1.0)
                .symbol(row.provenance == .asserted ? .circle : .diamond)
                .symbolSize(row.isSelected ? 220 : 90)
            }
        }
        .chartYScale(domain: Self.laneOrder)
        .chartYAxis {
            AxisMarks(preset: .aligned, position: .leading) { _ in
                AxisGridLine()
                AxisValueLabel().font(.caption2)
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisGridLine()
                AxisValueLabel(format: .dateTime.year()).font(.caption2)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                Rectangle()
                    .fill(.clear)
                    .contentShape(Rectangle())
                    .onTapGesture { location in
                        handleTap(at: location, proxy: proxy, geo: geo)
                    }
            }
        }
        .padding(16)
    }

    // MARK: - Selection / cross-filter

    /// Map a tap to the nearest dated claim and select its entity. Selection
    /// flows back through `selectedEntityId` to the rest of the browser.
    private func handleTap(at location: CGPoint, proxy: ChartProxy, geo: GeometryProxy) {
        guard let plotFrame = proxy.plotFrame else { return }
        let origin = geo[plotFrame].origin
        let xPosition = location.x - origin.x
        guard let tappedDate = proxy.value(atX: xPosition, as: Date.self) else { return }

        // Nearest dated claim by absolute time distance — close enough for a
        // sparse historical timeline; ties break to the earlier claim.
        let nearest = datedClaims.min { lhs, rhs in
            abs(lhs.start.timeIntervalSince(tappedDate)) < abs(rhs.start.timeIntervalSince(tappedDate))
        }
        if let entityId = nearest?.primaryEntityId {
            selectedEntityId = entityId
        }
    }

    // MARK: - Data

    /// Lookup of entityId → kind, built from the (already-filtered) entity
    /// set so swimlane assignment and colour stay consistent with the list.
    private var entityKindById: [String: Components.Schemas.EntityTypeOutput] {
        var map: [String: Components.Schemas.EntityTypeOutput] = [:]
        for entity in entities {
            if let id = entity.id { map[id] = entity.entityType }
        }
        return map
    }

    /// Claims with a parseable start date, in scope, sorted by start.
    private var datedClaims: [DatedClaim] {
        claims.compactMap { claim -> DatedClaim? in
            guard let start = KGTemporal.parseFlexibleDate(claim.timeStart) else { return nil }
            guard isInScope(claim) else { return nil }
            let primary = claim.subjectEntityId ?? (claim.entityIds ?? []).first
            let end = KGTemporal.parseFlexibleDate(claim.timeEnd) ?? start
            let kind = primary.flatMap { entityKindById[$0] }
            return DatedClaim(
                claim: claim,
                start: start,
                end: max(end, start),
                provenance: KGTemporal.provenance(for: claim),
                color: kgEntityColor(for: kind),
                lane: Self.lane(for: kind),
                primaryEntityId: primary,
                isSelected: primary != nil && primary == selectedEntityId
            )
        }
        .sorted { $0.start < $1.start }
    }

    /// Count of in-scope claims that have no plottable date — surfaced in the
    /// header so the user knows the timeline isn't the whole picture.
    private var undatedInScopeCount: Int {
        claims.filter { isInScope($0) && KGTemporal.parseFlexibleDate($0.timeStart) == nil }.count
    }

    /// In scope when (a) the claim's subject resolves to a visible entity
    /// (kind filter), and (b) if focusing, it belongs to the selected entity.
    private func isInScope(_ claim: Components.Schemas.KnowledgeClaim) -> Bool {
        // `claims` are already document-scoped by listClaims(sourceDocumentId:,
        // includeDescendants:), so every loaded claim is in scope by
        // construction. The previous entity-overlap filter (claim's entities ∩
        // this document's entity list) dropped every dated claim whose entity
        // wasn't in the doc-only entity list, so the timeline showed "No dated
        // claims" even with parseable dates (#1470). Only narrow by entity when
        // the user explicitly focuses on a selection.
        guard focusOnSelection, let selectedEntityId else { return true }
        let ids = Set([claim.subjectEntityId].compactMap { $0 }).union(claim.entityIds ?? [])
        return ids.contains(selectedEntityId)
    }

    private static func lane(for kind: Components.Schemas.EntityTypeOutput?) -> String {
        switch kind {
        case .person: return "People"
        case .location: return "Places"
        case .organization: return "Organizations"
        case .event: return "Events"
        case .concept: return "Concepts"
        case .citation: return "Citations"
        case .other, .none: return "Other"
        }
    }

    @MainActor
    private func load() async {
        guard let library = LibraryManager.shared.globalLibrary else {
            loadError = "No library"
            return
        }
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            claims = try await library.entityService.listClaims(
                sourceDocumentId: sourceDocumentId,
                includeDescendants: sourceDocumentId != nil,
                limit: 500
            )
        } catch {
            loadError = error.localizedDescription
        }
    }

    /// One plottable claim. Pre-computes colour / lane / provenance so the
    /// Chart content builder stays a thin mapping.
    private struct DatedClaim: Identifiable {
        let claim: Components.Schemas.KnowledgeClaim
        let start: Date
        let end: Date
        let provenance: KGProvenance
        let color: Color
        let lane: String
        let primaryEntityId: String?
        let isSelected: Bool

        var id: String { claim.id ?? "\(start.timeIntervalSince1970)-\(claim.text.hashValue)" }
        var isSpan: Bool { end.timeIntervalSince(start) > 86_400 }
    }
}
