import FicheroAPIClient
import SwiftUI

/// Pure words and rules for the Pages to check worklist (`prep.check.worklist-of-proposals-and-a-sample`).
enum PrepareCheck {
    /// The count's line: "Pages to check: N".
    static func line(_ count: Int) -> String { "Pages to check: \(count)" }

    /// A row's words: what is unsure, as the engine said it, joined for one caption.
    static func words(_ item: Components.Schemas.PrepareCheckItem) -> String { item.words.joined(separator: "; ") }

    /// Accept leaves the page as it is: one answer per proposal open on it (a sample page has none, so Accept is a no-op).
    static func acceptKinds(_ item: Components.Schemas.PrepareCheckItem) -> [String] { item.kinds }

    /// Hiding as blank is offered where the run was unsure of blank, or on a sample page (a person may hide any page).
    static func canMarkBlank(_ item: Components.Schemas.PrepareCheckItem) -> Bool {
        item.sample || item.kinds.contains("blank")
    }
}

/// "Pages to check: N" with the worklist under it: pages with a proposal first, then the sample, each saying in words what
/// is unsure. Accept, Mark blank and Open in Preview are a person's word, each one audited action with Undo; the engine
/// drops the page from the list. Nothing shows when there is nothing to check.
struct PrepareImagesCheckList: View {
    let store: RecipeSetupStore
    var actionsService: ActionsService?

    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @State private var expanded = false
    @State private var failure: String?

    var body: some View {
        if let list = store.prepareCheck, !list.items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    expanded.toggle()
                } label: {
                    Label(PrepareCheck.line(list.count), systemImage: expanded ? "chevron.down" : "chevron.right")
                        .font(.callout)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("prepareImages.toCheck")
                if expanded {
                    ForEach(list.items, id: \.id) { item in row(item) }
                }
                if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            }
        }
    }

    private func row(_ item: Components.Schemas.PrepareCheckItem) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(item.name).font(.callout).lineLimit(1)
                Spacer()
                if !item.kinds.isEmpty {
                    Button("Accept") { Task { await accept(item) } }
                        .controlSize(.small)
                        .accessibilityIdentifier("prepareImages.check.accept")
                }
                if PrepareCheck.canMarkBlank(item) {
                    Button("Mark blank") { Task { await markBlank(item) } }
                        .controlSize(.small)
                        .accessibilityIdentifier("prepareImages.check.markBlank")
                }
                Button("Open in Preview") { open(item) }
                    .controlSize(.small)
                    .accessibilityIdentifier("prepareImages.check.open")
            }
            Text(PrepareCheck.words(item)).font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("prepareImages.check.row")
    }

    private func accept(_ item: Components.Schemas.PrepareCheckItem) async {
        for kind in PrepareCheck.acceptKinds(item) {
            await answer("image.accept_proposal", ImageAcceptProposalRequest(documentId: item.id, kind: kind), "Accept Page")
        }
    }

    private func markBlank(_ item: Components.Schemas.PrepareCheckItem) async {
        await answer("image.mark_blank", ImageMarkBlankRequest(documentId: item.id, blank: true), "Hide Page")
    }

    private func answer<Params: Encodable>(_ action: String, _ params: Params, _ name: String) async {
        guard let actionsService else { return }
        do {
            try await AuditedAction.run(
                action, params: params, actionName: name, actionsService: actionsService, steps: windowSteps,
                afterChange: { await store.loadPrepareCheck() })
            failure = nil
        } catch {
            failure = "Couldn't answer: \(error.localizedDescription)"
        }
    }

    /// Preview on the page, through the sidebar's reveal (the same seam a breadcrumb uses).
    private func open(_ item: Components.Schemas.PrepareCheckItem) {
        NotificationCenter.default.post(name: .sidebarRevealDocument, object: nil, userInfo: ["documentId": item.id])
    }
}

#Preview("Pages to check") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.prepareCheck = .init(
        items: [
            .init(id: "p1", name: "page-014", kinds: ["blank"], words: ["very little ink beyond its ruling"], sample: false),
            .init(id: "p2", name: "page-020", kinds: [], words: ["checked as a sample"], sample: true)
        ],
        count: 2, proposed: 1)
    return PrepareImagesCheckList(store: store).padding().frame(width: 420)
}
