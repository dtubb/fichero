import FicheroAPIClient
import SwiftUI

/// "Tries" in the document Inspector, under What has been run: a try's readings and lines on this page, each headed as a try's with its day
/// and model, never counted as the project's and never shown as a run's (`wide.try.shown-outside-set-up`, 10.1). Nothing when no try kept
/// readings for the page. The same store and list as the reader's Tries popover.
struct InspectorTriesSection: View {
    let pageId: String
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @State private var store: TryLabelStore?

    var body: some View {
        InspectorTriesList(tries: store?.tries ?? [])
            .task(id: pageId) {
                guard FeatureManager.shared.isWideSetUpEnabled, let client = actionStore?.actionsService.client else { return }
                let made = TryLabelStore(client: client, pageId: pageId)
                store = made
                await made.load()
            }
    }
}

/// The section's body, given the tries: nothing for none.
struct InspectorTriesList: View {
    let tries: [TryLabel]

    var body: some View {
        if !tries.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("Tries").font(.headline)
                TryLabelList(tries: tries)
            }
            .accessibilityIdentifier("inspector.tries")
        }
    }
}

#Preview("A try on a page") {
    InspectorTriesList(tries: [TryLabel(stage: "read", ranAt: Date(), model: "gemini-pro", lines: ["hola", "adiós"])]).padding()
}
