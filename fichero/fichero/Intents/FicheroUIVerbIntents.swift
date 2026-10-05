import AppIntents
import Foundation

// The UI verbs as App Intents (#5453, `openapi.ui.verbs-are-the-click`, `openapi.ui.verbs-on-every-device`):
// the one way to drive the app on iPhone and iPad from outside, and the same verbs Shortcuts and a UI
// test reach on the Mac. Each `perform` is one `UIVerbs` call -- the method the click calls.

struct OpenProjectIntent: AppIntent {
    static let title: LocalizedStringResource = "Open Project"
    static let description = IntentDescription("Open a .fichero project in the front window, as File ▸ Open does.")
    static let openAppWhenRun = true

    @Parameter(title: "Project Path")
    var path: String

    @MainActor func perform() async throws -> some IntentResult & ReturnsValue<String> {
        let id = UIVerbs.openProject(at: URL(fileURLWithPath: (path as NSString).expandingTildeInPath))
        return .result(value: id.uuidString)
    }
}

struct OpenNodeIntent: AppIntent {
    static let title: LocalizedStringResource = "Open Node"
    static let description = IntentDescription("Open a node (a page, document or folder) by its id, as clicking it does.")
    static let openAppWhenRun = true

    @Parameter(title: "Node ID")
    var nodeId: String

    @MainActor func perform() async throws -> some IntentResult {
        UIVerbs.openNode(nodeId)
        return .result()
    }
}

struct SelectNodesIntent: AppIntent {
    static let title: LocalizedStringResource = "Select Nodes"
    static let description = IntentDescription("Select nodes in the Library by id, as clicking them does.")
    static let openAppWhenRun = true

    @Parameter(title: "Node IDs")
    var nodeIds: [String]

    @MainActor func perform() async throws -> some IntentResult {
        try UIVerbs.selectNodes(nodeIds)
        return .result()
    }
}

struct RevealSegmentsIntent: AppIntent {
    static let title: LocalizedStringResource = "Reveal Lines in Preview"
    static let description = IntentDescription(
        "Select segments in the Preview showing their page, and zoom to them, as clicking a line in the Reader does."
    )
    static let openAppWhenRun = true

    @Parameter(title: "Segment IDs")
    var segmentIds: [String]

    @Parameter(title: "Page ID")
    var documentId: String

    @MainActor func perform() async throws -> some IntentResult & ReturnsValue<[String]> {
        .result(value: try UIVerbs.revealSegments(segmentIds, documentId: documentId))
    }
}

struct ShowPaneIntent: AppIntent {
    static let title: LocalizedStringResource = "Show Pane"
    static let description = IntentDescription("Show a pane (Library, Preview, Reader, Inspector, Activity) in the front window.")
    static let openAppWhenRun = true

    @Parameter(title: "Pane")
    var pane: UIPane

    @MainActor func perform() async throws -> some IntentResult {
        try UIVerbs.showPane(pane)
        return .result()
    }
}

struct ShowInspectorTabIntent: AppIntent {
    static let title: LocalizedStringResource = "Show Inspector Tab"
    static let description = IntentDescription("Show the Inspector at a tab, as clicking the tab does.")
    static let openAppWhenRun = true

    @Parameter(title: "Tab", description: "The tab's name, such as Content, Artifacts, Entities or Info.")
    var tab: String

    @MainActor func perform() async throws -> some IntentResult {
        guard let inspectorTab = InspectorTab(named: tab) else { throw UIVerbs.Failure.unknownInspectorTab(tab) }
        try UIVerbs.showInspectorTab(inspectorTab)
        return .result()
    }
}

struct TakeScreenshotIntent: AppIntent {
    static let title: LocalizedStringResource = "Take Screenshot"
    static let description = IntentDescription("Save a picture of the front window, or of one pane, as a PNG.")
    static let openAppWhenRun = true

    @Parameter(title: "Path")
    var path: String

    @Parameter(title: "Pane")
    var pane: UIPane?

    @MainActor func perform() async throws -> some IntentResult & ReturnsValue<String> {
        .result(value: try UIVerbs.screenshot(of: pane, to: path))
    }
}
