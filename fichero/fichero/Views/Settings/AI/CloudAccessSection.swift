import SwiftUI

/// The app-wide cloud switch in Settings (`source.onboard.places-cap-projects`): the same engine setting as Set Up
/// Fichero's "A cloud AI service" tick (`AppPlacesStore`, `PUT /api/recipes/places`). Off caps every project; on lets
/// each project's own yes (Set Up) send its pages.
struct CloudAccessSection: View {
    @Environment(AppState.self) private var appState
    @State private var places: AppPlacesStore?

    var body: some View {
        Section("Cloud") {
            if let places {
                Toggle("Allow cloud AI services", isOn: Binding(
                    get: { places.allows(.cloud) },
                    set: { allowed in Task { await places.set(.cloud, allowed: allowed) } }))
                    .accessibilityIdentifier("settings.ai.cloudAllowed")
                if let message = places.errorMessage {
                    Text(message).font(.caption).foregroundStyle(.red)
                }
            }
            Text("Off: no project's pages leave this Mac. On: each project still asks in Set Up.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .task {
            if places == nil { places = AppPlacesStore(client: appState.ficheroClient) }
            await places?.load()
        }
    }
}
