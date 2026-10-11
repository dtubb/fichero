import FicheroAPIClient
import SwiftUI

// Locate Originals (#5672): linked originals that moved, said plainly where they show (the Items pane, the
// Inspector), and found again from one sheet: File › Locate Originals…, an item's menu, or the notice's button.

extension FocusedValues {
    /// The key window's project's originals, for File › Locate Originals….
    @Entry var originals: OriginalsStore?
}

/// File › Locate Originals…: opens the sheet for the key window's project.
struct FocusedLocateOriginalsButton: View {
    @FocusedValue(\.originals) private var store

    var body: some View {
        Button("Locate Originals…") { store?.begin() }
            .disabled(store == nil)
    }
}

/// The Items pane's notice when originals are missing: the engine's sentence and the Locate button, above the rows.
struct MissingOriginalsNotice: View {
    let store: OriginalsStore
    let folderId: String?

    var body: some View {
        Group {
            if let missing = store.missing, missing.pages > 0 {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                    Text(missing.sentence).font(.callout).lineLimit(2)
                    Spacer()
                    Button("Locate Originals…") { store.begin(folderId: folderId) }
                        .controlSize(.small)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(.bar)
                .accessibilityIdentifier("library.missingOriginals")
            }
        }
        .task(id: folderId) { await store.loadMissing(folderId: folderId) }
    }
}

/// The Inspector's line for a page whose original is missing.
struct MissingOriginalNote: View {
    let store: OriginalsStore
    let documentId: String

    var body: some View {
        if store.isMissing(documentId) {
            VStack(alignment: .leading, spacing: 4) {
                Label("The original is not where the project says.", systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.orange)
                Button("Locate Originals…") { store.begin() }
                    .controlSize(.small)
            }
            .font(.callout)
        }
    }
}

/// The sheet: what is missing, the folder they are in now, the plan in words, then Relink.
struct LocateOriginalsSheet: View {
    let store: OriginalsStore
    let actionsService: ActionsService
    @Environment(WindowSteps.self) private var steps: WindowSteps?
    @State private var choosingFolder = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Locate Originals").font(.headline)
            if let missing = store.missing {
                Text(missing.sentence).font(.callout)
                if !missing.folders.isEmpty {
                    Text("They were in: " + missing.folders.prefix(5).joined(separator: ", "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(3)
                }
            } else {
                Text("Every linked original is where the project says.").font(.callout)
            }
            HStack {
                Button("Choose the Folder They Are In Now…") { choosingFolder = true }
                if let root = store.newRoot { Text(root.path).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            }
            if store.isWorking { ProgressView().controlSize(.small) }
            if let plan = store.plan {
                ForEach(OriginalsStore.lines(of: plan), id: \.self) { line in Text(line).font(.callout) }
                ForEach(plan.ambiguous.prefix(5), id: \.id) { entry in
                    Text("\(entry.name): \(entry.why ?? "more than one file matches")")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            if let refusal = store.refusal {
                Label(refusal, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            HStack {
                Spacer()
                Button("Cancel") {
                    store.cancel()
                    store.isChoosing = false
                }
                .keyboardShortcut(.cancelAction)
                Button("Relink") {
                    Task {
                        if await store.relink(actionsService: actionsService, steps: steps) { store.isChoosing = false }
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(store.plan?.matched.isEmpty ?? true || store.isWorking)
            }
        }
        .padding()
        .frame(minWidth: 480)
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            guard case .success(let folder) = result else { return }
            Task { await store.choose(folder, folderId: store.folderId) }
        }
        .task { await store.loadMissing(folderId: store.folderId) }
    }
}

/// Locate Originals on the Items pane: the notice above the rows, the sheet, and File › Locate Originals… pointed
/// at this project.
struct LocateOriginalsPresenter: ViewModifier {
    let store: OriginalsStore?
    let actionsService: ActionsService?
    let folderId: String?

    func body(content: Content) -> some View {
        content
            .safeAreaInset(edge: .top, spacing: 0) {
                if let store { MissingOriginalsNotice(store: store, folderId: folderId) }
            }
            .focusedSceneValue(\.originals, store)
            .sheet(isPresented: Binding(get: { store?.isChoosing ?? false }, set: { store?.isChoosing = $0 })) {
                if let store, let actionsService {
                    LocateOriginalsSheet(store: store, actionsService: actionsService)
                }
            }
    }
}

#Preview("The Items pane's notice") {
    MissingOriginalsNotice(store: OriginalsStore(client: FicheroClient(libraryPath: nil)), folderId: nil)
        .frame(width: 520)
}
