import FicheroAPIClient
import SwiftUI

/// "Accept all N" in the reader's head, shown only while the page has lines a review's reading counts on that no person has
/// chosen (`wide.review.accept-line-and-all`). One press, one undo; the count is the engine's.
struct ReviewAcceptAllButton: View {
    let documentId: String
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var store: ReviewAcceptStore?

    init(documentId: String, store: ReviewAcceptStore? = nil) {
        self.documentId = documentId
        _store = State(initialValue: store)
    }

    var body: some View {
        Group {
            if let store, store.isOffered, let actionsService = actionStore?.actionsService {
                Button(ReviewAcceptWords.button(store.count)) {
                    Task { await store.accept(actionsService: actionsService, steps: windowSteps) }
                }
                .disabled(store.isAccepting)
                .help(ReviewAcceptWords.help(store.count))
                .accessibilityIdentifier("reader.review.acceptAll")
            }
        }
        .task(id: documentId) {
            guard FeatureManager.shared.isWideSetUpEnabled, store == nil, let client = actionStore?.actionsService.client else { return }
            let made = ReviewAcceptStore(client: client, documentId: documentId)
            store = made
            await made.load()
        }
    }
}

#Preview("Accept all 12") {
    let store = ReviewAcceptStore(client: FicheroClient(libraryPath: nil), documentId: "page-1", count: 12)
    ReviewAcceptAllButton(documentId: "page-1", store: store).padding()
}
