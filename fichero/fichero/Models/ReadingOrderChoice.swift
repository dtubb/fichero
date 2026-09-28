import Foundation

/// Choosing among a page's orders, making a new one, and stepping through one (#5160;
/// `source.order.named-multiple`, `source.order.next-previous`, `source.segment.flow`). Pure: the
/// rules live where a test can reach them; the picker (`ReadingOrderPicker`) sends them.
enum ReadingOrderChoice {
    /// What a new order is: a named reading of this page, or a flow that may continue onto others.
    enum NewKind: Equatable {
        case named
        case flow

        var engineKind: String { self == .named ? "imposed" : "flow" }
        var title: String { self == .named ? "New Order" : "New Flow" }
    }

    struct Neighbours: Equatable {
        let previous: String?
        let next: String?
    }

    /// The create the picker sends: over the same pass as the order shown, filled with the pass's
    /// segments in page order so it starts as a copy to rearrange -- never an empty order to explain.
    /// Nil for a blank name or when the order shown names no pass.
    static func create(
        _ kind: NewKind, name: String, documentId: String, from shown: ReadingOrderSummary?
    ) -> ReadingOrderCreateRequest? {
        let name = name.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty, let passId = shown?.passId else { return nil }
        return ReadingOrderCreateRequest(
            documentId: documentId, passId: passId, name: name, kind: kind.engineKind, seedFromPass: true
        )
    }

    /// The order a create just made: the one with its name that was not there before.
    static func made(named name: String, before: [ReadingOrderSummary], after: [ReadingOrderSummary]) -> ReadingOrderSummary? {
        let known = Set(before.map(\.id))
        return after.first { $0.name == name.trimmingCharacters(in: .whitespaces) && !known.contains($0.id) }
    }

    /// Where a step lands: on this page (select it), on another page (open that page, then select it),
    /// or nowhere -- the order ends there.
    struct Landing: Equatable {
        let documentId: String
        let segmentId: String
    }

    /// The segment a step goes to, or nil at the order's end.
    static func target(_ neighbours: Neighbours, forward: Bool) -> String? {
        forward ? neighbours.next : neighbours.previous
    }

    /// A flow this page could continue: which, where it ends, and how it relates to this page.
    struct ContinuableFlow: Equatable, Identifiable {
        let order: ReadingOrderSummary
        let lastPageId: String?
        /// "earlier page" (of this source) or "same project".
        let relation: String
        var id: String { order.id }
        var title: String { "\(order.name) (\(relation))" }
    }

    struct FlowsOnto: Equatable {
        var flows: [ContinuableFlow] = []
        /// Flows on pages this reader may not read, left out and counted.
        var withheld = 0
    }

    /// What continuing a flow here places at its end: the page's segments on the shown pass, in the
    /// page's own order (the order the canvas numbers them), each once.
    static func continuation(of segments: [Segment], onPass passId: String) -> [String] {
        segments.filter { $0.passId == passId && !$0.provisional }
            .sorted { ($0.boxIndex ?? .max, $0.id) < ($1.boxIndex ?? .max, $1.id) }
            .map(\.id)
    }

    /// How an order is listed in the picker: its name, and what kind of claim it makes. The page's own
    /// order says where it came from (#5216): the file's, or the layout's (a recogniser's boxes, in the
    /// order it found them).
    static func title(_ order: ReadingOrderSummary) -> String {
        switch order.kind {
        case "as-written": order.provenanceKind == "external_import" ? "Order: As in the File" : "Layout Order"
        case "flow": "\(order.name) (flow)"
        default: order.name
        }
    }

    /// The picker's tooltip for an order: what the title's words mean.
    static func help(_ order: ReadingOrderSummary?) -> String {
        guard let order, order.kind == "as-written" else { return "Which reading order the list shows" }
        return order.provenanceKind == "external_import"
            ? "The reading order the imported file gives, kept as it came"
            : "The order the layout found the segments in; no file gave one"
    }
}

/// `reading_order.create`.
struct ReadingOrderCreateRequest: Encodable, Equatable {
    let documentId: String
    let passId: String
    let name: String
    let kind: String
    let seedFromPass: Bool

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id", passId = "pass_id", name, kind, seedFromPass = "seed_from_pass"
    }
}
