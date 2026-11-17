import FicheroAPIClient
import Foundation

/// One model of the tree, as the sidebar reads it: the engine's answer without its generated types.
struct ActivityModelEntry: Equatable, Identifiable, Sendable {
    enum Place: String, CaseIterable, Sendable {
        case thisMac = "this-mac", remote, cloud

        var title: String {
            switch self {
            case .thisMac: "This Mac"
            case .remote: "Remote"
            case .cloud: "Cloud"
            }
        }

        var icon: String {
            switch self {
            case .thisMac: "desktopcomputer"
            case .remote: "server.rack"
            case .cloud: "cloud"
            }
        }
    }

    let id: String
    let name: String
    let place: Place
    let provider: String
    var loaded = false
    var active = false
    var memoryBytes: Int?
    var memoryEstimated = false
    var running = 0
    var pagesToday = 0
    var callsToday = 0

    init(id: String, name: String, place: Place, provider: String, loaded: Bool = false, active: Bool = false,
         memoryBytes: Int? = nil, memoryEstimated: Bool = false, running: Int = 0, pagesToday: Int = 0, callsToday: Int = 0) {
        self.id = id; self.name = name; self.place = place; self.provider = provider; self.loaded = loaded
        self.active = active; self.memoryBytes = memoryBytes; self.memoryEstimated = memoryEstimated
        self.running = running; self.pagesToday = pagesToday; self.callsToday = callsToday
    }

    init(_ model: Components.Schemas.ActivityModel) {
        self.init(id: model.id, name: model.name, place: Place(rawValue: model.place.rawValue) ?? .thisMac,
                  provider: model.provider, loaded: model.loaded, active: model.active, memoryBytes: model.memoryBytes,
                  memoryEstimated: model.memoryEstimated ?? false, running: model.running ?? 0,
                  pagesToday: model.pagesToday ?? 0, callsToday: model.callsToday ?? 0)
    }

    /// "312 MB", "~2.5 GB" when estimated, "—" when nothing measures it (`activity.resources.everything-measured`).
    var memoryWords: String {
        guard let memoryBytes else { return "—" }
        let words = ByteCountFormatter.string(fromByteCount: Int64(memoryBytes), countStyle: .memory)
        return memoryEstimated ? "~\(words)" : words
    }

    /// The icon's symbol: filled while it is loaded, hollow when not (decision 33).
    var symbol: String { loaded ? "cpu.fill" : "cpu" }

    /// Several projects' lists as one: a model in two is one row, loaded or active if either says so, its counts added.
    static func merged(_ lists: [[ActivityModelEntry]]) -> [ActivityModelEntry] {
        var byId: [String: ActivityModelEntry] = [:]
        var order: [String] = []
        for model in lists.joined() {
            guard var seen = byId[model.id] else { byId[model.id] = model; order.append(model.id); continue }
            seen.loaded = seen.loaded || model.loaded
            seen.active = seen.active || model.active
            seen.memoryBytes = seen.memoryBytes ?? model.memoryBytes
            seen.running += model.running
            seen.pagesToday += model.pagesToday
            seen.callsToday += model.callsToday
            byId[model.id] = seen
        }
        return order.compactMap { byId[$0] }
    }

    /// A place work can run, set up whether used or not (owner 2026-11-16): its node under the place, as a
    /// model's provider.
    struct SetUp: Equatable, Hashable, Sendable {
        let place: Place
        let provider: String

        init(place: Place, provider: String) { self.place = place; self.provider = provider }

        init(_ place: Components.Schemas.ActivityPlace) {
            self.init(place: Place(rawValue: place.place.rawValue) ?? .thisMac, provider: place.provider)
        }
    }

    /// The tree: place › provider › its models, places in their order. Every place set up is in it with its
    /// providers, used or not (This Mac always); a place nothing is set up at and nothing ran on is left out. A
    /// place's own name is not a provider under it.
    static func tree(_ models: [ActivityModelEntry], places: [SetUp] = [])
        -> [(place: Place, providers: [(name: String, models: [ActivityModelEntry])])] {
        Place.allCases.compactMap { place in
            let here = models.filter { $0.place == place }
            let setUp = places.filter { $0.place == place }
            guard !here.isEmpty || !setUp.isEmpty else { return nil }
            let names = (here.map(\.provider) + setUp.map(\.provider).filter { $0 != place.title })
                .reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
            return (place, names.map { name in (name, here.filter { $0.provider == name }) })
        }
    }
}

/// The engine's Models answer: the models, and every place set up (`GET /api/activity/models`).
struct ActivityModelsAnswer: Equatable, Sendable {
    var models: [ActivityModelEntry] = []
    var places: [ActivityModelEntry.SetUp] = []

    /// Several projects' answers as one: the models merged, the places once each in the order first seen.
    static func merged(_ answers: [ActivityModelsAnswer]) -> ActivityModelsAnswer {
        let places = answers.flatMap(\.places).reduce(into: [ActivityModelEntry.SetUp]()) {
            if !$0.contains($1) { $0.append($1) }
        }
        return ActivityModelsAnswer(models: ActivityModelEntry.merged(answers.map(\.models)), places: places)
    }
}
