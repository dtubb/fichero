import AppIntents

struct FicheroShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: MergeEntitiesIntent(),
            phrases: ["Merge entities in \(.applicationName)"],
            shortTitle: "Merge Entities",
            systemImageName: "arrow.triangle.merge"
        )
        AppShortcut(
            intent: CreateNoteIntent(),
            phrases: ["Create a note in \(.applicationName)"],
            shortTitle: "Create Note",
            systemImageName: "note.text"
        )
        AppShortcut(
            intent: DeleteDocumentIntent(),
            phrases: ["Delete a document in \(.applicationName)"],
            shortTitle: "Delete Document",
            systemImageName: "trash"
        )
        AppShortcut(
            intent: RunWorkflowIntent(),
            phrases: ["Run a workflow in \(.applicationName)"],
            shortTitle: "Run Workflow",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: CreateAnnotationIntent(),
            phrases: ["Create an annotation in \(.applicationName)"],
            shortTitle: "Create Annotation",
            systemImageName: "highlighter"
        )
        // The UI verbs (#5453): App Shortcuts allows ten, so the five an agent or a person drives most.
        AppShortcut(
            intent: OpenProjectIntent(),
            phrases: ["Open a project in \(.applicationName)"],
            shortTitle: "Open Project",
            systemImageName: "folder"
        )
        AppShortcut(
            intent: OpenNodeIntent(),
            phrases: ["Open an item in \(.applicationName)"],
            shortTitle: "Open Item",
            systemImageName: "doc"
        )
        AppShortcut(
            intent: ShowPaneIntent(),
            phrases: ["Show a pane in \(.applicationName)"],
            shortTitle: "Show Pane",
            systemImageName: "rectangle.split.3x1"
        )
        AppShortcut(
            intent: RevealSegmentsIntent(),
            phrases: ["Reveal a line in \(.applicationName)"],
            shortTitle: "Reveal Line",
            systemImageName: "text.magnifyingglass"
        )
        AppShortcut(
            intent: TakeScreenshotIntent(),
            phrases: ["Take a screenshot of \(.applicationName)"],
            shortTitle: "Take Screenshot",
            systemImageName: "camera"
        )
    }
}
