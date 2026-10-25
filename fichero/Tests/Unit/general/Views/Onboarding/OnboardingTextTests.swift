@testable import Fichero
import Foundation
import Testing

/// The Fable onboarding text pass (2026-10-17): the words a person reads, pinned where they carry a rule.
@MainActor
struct OnboardingTextTests {
    @Test("the downloads sentence says how much room there is")
    func freeDisk() {
        let line = RecipeDownloadRows.withFreeDisk("Start downloads X (5.7 GB): 5.8 GB in all.", free: 112_000_000_000)
        #expect(line == "Start downloads X (5.7 GB): 5.8 GB in all; 112 GB free.")
        #expect(RecipeDownloadRows.withFreeDisk("Start downloads X.", free: nil) == "Start downloads X.")
    }

    @Test("the welcome ends on the originals, and the hand-off says how many projects, not the always-there one")
    func welcomeEnd() {
        // The owner's words of 2026-10-19 (#5828) moved the projects sentence from the welcome to Your First Project.
        #expect(FirstLaunchChoices.welcomeParagraphs.last?.hasSuffix("Your originals are never changed.") == true)
        #expect(FirstLaunchChoices.handOffParagraphs.first?.hasSuffix("You can have as many as you like.") == true)
    }

    @Test("the bake-off columns and the licence sheet speak plainly")
    func plainWords() throws {
        let sheet = try AppSource.code("Views/Onboarding/BakeoffSection.swift")
        #expect(sheet.contains("Errors per 100 letters") && !sheet.contains("TableColumn(\"CER\")"))
    }
}

/// Copy is the default intake, so setup says what a copy takes before Start.
@MainActor
struct CopySpaceTests {
    @Test("the sentence names the size and the room")
    func sentence() {
        #expect(RecipeSetupStore.copySpaceSentence(bytes: 1_200_000_000, free: 112_000_000_000)
                == "The copy takes 1.2 GB; 112 GB free.")
        #expect(RecipeSetupStore.copySpaceSentence(bytes: 1_200_000_000, free: nil) == "The copy takes 1.2 GB.")
    }

    @Test("the size counts every file under a chosen folder and a loose file")
    func sizes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let sub = root.appendingPathComponent("box", isDirectory: true)
        try FileManager.default.createDirectory(at: sub, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data(count: 1000).write(to: sub.appendingPathComponent("a.jpg"))
        try Data(count: 500).write(to: sub.appendingPathComponent("b.jpg"))
        let loose = root.appendingPathComponent("c.pdf")
        try Data(count: 250).write(to: loose)
        #expect(await RecipeSetupStore.byteSize(of: [sub, loose]) == 1750)
    }
}
