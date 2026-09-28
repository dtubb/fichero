import FicheroAPIClient
import Foundation
import Observation

/// Reading orders through the generated client (`source.editor.reorder`, ruled 2026-09-27, Q5).
/// A plain transport wrapper, like `SegmentService`: no cache -- `ReadingOrderStore` owns the state.
@MainActor
@Observable
final class ReadingOrderService: ReadingOrderTransport {
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    func orders(documentId: String) async throws -> [ReadingOrderSummary] {
        let response = try await client.api.listDocumentOrdersApiReadingOrdersDocumentDocumentIdGet(
            path: .init(documentId: documentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.orders.map {
                ReadingOrderSummary(id: $0.id, name: $0.name, kind: $0.kind, passId: $0.passId)
            }
        case .unprocessableContent:
            throw ReadingOrderError.refused("the engine refused the document id")
        case .undocumented(let status, _):
            throw ReadingOrderError.unexpected(status)
        }
    }

    /// One LEVEL of an order: the top with `parentEntryId` nil, else the entries under that one.
    func entries(orderId: String, parentEntryId: String?) async throws -> [ReadingOrderMove.Entry] {
        let response = try await client.api.listOrderEntriesApiReadingOrdersOrderIdEntriesGet(
            path: .init(orderId: orderId),
            query: .init(parentEntryId: parentEntryId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.entries.map {
                ReadingOrderMove.Entry(
                    entryId: $0.id, segmentId: $0.segmentId, version: $0.version, parentEntryId: $0.parentEntryId
                )
            }
        case .unprocessableContent:
            throw ReadingOrderError.refused("the engine refused the order id")
        case .undocumented(let status, _):
            throw ReadingOrderError.unexpected(status)
        }
    }

    /// The ONE reorder call, by drag or by key; answers the audit id ⌘Z inverts.
    func place(_ place: ReadingOrderMove.Place) async throws -> String? {
        let response = try await client.api.placeInReadingOrderApiReadingOrdersOrderIdPlacePost(
            path: .init(orderId: place.orderId),
            body: .json(.init(
                segmentId: place.segmentId,
                afterEntryId: place.afterEntryId,
                parentEntryId: place.parentEntryId,
                expectedVersion: place.expectedVersion
            ))
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.auditId
        case .unprocessableContent:
            throw ReadingOrderError.refused("the engine refused the move")
        case .undocumented(let status, _):
            // 409: somebody moved it first. Said, never retried with a fresh version, which would
            // overwrite their move with ours.
            throw status == 409 ? ReadingOrderError.movedMeanwhile : ReadingOrderError.unexpected(status)
        }
    }
}

extension ReadingOrderService {
    /// What reads before and after one segment IN ONE NAMED ORDER (`source.order.next-previous`,
    /// #5160). In a flow the next may be on another page.
    func neighbours(orderId: String, segmentId: String) async throws -> ReadingOrderChoice.Neighbours {
        let response = try await client.api.orderNeighboursApiReadingOrdersOrderIdNeighboursGet(
            path: .init(orderId: orderId), query: .init(segmentId: segmentId)
        )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return ReadingOrderChoice.Neighbours(previous: body.previousSegmentId, next: body.nextSegmentId)
        case .unprocessableContent:
            throw ReadingOrderError.refused("the engine refused the segment")
        case .undocumented(let status, _):
            // 404: the segment is not in this order -- no neighbours to go to, said as a refusal.
            throw status == 404 ? ReadingOrderError.refused("this segment is not in the order") : ReadingOrderError.unexpected(status)
        }
    }
}

enum ReadingOrderError: Error, Equatable {
    case refused(String)
    case movedMeanwhile
    case unexpected(Int)
}

struct ReadingOrderSummary: Equatable, Identifiable {
    let id: String
    let name: String
    let kind: String
    /// The pass it orders; a new order is made over the same one (#5160).
    var passId: String?
}

/// What the store needs from the engine -- a protocol so the store is tested without one.
@MainActor
protocol ReadingOrderTransport {
    func orders(documentId: String) async throws -> [ReadingOrderSummary]
    func entries(orderId: String, parentEntryId: String?) async throws -> [ReadingOrderMove.Entry]
    func place(_ place: ReadingOrderMove.Place) async throws -> String?
}
