import FicheroAPIClient
import MapKit
import SwiftUI

/// Map visualization of geo-located claims (#1267). Each claim that carries
/// a `claimGeo` point is plotted as a pin coloured by its subject entity's
/// kind, using the shared KG palette so it lines up with the Graph, Chart,
/// and Timeline views.
///
/// Asserted vs inferred locations are distinguished visually (see
/// `KGSpatial.provenance`): asserted (a precise fix from a trustworthy
/// source) renders as a solid filled pin; inferred (a coarse radius or a
/// low-trust confidence origin) renders as a dimmed open pin. Tapping a pin
/// selects its entity, cross-filtering the entity list, detail pane, and the
/// focus-neighborhood Graph view through the shared `selectedEntityId`.
///
/// Scope: honours the upstream entity-kind filter (a claim is plotted only
/// when its subject resolves to a visible entity); a "Focus" toggle narrows
/// to the selected entity's located claims. Claims with only `claimLocation`
/// text and no coordinate can't be mapped — they're counted in the header so
/// the map isn't silently partial. Degrades to an explanatory empty state
/// when no claim has spatial data yet (#1266 pending).
struct KGMapView: View {
    let entities: [Components.Schemas.KnowledgeEntity]
    @Binding var selectedEntityId: String?
    var sourceDocumentId: String?

    @State private var claims: [Components.Schemas.KnowledgeClaim] = []
    @State private var isLoading = false
    @State private var loadError: String?
    @State private var focusOnSelection = false
    @State private var cameraPosition: MapCameraPosition = .automatic

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
            Text("Map")
                .font(.headline)
            Text("\(locatedClaims.count) mapped · \(unmappedInScopeCount) unmapped")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            provenanceLegend
            if selectedEntityId != nil {
                Toggle("Focus", isOn: $focusOnSelection)
                    .toggleStyle(.switch)
                    .controlSize(.mini)
                    .help("Show only the selected entity's located claims")
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var provenanceLegend: some View {
        HStack(spacing: 10) {
            HStack(spacing: 4) {
                Image(systemName: "mappin.circle.fill").font(.caption2).foregroundStyle(.secondary)
                Text("Asserted").font(.caption2).foregroundStyle(.secondary)
            }
            HStack(spacing: 4) {
                Image(systemName: "mappin.circle").font(.caption2).foregroundStyle(.secondary)
                Text("Inferred").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Content states

    @ViewBuilder
    private var content: some View {
        if isLoading {
            ProgressView("Loading map…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let loadError {
            errorState(loadError)
        } else if locatedClaims.isEmpty {
            emptyState
        } else {
            map
        }
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No mapped claims", systemImage: "mappin.slash")
        } description: {
            Text(claims.isEmpty
                    ? "Claims will appear here once extraction has run"
                    : "Claims need coordinates (claimGeo) to plot on the map")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Couldn't load map", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Map

    private var map: some View {
        Map(position: $cameraPosition) {
            ForEach(locatedClaims) { located in
                Annotation(located.label, coordinate: located.coordinate) {
                    pin(for: located)
                        .onTapGesture {
                            if let entityId = located.primaryEntityId {
                                selectedEntityId = entityId
                            }
                        }
                }
            }
        }
        .mapStyle(.standard(elevation: .flat))
    }

    private func pin(for located: LocatedClaim) -> some View {
        Image(systemName: located.provenance == .asserted ? "mappin.circle.fill" : "mappin.circle")
            .font(.system(size: located.isSelected ? 28 : 20))
            .foregroundStyle(located.color)
            .opacity(located.provenance == .inferred ? 0.6 : 1.0)
            .background(
                Circle()
                    .fill(Color(.windowBackgroundColor))
                    .padding(2)
            )
            .overlay(
                Circle()
                    .stroke(Color.accentColor, lineWidth: located.isSelected ? 2 : 0)
            )
            .help(located.label)
    }

    // MARK: - Data

    private var entityKindById: [String: Components.Schemas.EntityTypeOutput] {
        var map: [String: Components.Schemas.EntityTypeOutput] = [:]
        for entity in entities {
            if let id = entity.id { map[id] = entity.entityType }
        }
        return map
    }

    /// Claims with valid coordinates that pass the scope filter.
    private var locatedClaims: [LocatedClaim] {
        claims.compactMap { claim -> LocatedClaim? in
            guard let geo = claim.claimGeo else { return nil }
            guard isInScope(claim) else { return nil }
            let coordinate = CLLocationCoordinate2D(latitude: geo.lat, longitude: geo.lon)
            guard CLLocationCoordinate2DIsValid(coordinate) else { return nil }
            let primary = claim.subjectEntityId ?? (claim.entityIds ?? []).first
            let kind = primary.flatMap { entityKindById[$0] }
            return LocatedClaim(
                claim: claim,
                coordinate: coordinate,
                provenance: KGSpatial.provenance(for: claim),
                color: kgEntityColor(for: kind),
                primaryEntityId: primary,
                isSelected: primary != nil && primary == selectedEntityId
            )
        }
    }

    /// In-scope claims that name a place but have no coordinate to map.
    private var unmappedInScopeCount: Int {
        claims.filter { claim in
            guard isInScope(claim) else { return false }
            guard claim.claimGeo == nil else { return false }
            return (claim.claimLocation?.isEmpty == false)
        }.count
    }

    private func isInScope(_ claim: Components.Schemas.KnowledgeClaim) -> Bool {
        // `claims` are already document-scoped by listClaims(sourceDocumentId:,
        // includeDescendants:), so every loaded claim is in scope by
        // construction. The previous additional entity-overlap filter (claim's
        // entities ∩ this document's entity list) dropped every geocoded place
        // claim whose place entity wasn't in the doc-only entity list, so the
        // map always read "No mapped claims" even with geocoded data (#1471).
        // Only narrow by entity when the user explicitly focuses on a selection.
        guard focusOnSelection, let selectedEntityId else { return true }
        let ids = Set([claim.subjectEntityId].compactMap { $0 }).union(claim.entityIds ?? [])
        return ids.contains(selectedEntityId)
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
            // Reframe to fit the freshly-loaded pins.
            cameraPosition = .automatic
        } catch {
            loadError = error.localizedDescription
        }
    }

    /// One plottable claim location. Pre-computes colour / provenance so the
    /// Map content builder stays a thin mapping.
    private struct LocatedClaim: Identifiable {
        let claim: Components.Schemas.KnowledgeClaim
        let coordinate: CLLocationCoordinate2D
        let provenance: KGProvenance
        let color: Color
        let primaryEntityId: String?
        let isSelected: Bool

        var id: String {
            claim.id ?? "\(coordinate.latitude),\(coordinate.longitude)-\(claim.text.hashValue)"
        }
        var label: String {
            claim.claimLocation
                ?? claim.claimGeo?.placeName
                ?? claim.subjectCanonical
                ?? "Claim"
        }
    }
}
