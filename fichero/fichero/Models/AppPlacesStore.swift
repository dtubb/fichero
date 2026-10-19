import FicheroAPIClient
import Foundation

/// Where models may run, app-wide (`source.onboard.places-cap-projects`, #5828): read from and written to the engine
/// (`GET`/`PUT /api/recipes/places`, an audited action). Nothing is kept here: the engine is the setting.
@MainActor
@Observable
final class AppPlacesStore {
    /// The allowed places, as the engine last said; this Mac only until it answers.
    private(set) var places: Set<String> = [WhereTheWorkRuns.thisMac.rawValue]
    /// The engine's sentence about this Mac's memory and what it can run; nil until it answers.
    private(set) var thisMacLine: String?
    /// Whether the person has answered: until then the engine caps nothing (unset is not "this Mac only").
    private(set) var answered = false
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    func allows(_ place: WhereTheWorkRuns) -> Bool { places.contains(place.rawValue) }

    func load() async {
        do {
            switch try await client.api.getPlacesApiRecipesPlacesGet() {
            case .ok(let success): take(try success.body.json)
            case .undocumented(let code, _): errorMessage = "Could not read where models may run (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read where models may run: \(error.localizedDescription)"
        }
    }

    /// Continue on the screen writes the answer, the default (this Mac only) included, so a fresh install lands at an
    /// answer and an existing one keeps working until its person gets here. False, said, if the engine refused.
    func keepAnswer() async -> Bool {
        // A tick's PUT still in flight is awaited first: Continue never races it.
        while sending { try? await Task.sleep(for: .milliseconds(50)) }
        if answered { return true }
        await set(.thisMac, allowed: true)  // sends the places as shown, this Mac among them
        return answered
    }

    /// What the person last asked for, and whether a PUT is in flight: ticks are sent one at a time and the latest
    /// wins, so two quick ticks cannot race.
    private var wanted: Set<String>?
    private var sending = false

    /// Allow or stop allowing one place; the engine keeps this Mac in, whatever is sent.
    func set(_ place: WhereTheWorkRuns, allowed: Bool) async {
        var next = wanted ?? places
        if allowed { next.insert(place.rawValue) } else { next.remove(place.rawValue) }
        wanted = next
        places = next  // shown at once; the engine's answer replaces it
        guard !sending else { return }
        sending = true
        defer { sending = false }
        var failed = false
        while let sendNow = wanted {
            wanted = nil
            do {
                let body = Components.Schemas.PlacesSetting(
                    places: WhereTheWorkRuns.allCases.map(\.rawValue).filter(sendNow.contains))
                switch try await client.api.putPlacesApiRecipesPlacesPut(body: .json(body)) {
                case .ok(let success): if wanted == nil { take(try success.body.json) }
                case .unprocessableContent(let error):
                    errorMessage = (try? error.body.json)?.detail ?? "That place was refused."
                    failed = true
                case .undocumented(let code, _):
                    errorMessage = "Could not change where models may run (HTTP \(code))"
                    failed = true
                }
            } catch {
                if error.isCancellationError { return }
                errorMessage = "Could not change where models may run: \(error.localizedDescription)"
                failed = true
            }
        }
        // The ticks show what the engine holds, not what was asked for.
        if failed { await load() }
    }

    private func take(_ view: Components.Schemas.PlacesView) {
        places = Set(view.places)
        answered = view.answered
        thisMacLine = view.thisMac
    }
}
