import SwiftUI

struct CollectionWorkspaceStub: View {
    let document: Document

    @Environment(DocumentStore.self) private var documentStore
    @State private var selectedWorkspaceId: String?
    @State private var showingNewWorkspace = false
    @State private var newWorkspaceName = ""
    @State private var renameWorkspaceName = ""
    @State private var workspaceToRename: Document?
    @State private var workspaceToDelete: Document?
    @State private var showingDeleteConfirmation = false
    @State private var isLoadingWorkspaces = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                workspaceSection
                curatedItemsSection
                surfacesSection
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task {
            await refreshWorkspaces()
            await selectWorkspace(document)
        }
        .sheet(isPresented: $showingNewWorkspace) {
            workspaceForm(
                title: "New Workspace",
                textFieldTitle: "Workspace name",
                text: $newWorkspaceName,
                confirmTitle: "Create",
                confirmAction: createWorkspace
            )
        }
        .sheet(item: $workspaceToRename) { workspace in
            workspaceForm(
                title: "Rename Workspace",
                textFieldTitle: "Workspace name",
                text: $renameWorkspaceName,
                confirmTitle: "Save",
                confirmAction: {
                    await renameWorkspace(workspace)
                }
            )
            .onAppear {
                renameWorkspaceName = workspace.name
            }
        }
        .confirmationDialog(
            "Delete Workspace?",
            isPresented: $showingDeleteConfirmation,
            presenting: workspaceToDelete
        ) { workspace in
            Button("Delete", role: .destructive) {
                Task { await deleteWorkspace(workspace) }
            }
            Button("Cancel", role: .cancel) {}
        } message: { workspace in
            Text("Delete “\(workspace.name)” and all curated items inside it?")
        }
    }
}

private extension CollectionWorkspaceStub {
    var sortedWorkspaces: [Document] {
        documentStore.workspaces.sorted {
            $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
        }
    }

    var selectedWorkspace: Document? {
        guard let selectedWorkspaceId else { return nil }
        return sortedWorkspaces.first(where: { $0.id == selectedWorkspaceId }) ?? (document.id == selectedWorkspaceId ? document : nil)
    }

    var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Workspace")
                        .font(.title2)
                    Text("Create and organize workspaces, then keep curated items grouped by the active collection.")
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    showingNewWorkspace = true
                } label: {
                    Label("New Workspace", systemImage: "square.stack.3d.up.badge.a")
                }
                .buttonStyle(.borderedProminent)
                .help("Create a workspace")
            }

            if let selectedWorkspace {
                HStack(spacing: 10) {
                    Image(systemName: "square.stack.3d.up.fill")
                        .foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(selectedWorkspace.name)
                            .font(.headline)
                        Text("\(selectedWorkspace.curatedItems.count) curated items")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.top, 4)
            }
        }
    }

    var workspaceSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(
                title: "Workspaces",
                subtitle: "Select a workspace to see its curated items.",
                icon: "square.stack.3d.up"
            )

            if isLoadingWorkspaces && sortedWorkspaces.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 10)
            } else if sortedWorkspaces.isEmpty {
                ContentUnavailableView(
                    "No Workspaces Yet",
                    systemImage: "square.stack.3d.up",
                    description: Text("Create a workspace to start organizing collections.")
                )
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                VStack(spacing: 8) {
                    ForEach(sortedWorkspaces) { workspace in
                        workspaceRow(workspace)
                    }
                }
            }
        }
    }

    var curatedItemsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(
                title: "Selected Workspace",
                subtitle: "Curated items in the active collection.",
                icon: "square.stack.3d.up.fill"
            )

            if documentStore.isLoadingChildren && documentStore.currentDocuments.isEmpty {
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 10)
            } else if let selectedWorkspace {
                if documentStore.currentDocuments.isEmpty {
                    ContentUnavailableView(
                        "No Curated Items",
                        systemImage: "tray",
                        description: Text("Add documents to this workspace to group them here.")
                    )
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    VStack(spacing: 8) {
                        ForEach(documentStore.currentDocuments) { document in
                            HStack(spacing: 10) {
                                Image(systemName: document.isWorkspace ? "square.stack.3d.up" : "doc")
                                    .foregroundStyle(.secondary)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(document.name)
                                        .font(.body)
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)
                                    Text(document.docType.rawValue)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(Color(platformColor: .controlBackgroundColor))
                            )
                        }
                    }
                }
                Text("Workspace: \(selectedWorkspace.name)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ContentUnavailableView(
                    "Select a Workspace",
                    systemImage: "square.stack.3d.up",
                    description: Text("Choose a workspace to inspect its curated items.")
                )
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    var surfacesSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(
                title: "Library Surfaces",
                subtitle: "Workspaces, ingest, IIIF, and export stay grouped as first-class library tools.",
                icon: "rectangle.3.group"
            )

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], alignment: .leading, spacing: 12) {
                surfaceCard(
                    title: "Ingest",
                    subtitle: "Bring files and folders into the library.",
                    icon: "tray.and.arrow.down"
                )
                surfaceCard(
                    title: "IIIF",
                    subtitle: "Browse image and manifest-backed collections.",
                    icon: "photo.stack"
                )
                surfaceCard(
                    title: "Export",
                    subtitle: "Move curated work back out of the library.",
                    icon: "square.and.arrow.up"
                )
            }
        }
    }

    func sectionHeader(title: String, subtitle: String, icon: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(.secondary)
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.headline)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    func surfaceCard(title: String, subtitle: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Color.accentColor)
            Text(title)
                .font(.headline)
            Text(subtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 96, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(platformColor: .controlBackgroundColor))
        )
    }

    func workspaceRow(_ workspace: Document) -> some View {
        Button {
            Task { await selectWorkspace(workspace) }
        } label: {
            HStack(spacing: 10) {
                Image(systemName: selectedWorkspaceId == workspace.id ? "checkmark.circle.fill" : "square.stack.3d.up")
                    .foregroundStyle(selectedWorkspaceId == workspace.id ? Color.accentColor : .secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(workspace.name)
                        .font(.body)
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text("\(workspace.curatedItems.count) curated items")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(selectedWorkspaceId == workspace.id ? Color.accentColor.opacity(0.12) : Color.clear)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Rename Workspace") {
                workspaceToRename = workspace
            }
            Button("Delete Workspace", role: .destructive) {
                workspaceToDelete = workspace
                showingDeleteConfirmation = true
            }
        }
    }

    func workspaceForm(
        title: String,
        textFieldTitle: String,
        text: Binding<String>,
        confirmTitle: String,
        confirmAction: @escaping @MainActor () async -> Void
    ) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
            TextField(textFieldTitle, text: text)
                .textFieldStyle(.roundedBorder)
                .frame(width: 260)
            HStack {
                Button("Cancel") {
                    showingNewWorkspace = false
                    workspaceToRename = nil
                }
                Button(confirmTitle) {
                    Task {
                        await confirmAction()
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(20)
    }

    func refreshWorkspaces() async {
        isLoadingWorkspaces = true
        defer { isLoadingWorkspaces = false }
        await documentStore.loadWorkspaces()
    }

    func selectWorkspace(_ workspace: Document) async {
        selectedWorkspaceId = workspace.id
        if documentStore.selectedCollection?.id != workspace.id {
            await documentStore.selectCollection(workspace)
        }
    }

    func createWorkspace() async {
        let name = newWorkspaceName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        showingNewWorkspace = false
        newWorkspaceName = ""
        do {
            let workspace = try await documentStore.createWorkspace(name: name)
            await refreshWorkspaces()
            await selectWorkspace(workspace)
        } catch {
            documentStore.error = error
        }
    }

    func renameWorkspace(_ workspace: Document) async {
        let name = renameWorkspaceName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        workspaceToRename = nil
        do {
            _ = try await documentStore.renameDocument(workspace, to: name)
            await refreshWorkspaces()
            if selectedWorkspaceId == workspace.id {
                selectedWorkspaceId = workspace.id
            }
        } catch {
            documentStore.error = error
        }
    }

    func deleteWorkspace(_ workspace: Document) async {
        workspaceToDelete = nil
        showingDeleteConfirmation = false
        do {
            try await documentStore.deleteDocument(workspace)
            await refreshWorkspaces()
            if selectedWorkspaceId == workspace.id {
                selectedWorkspaceId = sortedWorkspaces.first?.id
                if let first = sortedWorkspaces.first {
                    await documentStore.selectCollection(first)
                }
            }
        } catch {
            documentStore.error = error
        }
    }
}
