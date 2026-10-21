import FicheroAPIClient
import SwiftUI

/// Ready's "Offered later: Train a model of your own for this step" (#5660 item 9): each trainable step, its ways to
/// train, where each runs and the need sentence. A way's buttons start it once it is ready; until then they are
/// disabled and the reason is said under them. A place that sends the pages away (Hugging Face Jobs) asks first.
/// Nothing here runs at Start.
struct RecipeTrainOffersFields: View {
    let store: RecipeSetupStore
    /// The ways started from here, by step and way, so the row says it started.
    @State private var started: Set<String> = []
    @State private var starting: String?
    /// A press on a place that sends the pages away, waiting for the person's yes.
    @State private var askingToSend: Pending?

    struct Pending {
        let offer: RecipeSetupStore.TrainOffer
        let way: RecipeSetupStore.TrainWay
        let target: RecipeSetupStore.TrainTarget
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(store.trainOffers, id: \.step) { offer in
                VStack(alignment: .leading, spacing: 8) {
                    Text(store.title(ofStepId: offer.step)).font(.subheadline.weight(.semibold))
                    ForEach(offer.ways, id: \.wayKey) { way in
                        wayRow(offer, way)
                    }
                }
            }
        }
        .confirmationDialog("Send these pages to \(askingToSend?.target.name ?? "Hugging Face Jobs")?",
                            isPresented: Binding(get: { askingToSend != nil }, set: { if !$0 { askingToSend = nil } }),
                            presenting: askingToSend) { pending in
            Button("Send the Pages and Train") { start(pending, pagesMayLeave: true) }
            Button("Cancel", role: .cancel) { askingToSend = nil }
        } message: { pending in
            Text("Your pages and corrected lines are copied to \(pending.target.name) to train there. "
                 + "The copy is deleted when training ends.")
        }
        // Opened straight on Train (Project › Train › Train a Model…): the offers are on the project's Start plan,
        // read here when no page before has read it (a folder's plan is not the project's).
        .task {
            if store.startPlan == nil || store.startPlanFolderId != nil { await store.loadStartPlan() }
        }
    }

    private func key(_ offer: RecipeSetupStore.TrainOffer, _ way: RecipeSetupStore.TrainWay) -> String {
        "\(offer.step)/\(way.wayKey)"
    }

    private func start(_ pending: Pending, pagesMayLeave: Bool) {
        let key = key(pending.offer, pending.way)
        starting = key
        Task {
            if await store.startTraining(pending.offer, way: pending.way, at: pending.target,
                                         pagesMayLeave: pagesMayLeave) != nil {
                started.insert(key)
            }
            starting = nil
        }
    }

    private func wayRow(_ offer: RecipeSetupStore.TrainOffer, _ way: RecipeSetupStore.TrainWay) -> some View {
        let reason = RecipeSetupStore.trainDisabledReason(offer, way)
        return VStack(alignment: .leading, spacing: 4) {
            Text(way.says).font(.body)
            if !way.targets.isEmpty {
                Text("Runs on \(way.targets.map(\.name).formatted(.list(type: .or)))")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if started.contains(key(offer, way)) {
                Label("Started: it shows in Activity", systemImage: "checkmark.circle")
                    .font(.callout).foregroundStyle(.secondary)
            } else if !way.targets.isEmpty {
                HStack(spacing: 8) {
                    ForEach(way.targets, id: \.name) { target in
                        Button("Train on \(target.name)") {
                            let pending = Pending(offer: offer, way: way, target: target)
                            if RecipeSetupStore.sendsPagesAway(target) {
                                askingToSend = pending
                            } else {
                                start(pending, pagesMayLeave: false)
                            }
                        }
                        .disabled(reason != nil || !RecipeSetupStore.canPost(target) || starting != nil)
                        .help(reason ?? "Start training on \(target.name)")
                    }
                }
            }
            if let reason {
                Text(reason).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

#Preview("Offered later: training") {
    RecipeTrainOffersFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 560, height: 200)
}
