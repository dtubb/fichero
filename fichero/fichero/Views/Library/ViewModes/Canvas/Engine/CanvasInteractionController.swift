import FicheroAPIClient
import Foundation
import simd
import SwiftUI

// MARK: - Renderer-agnostic interaction semantics (#3103)

/// A user gesture, renderer-agnostic. Renderers translate their native events
/// into these and dispatch them; the `CanvasInteractionController` owns what
/// each one MEANS against the shared stores. Both renderers share this exactly.
enum CanvasIntent {
    case tap(id: String?)                         // nil clears selection
    case marquee(ids: Set<String>)                // rubber-band multi-select
    case dragBegan(id: String)
    case dragMoved(id: String, position: SIMD3<Double>)
    case dragEnded(id: String, position: SIMD3<Double>, dropTarget: CanvasDropTarget?, modifiers: CanvasDropModifiers)
    case addItem(kind: Components.Schemas.CanvasItemKind, position: SIMD3<Double>)
    case editItem(id: String, text: String)
    case deleteItem(id: String)
    case connect(sourceId: String, targetId: String)
}

// MARK: - Store seams (so the controller is unit-testable without a network)

/// The layout-persistence surface the controller needs. `CanvasLayoutStore`
/// (#3082) conforms as-is; tests inject a spy. Keeps the stores unchanged.
@MainActor
protocol CanvasLayoutPersisting: AnyObject {
    func layout(for scopeId: String) -> [CanvasItemLayout]
    @discardableResult func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool
    var loadError: String? { get }
}

/// The item-CRUD surface the controller needs. `CanvasItemStore` conforms as-is.
@MainActor
protocol CanvasItemMutating: AnyObject {
    func items(for scopeId: String) -> [CanvasItemDisplay]
    @discardableResult func createItem(
        folderId: String,
        kind: Components.Schemas.CanvasItemKind,
        text: String?,
        sourceItemId: String?,
        targetItemId: String?
    ) async -> CanvasItemDisplay?
    // swiftlint:disable:next function_parameter_count
    @discardableResult func updateItem(   // mirrors the #3082 CanvasItemStore API (unchanged)
        folderId: String,
        itemId: String,
        kind: Components.Schemas.CanvasItemKind?,
        text: String?,
        sourceItemId: String?,
        targetItemId: String?
    ) async -> Bool
    @discardableResult func deleteItem(folderId: String, itemId: String) async -> Bool
    var loadError: String? { get }
}

extension CanvasLayoutStore: CanvasLayoutPersisting {}
extension CanvasItemStore: CanvasItemMutating {}

// MARK: - The controller

/// One per open canvas scene (both renderers share ONE). Turns renderer-agnostic
/// `CanvasIntent`s into store mutations, owning the subtle rules both renderers
/// used to re-implement: don't fight the gesture mid-drag, snap on release,
/// persist a SINGLE row (not the pin-all-visible batch), optimistic-with-rollback.
@MainActor
final class CanvasInteractionController {
    private let layoutStore: any CanvasLayoutPersisting
    private let itemStore: any CanvasItemMutating
    private let scopeId: String
    private let selection: Binding<String?>

    /// `.moveInto` drops route here — #3086 wires this to the audited
    /// `document.move` action + the layout-row-leaves-scope. A hook so this
    /// contract slice carries no backend-move dependency.
    var onMoveInto: ((_ itemId: String, _ containerId: String) -> Void)?

    /// A failed optimistic persist routes here so the renderer snaps the entity
    /// back to `position` — rollback is surfaced, never silently dropped.
    var onRollback: ((_ id: String, _ position: SIMD3<Double>) -> Void)?

    // Drag state machine — the "don't fight the gesture" rule.
    private(set) var draggingId: String?
    private var dragOriginPosition: SIMD3<Double>?
    private var dragCurrentPosition: SIMD3<Double>?

    /// The live selection set (marquee-capable). The single `selectedNodeId`
    /// binding mirrors the primary member for renderers that only track one.
    private(set) var selectionSet: Set<String> = []

    init(
        layoutStore: any CanvasLayoutPersisting,
        itemStore: any CanvasItemMutating,
        scopeId: String,
        selection: Binding<String?>
    ) {
        self.layoutStore = layoutStore
        self.itemStore = itemStore
        self.scopeId = scopeId
        self.selection = selection
    }

    /// The most recent store error (rollback context) — never a silent substitute.
    var lastError: String? { layoutStore.loadError ?? itemStore.loadError }

    /// True while `id` is being dragged: renderers skip store-echo `.move` ops
    /// for it so a mid-drag store patch never fights the live gesture.
    func isDragging(_ id: String) -> Bool { draggingId == id }

    // MARK: Renderer entry point

    /// Fire-and-forget dispatch for renderers. Synchronous intents run inline;
    /// mutating intents run in a Task (the async methods are unit-tested directly).
    func dispatch(_ intent: CanvasIntent) {
        switch intent {
        case .tap(let id):
            select(id)
        case .marquee(let ids):
            selectMany(ids)
        case .dragBegan(let id):
            beginDrag(id)
        case .dragMoved(let id, let position):
            dragMoved(id: id, position: position)
        case .dragEnded(let id, let position, let dropTarget, let modifiers):
            Task { await endDrag(id: id, position: position, dropTarget: dropTarget, modifiers: modifiers) }
        case .addItem(let kind, let position):
            Task { await addItem(kind: kind, position: position) }
        case .editItem(let id, let text):
            Task { await editItem(id: id, text: text) }
        case .deleteItem(let id):
            Task { await deleteItem(id: id) }
        case .connect(let sourceId, let targetId):
            Task { await connect(sourceId: sourceId, targetId: targetId) }
        }
    }

    // MARK: Selection

    func select(_ id: String?) {
        selectionSet = id.map { [$0] } ?? []
        selection.wrappedValue = id
    }

    func selectMany(_ ids: Set<String>) {
        selectionSet = ids
        selection.wrappedValue = ids.first
    }

    // MARK: Drag machine

    func beginDrag(_ id: String) {
        draggingId = id
        // Pre-drag world position (from the saved row, if any) so a failed
        // persist can snap the entity back.
        dragOriginPosition = layoutStore.layout(for: scopeId).first { $0.itemId == id }
            .map { SIMD3<Double>($0.x, $0.y, $0.z) }
        dragCurrentPosition = nil
        select(id)
    }

    func dragMoved(id: String, position: SIMD3<Double>) {
        guard draggingId == id else { return }
        dragCurrentPosition = position
    }

    func endDrag(
        id: String,
        position: SIMD3<Double>,
        dropTarget: CanvasDropTarget?,
        modifiers: CanvasDropModifiers
    ) async {
        let origin = dragOriginPosition
        defer {
            draggingId = nil
            dragOriginPosition = nil
            dragCurrentPosition = nil
        }
        let snapped = snap(position)
        switch DropOutcome.classify(draggedId: id, target: dropTarget, position: snapped, modifiers: modifiers) {
        case .cancel:
            if let origin { onRollback?(id, origin) }
        case .moveInto(let containerId):
            onMoveInto?(id, containerId)
        case .link(let targetId):
            await connect(sourceId: id, targetId: targetId)
            await persistSingleRow(id: id, to: snapped, rollbackTo: origin)
        case .place(let dropped):
            await persistSingleRow(id: id, to: dropped, rollbackTo: origin)
        }
    }

    /// Mid-drag flush when the view disappears (gesture `.onEnded` never fires).
    func flushActiveDrag() async {
        guard let id = draggingId, let position = dragCurrentPosition else { return }
        let origin = dragOriginPosition
        draggingId = nil
        dragOriginPosition = nil
        dragCurrentPosition = nil
        await persistSingleRow(id: id, to: snap(position), rollbackTo: origin)
    }

    // MARK: CRUD

    @discardableResult
    func addItem(kind: Components.Schemas.CanvasItemKind, position: SIMD3<Double>) async -> CanvasItemDisplay? {
        guard let created = await itemStore.createItem(
            folderId: scopeId, kind: kind, text: nil, sourceItemId: nil, targetItemId: nil
        ) else { return nil }
        // Immediate layout row so the new card lands where the user added it.
        await persistSingleRow(id: created.id, to: snap(position), rollbackTo: nil)
        return created
    }

    @discardableResult
    func editItem(id: String, text: String) async -> Bool {
        await itemStore.updateItem(
            folderId: scopeId, itemId: id, kind: nil, text: text, sourceItemId: nil, targetItemId: nil
        )
    }

    @discardableResult
    func deleteItem(id: String) async -> Bool {
        await itemStore.deleteItem(folderId: scopeId, itemId: id)
    }

    @discardableResult
    func connect(sourceId: String, targetId: String) async -> CanvasItemDisplay? {
        await itemStore.createItem(
            folderId: scopeId, kind: .link, text: nil, sourceItemId: sourceId, targetItemId: targetId
        )
    }

    // MARK: Move + undo (#3084)

    /// Persist a single item's snapped position — the undo/redo primitive and any
    /// programmatic move. Reuses the exactly-one-row persist.
    @discardableResult
    func moveItem(id: String, to worldPosition: SIMD3<Double>) async -> Bool {
        await persistSingleRow(id: id, to: snap(worldPosition), rollbackTo: nil)
    }

    /// Register a drag move with the window `UndoManager` (position before/after,
    /// #3084). The canonical move pattern: undoing moves back to `from` and
    /// re-registers the inverse, so redo replays the move — repeatable both ways.
    func registerMoveUndo(id: String, origin: SIMD3<Double>, destination: SIMD3<Double>, undoManager: UndoManager?) {
        guard let undoManager, origin != destination else { return }
        undoManager.registerUndo(withTarget: self) { controller in
            // UndoManager invokes the handler on the thread that called undo()
            // (main, for UI), so assume main-actor isolation to reach the
            // @MainActor controller. Undoing moves back to `origin` and registers
            // the inverse, so redo replays the move — repeatable both directions.
            MainActor.assumeIsolated {
                Task { await controller.moveItem(id: id, to: origin) }
                controller.registerMoveUndo(id: id, origin: destination, destination: origin, undoManager: undoManager)
            }
        }
        undoManager.setActionName("Move")
    }

    // MARK: Persistence — exactly one row

    /// Persist ONE row's position through `saveLayout`: patch the dragged/added
    /// id in place (or append it) and leave every other row untouched — NOT the
    /// pin-all-visible-nodes batch (#3084's save-poison). On failure, snap back.
    @discardableResult
    private func persistSingleRow(id: String, to position: SIMD3<Double>, rollbackTo origin: SIMD3<Double>?) async -> Bool {
        var rows = layoutStore.layout(for: scopeId)
        if let index = rows.firstIndex(where: { $0.itemId == id }) {
            rows[index].x = position.x
            rows[index].y = position.y
            rows[index].z = position.z
        } else {
            rows.append(CanvasItemLayout(itemId: id, x: position.x, y: position.y, z: position.z))
        }
        let succeeded = await layoutStore.saveLayout(folderId: scopeId, items: rows)
        if !succeeded, let origin {
            onRollback?(id, origin)
        }
        return succeeded
    }

    private func snap(_ point: SIMD3<Double>) -> SIMD3<Double> {
        SIMD3<Double>(SpatialNode.snap(point.x), SpatialNode.snap(point.y), SpatialNode.snap(point.z))
    }
}
