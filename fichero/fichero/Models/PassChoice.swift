import Foundation

/// Which pass a page shows (#6670, `source.editor.pass-shown-is-picked`): the one a person picked in the
/// Source's or the Reader's Pass menu, else the engine's working pass. Picking shows a pass without promoting
/// it; promoting (`pass.choose_working`) stays the way to set the default.
enum PassChoice {
    /// One row of the Pass menu.
    struct Item: Equatable, Identifiable {
        let id: String
        let title: String
        let isShown: Bool
    }

    /// The pass shown: the picked one while the page still has it, else the working pass.
    static func shown(passes: [SegmentPassValue], pickedId: String?) -> SegmentPassValue? {
        if let pickedId, let picked = passes.first(where: { $0.id == pickedId }) { return picked }
        return passes.first(where: \.working)
    }

    /// The page's passes a person can pick between: every pass with text (a georeferencing pass places the
    /// page and has none), the working pass first, then the engine's ranking. Titled with the time as well as the
    /// day: three runs of one model on one day are three passes a person must tell apart.
    static func items(
        passes: [SegmentPassValue], pickedId: String?,
        format: Date.FormatStyle = .dateTime.month(.abbreviated).day().hour().minute()
    ) -> [Item] {
        let shownId = shown(passes: passes, pickedId: pickedId)?.id
        let ranked = passes.filter { !$0.isGeoreferencing }.enumerated().sorted { lhs, rhs in
            switch (lhs.element.rank, rhs.element.rank) {
            case let (left?, right?) where left != right: return left < right
            case (.some, nil): return true
            case (nil, .some): return false
            default: return lhs.offset < rhs.offset
            }
        }.map(\.element)
        return ranked.map { pass in
            let label = ReadingOrderChoice.passLabel(pass, format: format)
            let mark = pass.working ? (pass.workingBasis == "chosen" ? " · promoted" : " · default") : ""
            return Item(id: pass.id, title: label + mark, isShown: pass.id == shownId)
        }
    }

    /// The menu's own label: the shown pass's title, so the head says which pass is on the page.
    static func shownTitle(
        passes: [SegmentPassValue], pickedId: String?,
        format: Date.FormatStyle = .dateTime.month(.abbreviated).day().hour().minute()
    ) -> String? {
        items(passes: passes, pickedId: pickedId, format: format).first(where: \.isShown)?.title
    }

    /// The menu is offered only where there is a choice to make.
    static func offersChoice(_ passes: [SegmentPassValue]) -> Bool {
        passes.filter { !$0.isGeoreferencing }.count > 1
    }
}
