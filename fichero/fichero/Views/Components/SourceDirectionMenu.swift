import OSLog
import SwiftUI

private let sourceDirectionLogger = Logger(subsystem: "app.fichero.fichero", category: "SourceDirection")

/// The six directions and Not Stated for a source -- a folder, a document or a page (`SourceDirection`).
/// The Library's right-click and the Inspector's Language section show this same menu.
struct SourceDirectionMenu: View {
    let nodeId: String
    let actionsService: ActionsService?
    var title = "Direction"
    @Environment(\.undoManager) private var undoManager

    var body: some View {
        Menu(title) {
            ForEach(SegmentEdit.directions, id: \.self) { direction in
                Button(SegmentEdit.directionName(direction)) { apply(direction) }
            }
            Divider()
            Button("Not Stated") { apply(nil) }
        }
        .disabled(actionsService == nil)
        .help("The direction every page here reads in, unless a page or a line says otherwise")
    }

    private func apply(_ direction: String?) {
        guard let actionsService else { return }
        let undoManager = undoManager
        let nodeId = nodeId
        Task {
            do {
                try await SourceDirection.apply(direction, on: nodeId, actionsService: actionsService, undoManager: undoManager)
            } catch {
                sourceDirectionLogger.error("direction on \(nodeId, privacy: .public) failed: \(error.localizedDescription)")
            }
        }
    }
}

/// The Inspector's Direction row for a source: what the engine resolves for it and where that came
/// from, and the menu to state it. Re-read after each change (`SourceDirection.didChange`).
struct SourceDirectionRow: View {
    let documentId: String
    let actionsService: ActionsService?
    let segmentService: SegmentService?
    @State private var resolved: InspectorLanguage.Row?

    var body: some View {
        LabeledContent("Direction") {
            SourceDirectionMenu(
                nodeId: documentId, actionsService: actionsService,
                title: resolved.map { "\($0.value) · \($0.origin)" } ?? "Not determined"
            )
            .fixedSize()
        }
        .task(id: documentId) { await load() }
        .onReceive(NotificationCenter.default.publisher(for: SourceDirection.didChange)) { _ in
            Task { await load() }
        }
    }

    private func load() async {
        guard let segmentService else { return }
        let settings = (try? await segmentService.resolvedSettings(documentId: documentId)) ?? []
        resolved = InspectorLanguage.rows(settings).first { $0.key == "direction" }
    }
}

#Preview {
    VStack(alignment: .leading) {
        SourceDirectionMenu(nodeId: "doc-1", actionsService: nil)
        SourceDirectionRow(documentId: "doc-1", actionsService: nil, segmentService: nil)
    }
    .padding()
}
