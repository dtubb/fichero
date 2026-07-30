import SwiftUI

struct ResearchTasksPane: View {
    var project: ResearchProject
    @Environment(ResearchStore.self) var researchStore

    // View-local state (selection + UI scaffolding)
    @State var selectedPlanId: String?
    @State var expandedTaskIds: Set<String> = []
    @State var selectedTab = 0

    @State var newTaskText = ""
    @State var newChecklistText = ""
    @State var newSourceText = ""
    @State var newNoteText = ""
    @State var editingNoteId: String?
    @State var editingNoteText = ""

    // "Start research with AI" composer (#1729) — name + term, POSTed with the
    // term so the backend runs its research plan agent.
    @State var isPlanComposerPresented = false
    @State var newPlanName = ""
    @State var newPlanTerm = ""

    var body: some View {
        VStack(spacing: 0) {
            Picker("", selection: $selectedTab) {
                Text("Tasks").tag(0)
                Text("Checklists").tag(1)
                Text("Sources").tag(2)
                Text("Notes").tag(3)
            }
            .pickerStyle(.segmented)
            .padding(8)

            Divider()

            if researchStore.isLoading {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                switch selectedTab {
                case 0: tasksTab
                case 1: checklistsTab
                case 2: sourcesTab
                default: notesTab
                }
            }
        }
        .task(id: project.id) { await reload() }
        .sheet(isPresented: $isPlanComposerPresented) { planComposerSheet }
    }
}
