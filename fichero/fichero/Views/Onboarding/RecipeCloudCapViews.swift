import FicheroAPIClient
import SwiftUI

/// The cloud spend caps against this run's estimate (`ai.where.cloud-spend-cap`, #5943, #6295): the engine's `cloud_cap` line in
/// words, the estimate's basis, and both caps to set in place (the monthly cap and the project's total cap), each an audited,
/// undoable engine action (`RecipeSetupStore.changeCloudCaps`), then the plan is read again: it says whether Start asks.
struct RecipeCloudCapRow: View {
    @Bindable var store: RecipeSetupStore
    let line: Components.Schemas.CloudCapLine
    /// The project's service, so a change is one undo step in the window (`undo.window.*`); nil without a project.
    var undo: (any UndoSetEngine)?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            CloudCapFields(store: store, line: line, undo: undo)
            Text(Self.words(line)).font(.caption).foregroundStyle(line.over ? .orange : .secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let estimate = store.startPlan?.estimate {
                // The best estimate with its basis, per step: what it is priced on, never a margin added here.
                ForEach(CloudCapFix.basis(of: estimate, title: store.title(ofJob:)), id: \.self) { basis in
                    Text(basis).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            if let note = line.note {  // e.g. a model with no listed price is run at an assumed one (#6259)
                Text(note).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
            CloudCapOffers(store: store, line: line, undo: undo)
        }
        .accessibilityIdentifier("setup.cloudCapRow")
    }

    /// What the caps leave against the estimate, in words. Pure, for the tests.
    nonisolated static func words(_ line: Components.Schemas.CloudCapLine) -> String {
        func usd(_ value: Double) -> String { value.formatted(.currency(code: "USD")) }
        let month = "\(usd(line.spentUsd)) spent this month, \(usd(line.remainingUsd)) left"
        guard let estimate = line.estimateUsd else { return "\(month). This run's cloud cost is not known yet." }
        return line.over
            ? "\(month). This run may cost \(usd(estimate)), more than that: Start asks first."
            : "\(month). This run may cost \(usd(estimate))."
    }
}

/// The two caps as fields: the monthly one and the project's total one (empty is no total limit). Each is saved when the person
/// presses Return or leaves the field, through the one audited action.
struct CloudCapFields: View {
    @Bindable var store: RecipeSetupStore
    let line: Components.Schemas.CloudCapLine
    var undo: (any UndoSetEngine)?
    @Environment(WindowSteps.self) private var steps: WindowSteps?
    @FocusState private var focus: Field?
    @State private var monthly: Double?
    @State private var project: Double?
    private enum Field { case monthly, project }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            row("Cloud spend a month, at most", value: $monthly, prompt: "10", field: .monthly, id: "setup.cloudCap")
            row("Cloud spend in all, at most", value: $project, prompt: "No limit", field: .project, id: "setup.cloudProjectCap")
        }
        .onAppear(perform: showSaved)
        .onChange(of: line) { _, _ in if focus == nil { showSaved() } }
    }

    private func row(_ title: String, value: Binding<Double?>, prompt: String, field: Field, id: String) -> some View {
        HStack {
            Text(title)
            // The engine refuses a cap below $0, so the field never holds one.
            TextField(prompt, value: Binding(get: { value.wrappedValue }, set: { value.wrappedValue = $0.map { max($0, 0) } }),
                      format: .currency(code: "USD"))
                .multilineTextAlignment(.trailing).frame(maxWidth: 110)
                .focused($focus, equals: field)
                .onSubmit { Task { await save() } }
                .onChange(of: focus) { old, _ in if old == field { Task { await save() } } }
                .accessibilityIdentifier(id)
        }
    }

    private func showSaved() {
        monthly = line.capUsd
        project = line.projectCapUsd
    }

    private func save() async {
        let change = Self.change(monthly: monthly, project: project, line: line)
        guard change.monthly != nil || change.project != nil || change.clear else { return }
        if await store.changeCloudCaps(monthlyUsd: change.monthly, projectUsd: change.project, clearProjectCap: change.clear,
                                       undo: undo, steps: steps) == false { showSaved() }
    }

    /// What differs from the engine's line: the monthly cap if it moved, the project cap if it moved, or cleared when emptied.
    /// Pure, for the tests.
    nonisolated static func change(monthly: Double?, project: Double?, line: Components.Schemas.CloudCapLine) -> Change {
        Change(monthly: monthly.flatMap { $0 == line.capUsd ? nil : $0 },
               project: project.flatMap { $0 == line.projectCapUsd ? nil : $0 },
               clear: project == nil && line.projectCapUsd != nil)
    }

    struct Change: Equatable {
        let monthly: Double?
        let project: Double?
        let clear: Bool
    }
}

/// What the person can do in place when the caps stop the run: the reason in words, "Raise the monthly cap to N" and "Raise
/// the project cap to N" (N is the engine's, from the plan) and "Run the first N pages" (Finder order). On Ready, and
/// beside a Start refused or a run paused at a cap. Nothing shows when the run is not over a cap.
struct CloudCapOffers: View {
    @Bindable var store: RecipeSetupStore
    let line: Components.Schemas.CloudCapLine
    var undo: (any UndoSetEngine)?
    @Environment(WindowSteps.self) private var steps: WindowSteps?

    var body: some View {
        let fix = CloudCapFix(line)
        if let reason = fix.reason {
            VStack(alignment: .leading, spacing: 4) {
                Label(reason, systemImage: "exclamationmark.triangle").font(.callout).foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
                HStack {
                    if let monthly = fix.monthly {
                        Button(monthly.title) { Task { await store.raise(monthly, project: false, undo: undo, steps: steps) } }
                            .accessibilityIdentifier("setup.raiseMonthlyCap")
                    }
                    if let project = fix.project {
                        Button(project.title) { Task { await store.raise(project, project: true, undo: undo, steps: steps) } }
                            .accessibilityIdentifier("setup.raiseProjectCap")
                    }
                    if let count = fix.firstPages {
                        Button(CloudCapFix.firstPagesTitle(count)) { Task { await store.limitRun(toFirst: count) } }
                            .help("The first \(count) pages in the order Finder shows them")
                            .accessibilityIdentifier("setup.runFirstPages")
                    }
                }
            }
        } else if store.runFirstPages != nil {
            Button("Run every page again") { Task { await store.limitRun(toFirst: nil) } }
                .accessibilityIdentifier("setup.runEveryPage")
        }
    }
}

/// Both caps and the fixes the plan offers, as one small view for a place that is not Ready: the paused-at-cap run strip (#6295).
/// Reads the Start plan when it opens, so the amounts are the engine's for what is left to run.
struct CloudCapChangeView: View {
    @Bindable var store: RecipeSetupStore
    var undo: (any UndoSetEngine)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Cloud spending caps").font(.headline)
            if let line = store.startPlan?.cloudCap {
                CloudCapFields(store: store, line: line, undo: undo)
                Text(RecipeCloudCapRow.words(line)).font(.caption).foregroundStyle(.secondary)
                CloudCapOffers(store: store, line: line, undo: undo)
                Text("Raising a cap does not resume a paused run: use its Resume.").font(.caption).foregroundStyle(.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
            if let error = store.errorMessage { Text(error).font(.caption).foregroundStyle(.orange) }
        }
        .padding(12)
        .frame(width: 380)
        .task { await store.loadStartPlan(folderId: store.startPlanFolderId) }
    }
}

#Preview("Over the monthly cap") {
    // swiftlint:disable:next force_try
    let line = try! JSONDecoder().decode(Components.Schemas.CloudCapLine.self, from: Data("""
    {"cap_usd":10,"spent_usd":4,"remaining_usd":6,"unpriced":false,"estimate_usd":14,"over":true,"over_month":true,
     "needed_cap_usd":18,"fewer_pages":42}
    """.utf8))
    return RecipeCloudCapRow(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)), line: line)
        .padding()
        .frame(width: 460, height: 260)
}
