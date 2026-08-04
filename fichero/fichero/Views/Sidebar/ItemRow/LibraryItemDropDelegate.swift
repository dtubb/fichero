import Foundation
import SwiftUI
import UniformTypeIdentifiers

// MARK: - The cursor must say what the drop will do (#4401)
//
// `.onDrop(of:isTargeted:perform:)` has NO say over the drag operation: SwiftUI
// always proposes `.copy`, so macOS paints a `+` badge. That is why an
// intra-library MOVE told the user it was copying. It is not a cosmetic
// mismatch — the badge is the only thing the user can read BEFORE committing to
// the drop, and it contradicted both the grammar (`sidebarDropOperation`) and
// the outcome (`applyLibraryItemDropOperation`).
//
// The badge was correct once. The library folder cell used to be a Transferable
// `.dropDestination`, which proposes `.move` for an in-app payload on its own.
// Widening it to the untyped provider API (#4474/#4475, so a sidebar drag and a
// library-pane drag could reach ONE reader) was right and is kept — this file
// pays back the one thing that widening cost.
//
// Only `.onDrop(of:delegate:)` can answer, via `dropUpdated`. Everything else
// about the drop is unchanged: the same `dropTypes`, the same providers, the
// same handler, the same `isTargeted` binding.

/// Does this drag look like it started inside Fichero?
///
/// The same heuristic `sidebarDropMightCarryInternalID` already routes on: an
/// in-app drag always vends its id as a string, and a Finder file drag puts
/// `public.file-url` on the pasteboard rather than the file's text content.
///
/// `DropInfo` is synchronous and cannot read a provider's contents, so this
/// cannot be the positive id check `readSidebarDropPayload` performs — and it
/// does not have to be. It decides a CURSOR BADGE. Being wrong shows the wrong
/// badge for one hover; the drop itself is still routed by the id actually
/// read, which is the #4401 ordering rule.
@MainActor
func dropInfoLooksLikeInAppDrag(_ info: DropInfo) -> Bool {
    info.hasItemsConforming(to: [.utf8PlainText])
}

/// The badge for a drag hovering a library-item drop target.
///
/// Pure, so the rule is testable without a live drag — the #4473 gap that let
/// "the cursor lies" survive four commits and a closure.
///
/// An EXTERNAL file drop genuinely is a copy (the bytes are ingested and the
/// original stays put), so `+` is correct there and is deliberately kept.
func libraryItemDropProposedOperation(
    isInAppDrag: Bool,
    modifiers: SidebarDropModifiers
) -> DropOperation {
    guard isInAppDrag else { return .copy }
    switch sidebarDropOperation(modifiers: modifiers, kind: .document) {
    case .move:
        return .move
    case .copy:
        return .copy
    case .alias:
        #if os(macOS)
        return .alias
        #else
        // `.alias` is macOS-only; ⌘⌥ has no iOS badge, and copy is the nearest
        // truthful one for a destination that gains a new row.
        return .copy
        #endif
    }
}

/// One drop delegate for every surface that accepts a library-item drag.
///
/// Deliberately a thin shell: it exists to answer `dropUpdated`, and hands the
/// providers straight to the handler the surface already had. Putting any
/// routing here would be a second classifier, which is the exact mistake
/// `SidebarDropClassification`'s header records.
struct LibraryItemDropDelegate: DropDelegate {
    /// The types the surface declared — `performDrop` must ask for the SAME
    /// set, or it collects fewer providers than the drop was accepted for.
    let acceptedTypes: [UTType]
    let isTargeted: Binding<Bool>
    /// Returns whether the drop was accepted, exactly as the `.onDrop` closure
    /// it replaces did. `@MainActor` because every handler it wraps is a method
    /// on a View, and `NSItemProvider` is not Sendable.
    let onDropProviders: @MainActor ([NSItemProvider]) -> Bool

    func validateDrop(info: DropInfo) -> Bool {
        // `acceptedTypes` already gated which drags reach this delegate; a
        // narrower answer here would REFUSE drops the closure form accepted,
        // which is a worse regression than the badge this file fixes.
        true
    }

    func dropEntered(info: DropInfo) {
        isTargeted.wrappedValue = true
    }

    func dropExited(info: DropInfo) {
        isTargeted.wrappedValue = false
    }

    func dropUpdated(info: DropInfo) -> DropProposal? {
        // Re-read the modifiers every update: this IS the hover feedback, the
        // one place `SidebarDropOperation`'s "sample once at the entry point"
        // rule explicitly exempts, because the badge must track the key the
        // user is holding right now.
        DropProposal(operation: libraryItemDropProposedOperation(
            isInAppDrag: dropInfoLooksLikeInAppDrag(info),
            modifiers: .current()
        ))
    }

    func performDrop(info: DropInfo) -> Bool {
        // The drop is committed — end the hover feedback NOW (#4229), same
        // reason `handleRowDrop` does: a row that rebuilds mid-drag can lose
        // the trailing `dropExited` and keep the accent wash stuck on.
        isTargeted.wrappedValue = false
        return onDropProviders(info.itemProviders(for: acceptedTypes))
    }
}
