import SwiftUI

/// Blank pages the run hid (`prep.blank-pages-hidden-in-the-item-view`): kept, never deleted, out of the rows, and said
/// in one "N hidden" line that reveals them dimmed, each with an Unhide button (`library.chrome.excluded-from-processing-treatment`).
enum HiddenPages {
    /// A page the blank rule (or a person) hid: `exclude_from_processing` set and the engine's `blank` mark true.
    /// A page a person merely excluded stays in the rows, as today.
    static func isHiddenBlank(_ document: Document) -> Bool {
        guard document.excludeFromProcessing,
              let mark = document.metadata["blank"]?.value as? [String: Any] else { return false }
        return (mark["blank"] as? Bool) == true
    }

    static func hidden(in documents: [Document]) -> [Document] { documents.filter(isHiddenBlank) }

    /// The page after Unhide, as the engine leaves it: shown, the person's word kept on the mark.
    static func unhidden(_ document: Document) -> Document {
        var page = document
        page.excludeFromProcessing = false
        var mark = (document.metadata["blank"]?.value as? [String: Any]) ?? [:]
        mark["blank"] = false
        mark["by"] = "person"
        page.metadata["blank"] = AnyCodable(mark)
        return page
    }

    static func line(_ count: Int) -> String { "\(count) hidden" }

    /// Read the page again from the engine and put it in the rows: after the action and after every Undo and Redo of it,
    /// so the line and the rows follow the page's real state (`undo.one-path`). With nothing fetched (the engine did not
    /// answer) `fallback`, the page as the action leaves it, is shown instead; Undo and Redo pass none.
    @MainActor
    static func settle(
        _ store: DocumentStore, id: String, fallback: Document? = nil,
        fetch: (([String]) async -> [Document])? = nil
    ) async {
        // Not `await (fetch?(..) ?? store.fresh..)`: an async call cannot sit in `??`'s autoclosure.
        let fresh: [Document]
        if let fetch {
            fresh = await fetch([id])
        } else {
            fresh = await store.freshDocuments(ids: [id])
        }
        if fresh.isEmpty {
            if let fallback { store.refreshLocalContent(fallback) }
            return
        }
        for page in fresh { store.refreshLocalContent(page) }
    }
}

/// The "N hidden" line above the rows; nothing when no page is hidden.
struct HiddenPagesLine: View {
    let documents: [Document]
    let store: DocumentStore

    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var revealed = false
    @State private var failure: String?

    var body: some View {
        let hidden = HiddenPages.hidden(in: documents)
        if !hidden.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    revealed.toggle()
                } label: {
                    Label(HiddenPages.line(hidden.count), systemImage: revealed ? "eye" : "eye.slash")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("library.hiddenPages")
                if revealed {
                    ForEach(hidden) { page in
                        HStack {
                            Text(page.name).font(.callout).lineLimit(1)
                            Spacer()
                            Button("Unhide") { Task { await unhide(page) } }
                                .controlSize(.small)
                                .accessibilityIdentifier("library.unhidePage")
                        }
                        .opacity(0.5)  // dimmed: kept, but out of the run
                    }
                }
                if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)
        }
    }

    private func unhide(_ page: Document) async {
        guard let actionsService = actionStore?.actionsService else { return }
        do {
            // One audited action, so ⌘Z hides the page again (`undo.one-path`).
            var first = true
            try await AuditedAction.run(
                "image.mark_blank", params: ImageMarkBlankRequest(documentId: page.id, blank: false),
                actionName: "Unhide Page", actionsService: actionsService, steps: windowSteps,
                afterChange: {
                    // The action's own result first, then the page again after each Undo and Redo.
                    await HiddenPages.settle(store, id: page.id, fallback: first ? HiddenPages.unhidden(page) : nil)
                    first = false
                }
            )
            failure = nil
        } catch {
            failure = "Couldn't unhide \(page.name): \(error.localizedDescription)"
        }
    }
}

#Preview("Hidden pages line") {
    let blank = Document(
        name: "IMG_0004", metadata: ["blank": AnyCodable(["blank": true, "by": "run r1"] as [String: Any])],
        excludeFromProcessing: true)
    HiddenPagesLine(documents: [blank], store: DocumentStore.preview)
        .frame(width: 360)
}
