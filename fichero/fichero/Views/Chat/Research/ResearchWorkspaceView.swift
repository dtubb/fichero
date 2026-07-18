import SwiftUI

/// 3-pane research workspace: CHAT | BROWSER | TASKS
struct ResearchWorkspaceView: View {
    var project: ResearchProject

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    @State private var chatPaneWidth: Double = 280
    @State private var tasksPaneWidth: Double = 280

    var body: some View {
        Group {
            if ContentView.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass) {
                VStack(spacing: 0) {
                    ResearchChatPane(project: project)
                        .frame(maxWidth: .infinity, maxHeight: 260)

                    Divider()

                    ResearchBrowserPane(project: project)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)

                    Divider()

                    ResearchTasksPane(project: project)
                        .frame(maxWidth: .infinity, maxHeight: 260)
                }
            } else {
                HStack(spacing: 0) {
                    // Pane 1: Chat
                    ResearchChatPane(project: project)
                        .frame(width: chatPaneWidth)

                    ResizableDivider(width: $chatPaneWidth, minWidth: 200, maxWidth: 500, edge: .trailing)

                    // Pane 2: Web Browser (fills remaining space)
                    ResearchBrowserPane(project: project)
                        .frame(maxWidth: .infinity)

                    ResizableDivider(width: $tasksPaneWidth, minWidth: 200, maxWidth: 500, edge: .leading)

                    // Pane 3: Tasks & Notes
                    ResearchTasksPane(project: project)
                        .frame(width: tasksPaneWidth)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
