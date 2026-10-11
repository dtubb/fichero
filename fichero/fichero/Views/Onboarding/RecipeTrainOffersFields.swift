import FicheroAPIClient
import SwiftUI

/// Ready's "Offered later: Train a model on your corrected pages" (#5660 item 9): each trainable step, its ways to
/// train, where each runs and the need sentence. A way's buttons start it once it is ready; until then they are
/// disabled and the reason is said under them. Nothing here runs at Start.
struct RecipeTrainOffersFields: View {
    let store: RecipeSetupStore
    /// The jobs started from here, by step and way, so the row says it started.
    @State private var started: [String: String] = [:]
    @State private var starting: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(store.trainOffers, id: \.step) { offer in
                VStack(alignment: .leading, spacing: 8) {
                    Text(store.title(ofStepId: offer.step)).font(.subheadline.weight(.semibold))
                    ForEach(offer.ways, id: \.method) { way in
                        wayRow(offer, way)
                    }
                }
            }
        }
    }

    private func wayRow(_ offer: RecipeSetupStore.TrainOffer, _ way: RecipeSetupStore.TrainWay) -> some View {
        let key = "\(offer.step)/\(way.method)"
        let reason = RecipeSetupStore.trainDisabledReason(offer, way)
        return VStack(alignment: .leading, spacing: 4) {
            Text(way.says).font(.body)
            if !way.targets.isEmpty {
                Text("Runs on \(way.targets.map(\.name).formatted(.list(type: .or)))")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if let jobId = started[key] {
                Label("Started (job \(jobId.prefix(8)))", systemImage: "checkmark.circle")
                    .font(.callout).foregroundStyle(.secondary)
            } else if !way.targets.isEmpty {
                HStack(spacing: 8) {
                    ForEach(way.targets, id: \.starts) { target in
                        Button("Train on \(target.name)") {
                            starting = key
                            Task {
                                if let jobId = await store.startTraining(offer, way: way, at: target) {
                                    started[key] = jobId
                                }
                                starting = nil
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
