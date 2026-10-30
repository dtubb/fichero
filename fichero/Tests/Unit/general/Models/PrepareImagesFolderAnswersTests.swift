//
//  PrepareImagesFolderAnswersTests.swift
//  FicheroTests
//
//  SPEC-BEHAVIOR (`prep.setup.three-questions-suggested-from-a-sample`, #5580): a folder's own answers to Prepare Images'
//  questions are kept by folder id and question key (`answers.job_answers_by_folder`), saved with the project's answers
//  and read back. Written 2026-10-30, never run (no xcodebuild in the builder lane).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct PrepareImagesFolderAnswersTests {
    private func store() -> RecipeSetupStore { RecipeSetupStore(client: FicheroClient(libraryPath: nil)) }

    @Test func aFoldersAnswersRoundTripThroughTheSavedShape() throws {
        let answers = RecipeSetupAnswers(
            jobAnswersByFolder: ["f1": ["the_paper": .many(["ruled"]), "two_pages_per_image": .yesNo(true)]])
        let json = try JSONEncoder().encode(answers)
        let object = try #require(try JSONSerialization.jsonObject(with: json) as? [String: Any])
        let byFolder = try #require(object["job_answers_by_folder"] as? [String: [String: Any]])
        #expect(byFolder["f1"]?["two_pages_per_image"] as? Bool == true)
        #expect(byFolder["f1"]?["the_paper"] as? [String] == ["ruled"])
        let back = try JSONDecoder().decode(RecipeSetupAnswers.self, from: json)
        #expect(back.jobAnswersByFolder == answers.jobAnswersByFolder)
    }

    @Test func aProjectSavedBeforeHasNoFolderAnswers() throws {
        let back = try JSONDecoder().decode(RecipeSetupAnswers.self, from: Data(#"{"purposes": ["transcribe"]}"#.utf8))
        #expect(back.jobAnswersByFolder == nil)
    }

    @Test func settingAFolderAnswerKeepsTheOthersAndTakingItBackDropsAnEmptyFolder() {
        let store = store()
        store.setFolderAnswer(.yesNo(false), to: "two_pages_per_image", in: "f1")
        store.setFolderPaper("ruled", true, in: "f1")
        store.setFolderPaper("show-through", true, in: "f1")
        store.setFolderPaper("ruled", false, in: "f1")
        #expect(store.folderAnswer("the_paper", in: "f1") == .many(["show-through"]))
        #expect(store.folderAnswer("two_pages_per_image", in: "f1") == .yesNo(false))
        #expect(store.folderAnswer("the_paper", in: "f2") == nil)
        for question in RecipeSetupStore.folderQuestions { store.setFolderAnswer(nil, to: question, in: "f1") }
        #expect(store.foldersWithOwnAnswers.isEmpty)
    }

    @Test func theFolderPickerAnswerMapsToTheStageAnswer() {
        #expect(FolderYesNo.followsProject.stageAnswer == nil)
        #expect(FolderYesNo.saysYes.stageAnswer == .yesNo(true))
        #expect(FolderYesNo.saysNo.stageAnswer == .yesNo(false))
        let store = store()
        #expect(PrepareImagesFolderAnswers.twoPages(of: store, in: "f1") == .followsProject)
        store.setFolderAnswer(.yesNo(true), to: "two_pages_per_image", in: "f1")
        #expect(PrepareImagesFolderAnswers.twoPages(of: store, in: "f1") == .saysYes)
        #expect(PrepareImagesFolderAnswers.paper(of: store, in: "f1").isEmpty)
    }
}
