import Foundation

/// The rules of the Models and Cluster window's list, apart from any view (`models.window.is-activitys-shape`,
/// `models.window.needs-you-badge`, `models.window.columns-and-verbs-are-activitys`, #6588): the sidebar's sections, the
/// rows needing you counted and sorted first, and the row's one button.
enum ModelsWindowModel {
    /// The sidebar's sections over the one list: This Mac, Places, Work.
    enum Section: String, CaseIterable, Sendable {
        case thisMac, places, work

        var title: String {
            switch self {
            case .thisMac: "This Mac"
            case .places: "Places"
            case .work: "Work"
            }
        }
    }

    /// A sidebar item: a grouping over the one list.
    enum Item: Hashable, Sendable {
        case thisMac
        case place(ActivityModelEntry.Place)
        case runningNow
        case failedToday

        var section: Section {
            switch self {
            case .thisMac: .thisMac
            case .place: .places
            case .runningNow, .failedToday: .work
            }
        }

        /// The accessibility id's last part: `models.sidebar.<item>`.
        var identifier: String {
            switch self {
            case .thisMac: "thisMac"
            case .place(let place): "place.\(place.rawValue)"
            case .runningNow: "runningNow"
            case .failedToday: "failedToday"
            }
        }
    }

    /// Every item, by section, in the sidebar's order.
    static let items: [(section: Section, items: [Item])] = [
        (.thisMac, [.thisMac]),
        (.places, [.place(.remote), .place(.cloud)]),
        (.work, [.runningNow, .failedToday])
    ]

    /// The rows an item groups: This Mac's models, a place's, what is in flight now, what failed today.
    static func rows(_ item: Item, in models: [ActivityModelEntry]) -> [ActivityModelEntry] {
        let rows: [ActivityModelEntry]
        switch item {
        case .thisMac: rows = models.filter { $0.place == .thisMac }
        case .place(let place): rows = models.filter { $0.place == place }
        case .runningNow: rows = models.filter { $0.active || !$0.usingNow.isEmpty }
        case .failedToday: rows = models.filter { $0.lastFailed != nil }
        }
        return needsYouFirst(rows)
    }

    /// The rows needing the person, counted for the item's badge.
    static func badge(_ item: Item, in models: [ActivityModelEntry]) -> Int {
        rows(item, in: models).filter(\.needsYou).count
    }

    /// Rows needing you first; the engine's order kept within each half.
    static func needsYouFirst(_ rows: [ActivityModelEntry]) -> [ActivityModelEntry] {
        rows.filter(\.needsYou) + rows.filter { !$0.needsYou }
    }

    /// The row's one button (`activity.pane.fix-button-has-words`): the fix of its newest failure when it has one, else its
    /// state verb (Unload on a loaded model); nil when there is nothing to press.
    static func button(for row: ActivityModelEntry) -> String? {
        if let failure = row.lastFailed {
            return fixWords(failure.button) ?? (row.loaded ? "Unload" : nil)
        }
        if row.account == .needsKey { return "Add Key…" }
        return row.loaded ? "Unload" : nil
    }

    /// A failure's first action in the verbs' words; nil for an action the window has no word for.
    static func fixWords(_ action: String?) -> String? {
        switch action {
        case "retry", "resume": "Retry"
        case "open-settings": "Open Settings"
        case "choose-model": "Choose a Model"
        case "reconnect": "Reconnect"
        default: nil
        }
    }
}
