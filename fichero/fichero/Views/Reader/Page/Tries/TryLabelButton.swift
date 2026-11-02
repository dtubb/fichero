import FicheroAPIClient
import SwiftUI

/// "Tries" in the reader's head, shown only while a try kept readings for the page shown: each is headed as a try's with its day and model
/// (`wide.try.shown-outside-set-up`). A popover, so the page itself never mixes a try's words with the project's.
struct TryLabelButton: View {
    let pageId: String
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @State private var store: TryLabelStore?
    @State private var isShowing = false

    init(pageId: String, store: TryLabelStore? = nil) {
        self.pageId = pageId
        _store = State(initialValue: store)
    }

    var body: some View {
        Group {
            if let store, !store.tries.isEmpty {
                Button("Tries") { isShowing.toggle() }
                    .help(TryLabel.note)
                    .accessibilityIdentifier("reader.tries")
                    .popover(isPresented: $isShowing) { TryLabelList(tries: store.tries).padding() }
            }
        }
        .task(id: pageId) {
            guard FeatureManager.shared.isWideSetUpEnabled, store == nil, let client = actionStore?.actionsService.client else { return }
            let made = TryLabelStore(client: client, pageId: pageId)
            store = made
            await made.load()
        }
    }
}

struct TryLabelList: View {
    let tries: [TryLabel]

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(TryLabel.note).font(.caption).foregroundStyle(.secondary)
            ForEach(tries) { found in
                VStack(alignment: .leading, spacing: 2) {
                    Text(found.title).font(.headline)
                    ForEach(Array(found.lines.enumerated()), id: \.offset) { _, line in Text(line) }
                }
            }
        }
        .frame(minWidth: 260, alignment: .leading)
    }
}

#Preview("A try on a page") {
    let found = TryLabel(stage: "read", ranAt: Date(), model: "gemini-pro", lines: ["hola", "adiós"])
    TryLabelList(tries: [found]).padding()
}
