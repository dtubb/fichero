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
