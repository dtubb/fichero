import SwiftUI

/// A recipe run paused at a cloud spend cap, in its Activity details (#6295): the engine's words and Change Caps…, which
/// changes the caps in place. It was the project window's bottom strip's; the strip is gone (owner 2026-11-13: a run is
/// Activity's, not the main window's), so the change lives with the run's details.
struct ActivityDetailsCapStop: View {
    let jobId: String
    let libraryId: UUID?
    @Environment(ActivityStore.self) private var store
    @State private var changingCaps = false

    var body: some View {
        if let stop = store.recipeRunStoppedAtCap[jobId] {
            HStack(alignment: .firstTextBaseline) {
                Label(stop.words, systemImage: "dollarsign.circle").foregroundStyle(.orange)
                Button("Change Caps…") { changingCaps = true }
                    .controlSize(.small)
                    .accessibilityIdentifier("activity.details.changeCaps")
            }
            .font(.callout)
            .popover(isPresented: $changingCaps, arrowEdge: .bottom) { capsPopover(for: stop) }
            .accessibilityIdentifier("activity.details.capStop")
        }
    }

    /// The caps to change, beside the amounts the plan needs and the ones that let the refused call through; the plan
    /// is read when it opens.
    @ViewBuilder
    private func capsPopover(for stop: CloudCapFix.Stop) -> some View {
        if let library = LibraryManager.shared.openLibraries.first(where: { $0.id == libraryId }) {
            CloudCapChangeView(store: library.recipeSetupStore, stop: stop, undo: library.actionsService)
        }
    }
}

#Preview("A run paused at the cloud spend cap") {
    let store = ActivityStore(service: ActivityService(apiClient: APIClient()), projectKey: "preview")
    if let status = try? JSONDecoder().decode(Components.Schemas.RecipeRunStatus.self, from: Data("""
    {"job_id":"run-1","state":"waiting","reason":"Paused at the cloud spend cap: a call could cost up to $0.04","steps":[],"skipped":[],
     "stopped_at_cap":true,"stopped_needs_cap_usd":1.04}
    """.utf8)), let stop = CloudCapFix.Stop(status) {
        store.recipeRunStoppedAtCap["run-1"] = stop
    }
    return ActivityDetailsCapStop(jobId: "run-1", libraryId: nil)
        .environment(store)
        .padding()
        .frame(width: 420)
}
