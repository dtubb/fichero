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
        entries = try await orderId.map { try await transport.entries(orderId: $0) } ?? []
    }

    /// A DRAG: `segmentId` to occupy `index` in the final list. Answers the audit id for ⌘Z.
    @discardableResult
    func move(_ segmentId: String, to index: Int) async -> String? {
        guard let orderId else { return nil }
        return await perform(ReadingOrderMove.place(orderId: orderId, entries: entries, moving: segmentId, to: index))
    }

    /// A KEY: one place up or down, or to the start or end. The same call as a drag.
    @discardableResult
    func move(_ segmentId: String, step: ReadingOrderMove.Step) async -> String? {
        guard let orderId else { return nil }
        return await perform(ReadingOrderMove.place(orderId: orderId, entries: entries, moving: segmentId, step: step))
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
        if let fresh = try? await transport.entries(orderId: orderId) { entries = fresh }
    }

    /// ⌘Z for a move, through the app's `UndoManager` (`ActionUndo`): the engine inverts the audit
    /// row, and the list re-reads the order so it shows where the row went back to.
    func registerUndo(auditId: String?, undoManager: UndoManager?, actionsService: ActionsService?) {
        guard let actionsService else { return }
        ActionUndo.register(
            auditId: auditId,
            actionName: "Move in Reading Order",
            undoManager: undoManager,
            performUndo: { [weak self] auditId in
                let next = try await actionsService.undoAction(auditId: auditId).auditId
                await self?.reloadEntries()
                return next
            }
        )
    }

    /// The engine's answer, applied to the one moved row: it now follows `afterEntryId`, and its
    /// version went up by one, as the engine's did.
    private func apply(_ place: ReadingOrderMove.Place) {
        guard let from = entries.firstIndex(where: { $0.segmentId == place.segmentId }) else { return }
        let moved = entries.remove(at: from)
        let target = place.afterEntryId.flatMap { after in entries.firstIndex { $0.entryId == after } }
            .map { $0 + 1 } ?? 0
        entries.insert(
            ReadingOrderMove.Entry(entryId: moved.entryId, segmentId: moved.segmentId, version: moved.version + 1),
            at: target
        )
    }
}
