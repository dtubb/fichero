import Foundation

/// A folder's own answers to Prepare Images' questions (`answers.job_answers_by_folder`): the same notebook is
/// photographed the same way, so one folder can differ from the project. A folder with no answer to a question follows
/// the project's.
extension RecipeSetupStore {
    /// The questions a folder can answer for itself; the engine reads these two (`start.FOLDER_QUESTIONS`).
    nonisolated static let folderQuestions = ["two_pages_per_image", "the_paper"]

    func folderAnswer(_ question: String, in folder: String) -> StageAnswer? {
        jobAnswersByFolder[folder]?[question]
    }

    /// Set a folder's answer; nil takes it back, and a folder left with no answers is dropped.
    func setFolderAnswer(_ answer: StageAnswer?, to question: String, in folder: String) {
        var mine = jobAnswersByFolder[folder] ?? [:]
        mine[question] = answer
        jobAnswersByFolder[folder] = mine.isEmpty ? nil : mine
    }

    /// Tick or untick one kind of paper in a folder's own paper answer (starting from nothing ticked).
    func setFolderPaper(_ option: String, _ isOn: Bool, in folder: String) {
        var chosen: [String] = []
        if case .many(let list)? = folderAnswer("the_paper", in: folder) { chosen = list }
        chosen.removeAll { $0 == option }
        if isOn { chosen.append(option) }
        setFolderAnswer(.many(chosen), to: "the_paper", in: folder)
    }

    /// The folders that have an answer of their own, for the line "N folders answer for themselves".
    var foldersWithOwnAnswers: [String] { jobAnswersByFolder.keys.sorted() }
}
