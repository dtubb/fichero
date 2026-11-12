import Foundation

/// A page with two passes has two Layout Orders (#6421, `source.editor.orders.say-where-they-came-from`): the picker lists
/// the working pass's orders first, then the others under "From other passes", each titled with the pass that made it.
extension ReadingOrderChoice {
    struct PickerItem: Equatable, Identifiable {
        let id: String
        let title: String
    }

    struct PickerSections: Equatable {
        /// The working pass's orders (every order, when the working pass is not known).
        let thisPass: [PickerItem]
        /// Orders over the page's other passes, titled with their pass.
        let otherPasses: [PickerItem]

        /// The title of the order with this id, wherever it is listed.
        func title(of id: String?) -> String? { (thisPass + otherPasses).first { $0.id == id }?.title }
    }

    static func sections(
        _ orders: [ReadingOrderSummary], workingPassId: String?, passes: [SegmentPassValue],
        format: Date.FormatStyle = .dateTime.month(.abbreviated).day()
    ) -> PickerSections {
        let byId = Dictionary(passes.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let isThisPass = { (order: ReadingOrderSummary) in
            workingPassId == nil || order.passId == nil || order.passId == workingPassId
        }
        let others = orders.filter { !isThisPass($0) }
        let thisPass = orders.filter(isThisPass).map { order in
            // Two Layout Orders on one page: the working pass's says it is the one shown on the page.
            let shownNote = !others.isEmpty && order.kind == "as-written" ? " · shown on the page" : ""
            return PickerItem(id: order.id, title: title(order) + shownNote)
        }
        let otherItems = others.map { order in
            let pass = order.passId.flatMap { byId[$0] }
            return PickerItem(id: order.id, title: [title(order), pass.map { passLabel($0, format: format) }]
                .compactMap { $0 }.joined(separator: " · "))
        }
        return PickerSections(thisPass: thisPass, otherPasses: otherItems)
    }

    /// Who made a pass and when: "from 0065.xml, Nov 8", "kraken, Nov 8", or its name with no date known.
    static func passLabel(_ pass: SegmentPassValue, format: Date.FormatStyle = .dateTime.month(.abbreviated).day()) -> String {
        let maker = pass.importFile.map { "from \($0)" } ?? pass.model ?? pass.provider ?? pass.name
        guard let made = pass.createdAt else { return maker }
        return "\(maker), \(made.formatted(format))"
    }
}
