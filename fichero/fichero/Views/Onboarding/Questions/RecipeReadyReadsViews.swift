import FicheroAPIClient
import SwiftUI

/// "Chosen because" on Ready (`designer.defaults.says-why`, #6052): each default's reason in the engine's words, with the answers
/// that chose it in grey. Nothing when the engine gave none.
struct RecipeDefaultsWhyView: View {
    let store: RecipeSetupStore

    var body: some View {
        if !store.defaultsWhy.isEmpty {
            Section("Chosen because") {
                ForEach(store.defaultsWhy) { row in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.why)
                        Text(row.because).font(.caption).foregroundStyle(.secondary)
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier("ready.defaultWhy.\(row.id)")
                }
            }
        }
    }
}

/// One line under a step of Ready (`designer.how.chain-risk-on-ready`, #6052): what feeds it and what it feeds, and "Check first"
/// where its errors carry furthest. The line is the engine's, from the job registry.
struct RecipeStepChainLine: View {
    let store: RecipeSetupStore
    let stepId: String

    var body: some View {
        if let line = store.chainRisk[stepId] {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(line.line).font(.callout).foregroundStyle(.secondary)
                if line.checkFirst {
                    Text("Check first").font(.caption.weight(.semibold)).foregroundStyle(.orange)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("ready.chainLine.\(stepId)")
        }
    }
}

#Preview("Chain line") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    if let line = try? JSONDecoder().decode(
        Components.Schemas.ChainLine.self,
        from: Data(#"{"job":"find-lines","line":"Read takes the lines Find Lines found.","check_first":true}"#.utf8)) {
        store.chainRisk = ["find-lines": line]
    }
    return Form { RecipeStepChainLine(store: store, stepId: "find-lines") }.formStyle(.grouped).frame(width: 460)
}
