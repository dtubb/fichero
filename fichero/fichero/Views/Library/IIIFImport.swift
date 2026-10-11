import FicheroAPIClient
import SwiftUI

// Import from IIIF (#5671): File › Import from IIIF… into a folder bound to the source, as a job in Activity; and a
// bound folder's source, with Refresh, in its Inspector.

/// What File › Import from IIIF… acts on: the key window's project's store, and the folder its Items pane shows.
struct IIIFImportTarget {
    let store: IIIFImportStore
    let folderId: String?
    let folderName: String?
}

extension FocusedValues {
    @Entry var iiifImport: IIIFImportTarget?
}

/// File › Import from IIIF….
struct FocusedIIIFImportButton: View {
    @FocusedValue(\.iiifImport) private var target

    var body: some View {
        Button("Import from IIIF…") { target?.store.isChoosing = true }
            .disabled(target == nil)
    }
}

/// The sheet: a manifest or collection URL (https only), the folder it goes into, Import.
struct IIIFImportSheet: View {
    let target: IIIFImportTarget
    @State private var text = ""
    @State private var intoShownFolder = false

    private var source: URL? { IIIFImportStore.source(from: text) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Import from IIIF").font(.headline)
            Text("Paste a manifest or collection address. The pages come in by reference, and no image is fetched "
                 + "until a step or a view needs it.")
                .font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            TextField("Manifest or collection", text: $text, prompt: Text("https://…/manifest.json"))
                .textFieldStyle(.roundedBorder)
            if !text.isEmpty, source == nil {
                Text("An https address of a IIIF manifest or collection.").font(.caption).foregroundStyle(.orange)
            }
            Picker("Into", selection: $intoShownFolder) {
                Text("A new folder named after the source").tag(false)
                if let name = target.folderName, target.folderId != nil { Text("The folder shown: \(name)").tag(true) }
            }
            .pickerStyle(.inline)
            if let refusal = target.store.refusal {
                Label(refusal, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            HStack {
                if target.store.isStarting { ProgressView().controlSize(.small) }
                Spacer()
                Button("Cancel") { target.store.isChoosing = false }
                    .keyboardShortcut(.cancelAction)
                Button("Import") {
                    guard let source else { return }
                    Task {
                        if await target.store.importSource(source, into: intoShownFolder ? target.folderId : nil) {
                            target.store.isChoosing = false
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(source == nil || target.store.isStarting)
            }
        }
        .padding()
        .frame(minWidth: 480)
    }
}

/// File › Import from IIIF… on the Items pane: published for the menu, and the sheet.
struct IIIFImportPresenter: ViewModifier {
    let target: IIIFImportTarget?

    func body(content: Content) -> some View {
        content
            .focusedSceneValue(\.iiifImport, target)
            .sheet(isPresented: Binding(get: { target?.store.isChoosing ?? false },
                                        set: { target?.store.isChoosing = $0 })) {
                if let target { IIIFImportSheet(target: target) }
            }
    }
}

/// A folder bound to a IIIF source, in its Inspector: where it comes from, how many pages, when it was last read,
/// and Refresh (one job in Activity).
struct IIIFFolderInspectorSection: View {
    let document: Document
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?

    private var store: IIIFImportStore? {
        documentStore.flatMap { libraryManager?.library(owningService: $0)?.iiifStore }
    }

    var body: some View {
        if let source = IIIFFolderSource.of(document) {
            VStack(alignment: .leading, spacing: 6) {
                Label("IIIF source", systemImage: "globe").font(.headline)
                if let url = URL(string: source.url) {
                    Link(source.url, destination: url).font(.callout).lineLimit(2)
                } else {
                    Text(source.url).font(.callout).lineLimit(2)
                }
                if let counts = source.countsSentence { Text(counts).font(.caption).foregroundStyle(.secondary) }
                if let rights = source.rights { Text(rights).font(.caption).foregroundStyle(.secondary) }
                if let store {
                    HStack {
                        Button("Refresh") { Task { await store.refresh(folderId: document.id) } }
                            .controlSize(.small)
                            .disabled(store.isStarting)
                            .help("Read the source again: new pages are added, none is made twice")
                        if store.isStarting { ProgressView().controlSize(.small) }
                    }
                    if let refusal = store.refusal { Text(refusal).font(.caption).foregroundStyle(.orange) }
                }
            }
            .padding(8)
            .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 6))
        }
    }
}

extension LibraryView {
    /// The document id of the folder the Items pane shows (its sidebar id is "doc:<id>"), as the engine's routes take
    /// it; nil at the project's top.
    var shownFolderDocumentId: String? {
        folderId.map { $0.hasPrefix("doc:") ? String($0.dropFirst(4)) : $0 }
    }

    /// That folder's name, when the store holds it.
    var shownFolderName: String? {
        guard let id = shownFolderDocumentId, let folder = documentStore.selectedCollection, folder.id == id else {
            return nil
        }
        return DocumentTitle.displayName(for: folder)
    }
}

#Preview("Import from IIIF") {
    IIIFImportSheet(target: IIIFImportTarget(
        store: IIIFImportStore(client: FicheroClient(libraryPath: nil)), folderId: "f1", folderName: "Letters"
    ))
}
