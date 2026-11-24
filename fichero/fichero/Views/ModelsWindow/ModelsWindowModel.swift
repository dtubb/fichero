import Foundation

/// The rules of the Models and Cluster window's list, apart from any view (`models.window.is-activitys-shape`,
/// `models.window.needs-you-badge`, `models.window.columns-and-verbs-are-activitys`, #6588): the sidebar's sections, the
/// rows needing you counted and sorted first, and the row's one button.
enum ModelsWindowModel {
    /// The window's scene id: `openWindow(id: ModelsWindowModel.windowID)`.
    static let windowID = "models-cluster"
    /// The scene's title, which the Window menu lists.
    static let windowTitle = "Models & Cluster"

    /// The sidebar's sections: Models (every model, then the found cards), Providers (every provider, local and cloud), then
    /// over the one list This Mac, Places, Work (`models.window.providers-and-models-in-the-sidebar`).
    enum Section: String, CaseIterable, Sendable {
        case models, providers, thisMac, places, work

        var title: String {
            switch self {
            case .models: "Models"
            case .providers: "Providers"
            case .thisMac: "This Mac"
            case .places: "Places"
            case .work: "Work"
            }
        }
    }

    /// A sidebar item: a grouping over the one list.
    enum Item: Hashable, Sendable {
        case allModels, usableNow, bookmarked, found
        case provider(String)
        case thisMac
        case place(ActivityModelEntry.Place)
        case runningNow
        case failedToday

        /// The candidates' list this item shows; nil for an item over the models answer.
        var candidateList: ModelCandidateRules.List? {
            switch self {
            case .usableNow: .usableNow
            case .bookmarked: .bookmarked
            case .found: .found
            default: nil
            }
        }

        var section: Section {
            switch self {
            case .allModels, .usableNow, .bookmarked, .found: .models
            case .provider: .providers
            case .thisMac: .thisMac
            case .place: .places
            case .runningNow, .failedToday: .work
            }
        }

        var title: String {
            switch self {
            case .allModels: "All Models"
            case .provider(let name): name
            case .usableNow: "Usable now"
            case .bookmarked: "Bookmarked"
            case .found: "Found"
            case .thisMac: "This Mac"
            case .place(let place): place.title
            case .runningNow: "Running now"
            case .failedToday: "Failed today"
            }
        }

        var icon: String {
            switch self {
            case .allModels: "cpu"
            case .provider: "shippingbox"
            case .usableNow: "checkmark.circle"
            case .bookmarked: "bookmark"
            case .found: "magnifyingglass"
            case .thisMac: "desktopcomputer"
            case .place(let place): place.icon
            case .runningNow: "play.circle"
            case .failedToday: "exclamationmark.triangle"
            }
        }

        /// The accessibility id's last part: `models.sidebar.<item>`.
        var identifier: String {
            switch self {
            case .allModels: "allModels"
            case .provider(let name): "provider.\(name)"
            case .usableNow: "usableNow"
            case .bookmarked: "bookmarked"
            case .found: "found"
            case .thisMac: "thisMac"
            case .place(let place): "place.\(place.rawValue)"
            case .runningNow: "runningNow"
            case .failedToday: "failedToday"
            }
        }
    }

    /// Every item, by section, in the sidebar's order.
    static let items: [(section: Section, items: [Item])] = [
        (.models, [.allModels, .usableNow, .bookmarked, .found]),
        (.thisMac, [.thisMac]),
        (.places, [.place(.remote), .place(.cloud)]),
        (.work, [.runningNow, .failedToday])
    ]

    /// One drawn sidebar item: the item, its words and the count of its rows needing you.
    struct SidebarEntry: Equatable {
        let item: Item
        let title: String
        let icon: String
        let badge: Int
    }

    /// The sidebar over the one list: each section's items with their badges, the Providers section after Models with one
    /// item per provider the list names (local runtimes first, then cloud, each by name).
    static func sidebar(_ models: [ActivityModelEntry]) -> [(section: Section, entries: [SidebarEntry])] {
        var result: [(section: Section, entries: [SidebarEntry])] = []
        for group in items {
            result.append((section: group.section, entries: group.items.map {
                SidebarEntry(item: $0, title: $0.title, icon: $0.icon, badge: badge($0, in: models))
            }))
            if group.section == .models {
                let entries = providers(in: models).map {
                    SidebarEntry(item: .provider($0), title: $0, icon: Item.provider($0).icon, badge: badge(.provider($0), in: models))
                }
                result.append((section: .providers, entries: entries))
            }
        }
        return result
    }

    /// Every provider the one list names, This Mac's first, then remote, then cloud, each place's by name.
    static func providers(in models: [ActivityModelEntry]) -> [String] {
        let order = Dictionary(uniqueKeysWithValues: ActivityModelEntry.Place.allCases.enumerated().map { ($1, $0) })
        var best: [String: Int] = [:]
        for model in models { best[model.provider] = min(best[model.provider] ?? .max, order[model.place] ?? .max) }
        return best.keys.sorted { (best[$0]!, $0.lowercased()) < (best[$1]!, $1.lowercased()) }
    }

    /// The rows whose name, provider or licence holds the query, ignoring case and accents; every row for an empty query
    /// (`models.search.over-every-model`).
    static func search(_ rows: [ActivityModelEntry], query: String) -> [ActivityModelEntry] {
        let words = query.split(separator: " ").map(String.init)
        guard !words.isEmpty else { return rows }
        return rows.filter { row in
            let text = [row.name, row.provider, row.place.title, row.licence ?? ""].joined(separator: " ")
            return words.allSatisfy { text.range(of: $0, options: [.caseInsensitive, .diacriticInsensitive]) != nil }
        }
    }

    /// The rows an item groups: This Mac's models, a place's, what is in flight now, what failed today.
    static func rows(_ item: Item, in models: [ActivityModelEntry]) -> [ActivityModelEntry] {
        let rows: [ActivityModelEntry]
        switch item {
        case .usableNow, .bookmarked, .found: rows = []  // drawn from the candidates, not the models answer
        case .allModels: rows = models
        case .provider(let name): rows = models.filter { $0.provider == name }
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
    /// state verb (Unload on a loaded model, Delete on an installed one); nil when there is nothing to press.
    static func button(for row: ActivityModelEntry) -> String? {
        if let failure = row.lastFailed {
            return fixWords(failure.button) ?? (row.loaded ? "Unload" : nil)
        }
        if row.account == .needsKey { return "Add Key…" }
        if row.loaded { return "Unload" }
        return row.modelType != nil && row.modelId != nil ? "Delete" : nil
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

    /// A place's state: the probe's answer for the provider, `unknown` when no row of it carries one
    /// (`ai.where.place-status-is-probed`); never worked out from a key alone.
    enum PlaceStatus: Equatable, Sendable {
        case ready, needsKey, notReachable, unknown
    }

    /// The probed state of a provider or place: its worst account among the rows listed under it.
    static func placeStatus(provider: String, in models: [ActivityModelEntry]) -> PlaceStatus {
        let accounts = models.filter { $0.provider == provider }.compactMap(\.account)
        if accounts.contains(.notReachable) { return .notReachable }
        if accounts.contains(.needsKey) { return .needsKey }
        return accounts.isEmpty ? .unknown : .ready
    }

    /// The row the Inspector shows: the selected id among the item's listed rows; nil when none is selected or it is not listed.
    static func selectedRow(_ id: ActivityModelEntry.ID?, in rows: [ActivityModelEntry]) -> ActivityModelEntry? {
        id.flatMap { id in rows.first { $0.id == id } }
    }

    /// One labelled line of the Inspector.
    struct InspectorLine: Equatable, Sendable {
        let label: String
        let value: String
    }

    /// The Inspector's lines for a selected row (`models.window.is-activitys-shape`): what the one list says of it, "—" where
    /// nothing measures it.
    static func inspectorLines(for row: ActivityModelEntry) -> [InspectorLine] {
        [
            InspectorLine(label: "Name", value: row.name),
            InspectorLine(label: "Where", value: row.provider),
            InspectorLine(label: "Runs on", value: row.place.title),
            InspectorLine(label: "Cost", value: row.costWords),
            InspectorLine(label: "Size", value: row.sizeWords),
            InspectorLine(label: "Fits here", value: row.fitsWords),
            InspectorLine(label: "Account", value: row.accountWords),
            InspectorLine(label: "Using now", value: row.usingNow.isEmpty ? "—" : row.usingNow.joined(separator: ", ")),
            InspectorLine(label: "Last failed", value: row.lastFailed?.words ?? "—")
        ]
    }
}
