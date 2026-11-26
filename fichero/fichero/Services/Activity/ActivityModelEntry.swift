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
    /// The columns of the Models and Cluster window (`models.window.one-list`): nil where nothing measures them.
    var sizeBytes: Int?
    var licence: String?
    var fitsHere: FitsHere?
    var fitsNote: String?
    var unloadToFit: [String] = []
    var account: Account?
    var usingNow: [String] = []
    var lastFailed: Failure?
    /// An installed model's address in the local-models routes (`models.manage.*`): nil for a model that is not installed.
    var modelType: String?
    var modelId: String?

    /// Whether a model fits this Mac now (`models.row.fits-here`), from the engine's one memory rule.
    enum FitsHere: String, Sendable {
        case yes, tight, wontFit = "no"
    }

    /// A place's account, from a probe or the key a call uses (`models.row.account-from-a-probe`).
    enum Account: String, Sendable {
        case ready, needsKey = "needs-key", notReachable = "not-reachable"

        var words: String {
            switch self {
            case .ready: "Ready"
            case .needsKey: "Needs key"
            case .notReachable: "Not reachable"
            }
        }
    }

    /// The newest failure on a model today: the row's words and the button of its fix (`models.row.using-now-and-last-failed`).
    struct Failure: Equatable, Sendable {
        let words: String
        var kind: String?
        var button: String?
    }

    init(id: String, name: String, place: Place, provider: String, loaded: Bool = false, active: Bool = false,
         memoryBytes: Int? = nil, memoryEstimated: Bool = false, running: Int = 0, pagesToday: Int = 0, callsToday: Int = 0,
         sizeBytes: Int? = nil, licence: String? = nil, fitsHere: FitsHere? = nil, fitsNote: String? = nil,
         unloadToFit: [String] = [], account: Account? = nil, usingNow: [String] = [], lastFailed: Failure? = nil,
         modelType: String? = nil, modelId: String? = nil) {
        self.id = id; self.name = name; self.place = place; self.provider = provider; self.loaded = loaded
        self.active = active; self.memoryBytes = memoryBytes; self.memoryEstimated = memoryEstimated
        self.running = running; self.pagesToday = pagesToday; self.callsToday = callsToday
        self.sizeBytes = sizeBytes; self.licence = licence; self.fitsHere = fitsHere; self.fitsNote = fitsNote
        self.unloadToFit = unloadToFit; self.account = account; self.usingNow = usingNow; self.lastFailed = lastFailed
        self.modelType = modelType; self.modelId = modelId
    }

    init(_ model: Components.Schemas.ActivityModel) {
        self.init(id: model.id, name: model.name, place: Place(rawValue: model.place.rawValue) ?? .thisMac,
                  provider: model.provider, loaded: model.loaded, active: model.active, memoryBytes: model.memoryBytes,
                  memoryEstimated: model.memoryEstimated ?? false, running: model.running ?? 0,
                  pagesToday: model.pagesToday ?? 0, callsToday: model.callsToday ?? 0, sizeBytes: model.sizeBytes,
                  licence: model.licence, fitsHere: model.fitsHere.flatMap { FitsHere(rawValue: $0.rawValue) },
                  fitsNote: model.fitsNote, unloadToFit: model.unloadToFit ?? [],
                  account: model.account.flatMap { Account(rawValue: $0.rawValue) }, usingNow: model.usingNow ?? [],
                  lastFailed: model.lastFailed.map { Failure(words: $0.words, kind: $0.kind, button: $0.button) },
                  modelType: model.modelType, modelId: model.modelId)
    }

    /// "2.1 GB", or "—" when nothing measures it.
    var sizeWords: String {
        guard let sizeBytes else { return "—" }
        return ByteCountFormatter.string(fromByteCount: Int64(sizeBytes), countStyle: .file)
    }

    /// "Yes" · "Tight" · "No" with what to unload, "—" when nothing sizes the model (`models.row.fits-here`).
    var fitsWords: String {
        switch fitsHere {
        case .yes: "Yes"
        case .tight: "Tight"
        case .wontFit: unloadToFit.isEmpty ? "No" : "No (unload \(unloadToFit.joined(separator: ", ")))"
        case nil: "—"
        }
    }

    /// What a call costs the person: a model on this Mac costs no money; a cloud or remote model's price is not in the
    /// answer yet, so "—" (never 0).
    var costWords: String { place == .thisMac ? "None (runs on this Mac)" : "—" }

    /// The Account column: the probe's word, "—" where nothing probes.
    var accountWords: String { account?.words ?? "—" }

    /// Whether this row needs the person: its newest failure today, or an account that is not ready.
    var needsYou: Bool { lastFailed != nil || account == .needsKey || account == .notReachable }

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
            seen.sizeBytes = seen.sizeBytes ?? model.sizeBytes
            seen.fitsHere = seen.fitsHere ?? model.fitsHere
            seen.account = seen.account ?? model.account
            seen.lastFailed = seen.lastFailed ?? model.lastFailed
            for kind in model.usingNow where !seen.usingNow.contains(kind) { seen.usingNow.append(kind) }
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
