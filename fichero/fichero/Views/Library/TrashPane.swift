import SwiftUI

/// A project's Trash in the Library pane (#2077, #5243, `safety.trash.lists-what-and-why`): what
/// each thing is, when it was deleted and by whom, where it was, and why ("Moved to Istmina on
/// 10 Oct 2026"). Things here can be put back; Empty Trash… asks first. The words come from the
/// engine; this view lays them out and publishes the selection to the Edit menu's Put Back.
struct TrashPane: View {
    let store: TrashStore

    @State private var selection = Set<String>()

    private var target: TrashActionsTarget { TrashActionsTarget(store: store, selection: selection) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let notice = store.notice {
                Text(notice)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)
                    .padding(.bottom, 6)
            }
            if let error = store.errorMessage {
                Text(error)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
                    .padding(.bottom, 6)
            }
            if store.isEmpty {
                ContentUnavailableView(
                    "The Trash Is Empty",
                    systemImage: "trash",
                    description: Text("Things you delete in this project wait here until you empty the Trash.")
                )
            } else {
                list
            }
        }
        .focusedSceneValue(\.trashActions, target)
        .task { await store.load() }
        .onChange(of: store.entries.map(\.id)) { _, ids in
            // An item put back or removed leaves the selection with it.
            selection.formIntersection(ids)
        }
        .alert(
            store.emptyQuestion?.question ?? "",
            isPresented: Binding(
                get: { store.emptyQuestion != nil },
                set: { if !$0 { store.cancelEmpty() } }
            ),
            presenting: store.emptyQuestion
        ) { _ in
            Button("Delete Permanently", role: .destructive) {
                Task { await store.confirmEmpty() }
            }
            Button("Cancel", role: .cancel) { store.cancelEmpty() }
        } message: { question in
            Text(question.message)
        }
    }

    private var header: some View {
        HStack {
            Text(SidebarTrashRow.name)
                .font(.headline)
            Spacer()
            EmptyTrashButton(store: store)
        }
        .padding()
    }

    private var list: some View {
        List(selection: $selection) {
            ForEach(store.entries) { entry in
                TrashEntryRow(entry: entry)
                    .tag(entry.id)
            }
        }
        .contextMenu(forSelectionType: String.self) { ids in
            PutBackButton(target: TrashActionsTarget(store: store, selection: ids))
            Divider()
            EmptyTrashButton(store: store)
        }
    }
}

/// One thing in the Trash: its name, why it is here, where it was and when, and what is inside.
struct TrashEntryRow: View {
    let entry: TrashEntry

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: entry.isFolder ? "folder" : "doc")
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.name)
                    .font(.body)
                Text(entry.why)
                    .font(.callout)
                    .foregroundStyle(entry.wasMoved ? Color.accentColor : Color.secondary)
                Text(entry.whereAndWhenText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if let contents = entry.contentsText {
                    Text(contents)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

#Preview("Trash with a deleted folder and a moved page") {
    let store = TrashStore(
        client: LibraryPreviewFixtures.library.ficheroClient,
        entries: [
            TrashEntry(
                id: "folder", name: "Letters", isFolder: true, deletedAt: .now, deletedBy: "ana",
                itemCount: 40, fromWhere: "Box 3", why: "Deleted by ana"
            ),
            TrashEntry(
                id: "page", name: "page-12.jpg", deletedAt: .now, deletedBy: "ana",
                fromWhere: "Box 3 / Letters", why: "Moved to Istmina on 10 Oct 2026", wasMoved: true
            )
        ]
    )
    return TrashPane(store: store)
        .frame(width: 420, height: 320)
}
