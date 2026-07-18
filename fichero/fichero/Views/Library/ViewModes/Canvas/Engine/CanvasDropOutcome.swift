import Foundation
import simd

// MARK: - Drag-item-onto-item semantics (#3086 rule, defined here in #3103)

/// What the drop target IS — decides move-into vs link. Neither current
/// renderer has drag-onto today, so the meaning is defined once, here, as a
/// pure function both renderers call.
enum CanvasTargetKind: Equatable {
    /// Folder / document-with-pages / workspace — a thing that CONTAINS items.
    case container
    /// Page / note / quote / text / entity — a leaf; dropping links to it.
    case leaf
}

/// The thing under the pointer at drop time (nil → empty canvas).
struct CanvasDropTarget: Equatable {
    let id: String
    let kind: CanvasTargetKind
}

/// Modifier state at drop time. `.forceLink` = ⌥ held; `.cancel` = Esc.
struct CanvasDropModifiers: OptionSet {
    let rawValue: Int
    static let forceLink = CanvasDropModifiers(rawValue: 1 << 0)
    static let cancel = CanvasDropModifiers(rawValue: 1 << 1)
}

/// The resolved drop action.
enum DropOutcome: Equatable {
    /// Move the dragged item INTO a container (→ audited `document.move`); its
    /// layout row leaves this scope and it appears on the container's canvas.
    case moveInto(containerId: String)
    /// Link the dragged item to a target (→ `canvas.item.create kind=link`).
    case link(targetId: String)
    /// Plain move — persist the dragged item's position in this scope.
    case place(position: SIMD3<Double>)
    /// Esc — abandon the drag, no persistence.
    case cancel
}

extension DropOutcome {
    /// Classify a drop. Pure — also drives the hover affordance (container →
    /// move-into ring, leaf → link glyph).
    ///
    ///   • Esc (`.cancel`) → `.cancel` (wins over everything).
    ///   • no target, or the target is the dragged item itself → `.place`.
    ///   • ⌥ (`.forceLink`) → `.link`, even over a container.
    ///   • container → `.moveInto`; leaf → `.link`.
    static func classify(
        draggedId: String,
        target: CanvasDropTarget?,
        position: SIMD3<Double>,
        modifiers: CanvasDropModifiers
    ) -> DropOutcome {
        if modifiers.contains(.cancel) {
            return .cancel
        }
        guard let target, target.id != draggedId else {
            return .place(position: position)
        }
        if modifiers.contains(.forceLink) {
            return .link(targetId: target.id)
        }
        switch target.kind {
        case .container:
            return .moveInto(containerId: target.id)
        case .leaf:
            return .link(targetId: target.id)
        }
    }
}
