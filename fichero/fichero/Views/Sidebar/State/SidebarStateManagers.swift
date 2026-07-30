import Observation
import SwiftUI

enum SidebarBrowserDestination: String, Hashable {
    case activity
    case workflows
    case batches
    case entities
    case comparison
    case research
}

enum SidebarDestination: Hashable {
    case document(String)
    case search(String)
    case chat(String)
    case workflow(String)
    case chain(String)
    case schedule(String)
    case trigger(String)
    case batch(String)
    case run(String)
    /// A model-comparison history row ("comparison:<id>", #4335). Routes to the
    /// comparison detail surface like `browser(.comparison)` does for the empty
    /// state — without this case the row id fell through to the `.document`
    /// fallback ("doc:comparison:…") and clicking it routed to nothing.
    case comparisonItem(String)
    case structure(documentId: String, nodeId: String)
    /// A virtual section folder (saved-search / chat / workflow). The payload is
    /// the folder item's id minus the "folder:" prefix, i.e. "<path>:<Category>",
    /// so `serializedID` round-trips back to the sidebar item's id and
    /// `findItemById` can resolve it (#11).
    case folder(String)
    case browser(SidebarBrowserDestination)
    case library(UUID)

    /// One prefix → constructor per case. Table-driven so adding a node kind
    /// (e.g. "comparison:", #4335) is one row, not another branch in an
    /// if-chain the complexity gate rejects. NOTE the "folder:" row: virtual
    /// folder rows use id "folder:<path>:<Category>"; without it the id fell
    /// through to the `.document(id)` fallback in `SidebarItem.destination`,
    /// so `serializedID` re-prefixed it to "doc:folder:…" and `findItemById`
    /// never matched — clicking a workflow (or search/chat) folder routed to
    /// nothing (#11).
    private static let prefixedCases: [(String, (String) -> SidebarDestination?)] = [
        ("doc:", { .document($0) }),
        ("search:", { .search($0) }),
        ("chat:", { .chat($0) }),
        ("workflow:", { .workflow($0) }),
        ("chain:", { .chain($0) }),
        ("schedule:", { .schedule($0) }),
        ("trigger:", { .trigger($0) }),
        ("batch:", { .batch($0) }),
        ("run:", { .run($0) }),
        ("comparison:", { .comparisonItem($0) }),
        ("structure:", { payload in
            let parts = payload.split(separator: ":", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { return nil }
            return .structure(documentId: parts[0], nodeId: parts[1])
        }),
        ("folder:", { .folder($0) }),
        ("library:", { id in UUID(uuidString: id).map { .library($0) } })
    ]

    private static let browserCases: [String: SidebarBrowserDestination] = [
        "activity-browser": .activity,
        "workflows-browser": .workflows,
        "batches-browser": .batches,
        "entities-browser": .entities,
        "comparison-browser": .comparison,
        "research-browser": .research
    ]

    init?(serializedID: String) {
        if let browser = Self.browserCases[serializedID] {
            self = .browser(browser)
            return
        }
        for (prefix, make) in Self.prefixedCases {
            guard let payload = serializedID.stripPrefix(prefix) else { continue }
            guard let destination = make(payload) else { return nil }
            self = destination
            return
        }
        return nil
    }

    var serializedID: String {
        switch self {
        case .document(let id): return "doc:\(id)"
        case .search(let id): return "search:\(id)"
        case .chat(let id): return "chat:\(id)"
        case .workflow(let id): return "workflow:\(id)"
        case .chain(let id): return "chain:\(id)"
        case .schedule(let id): return "schedule:\(id)"
        case .trigger(let id): return "trigger:\(id)"
        case .batch(let id): return "batch:\(id)"
        case .run(let id): return "run:\(id)"
        case .comparisonItem(let id): return "comparison:\(id)"
        case .structure(let documentId, let nodeId): return "structure:\(documentId):\(nodeId)"
        case .folder(let id): return "folder:\(id)"
        case .browser(.activity): return "activity-browser"
        case .browser(.workflows): return "workflows-browser"
        case .browser(.batches): return "batches-browser"
        case .browser(.entities): return "entities-browser"
        case .browser(.comparison): return "comparison-browser"
        case .browser(.research): return "research-browser"
        case .library(let id): return "library:\(id.uuidString)"
        }
    }
}

private extension String {
    func stripPrefix(_ prefix: String) -> String? {
        hasPrefix(prefix) ? String(dropFirst(prefix.count)) : nil
    }
}

/// Manages rename state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class RenameStateManager {
    var renamingItemId: String?
    var editingName: String = ""

    func startRename(itemId: String, currentName: String) {
        renamingItemId = itemId
        editingName = currentName
    }

    func cancelRename() {
        renamingItemId = nil
        editingName = ""
    }
}

/// Manages delete confirmation state for sidebar items.
/// Use @State in parent view, pass as @Bindable to children.
@MainActor
@Observable
class DeleteStateManager {
    var showingDeleteConfirmation = false
    var showingDeleteError = false
    /// The items pending deletion. One element for a single-row delete, several
    /// for a multi-selection batch delete. `itemToDelete` stays as the
    /// single-item convenience (nil for a batch) so existing single-delete
    /// callers/messages keep working.
    var itemsToDelete: [SidebarItem] = []
    var itemToDelete: SidebarItem? { itemsToDelete.count == 1 ? itemsToDelete.first : nil }
    var deleteErrorMessage = ""

    func showDeleteConfirmation(for item: SidebarItem) {
        showDeleteConfirmation(for: [item])
    }

    func showDeleteConfirmation(for items: [SidebarItem]) {
        guard !items.isEmpty else { return }
        itemsToDelete = items
        showingDeleteConfirmation = true
    }

    func cancelDelete() {
        showingDeleteConfirmation = false
        showingDeleteError = false
        itemsToDelete = []
        deleteErrorMessage = ""
    }

    func showError(message: String) {
        deleteErrorMessage = message
        showingDeleteError = true
        showingDeleteConfirmation = false
    }
}

/// The single node that drives the detail pane, derived from the multi-row
/// highlight set. A one-row selection routes to that row; an empty selection
/// clears; a multi-row (batch) selection keeps the previous primary so the
/// detail view doesn't thrash while the user builds up a selection — UNLESS
/// that previous primary was just removed from the set, in which case it falls
/// back to a remaining member (never routes to an unhighlighted row).
func sidebarPrimaryDestination(
    for selection: Set<SidebarDestination>,
    previous: SidebarDestination?
) -> SidebarDestination? {
    switch selection.count {
    case 0: return nil
    case 1: return selection.first
    default:
        // Batch selection: keep the primary stable if it's still selected;
        // otherwise pick any remaining member so the detail matches a
        // highlighted row (Set.first is fine — any selected row is valid).
        if let previous, selection.contains(previous) { return previous }
        return selection.first
    }
}

/// Collapse a multi-row selection back to a single anchor — used by Escape
/// (and any plain-click path). A nil primary clears the selection entirely.
func sidebarCollapsedSelection(primary: SidebarDestination?) -> Set<SidebarDestination> {
    guard let primary else { return [] }
    return [primary]
}

/// Shared live selection for the sidebar tree.
/// Keep this as the single runtime source of truth so the List selection,
/// row taps, and content routing all observe the same value.
@MainActor
@Observable
class SidebarSelectionState {
    /// Rows highlighted in the sidebar. Bound to `List(selection:)` so macOS
    /// gives shift-click contiguous range, cmd-click toggle, and shift+arrow
    /// extend natively — the priority multi-select feature. Kept in sync with
    /// `selectedDestination` (the routed primary) so single-selection consumers
    /// are unaffected.
    var selectedDestinations: Set<SidebarDestination> = []

    /// The single node that drives the detail pane. Existing navigation,
    /// persistence, and creation code read/write this (via `selectedItemId`)
    /// unchanged; the multi-row highlight set is kept in sync at the two write
    /// seams — this `selectedItemId` setter (programmatic single-selection) and
    /// the `List(selection:)` binding in `SidebarView.unifiedContent` (native
    /// mouse/keyboard multi-select). Deliberately a plain stored property (no
    /// `didSet`): the List binding legitimately holds `selectedDestinations`
    /// different from `[selectedDestination]` during a batch selection, so a
    /// didSet that force-synced them would clobber the multi-row set.
    var selectedDestination: SidebarDestination?

    var selectedItemId: String? {
        get { selectedDestination?.serializedID }
        set {
            let dest = newValue.flatMap(SidebarDestination.init(serializedID:))
            selectedDestination = dest
            // Programmatic single-selection (or clear) drives the highlight to
            // match: exactly this row, or nothing.
            selectedDestinations = sidebarCollapsedSelection(primary: dest)
        }
    }
}
