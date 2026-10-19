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

    /// Allow or stop allowing one place; the engine keeps this Mac in, whatever is sent.
    func set(_ place: WhereTheWorkRuns, allowed: Bool) async {
        var next = places
        if allowed { next.insert(place.rawValue) } else { next.remove(place.rawValue) }
        do {
            let body = Components.Schemas.PlacesSetting(places: WhereTheWorkRuns.allCases.map(\.rawValue).filter(next.contains))
            switch try await client.api.putPlacesApiRecipesPlacesPut(body: .json(body)) {
            case .ok(let success): take(try success.body.json)
            case .unprocessableContent(let error):
                errorMessage = (try? error.body.json)?.detail ?? "That place was refused."
            case .undocumented(let code, _): errorMessage = "Could not change where models may run (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not change where models may run: \(error.localizedDescription)"
        }
    }

    private func take(_ view: Components.Schemas.PlacesView) {
        places = Set(view.places)
        thisMacLine = view.thisMac
    }
}
