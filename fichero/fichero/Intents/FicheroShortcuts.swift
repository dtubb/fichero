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
    }
}
