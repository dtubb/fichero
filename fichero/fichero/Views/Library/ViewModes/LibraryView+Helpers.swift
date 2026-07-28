import FicheroAPIClient
import SwiftUI

// MARK: - Helper Types for Display Modes

/// A list row whose selection tint is diffed by VALUE — the row's data `identity`,
/// `isSelected`, and `tint` — not the whole selection `Set` (#3868). Marked
/// `Equatable` and applied with `.equatable()` so one selection click only
/// re-renders the rows whose selection actually changed; unchanged rows are skipped
/// even though their content holds closures (which would otherwise defeat SwiftUI's
/// field diffing). The tap / context-menu actions are applied OUTSIDE this wrapper,
/// so they're excluded from `==` — safe because they act on the same `identity`.
/// Everything a document list row renders from besides its selection state, so the
/// `.equatable()` skip stays correct when the visible-tag filter changes (#3868).
struct DocRowIdentity: Equatable, Sendable {
    let document: Document
    let visibleEntityTypes: Set<String>
    /// Inline rename toggles the title between Text and TextField (#4160) —
    /// without this in `==`, `.equatable()` suppresses the redraw and the
    /// rename field never appears.
    var isRenaming: Bool = false
}

/// Icon-grid analogue of `DocRowIdentity` (#4160): everything a tile renders
/// from besides its selection state, so `.equatable()` can skip unchanged
/// tiles — a click previously re-evaluated every materialised tile body.
struct IconCellIdentity: Equatable, Sendable {
    let document: Document
    let scale: Double
    var isRenaming: Bool = false
}

/// Equatable identity for a Miller column row — everything the row renders
/// from besides selection/tint (which LibrarySelectableRow already
/// compares): the document, its column, whether it's the disclosed path
/// segment, and rename state.
struct ColumnRowIdentity: Equatable, Sendable {
    let document: Document
    let depth: Int
    let isPathSegment: Bool
    let isRenaming: Bool
}

/// Chrome-free equatable wrapper for grid tiles. `LibrarySelectableRow` adds
/// row padding/background the tiles already draw themselves, so this only
/// contributes the value-diffed skip. `tint` is compared so focus/key
/// changes (which change `selectionTint`) still redraw selected tiles.
struct LibraryIconCell<Identity: Equatable & Sendable, Content: View>: View, Equatable {
    let identity: Identity
    let isSelected: Bool
    let tint: Color
    @ViewBuilder let content: Content

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.identity == rhs.identity
            && lhs.isSelected == rhs.isSelected
            && lhs.tint == rhs.tint
    }

    var body: some View { content }
}

/// Subtle hover wash on unselected list rows (#4160), like the sidebar's
/// hover affordance — pointer feedback without stealing the selection tint.
/// Per-row @State so hovering re-renders ONE row, not the list.
struct LibraryRowHoverWash: ViewModifier {
    let enabled: Bool
    @State private var isHovered = false

    func body(content: Content) -> some View {
        content
            .background(enabled && isHovered ? Color.primary.opacity(0.05) : Color.clear)
            .onHover { isHovered = $0 }
    }
}

struct LibrarySelectableRow<Identity: Equatable & Sendable, Content: View>: View, Equatable {
    let identity: Identity
    let isSelected: Bool
    let tint: Color
    @ViewBuilder let content: Content

    // nonisolated: this View is implicitly @MainActor, but Equatable's `==` must be
    // nonisolated (Swift 6). Safe — all compared properties are immutable value types;
    // `Identity: Sendable` lets `==` read `identity` cross-actor like the Sendable
    // `isSelected`/`tint` lets it already compares (#3977).
    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.identity == rhs.identity
            && lhs.isSelected == rhs.isSelected
            && lhs.tint == rhs.tint
    }

    var body: some View {
        content
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            // Mail-style selection (#4191): the fill is always the subtle
            // grey rounded rect — focus is signalled by the row's LABEL tint,
            // not the fill. `tint` still carries the focus-dependent label
            // color so `==` re-renders selected rows when focus flips.
            .background(
                RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                    .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
            )
            .contentShape(Rectangle())
    }
}
