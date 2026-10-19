import FicheroAPIClient
import SwiftUI
import UniformTypeIdentifiers

// Setup's first three steps (section 7b, four steps ruled 2026-10-06, #5492), as subviews
// `FirstRunWindow` hosts, so first run, Set Up New Project… and Set Up… are one flow
// (`source.onboard.where-it-lives`, `source.onboard.purpose-first`,
// `source.onboard.widget-and-search`, `source.onboard.five-questions`). A form with search, not
// a conversation; the answers stay on the project's store; nothing runs here. No disclosure
// anywhere (#5481).

/// Step 1, "Your project" (#5482): the name, and Inside Fichero (the default) or a folder
/// the person chooses. A place that cannot be written is refused here in words.
struct SetupWhereItLivesFields: View {
    @Bindable var store: NewProjectStore
    @State private var choosingFolder = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            LabeledContent("Name") {
                TextField("Name", text: $store.name, prompt: Text("Untitled Project"))
                    .labelsHidden()
                    .disabled(store.created != nil)
            }
            Picker("Where it lives", selection: placeChoice) {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Inside Fichero")
                    Text("Fichero keeps it in its own folder and looks after it for you.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .tag(false)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Choose a location…")
                    Text(chosenFolderText).font(.caption).foregroundStyle(.secondary)
                        .lineLimit(2)
                        .truncationMode(.middle)
                }
                .tag(true)
            }
            .setupRadioGroup()
            .disabled(store.created != nil)
            if let url = store.projectURL {
                Text(url.path)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .lineLimit(2)
                    .truncationMode(.middle)
            }
            if let created = store.created {
                Label("Made: \(created.displayName)", systemImage: "checkmark.circle").font(.body)
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
        }
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            guard case .success(let folder) = result else { return }
            #if os(macOS)
            // A synced folder can upload the live database mid-write: say so before choosing it.
            guard NewLibraryPanel.confirmSyncedLocationIfNeeded(at: folder.appendingPathComponent(store.fileName)) else { return }
            #endif
            store.place = .chosen(folder)
        }
    }

    /// Choosing "Choose a location…" opens the folder picker at once; Inside Fichero is one click back.
    private var placeChoice: Binding<Bool> {
        Binding(
            get: { if case .chosen = store.place { true } else { false } },
            set: { chosen in
                if chosen { choosingFolder = true } else { store.place = .insideFichero }
            }
        )
    }

    private var chosenFolderText: String {
        if case .chosen(let folder) = store.place { return folder.path }
        return "A folder you pick, such as ~/Fichero; it shows in Finder."
    }
}

/// How sources come in (ruled 2026-10-18, `source.onboard.five-ways-in`): Copy, Leave in place or
/// Move, each with what it does to the originals. Copy is the default; Move says plainly that the
/// originals go. Index and Keep arranged (#5480) are set on a synced folder in the Inspector.
struct ProjectIntakeChoice: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("How do your sources come in?").font(.headline)
            Picker("How do your sources come in?", selection: Binding(
                get: { store.wayIn.shownInSetup }, set: { store.wayIn = $0 })) {
                ForEach(SetupWayIn.setupChoices) { way in
                    option(way.title, way.sentence).tag(way)
                }
            }
            .setupRadioGroup()
            .labelsHidden()
            if store.ingestMode == .move {
                Label("Your original files will be removed from where they are now.",
                      systemImage: "exclamationmark.triangle")
                    .font(.body)
                    .foregroundStyle(.orange)
            }
        }
    }

    private func option(_ title: String, _ explanation: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title)
            Text(explanation).font(.caption).foregroundStyle(.secondary)
        }
    }
}

/// Step 2, "Your material", its first half: how sources come in, a folder to bring in now
/// (or later, from the project), and how much there is.
struct RecipeMaterialSourceFields: View {
    @Bindable var store: RecipeSetupStore
    /// The project's import path; nil where setup has no project yet.
    let importer: ImportService?
    /// The project's synced folders: an Index folder is tied there and shown below (#5480).
    var syncFolders: SyncFolderStore?
    /// What of the added material is in iCloud and not on this Mac, with Copy into the Project (#5669).
    var icloud: ICloudPagesStore?
    var actionsService: ActionsService?
    @State private var choosingFolder = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ProjectIntakeChoice(store: store)
            Divider()
            HStack {
                Button("Add Files or Folders…") { chooseMaterial() }
                    .disabled(importer == nil || store.isAddingMaterial)
                    .help(importer == nil ? "Open the project first; its folder is added to it"
                          : store.isAddingMaterial ? "Adding the material…" : "Choose files or folders of material to add")
                if store.isAddingMaterial {
                    ProgressView().controlSize(.small)
                    Text(Self.progressWords(importer?.activeIngest)).font(.caption).foregroundStyle(.secondary)
                }
            }
            if let icloud { ICloudPagesNotice(store: icloud, actionsService: actionsService) }
            if let space = store.copySpace {
                Label(space, systemImage: "internaldrive").font(.body)
            }
            if let added = store.materialAdded {
                Label(added, systemImage: "checkmark.circle").font(.body)
            }
            if let syncFolders, let path = store.tiedFolderPath, let folder = syncFolders.folder(atPath: path) {
                SyncedFolderSection(store: syncFolders, folder: folder)
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
        }
        // Files or folders, several at once (section 7d). Off the Mac, the system's importer.
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder, .item],
                      allowsMultipleSelection: true) { result in
            guard case .success(let urls) = result else { return }
            add(urls)
        }
        // A project reopened with pages already in it can continue at once (#5813: Continue waits for material).
        .task { if store.startPlan == nil { await store.countPages() } }
    }

    /// The Mac's own open panel (2026-10-11): the importer inside setup's sheet did not hand back what was chosen,
    /// so nothing reached the project. The panel answers in place, with the app's access to what was chosen.
    private func chooseMaterial() {
        #if os(macOS)
        add(FolderAccessManager.shared.chooseMaterial())
        #else
        choosingFolder = true
        #endif
    }

    /// Add into THIS project, then count its pages (About the material) and say what is in iCloud.
    private func add(_ urls: [URL]) {
        guard !urls.isEmpty, let importer else { return }
        Task {
            await store.addMaterial(urls, importer: importer, syncFolders: syncFolders)
            await store.countPages()
            await icloud?.load()
        }
    }

    /// The folder import's progress in words: "120 of 184 files", or "Counting the files…" before the walk is done.
    static func progressWords(_ status: IngestTaskStatus?) -> String {
        guard let status, let total = status.total, total > 0 else { return "Adding…" }
        return "\(status.processed ?? 0) of \(total) files"
    }
}

/// Step 2, "Your material", its second half, what it is (#5479, #5478): languages and scripts, each found by typing and
/// shown as tokens (direction follows from the script, never asked, ruled 2026-10-18); the kinds of material.
struct RecipeAboutFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // The pages, counted from what was added (section 7d); a rough number only while nothing is added yet.
            if let counted = store.countedPages, counted > 0 {
                LabeledContent("Pages") { Text("\(counted), counted from what was added") }
            } else {
                LabeledContent("Roughly how many pages") {
                    TextField("Pages", value: $store.pages, format: .number).labelsHidden()
                }
            }
            CodeTokenField(store: store, scripts: false)
            CodeTokenField(store: store, scripts: true)
            if !store.proposedScripts.isEmpty {
                // #5626: the usual script of each language chosen is put in; the pages may say otherwise.
                Text("Proposed from the languages: \(store.proposedScripts.keys.sorted().map(store.name(of:)).joined(separator: ", ")). "
                     + "Remove or add writing systems if the pages are written otherwise.")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(store.scripts, id: \.self) { code in
                VStack(alignment: .leading, spacing: 2) {
                    if let facts = store.derivedScripts[code] {
                        DerivedScriptRow(facts: facts)
                    }
                }
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            Divider()
            Text("Material").font(.headline)
            Text("Handwriting, print or typescript decides which reader is tried.")
                .font(.caption).foregroundStyle(.secondary)
            FlowLayout(spacing: 16) {
                ForEach(RecipeSetupStore.materialKinds, id: \.self) { kind in
                    Toggle(kind.capitalized, isOn: Binding(
                        get: { store.materials.contains(kind) },
                        set: { isOn in
                            if isOn {
                                store.materials.append(kind)
                            } else if store.materials.count > 1 {
                                store.materials.removeAll { $0 == kind }
                            }
                        }
                    ))
                    .setupCheckbox()
                }
            }
            Divider()
            RecipeWhenWhereHandFields(store: store)
        }
        .task(id: store.scripts) { await store.loadDerived() }
        .task { await store.countPages() }
    }
}

/// What the engine worked out for one script, shown under its token
/// (`source.onboard.derives-not-asks`): a bundled font, and, for a script that may be written
/// vertically, the one thing only the pages can settle.
private struct DerivedScriptRow: View {
    let facts: Components.Schemas.ScriptFacts

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let font = facts.font {
                Text("Shown in \(font)").help(facts.fontFrom)
            }
            if facts.mayBeVertical {
                Label("May be written in vertical columns: check a page.", systemImage: "text.alignleft")
            }
        }
        .font(.caption)
        .foregroundStyle(.secondary)
    }
}

/// Languages or scripts, type-to-find only (#5479, ruled 2026-10-05: no Browse… and no
/// alphabetical list): typing shows the engine registry's matches in a dropdown under the field;
/// a pick becomes a token (its name shown, its tag or code saved); several at once; × removes.
/// Return on a typed word takes the engine's best answer (its tag, never the word); a word the
/// engine does not know is refused in words.
struct CodeTokenField: View {
    let store: RecipeSetupStore
    let scripts: Bool
    /// Called after a token is added or removed (the Inspector saves then).
    var onChange: () -> Void = {}
    @State private var query = ""
    @State private var matches: [RecipeSetupStore.CodeChoice] = []

    private var title: String { scripts ? "Writing system" : "Languages" }
    private var codes: [String] { scripts ? store.scripts : store.languages }
    private var unchosen: [RecipeSetupStore.CodeChoice] { matches.filter { !codes.contains($0.code) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            LabeledContent(title) {
                field
            }
            // The matches as the person types, under the field, on every platform
            // (`source.onboard.project.language-as-you-type`): the Mac's text-field dropdown did not show them.
            if !unchosen.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(unchosen.prefix(8), id: \.self) { match in
                        Button { take(RecipeSetupStore.completion(for: match)) } label: { MatchLabel(match: match) }
                            .buttonStyle(.plain)
                    }
                }
                .padding(6)
                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 6))
            }
            if let refusal = store.typedRefusal, refusal.scripts == scripts {
                Label(refusal.text, systemImage: "exclamationmark.triangle").font(.caption).foregroundStyle(.orange)
            }
            if !codes.isEmpty {
                FlowTokens(codes: codes, name: store.name(of:)) { code in
                    store.remove(code, fromScripts: scripts)
                    onChange()
                }
            }
        }
        .task(id: query) {
            let needle = query.trimmingCharacters(in: .whitespaces)
            guard !needle.isEmpty else { matches = []; return }
            // A pick puts its completion in the field; that is not a new search.
            guard !unchosen.contains(where: { RecipeSetupStore.completion(for: $0) == needle }) else { return }
            try? await Task.sleep(for: .milliseconds(200))  // typing: ask once the person pauses
            guard !Task.isCancelled else { return }
            matches = scripts ? await store.searchScripts(needle) : await store.searchLanguages(needle)
        }
    }

    private var field: some View {
        TextField(title, text: $query, prompt: Text(scripts ? "e.g. Latin alphabet, Arabic, Cyrillic" : "e.g. Spanish, Latin"))
            .labelsHidden()
            .onChange(of: query) { _, text in take(text) }
            .onSubmit {
                let typed = query
                if take(typed) { return }
                Task {
                    if await store.addTyped(typed, toScripts: scripts) {
                        clear()
                        onChange()
                    }
                }
            }
    }

    /// A match picked in the dropdown becomes a token and the field clears.
    @discardableResult
    private func take(_ text: String) -> Bool {
        guard store.pick(text, among: matches, toScripts: scripts) else { return false }
        clear()
        onChange()
        return true
    }

    private func clear() {
        query = ""
        matches = []
    }
}

/// One match in the dropdown: its name, and where it came from (a dialect's language, a code).
private struct MatchLabel: View {
    let match: RecipeSetupStore.CodeChoice

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(match.name)
            if let detail = match.detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

/// The chosen languages or scripts as blue lozenges, each with its name (its tag on hover) and ×.
private struct FlowTokens: View {
    let codes: [String]
    let name: (String) -> String
    let remove: (String) -> Void

    var body: some View {
        // Wraps: many languages in one row must not widen the sheet (#5624).
        FlowLayout(spacing: 6) {
            ForEach(codes, id: \.self) { code in
                HStack(spacing: 4) {
                    Text(name(code))
                    Button { remove(code) } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Remove \(name(code))")
                }
                .font(.body)
                .foregroundStyle(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 3)
                .background(Color.accentColor, in: Capsule())
                .help(code)
            }
        }
    }
}

extension View {
    /// A checkbox on the Mac; the platform's own toggle elsewhere.
    @ViewBuilder
    func setupCheckbox() -> some View {
        #if os(macOS)
        toggleStyle(.checkbox)
        #else
        self
        #endif
    }

    /// Radio buttons on the Mac; an inline list elsewhere.
    @ViewBuilder
    func setupRadioGroup() -> some View {
        #if os(macOS)
        pickerStyle(.radioGroup)
        #else
        pickerStyle(.inline)
        #endif
    }
}

#Preview("Your project") {
    SetupWhereItLivesFields(store: NewProjectStore(libraryManager: LibraryManager.shared))
        .padding()
        .frame(width: 520, height: 300)
}

#Preview("Your material") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.ingestMode = .index
    store.pages = 1200
    return RecipeMaterialSourceFields(store: store, importer: nil)
        .padding()
        .frame(width: 520, height: 480)
}

#Preview("What it is") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    store.add(.init(code: "es", name: "Spanish", detail: nil), toScripts: false)
    store.add(.init(code: "la", name: "Latin", detail: nil), toScripts: false)
    store.add(.init(code: "Latn", name: "Latin", detail: nil), toScripts: true)
    store.materials = ["handwriting", "print"]
    return RecipeAboutFields(store: store)
        .padding()
        .frame(width: 520, height: 420)
}

#Preview("Project intake") {
    ProjectIntakeChoice(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
}
