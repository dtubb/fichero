import FicheroAPIClient
import SwiftUI

/// The app-wide cloud spending caps in Settings > AI (`ai.cloud.monthly-cap-in-settings`, `ai.cloud.daily-cap`, #6346, #6347): what a
/// project with no cap of its own may spend a month and a day. A project's own cap in Set Up wins; these are its defaults, not a
/// second ceiling. Each is saved when the person presses Return or leaves the field, through the one audited engine action.
struct CloudCapsSection: View {
    @Environment(AppState.self) private var appState
    @State private var caps: CloudCapsStore?
    @State private var monthly: Double?
    @State private var daily: Double?
    @FocusState private var focus: Field?
    /// The field's width grows with the person's text size (Dynamic Type).
    @ScaledMetric(relativeTo: .callout) private var fieldWidth: CGFloat = 110
    private enum Field { case monthly, daily }

    var body: some View {
        Section("Cloud spending") {
            if let caps {
                row("A month, at most", value: $monthly, prompt: "10", field: .monthly, id: "settings.ai.cloudMonthlyCap")
                row("A day, at most", value: $daily, prompt: "No limit", field: .daily, id: "settings.ai.cloudDailyCap")
                if let message = caps.errorMessage {
                    Text(message).font(.caption).foregroundStyle(.red)
                }
            }
            Text("What a project with no cap of its own may spend on cloud AI. A project's own cap, set in its Set Up, wins.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("settings.ai.cloudCaps")
        .task {
            if caps == nil { caps = CloudCapsStore(client: appState.ficheroClient) }
            await caps?.load()
            showSaved()
        }
    }

    private func row(_ title: String, value: Binding<Double?>, prompt: String, field: Field, id: String) -> some View {
        HStack {
            Text(title)
            // The engine refuses a cap below $0, so the field never holds one.
            TextField(prompt, value: Binding(get: { value.wrappedValue }, set: { value.wrappedValue = $0.map { max($0, 0) } }),
                      format: .currency(code: "USD"))
                .multilineTextAlignment(.trailing).frame(maxWidth: fieldWidth)
                .focused($focus, equals: field)
                .onSubmit { Task { await save() } }
                .onChange(of: focus) { old, _ in if old == field { Task { await save() } } }
                .accessibilityIdentifier(id)
        }
    }

    private func showSaved() {
        monthly = caps?.monthlyUsd
        daily = caps?.dailyUsd
    }

    private func save() async {
        guard let caps else { return }
        for edit in Self.edits(monthly: monthly, daily: daily, heldMonthly: caps.monthlyUsd, heldDaily: caps.dailyUsd) {
            await caps.set(edit.which, usd: edit.usd)
        }
        showSaved()  // the engine's figure, whatever it kept
    }

    /// One cap to send: which, and the figure (nil clears it). Pure, for the tests.
    struct Edit: Equatable {
        let which: Components.Schemas.CloudCapSetting.WhichPayload
        let usd: Double?
    }

    /// What differs from the figures the engine holds: the monthly cap if it moved (emptied: back to the engine's default, which
    /// needs no send when that is what it already holds), the daily one if it moved (emptied: cleared). Pure, for the tests.
    nonisolated static func edits(monthly: Double?, daily: Double?, heldMonthly: Double, heldDaily: Double?) -> [Edit] {
        var out: [Edit] = []
        let wantedMonthly = monthly ?? CloudCapsStore.engineDefaultMonthlyUsd
        if wantedMonthly != heldMonthly { out.append(Edit(which: .monthly, usd: monthly)) }
        if daily != heldDaily { out.append(Edit(which: .daily, usd: daily)) }
        return out
    }
}

#Preview("Cloud caps in Settings") {
    Form { CloudCapsSection() }
        .formStyle(.grouped)
        .environment(AppState())
        .frame(width: 520)
}
