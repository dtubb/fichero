import FicheroAPIClient
import SwiftUI

/// The alert a refused hand run raises (`ai.cloud.alert-on-hand-run-paths`, #6349): the engine's words, then a button for each
/// fix it offers. After a button that changes a setting the run is sent again; a once button sends it again with that override.
struct CloudRefusalAlert: ViewModifier {
    @Environment(WorkflowExecutionObserver.self) private var observer
    @Environment(AppState.self) private var appState

    func body(content: Content) -> some View {
        content.alert(
            "Fichero stopped this run",
            isPresented: Binding(
                get: { observer.cloudRefusal != nil },
                set: { if !$0 { observer.cloudRefusal = nil } }),
            presenting: observer.cloudRefusal
        ) { prompt in
            ForEach(prompt.choices) { choice in
                Button(choice.title) { Task { await perform(choice.action, for: prompt) } }
            }
            Button("Cancel", role: .cancel) {}
        } message: { prompt in
            Text(prompt.refusal.words)
        }
    }

    private func perform(_ action: CloudRefusalPrompt.Action, for prompt: CloudRefusalPrompt) async {
        switch action {
        case .allowEverywhere:
            let places = AppPlacesStore(client: appState.ficheroClient)
            await places.load()
            await places.set(.cloud, allowed: true)
            prompt.resend(.init())
        case .allowProject:
            let body = Components.Schemas.AllowCloudRequest(allowed: true)
            _ = try? await appState.ficheroClient.api.allowCloudApiRecipesProjectAllowCloudPost(body: .json(body))
            prompt.resend(.init())
        case .runAgain(let once):
            prompt.resend(once)
        case .openSettings:
            appState.openSettings(tab: .aiModels)
        }
    }
}
