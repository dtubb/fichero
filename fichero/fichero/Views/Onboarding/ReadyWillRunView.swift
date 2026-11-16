import FicheroAPIClient
import SwiftUI

/// What Ready says will run, from the engine's start plan (`wide.ready.only-what-will-run`, #5840): each job with its pages done,
/// then the skipped steps with why and their fix. Behind the `wideSetUp` flag; reads `ReadyWillRun` alone.
struct ReadyWillRunView: View {
    let store: RecipeSetupStore

    var body: some View {
        if let plan = store.readyWillRun, !plan.running.isEmpty || !plan.skipped.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                ForEach(plan.running) { line in
                    HStack(alignment: .firstTextBaseline) {
                        Text(line.job).font(.callout)
                        Text(line.runsOn).font(.caption).foregroundStyle(.secondary)
                        if let progress = line.progress {
                            Text(progress).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                ForEach(plan.skipped) { skipped in
                    Text(skipped.fix.map { "\(skipped.why) \($0)" } ?? skipped.why)
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("setup.ready.willRun")
        }
    }
}

#Preview("Nothing yet (draws nothing until the plan is read)") {
    ReadyWillRunView(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil))).padding().frame(width: 420)
}
