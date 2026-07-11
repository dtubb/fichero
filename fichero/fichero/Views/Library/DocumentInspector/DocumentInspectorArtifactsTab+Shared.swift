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
    /// page_content happens to mention it. Daniel's "if I click on a
    /// name, it should find other documents with that person's name"
    /// requirement.
    var entityType: String?
    /// Cap so a single super-long name (e.g. 'Canadian Association of
    /// Latin American and Caribbean Studies') doesn't push the lozenge
    /// past its column boundary. Truncated with middle-ellipsis like
    /// Finder filename truncation. (Daniel: 'elipses in the middle')
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

    func request(name: String, entityType: String?) {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedName.isEmpty else { return }
        requestedName = trimmedName
        requestedEntityType = entityType?.trimmingCharacters(in: .whitespacesAndNewlines)
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
