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

    @Test("the welcome's last paragraph ends on how many projects, not on the always-there one")
    func welcomeEnd() {
        #expect(FirstLaunchChoices.welcomeParagraphs.last?.hasSuffix("as many as you like.") == true)
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
    func sizes() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        let sub = root.appendingPathComponent("box", isDirectory: true)
        try FileManager.default.createDirectory(at: sub, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data(count: 1000).write(to: sub.appendingPathComponent("a.jpg"))
        try Data(count: 500).write(to: sub.appendingPathComponent("b.jpg"))
        let loose = root.appendingPathComponent("c.pdf")
        try Data(count: 250).write(to: loose)
        #expect(RecipeSetupStore.byteSize(of: [sub, loose]) == 1750)
    }
}
