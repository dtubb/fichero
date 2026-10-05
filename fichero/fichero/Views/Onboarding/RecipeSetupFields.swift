import FicheroAPIClient
import SwiftUI
import UniformTypeIdentifiers

// Setup's first four screens (section 7b), as subviews `FirstRunWindow` hosts, so first run,
// Set Up New Project… and Set Up… are one flow (`source.onboard.where-it-lives`,
// `source.onboard.purpose-first`, `source.onboard.widget-and-search`,
// `source.onboard.five-questions`). A form with search, not a conversation; the answers stay
// on the project's store; nothing runs here. No disclosure anywhere (#5481).

/// Screen 1, "Where it lives" (#5482): the name, and Inside Fichero (the default) or a folder
/// the person chooses. A place that cannot be written is refused here in words.
struct SetupWhereItLivesFields: View {
    @Bindable var store: NewProjectStore
    @State private var choosingFolder = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            LabeledContent("Name") {
                TextField("Name", text: $store.name, prompt: Text("My Project"))
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
                Label("Made: \(created.displayName)", systemImage: "checkmark.circle").font(.callout)
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

/// Screen 4, "What it is for" (#5478): the engine's purposes as checkboxes, any combination, each
/// ticked purpose with its jobs in one line; then every job as a checkbox. A job a ticked purpose
/// brings is ticked and stays ticked while the purpose is (the engine adds jobs, never removes one).
struct RecipePurposeFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if store.purposeOptions.isEmpty, let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            } else if store.purposeOptions.isEmpty {
                ProgressView()
            }
            ForEach(store.purposeOptions.filter { $0.id != "not-sure" }, id: \.id) { purpose in
                VStack(alignment: .leading, spacing: 2) {
                    Toggle(isOn: Binding(get: { store.purposes.contains(purpose.id) },
                                         set: { _ in store.toggle(purpose: purpose.id) })) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(purpose.title)
                            Text(purpose.description).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .setupCheckbox()
                    if store.purposes.contains(purpose.id), let jobs = purpose.jobs, !jobs.isEmpty {
                        Text(jobs.map(\.title).joined(separator: " · "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .padding(.leading, 20)
                    }
                }
            }
            if store.purposes.isEmpty {
                Text("Not sure yet: nothing is proposed, and every tool is on hand when you want it.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if !store.jobOrder.isEmpty {
                Divider()
                Text("Jobs").font(.headline)
                ForEach(store.jobOrder, id: \.self) { job in
                    let fromPurposes = store.purposeTitles(bringing: job)
                    Toggle(store.title(ofJob: job), isOn: Binding(
                        get: { store.tickedJobs.contains(job) },
                        set: { _ in store.toggle(job: job) }
                    ))
                    .setupCheckbox()
                    .disabled(!fromPurposes.isEmpty)
                    .help(fromPurposes.isEmpty ? "" : "Part of \(fromPurposes.joined(separator: ", "))")
                }
            }
        }
        .task {
            await store.loadPurposes()
            await store.loadJobs()
        }
    }
}

/// How sources come in (ruled 2026-10-03 and 2026-10-05, `source.onboard.five-ways-in`): Link,
/// Copy, Move or Index, each with what it does to the originals. Link is the default; Move says
/// plainly that the originals go. Keep arranged is shown as not yet available: the engine has no
/// arranging yet (#5480), so it is not offered as if it worked.
struct ProjectIntakeChoice: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("How do your sources come in?").font(.headline)
            Picker("How do your sources come in?", selection: $store.ingestMode) {
                option("Link", "Fichero reads the files where they are and never changes the originals.")
                    .tag(IngestMode.link)
                option("Copy", "Fichero makes its own copy in the project; the originals are never touched.")
                    .tag(IngestMode.copy)
                option("Move", "The files move into the project, stored in the app; "
                       + "the originals are removed from where they were.")
                    .tag(IngestMode.move)
                option("Index", "Fichero works on the folder in place and writes its changes back "
                       + "into the original files, keeping that folder up to date. For folders; "
                       + "single files are linked.")
                    .tag(IngestMode.index)
            }
            .setupRadioGroup()
            .labelsHidden()
            option("Keep arranged (not available yet)",
                   "As Index, and Fichero also keeps the files in the folder arranged.")
                .foregroundStyle(.tertiary)
                .padding(.leading, 20)
            if store.ingestMode == .move {
                Label("Your original files will be removed from where they are now.",
                      systemImage: "exclamationmark.triangle")
                    .font(.callout)
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

/// Screen 2, "Your material": how sources come in, a folder to bring in now
/// (or later, from the project), and how much there is.
struct RecipeMaterialSourceFields: View {
    @Bindable var store: RecipeSetupStore
    /// The project's import path; nil where setup has no project yet.
    let importer: ImportService?
    /// The project's synced folders: an Index folder is tied there and shown below (#5480).
    var syncFolders: SyncFolderStore?
    @State private var choosingFolder = false
    @State private var adding = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ProjectIntakeChoice(store: store)
            Divider()
            HStack {
                Button("Add a Folder…") { choosingFolder = true }
                    .disabled(importer == nil || adding)
                if adding { ProgressView().controlSize(.small) }
            }
            Text("Or add material later; it comes in the way chosen above.")
                .font(.caption).foregroundStyle(.secondary)
            if let added = store.materialAdded {
                Label(added, systemImage: "checkmark.circle").font(.callout)
            }
            if let syncFolders, let path = store.tiedFolderPath, let folder = syncFolders.folder(atPath: path) {
                SyncedFolderSection(store: syncFolders, folder: folder)
            }
            if let error = store.errorMessage {
                Label(error, systemImage: "exclamationmark.triangle").foregroundStyle(.orange)
            }
            LabeledContent("Roughly how many pages") {
                TextField("Pages", value: $store.pages, format: .number).labelsHidden()
            }
        }
        .fileImporter(isPresented: $choosingFolder, allowedContentTypes: [.folder]) { result in
            guard case .success(let url) = result, let importer else { return }
            adding = true
            Task {
                await store.addFolder(url, importer: importer, syncFolders: syncFolders)
                adding = false
            }
        }
    }
}

/// Screen 5, "What it is" (#5479, #5478): languages and scripts, each found by typing and
/// shown as tokens; one direction per script, pre-filled from it; the kinds of material.
struct RecipeAboutFields: View {
    @Bindable var store: RecipeSetupStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CodeTokenField(store: store, scripts: false)
            CodeTokenField(store: store, scripts: true)
            ForEach(store.scripts, id: \.self) { code in
                VStack(alignment: .leading, spacing: 2) {
                    Picker("Direction of \(store.name(of: code))", selection: Binding(
                        get: { store.direction(of: code) },
                        set: { store.directions[code] = $0 }
                    )) {
                        ForEach(RecipeSetupStore.directionChoices, id: \.id) { Text($0.title).tag($0.id) }
                    }
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
            HStack(spacing: 16) {
                ForEach(RecipeSetupStore.materialKinds, id: \.self) { kind in
                    Toggle(kind.capitalized, isOn: Binding(
                        get: { store.materials.contains(kind) },
                        set: { on in
                            if on {
                                store.materials.append(kind)
                            } else if store.materials.count > 1 {
                                store.materials.removeAll { $0 == kind }
                            }
                        }
                    ))
                    .setupCheckbox()
                }
            }
            Text("Tick every kind there is; a reader is proposed for each.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .task(id: store.scripts) { await store.loadDerived() }
    }
}

/// What the engine worked out for one script, shown under its direction
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

    private var title: String { scripts ? "Scripts" : "Languages" }
    private var codes: [String] { scripts ? store.scripts : store.languages }
    private var unchosen: [RecipeSetupStore.CodeChoice] { matches.filter { !codes.contains($0.code) } }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            LabeledContent(title) {
                field
            }
            #if !os(macOS)
            // No text-field dropdown off the Mac: the same matches, as a list under the field.
            if !unchosen.isEmpty {
                List(unchosen, id: \.self) { match in
                    Button { take(RecipeSetupStore.completion(for: match)) } label: { MatchLabel(match: match) }
                }
                .frame(height: 160)
            }
            #endif
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
        TextField(title, text: $query, prompt: Text(scripts ? "Type to find, e.g. Latin" : "Type to find, e.g. Spanish"))
            .labelsHidden()
            #if os(macOS)
            .textInputSuggestions(unchosen, id: \.self) { match in
                MatchLabel(match: match)
                    .textInputCompletion(RecipeSetupStore.completion(for: match))
            }
            #endif
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
        HStack(spacing: 6) {
            ForEach(codes, id: \.self) { code in
                HStack(spacing: 4) {
                    Text(name(code))
                    Button { remove(code) } label: {
                        Image(systemName: "xmark.circle.fill")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Remove \(name(code))")
                }
                .font(.callout)
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

#Preview("Where it lives") {
    SetupWhereItLivesFields(store: NewProjectStore(libraryManager: LibraryManager.shared))
        .padding()
        .frame(width: 520, height: 300)
}

#Preview("What it is for") {
    RecipePurposeFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520, height: 480)
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
