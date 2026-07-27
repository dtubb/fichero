import FicheroAPIClient
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
    /// page_content happens to mention it. The maintainer's "if I click on a
    /// name, it should find other documents with that person's name"
    /// requirement.
    var entityType: String?
    /// Cap so a single super-long name (e.g. 'Canadian Association of
    /// Latin American and Caribbean Studies') doesn't push the lozenge
    /// past its column boundary. Truncated with middle-ellipsis like
    /// Finder filename truncation. (The maintainer: 'elipses in the middle')
    var maxWidth: CGFloat = 180

    /// Per-window search bus (#3437). Optional so a lozenge shown in a host that
    /// hasn't injected the state safely no-ops instead of trapping.
    @Environment(EntitySearchState.self) private var entitySearchState: EntitySearchState?

    var body: some View {
        Button {
            entitySearchState?.request(name: name, entityType: entityType)
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

/// Per-window entity-search request bus. Scoped to the window/library via the
/// SwiftUI environment (#3437) — NOT a process-global singleton, so a search
/// fired in one window never drives another. `ContentView` owns one instance
/// and injects it; producers read it from `@Environment`.
@Observable
@MainActor
final class EntitySearchState {
    private(set) var requestID: Int = 0
    private(set) var requestedName: String?
    private(set) var requestedEntityType: String?
    /// Smart-folder hop (#4114): also persist the scoped query as a
    /// SavedSearch so it lands in the sidebar in ONE click.
    private(set) var requestedSaveAsSmartSearch: Bool = false

    func request(name: String, entityType: String?, saveAsSmartSearch: Bool = false) {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return }
        requestedName = trimmedName
        requestedEntityType = entityType?.trimmingCharacters(in: .whitespacesAndNewlines)
        requestedSaveAsSmartSearch = saveAsSmartSearch
        requestID &+= 1
    }
}

/// Where a source-navigation request wants the user taken. The popover
/// quick-look (#3449) needs neither (it renders the crop inline), but a
/// "reveal" action states whether the center Preview pane, the full Reader,
/// or both should follow the anchor (#2105 tier 2). Defaults to `.reader`
/// to preserve the pre-existing jump-to-page behaviour.
enum SourceDestination: String, Equatable, Sendable {
    case preview
    case reader
    case both
}

/// The cross-cutting "trace this record back to its source" contract
/// (#2105). Any bbox-anchored item — claim, entity mention, face,
/// annotation, transcribed line — carries this so the inspector can both
/// render the cropped source region (via the ephemeral-crop endpoint) and
/// reveal the exact place on the page. `bbox`/`pageIndex` are optional so
/// existing char-range callers keep working unchanged.
struct ClaimSourceNavigationRequest: Equatable {
    let documentId: String
    var claimId: String?
    var claimText: String?
    var pageLabel: String?
    var pageIndex: Int?
    var charStart: Int?
    var charEnd: Int?
    /// Normalized [x, y, w, h] source region (top-left origin), matching the
    /// engine's annotation bbox convention (crop_pdf_page / crop_image). Drives
    /// the cropped-source popover and the page-highlight overlay.
    var bbox: [Double]?
    /// Where a reveal should take the user. Ignored by the inline popover.
    var destination: SourceDestination = .reader
}

extension SourceDestination {
    /// Widen to the engine's `LocationSurface` (#3577). `SourceDestination` has
    /// no `.inspector` case, so this only ever produces preview/reader/both.
    var locationSurface: Components.Schemas.LocationSurface {
        switch self {
        case .preview: return .preview
        case .reader: return .reader
        case .both: return .both
        }
    }
}

extension ClaimSourceNavigationRequest {
    /// This request as the engine-known `Location` (#3577). The Swift request
    /// keeps its own shape (locked by `SourceNavigationContractTests`); this is
    /// the thin wrapper that lets `locationService.resolve` do page-child →
    /// parent resolution in ONE place. `pageIndex` is 0-based here but the engine
    /// `page` is 1-based, so it is bumped by one.
    var asLocation: Components.Schemas.Location {
        let charRange: Components.Schemas.CharacterRange? = {
            guard let charStart, let charEnd else { return nil }
            return Components.Schemas.CharacterRange(start: charStart, end: charEnd)
        }()
        return Components.Schemas.Location(
            documentId: documentId,
            page: pageIndex.map { $0 + 1 },
            bbox: bbox,
            charRange: charRange,
            claimId: claimId,
            entityId: nil,
            surface: destination.locationSurface
        )
    }
}

/// Per-window claim/entity/citation source-navigation request bus. Scoped to
/// the window/library via the SwiftUI environment (#3437) — NOT a process-global
/// singleton, so a source reveal in one window never navigates another.
/// `ContentView` owns one instance and injects it; producers read it from
/// `@Environment` (optional, so a host that hasn't injected safely no-ops).
@Observable
@MainActor
final class ClaimSourceNavigationState {
    private(set) var requestID: Int = 0
    private(set) var currentRequest: ClaimSourceNavigationRequest?

    func request(_ request: ClaimSourceNavigationRequest) {
        guard !request.documentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        currentRequest = request
        requestID &+= 1
    }
}

// MARK: - Active surface (#3579)

/// Stable identity for one Preview/Reader pane instance. A fresh value is
/// minted at pane mount (`@State private var surfaceId = SurfaceID()`), so left
/// and right split panes qualify independently — mirroring the per-instance
/// `isPinned` design (#3579, §0.2).
struct SurfaceID: Hashable {
    private let id = UUID()
}

/// Per-window "which pane updates on the next library click" marker (#3579).
/// Scoped to the window/library via the SwiftUI environment (NOT `.shared`),
/// matching `ClaimSourceNavigationState` and the #3437 scoping invariant locked
/// by `InspectorNavigationScopingTests`. A direct click inside a Preview/Reader
/// pane writes its `SurfaceID` here; the active pane draws an accent hairline.
@Observable
@MainActor
final class ActiveSurfaceState {
    /// The pane that updates on the next library click, or nil when no unpinned
    /// Preview/Reader pane exists. All mutation flows through the methods below
    /// so the pin ⇄ active invariants (#3580, §2.3) hold in one place.
    private(set) var activeSurfaceId: SurfaceID?

    /// Currently-mounted, UNPINNED Preview/Reader panes (#3580). A pane can't
    /// tell on its own whether it's "the only unpinned one", so the set lives
    /// here — the minimal shared state needed to kill the dead-active case.
    private var unpinnedSurfaces: Set<SurfaceID> = []

    /// A pane appears (or unpins): it joins the pool and, if it's now the sole
    /// unpinned pane, silently becomes active — no dead state (§2.3).
    func registerUnpinned(_ id: SurfaceID) {
        unpinnedSurfaces.insert(id)
        resolveSoleActive()
    }

    /// A pane pins, disappears, or its split collapses: it leaves the pool. If
    /// it was the active one, active clears; a lone survivor then auto-activates.
    func unregister(_ id: SurfaceID) {
        unpinnedSurfaces.remove(id)
        if activeSurfaceId == id { activeSurfaceId = nil }
        resolveSoleActive()
    }

    /// A direct click picks this pane as active — unless it's pinned, in which
    /// case it's skipped (§2.1: a pinned pane is never a NEW active target).
    func activate(_ id: SurfaceID) {
        guard unpinnedSurfaces.contains(id) else { return }
        activeSurfaceId = id
    }

    /// No dead state: exactly one unpinned pane ⇒ it is active. If the active id
    /// no longer names an unpinned pane, clear it.
    private func resolveSoleActive() {
        if unpinnedSurfaces.count == 1 {
            activeSurfaceId = unpinnedSurfaces.first
        } else if let active = activeSurfaceId, !unpinnedSurfaces.contains(active) {
            activeSurfaceId = nil
        }
    }
}

// MARK: - Notification names

extension Notification.Name {
    // The claim/entity *data-mutation* notifications (`.ficheroClaimDeleted`,
    // `.ficheroClaimUpdated`, `.ficheroEntityUpdated`) were retired in #1862.
    // Claim/entity mutations now flow through ClaimStore/EntityStore and the
    // per-library change-stream (#1863), which fans `claim.*`/`entity.*` events
    // to every window's stores. Only *navigation* signals remain — those are
    // not data mutations and stay out of the change-stream (spec §4.3).

    /// Forwarded from the typed source-open request after ContentView
    /// has resolved the source-doc id to a page number. Received by the
    /// PDF canvas so it can jump to the right page. (#833)
    static let ficheroNavigateToPage = Notification.Name("ficheroNavigateToPage")
}

// MARK: - KGDisplayMode

/// Toggle between dense prose digest and grouped disclosure list.
enum KGDisplayMode: String {
    case text
    case list
}

// MARK: - EntityKind

/// Local enum mirroring the API EntityType plus a "date" bucket for
/// claim-only date entries (those have no entity at all).
enum EntityKind: String, Hashable, CaseIterable {
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

    var apiTypeId: String? {
        switch self {
        case .person: return "person"
        case .location: return "location"
        case .organization: return "organization"
        case .event: return "event"
        case .concept: return "concept"
        case .date, .other: return nil
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
