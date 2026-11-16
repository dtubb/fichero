import SwiftUI

/// Pages that are only the page before seen through (`image.enhance.show-through-only-verso`, #6197): listed dimmed with the
/// words "show-through of <name>", left out of reading by default, one button to include and one to leave out again. The
/// page is never removed from the list.
enum ShowThroughOnly {
    static let kind = "show-through-only"

    static func isMarked(_ document: Document) -> Bool {
        (document.metadata["page_kind"]?.value as? String) == kind
    }

    static func marked(in documents: [Document]) -> [Document] { documents.filter(isMarked) }

    static func isIncluded(_ document: Document) -> Bool {
        (document.metadata["show_through_included"]?.value as? Bool) == true
    }

    /// "show-through of <the page before's name>", the recto found by the id the run stored; its id when it is not in the list.
    static func words(_ document: Document, in documents: [Document]) -> String {
        let recto = document.metadata["show_through_of"]?.value as? String
        let name = documents.first { $0.id == recto }?.name ?? recto ?? "the page before"
        return "show-through of \(name)"
    }

    static func line(_ count: Int) -> String { "\(count) show-through" }

    /// The page as the engine leaves it after Include or Leave out.
    static func changed(_ document: Document, included: Bool) -> Document {
        var page = document
        page.metadata["show_through_included"] = AnyCodable(included)
        return page
    }
}

/// The "N show-through" line above the rows; nothing when no page is marked.
struct ShowThroughOnlyLine: View {
    let documents: [Document]
    let store: DocumentStore

    @State private var expanded = false
    @State private var failure: String?

    var body: some View {
        let marked = ShowThroughOnly.marked(in: documents)
        if !marked.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    expanded.toggle()
                } label: {
                    Label(ShowThroughOnly.line(marked.count), systemImage: "doc.on.doc")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("library.showThroughOnly")
                if expanded {
                    ForEach(marked) { page in
                        ShowThroughPageRow(page: page, documents: documents, store: store, failure: $failure)
                    }
                }
                if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.bar)
        }
    }
}

/// One marked page: its name, "show-through of <name>" dimmed until it is included, and the one button (Include / Leave Out). The
/// same row in the Library line, the Source pane and the Inspector's Edits facet (`image.enhance.show-through-only-verso`, #6362).
struct ShowThroughPageRow: View {
    let page: Document
    let documents: [Document]
    let store: DocumentStore
    @Binding var failure: String?

    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    var body: some View {
        let included = ShowThroughOnly.isIncluded(page)
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(page.name).font(.callout).lineLimit(1)
                Text(ShowThroughOnly.words(page, in: documents)).font(.caption).foregroundStyle(.secondary)
            }
            .opacity(included ? 1 : 0.5)
            Spacer()
            Button(included ? "Leave Out" : "Include") { Task { await set(included: !included) } }
                .controlSize(.small)
                .accessibilityIdentifier(included ? "library.showThrough.leaveOut" : "library.showThrough.include")
        }
    }

    private func set(included: Bool) async {
        guard let actionsService = actionStore?.actionsService else { return }
        do {
            var first = true
            try await AuditedAction.run(
                "image.include_show_through_only", params: ImageIncludeShowThroughRequest(documentId: page.id, included: included),
                actionName: included ? "Include Page" : "Leave Page Out", actionsService: actionsService, steps: windowSteps,
                afterChange: {
                    await HiddenPages.settle(
                        store, id: page.id, fallback: first ? ShowThroughOnly.changed(page, included: included) : nil)
                    first = false
                }
            )
            failure = nil
        } catch {
            failure = "Couldn't change \(page.name): \(error.localizedDescription)"
        }
    }
}

#Preview("Show-through line") {
    let recto = Document(id: "r1", name: "IMG_0006")
    let verso = Document(
        name: "IMG_0007",
        metadata: ["page_kind": AnyCodable("show-through-only"), "show_through_of": AnyCodable("r1")])
    ShowThroughOnlyLine(documents: [recto, verso], store: DocumentStore.preview)
        .frame(width: 360)
}
