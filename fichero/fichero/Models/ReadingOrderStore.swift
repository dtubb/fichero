import Foundation
import Observation

/// One document's reading order, as the Reader and the Inspector list it (ruled 2026-09-27, Q5:
/// reorder in all three places, by drag and by keys, ONE implementation). Every list reads this
/// store and every move goes through `move(_:to:)` or `move(_:step:)`, which turn into the one
/// `reading_order.place` through `ReadingOrderMove`. Never three copies of the rule.
///
/// A move updates ONE row in place (its position and version), never a reload of the list.
@MainActor
@Observable
final class ReadingOrderStore {
    private let transport: ReadingOrderTransport
    private(set) var documentId: String?
    private(set) var orders: [ReadingOrderSummary] = []
    private(set) var orderId: String?
    /// The top level of the chosen order, in reading sequence.
    private(set) var entries: [ReadingOrderMove.Entry] = []
    /// Levels below the top (a block's lines), keyed by their parent entry, read when a move names
    /// a segment that is not at the top -- the Reader's caret is on a LINE.
    private var levels: [String: [ReadingOrderMove.Entry]] = [:]
    /// Why the last move did not happen, for the list to say; nil after a move that did.
    private(set) var lastRefusal: String?

    init(transport: ReadingOrderTransport) {
        self.transport = transport
    }

    /// Load a document's orders and show `preferred` (the file's own order, by default) or the first.
    func load(documentId: String, preferred name: String = "as-written") async throws {
        self.documentId = documentId
        orders = try await transport.orders(documentId: documentId)
        orderId = (orders.first { $0.name == name } ?? orders.first)?.id
        levels = [:]
        if let orderId {
            entries = try await transport.entries(orderId: orderId, parentEntryId: nil)
        } else {
            entries = []
        }
    }

    /// A DRAG: `segmentId` to occupy `index` in the final list. Answers the audit id for ⌘Z.
    @discardableResult
    func move(_ segmentId: String, to index: Int) async -> String? {
        guard let orderId else { return nil }
        return await perform(ReadingOrderMove.place(orderId: orderId, entries: entries, moving: segmentId, to: index))
    }

    /// A KEY: one place up or down, or to the start or end, within the segment's OWN level (a line
    /// among its block's lines). The same call as a drag, from the Inspector or the Reader.
    @discardableResult
    func move(_ segmentId: String, step: ReadingOrderMove.Step) async -> String? {
        guard let orderId else { return nil }
        guard let level = await level(holding: segmentId) else {
            lastRefusal = String(describing: ReadingOrderMove.Refusal.notInThisOrder)
            return nil
        }
        return await perform(ReadingOrderMove.place(orderId: orderId, entries: level, moving: segmentId, step: step))
    }

    /// The level that holds `segmentId`: the top, a level already read, or the first block whose
    /// lines hold it.
    private func level(holding segmentId: String) async -> [ReadingOrderMove.Entry]? {
        // ponytail: one read per block until found (then kept), and two levels deep -- lines under
        // blocks, which is what the Reader moves. A parent id on the neighbours answer makes it one read.
        if entries.contains(where: { $0.segmentId == segmentId }) { return entries }
        if let known = levels.values.first(where: { $0.contains { $0.segmentId == segmentId } }) { return known }
        guard let orderId else { return nil }
        for parent in entries where levels[parent.entryId] == nil {
            guard let children = try? await transport.entries(orderId: orderId, parentEntryId: parent.entryId) else {
                continue
            }
            levels[parent.entryId] = children
            if children.contains(where: { $0.segmentId == segmentId }) { return children }
        }
        return nil
    }

    private func perform(_ planned: Result<ReadingOrderMove.Place, ReadingOrderMove.Refusal>) async -> String? {
        switch planned {
        case .failure(let refusal):
            // Nothing is sent: a move to where it already is would write an action that did nothing.
            lastRefusal = String(describing: refusal)
            return nil
        case .success(let place):
            do {
                let auditId = try await transport.place(place)
                apply(place)
                lastRefusal = nil
                return auditId
            } catch {
                lastRefusal = String(describing: error)
                return nil
            }
        }
    }

    /// Re-read the chosen order's entries -- after ⌘Z or ⇧⌘Z, when the engine put a row back and
    /// the local sequence no longer says where it is. One level of one order, not the page.
    func reloadEntries() async {
        guard let orderId else { return }
        levels = [:]
        if let fresh = try? await transport.entries(orderId: orderId, parentEntryId: nil) { entries = fresh }
    }

    /// ⌘Z for a move, through the app's `UndoManager` (`ActionUndo`): the engine inverts the audit
    /// row, and the list re-reads the order so it shows where the row went back to.
    /// `afterUndo` is for a surface that shows the order some other way -- the Reader's text.
    func registerUndo(
        auditId: String?, undoManager: UndoManager?, actionsService: ActionsService?,
        afterUndo: @escaping @MainActor () -> Void = {}
    ) {
        guard let actionsService else { return }
        ActionUndo.register(
            auditId: auditId,
            actionName: "Move in Reading Order",
            undoManager: undoManager,
            performUndo: { [weak self] auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await self?.reloadEntries()
                afterUndo()
                return next
            }
        )
    }

    /// The engine's answer, applied to the one moved row: it now follows `afterEntryId`, and its
    /// version went up by one, as the engine's did.
    private func apply(_ place: ReadingOrderMove.Place) {
        guard let parent = place.parentEntryId else { return Self.apply(place, to: &entries) }
        guard var level = levels[parent] else { return }
        Self.apply(place, to: &level)
        levels[parent] = level
    }

    private static func apply(_ place: ReadingOrderMove.Place, to level: inout [ReadingOrderMove.Entry]) {
        guard let from = level.firstIndex(where: { $0.segmentId == place.segmentId }) else { return }
        var moved = level.remove(at: from)
        let target = place.afterEntryId.flatMap { after in level.firstIndex { $0.entryId == after } }
            .map { $0 + 1 } ?? 0
        moved = ReadingOrderMove.Entry(
            entryId: moved.entryId, segmentId: moved.segmentId, version: moved.version + 1,
            parentEntryId: moved.parentEntryId
        )
        level.insert(moved, at: target)
    }
}
