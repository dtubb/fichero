#if DEBUG

/// A page of three regions, the middle one holding three lines, as the engine would list them.
@MainActor
final class PreviewOrderTransport: ReadingOrderTransport {
    func orders(documentId: String) async throws -> [ReadingOrderSummary] {
        [.init(id: "o1", name: "as-written", kind: "as-written")]
    }
    func entries(orderId: String, parentEntryId: String?) async throws -> [ReadingOrderMove.Entry] {
        parentEntryId == nil
            ? ["heading", "body", "marginal note"].map { .init(entryId: "e-\($0)", segmentId: $0, version: 1) }
            : ["line 1", "line 2", "line 3"].map {
                .init(entryId: "e-\($0)", segmentId: $0, version: 1, parentEntryId: parentEntryId)
            }
    }
    func place(_ place: ReadingOrderMove.Place) async throws -> String? { "preview-audit" }
}

#Preview("A block's lines") {
    ReadingOrderList(
        documentId: "page-1", parentSegmentId: "body", store: ReadingOrderStore(transport: PreviewOrderTransport())
    )
    .frame(width: 320, height: 260)
}
#endif
