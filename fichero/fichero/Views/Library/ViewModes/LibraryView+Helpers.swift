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
            .background(isSelected ? tint : Color.clear)
            .contentShape(Rectangle())
    }
}
