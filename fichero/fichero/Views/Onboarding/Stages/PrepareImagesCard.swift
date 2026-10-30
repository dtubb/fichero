import FicheroAPIClient
import OpenAPIRuntime
import SwiftUI

/// What the Prepare Images card shows besides its questions: the engine's sentence naming the operations, an answer
/// suggested from five sample pages ("3 of 5 pages agree") with a Use button, and the time line
/// (`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`). The engine
/// writes every word; this view only lays them out (`GET /api/recipes/prepare-images/facts`).
struct PrepareImagesCard: View {
    let store: RecipeSetupStore
    /// The project's folders, for a folder's own answers (`BakeoffStore.Folder.folders(in:)`).
    var folders: [BakeoffStore.Folder] = []
    /// The project's actions, for answering a page on the worklist (each answer is one audited action with Undo).
    var actionsService: ActionsService?

    /// The engine's suggestions by question key; the schema does not require them, so none is an empty list.
    static func suggestions(of facts: Components.Schemas.PrepareImagesFacts) -> [String: Components.Schemas.PrepareSuggestion] {
        facts.suggestions?.additionalProperties ?? [:]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let facts = store.prepareFacts {
                if !facts.howItWorks.isEmpty {
                    Text(facts.howItWorks).font(.callout).fixedSize(horizontal: false, vertical: true)
                }
                let suggestions = Self.suggestions(of: facts)
                ForEach(suggestions.keys.sorted(), id: \.self) { key in
                    if let suggestion = suggestions[key] {
                        HStack {
                            Text("Suggested: \(suggestion.why) (\(suggestion.agree) pages)")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button("Use") {
                                if let answer = StageAnswer.from(suggestion.value.value) {
                                    store.jobAnswers[question: key] = answer
                                }
                            }
                            .controlSize(.small)
                            .accessibilityIdentifier("prepareImages.use.\(key)")
                        }
                    }
                }
                Text(facts.estimate)
                    .font(.caption).foregroundStyle(.secondary)
                    .accessibilityIdentifier("prepareImages.estimate")
            }
            PrepareImagesCheckList(store: store, actionsService: actionsService)
            if !folders.isEmpty {
                PrepareImagesFolderAnswers(store: store, folders: folders)
            }
        }
        .task {
            await store.loadPrepareFacts()
            await store.loadPrepareCheck()
        }
    }
}

/// One folder's own answers to the two questions that can differ by folder: a picker for the folder, then "Two pages in
/// one picture?" and the paper, each either following the project or answered here (`answers.job_answers_by_folder`).
struct PrepareImagesFolderAnswers: View {
    @Bindable var store: RecipeSetupStore
    let folders: [BakeoffStore.Folder]
    @State private var folderId: String = ""

    static let paperOptions: [(id: String, title: String)] = [
        ("ruled", "Ruled or graph paper"), ("faded", "Stained or faded"), ("show-through", "Writing shows through")
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider()
            Picker("Answer for one folder", selection: $folderId) {
                Text("The whole project").tag("")
                ForEach(folders) { folder in
                    Text(store.folderAnswer("two_pages_per_image", in: folder.id) == nil
                         && store.folderAnswer("the_paper", in: folder.id) == nil
                         ? folder.name : "\(folder.name) (own answers)").tag(folder.id)
                }
            }
            .accessibilityIdentifier("prepareImages.folder.picker")
            if !folderId.isEmpty {
                twoPages
                ForEach(Self.paperOptions, id: \.id) { option in
                    Toggle(option.title, isOn: Binding(
                        get: { Self.paper(of: store, in: folderId).contains(option.id) },
                        set: { store.setFolderPaper(option.id, $0, in: folderId) }
                    ))
                    .setupCheckbox()
                    .accessibilityIdentifier("prepareImages.folder.paper.\(option.id)")
                }
                Button("Follow the project again") {
                    for question in RecipeSetupStore.folderQuestions { store.setFolderAnswer(nil, to: question, in: folderId) }
                }
                .controlSize(.small)
                .accessibilityIdentifier("prepareImages.folder.clear")
            }
        }
    }

    private var twoPages: some View {
        Picker("Two pages in one picture?", selection: Binding(
            get: { Self.twoPages(of: store, in: folderId) },
            set: { store.setFolderAnswer($0.stageAnswer, to: "two_pages_per_image", in: folderId) }
        )) {
            Text("Like the project").tag(FolderYesNo.followsProject)
            Text("Yes").tag(FolderYesNo.saysYes)
            Text("No").tag(FolderYesNo.saysNo)
        }
        .accessibilityIdentifier("prepareImages.folder.twoPages")
    }

    static func twoPages(of store: RecipeSetupStore, in folder: String) -> FolderYesNo {
        if case .yesNo(let flag)? = store.folderAnswer("two_pages_per_image", in: folder) { return flag ? .saysYes : .saysNo }
        return .followsProject
    }

    static func paper(of store: RecipeSetupStore, in folder: String) -> [String] {
        if case .many(let list)? = store.folderAnswer("the_paper", in: folder) { return list }
        return []
    }
}

/// A folder's answer to a yes-or-no question: its own, or the project's.
enum FolderYesNo: Hashable {
    case followsProject, saysYes, saysNo

    var stageAnswer: StageAnswer? {
        switch self {
        case .followsProject: nil
        case .saysYes: .yesNo(true)
        case .saysNo: .yesNo(false)
        }
    }
}

#Preview("Prepare Images card") {
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    let ruled = (try? OpenAPIValueContainer(unvalidatedValue: ["ruled"])) ?? "ruled"
    store.prepareFacts = .init(
        suggestions: .init(additionalProperties: [
            "the_paper": .init(value: ruled, agree: "4 of 5", why: "the sample shows ruled paper")
        ]),
        estimate: "About 2 min for 374 pages on this Mac (estimate). Nothing leaves this Mac.",
        howItWorks: "Finds each page, squares it, turns it upright and straightens it.")
    return PrepareImagesCard(store: store).padding().frame(width: 420)
}
