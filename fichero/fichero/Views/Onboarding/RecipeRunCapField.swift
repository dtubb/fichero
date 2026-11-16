import FicheroAPIClient
import SwiftUI

/// "This run, at most" (`designer.budget.run-cap`, #6295): the cap for this Start alone, beside the project's caps. Empty: the
/// project's caps hold. The engine proposes the estimate; it is written only when the person types or accepts it ("Use $N").
struct RecipeRunCapField: View {
    @Bindable var store: RecipeSetupStore
    let line: Components.Schemas.CloudCapLine
    @ScaledMetric(relativeTo: .callout) private var fieldWidth: CGFloat = CloudCapFields.baseFieldWidth

    var body: some View {
        let block = BudgetBlock(line)
        HStack {
            Text("This run, at most")
            TextField(block.prompt, value: Binding(get: { store.runCapUsd }, set: { store.runCapUsd = BudgetBlock.clamped($0) }),
                      format: .currency(code: "USD"))
                .multilineTextAlignment(.trailing).frame(maxWidth: fieldWidth)
                .help("Cloud spending this run may reach; the run pauses at it and asks")
                .accessibilityIdentifier("setup.runCap")
            if store.runCapUsd == nil, let proposed = block.proposedRunCapUsd {
                Button("Use \(CloudCapFix.usd(proposed))") { store.runCapUsd = proposed }
                    .accessibilityIdentifier("setup.useProposedRunCap")
            }
        }
    }
}

#Preview("Run cap with the engine's proposal") {
    let json = #"{"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":14,"over":true,"proposed_run_cap_usd":14}"#
    let line = try? JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data(json.utf8))
    return Group {
        if let line {
            RecipeRunCapField(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), line: line)
        }
    }
    .padding()
    .frame(width: 420)
}
