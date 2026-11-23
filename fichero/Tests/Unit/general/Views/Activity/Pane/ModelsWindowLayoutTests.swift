@testable import Fichero
import Foundation
import Testing

/// `models.window.is-activitys-shape`, `models.window.needs-you-badge`, `models.window.columns-and-verbs-are-activitys`
/// (#6588): the sidebar's three sections over the one list, the rows needing you first and counted, the row's one button.
struct ModelsWindowLayoutTests {
    private let kraken = ActivityModelEntry(id: "this-mac|Kraken|blla", name: "blla", place: .thisMac, provider: "Kraken",
                                            loaded: true, active: true, usingNow: ["kraken-lines"])
    private let broken = ActivityModelEntry(id: "this-mac|MLX|chandra", name: "chandra", place: .thisMac, provider: "MLX",
                                            lastFailed: .init(words: "Model failed to load", kind: "model-broken",
                                                              button: "retry"))
    private let idle = ActivityModelEntry(id: "this-mac|MLX|small", name: "small", place: .thisMac, provider: "MLX")
    private let keyless = ActivityModelEntry(id: "cloud|Anthropic|claude", name: "claude", place: .cloud,
                                             provider: "Anthropic", account: .needsKey)

    @Test("the sidebar has three sections, This Mac, Places and Work, each item in the section it belongs to")
    func sections() {
        #expect(ModelsWindowModel.items.map(\.section) == [.thisMac, .places, .work])
        #expect(ModelsWindowModel.Section.allCases.map(\.title) == ["This Mac", "Places", "Work"])
        for entry in ModelsWindowModel.items {
            #expect(entry.items.allSatisfy { $0.section == entry.section })
        }
    }

    @Test("an item groups the one list; Work lists what is running and what failed")
    func grouping() {
        let all = [kraken, idle, broken, keyless]
        #expect(ModelsWindowModel.rows(.thisMac, in: all).map(\.name) == ["chandra", "blla", "small"])
        #expect(ModelsWindowModel.rows(.place(.cloud), in: all).map(\.name) == ["claude"])
        #expect(ModelsWindowModel.rows(.runningNow, in: all).map(\.name) == ["blla"])
        #expect(ModelsWindowModel.rows(.failedToday, in: all).map(\.name) == ["chandra"])
    }

    @Test("the badge counts the rows needing you: a failure today, a missing key, a place not reachable")
    func badge() {
        let down = ActivityModelEntry(id: "remote|studio|llama", name: "llama", place: .remote, provider: "studio",
                                      account: .notReachable)
        let all = [kraken, idle, broken, keyless, down]
        #expect(ModelsWindowModel.badge(.thisMac, in: all) == 1)
        #expect(ModelsWindowModel.badge(.place(.cloud), in: all) == 1)
        #expect(ModelsWindowModel.badge(.place(.remote), in: all) == 1)
        #expect(ModelsWindowModel.badge(.runningNow, in: all) == 0)
    }

    @Test("the one button is the fix of the newest failure, else Add Key… on a keyless place, else Unload on a loaded model")
    func button() {
        #expect(ModelsWindowModel.button(for: broken) == "Retry")
        #expect(ModelsWindowModel.button(for: keyless) == "Add Key…")
        #expect(ModelsWindowModel.button(for: kraken) == "Unload")
        #expect(ModelsWindowModel.button(for: idle) == nil)
    }

    @Test("the columns the engine now answers read in words, and \"—\" for what nothing measures")
    func columns() {
        #expect(idle.sizeWords == "—" && idle.fitsWords == "—" && idle.accountWords == "—")
        let sized = ActivityModelEntry(id: "x", name: "x", place: .thisMac, provider: "MLX", sizeBytes: 2_000_000_000,
                                       fitsHere: .wontFit, unloadToFit: ["nomic"], account: .ready)
        #expect(sized.sizeWords == "2 GB")
        #expect(sized.fitsWords == "No (unload nomic)")
        #expect(sized.accountWords == "Ready")
    }

    @Test("a place's dot is its probe's answer, never the key alone; a place nobody probed is unknown, not green")
    func placeStatusIsProbed() {
        let down = ActivityModelEntry(id: "remote|studio|llama", name: "llama", place: .remote, provider: "studio",
                                      account: .notReachable)
        let up = ActivityModelEntry(id: "cloud|OpenAI|gpt", name: "gpt", place: .cloud, provider: "OpenAI", account: .ready)
        let all = [down, up, keyless, idle]
        #expect(ModelsWindowModel.placeStatus(provider: "studio", in: all) == .notReachable)
        #expect(ModelsWindowModel.placeStatus(provider: "OpenAI", in: all) == .ready)
        #expect(ModelsWindowModel.placeStatus(provider: "Anthropic", in: all) == .needsKey)
        #expect(ModelsWindowModel.placeStatus(provider: "MLX", in: all) == .unknown)
        #expect(ModelsWindowModel.placeStatus(provider: "nowhere", in: all) == .unknown)
    }

    @Test("the Inspector says a model's size, fits-here, account, what is using it and its newest failure; '—' where nothing measures")
    func inspectorLines() {
        let lines = ModelsWindowModel.inspectorLines(for: broken)
        #expect(lines.map(\.label) == ["Name", "Where", "Size", "Fits here", "Account", "Using now", "Last failed"])
        #expect(lines.first { $0.label == "Size" }?.value == "—")
        #expect(lines.first { $0.label == "Last failed" }?.value == "Model failed to load")
        #expect(ModelsWindowModel.inspectorLines(for: kraken).first { $0.label == "Using now" }?.value == "kraken-lines")
    }
}
