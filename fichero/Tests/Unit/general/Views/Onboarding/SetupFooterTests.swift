@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The setup window's chrome, the Mac setup assistant's (ruled 2026-10-11 from Daniel's screenshot of the welcome):
/// one secondary choice at the far left, Back beside the primary (hidden, not disabled, on the first page), the
/// primary the default button at the far right, named for what it does; all navigation in the footer, none in the
/// content. And the Models & Services page's copy and accounts.
@MainActor
struct SetupFooterTests {
    private let firstRun = FirstRunWindow.flow(for: .firstRun, isCompanionPlatform: false).steps
    private var newProject: [SetupStep] {
        var flow = FirstRunWindow.flow(for: .newProject)
        flow.chosenStages = ["read", "organise"]
        return flow.steps
    }

    private func footer(_ step: SetupStep, _ steps: [SetupStep], _ mode: FirstRunWindow.Mode = .firstRun,
                        projectChosen: Bool = false, hasMaterial: Bool = true) -> SetupFooter {
        SetupFooter.of(step, in: steps, mode: mode, projectChosen: projectChosen, hasMaterial: hasMaterial)
    }

    /// WHY: Daniel's screenshot: a centred full-width capsule, a "Skip" and a disabled Back on the first page.
    @Test("the welcome: Continue the default, nothing at the left, and no Back at all (#5828)")
    func welcome() {
        let welcome = footer(.welcome, firstRun)
        #expect(welcome.leading == nil)
        #expect(welcome.primary == .init(title: "Continue", action: .advance))
        #expect(!welcome.showsBack, "the first page has no Back: hidden, not disabled")
    }

    @Test("Skip is gone: Skip This Stage on a stage, nothing where a page can't be skipped")
    func leftHandChoices() {
        #expect(footer(.whatFicheroRuns, firstRun).leading == nil, "Continue and Back only (#5828)")
        #expect(footer(.stage("read"), newProject, .firstRun).leading?.title == "Skip This Stage")
        for step in [SetupStep.project, .aboutMaterial, .stages, .ready] {  // Your Material leaves Set Up (#5813)
            #expect(footer(step, newProject, .firstRun).leading == nil, "\(step.id) cannot be skipped")
        }
        let all = (firstRun + newProject).map { footer($0, firstRun + newProject).leading?.title }
        #expect(!all.contains("Skip"), "no bare Skip anywhere")
    }

    @Test("Back shows on every page after the first, beside the primary")
    func back() {
        for step in firstRun.dropFirst() { #expect(footer(step, firstRun).showsBack) }
        #expect(!footer(.project, newProject, .newProject).showsBack, "Your project is the first page from the menu")
        #expect(footer(.addMaterial, newProject, .newProject).showsBack)
    }

    @Test("the primary says what it does: Continue, Create Project, Start; the hand-off without a project starts")
    func primaryTitles() {
        #expect(footer(.whatFicheroRuns, firstRun).primary.title == "Continue")
        #expect(footer(.project, newProject).primary.title == "Create Project")
        #expect(footer(.stages, newProject).primary.title == "Continue")
        #expect(footer(.ready, newProject).primary == .init(title: "Start", action: .start))
        // Ready's Start sits in the page's last box with the total and why it waits (#5840): no default button there.
        #expect(footer(.ready, newProject).primaryLivesInPage)
        #expect(!footer(.stages, newProject).primaryLivesInPage)
        let handOff = footer(.handOff, firstRun, projectChosen: false)
        #expect(handOff.primary == .init(title: "Set Up a New Project…", action: .setUpNewProject))
        #expect(handOff.leading == .init(title: "Start Without a Project", action: .finish))
    }

    @Test("a setup opened on purpose can always be closed from the left, where its page has no other choice")
    func closeOnPurpose() {
        #expect(footer(.addMaterial, newProject, .setUp).leading == .init(title: "Close", action: .close))
        #expect(footer(.project, newProject, .newProject).leading == .init(title: "Cancel", action: .close))
        #expect(footer(.stage("read"), newProject, .setUp).leading?.title == "Skip This Stage",
                "the page's own choice wins")
    }

    /// WHY (#5813, the owner's test of c13efa580): Continue on Your Material went on to the stages with nothing to read.
    @Test("Your Material: Continue waits for material and says why; one file lets it on; Not Now leaves Set Up")
    func continueWaitsForMaterial() {
        let empty = footer(.addMaterial, newProject, .firstRun, hasMaterial: false)
        #expect(empty.waitsFor == "Add your pages to continue")
        #expect(empty.primary == .init(title: "Continue", action: .advance))
        #expect(footer(.addMaterial, newProject, .firstRun, hasMaterial: true).waitsFor == nil, "one file is enough")
        for mode in [FirstRunWindow.Mode.firstRun, .newProject, .setUp] {
            #expect(footer(.addMaterial, newProject, mode, hasMaterial: false).leading?.action == .close,
                    "leaving Your Material leaves Set Up, never goes on to the stages")
        }
        #expect(footer(.aboutMaterial, newProject, .firstRun, hasMaterial: false).waitsFor == nil,
                "About the Material does not wait for material")
    }

    /// WHY (Test 13, owner ruling): Set Up let Continue go on with Languages blank, and every stage page then proposed nothing.
    @Test("About the Material: a blank Languages waits and says why; a language or Not sure lets Continue on")
    func continueWaitsForTheLanguage() {
        let blank = SetupFooter.of(.aboutMaterial, in: newProject, mode: .firstRun, projectChosen: true, hasLanguage: false)
        #expect(blank.waitsFor == SetupFooter.chooseTheLanguage)
        #expect(blank.primary == .init(title: "Continue", action: .advance))
        #expect(footer(.aboutMaterial, newProject).waitsFor == nil)
        #expect(footer(.addMaterial, newProject, hasMaterial: true).waitsFor == nil, "only About the Material waits for it")
    }

    @Test("Not sure is an answer: it stands alone, naming a language clears it, and the store can assemble")
    func notSureIsAnAnswer() {
        let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
        #expect(store.languageWait == SetupFooter.chooseTheLanguage, "blank is not an answer")
        store.setLanguagesNotSure(true)
        #expect(store.languagesNotSure && store.languageWait == nil && store.canAssemble)
        #expect(store.namedLanguages.isEmpty)
        store.add(.init(code: "es", name: "Spanish", detail: nil, usualScript: nil), toScripts: false)
        #expect(store.languages == ["es"] && !store.languagesNotSure, "naming a language clears Not sure")
        store.setLanguagesNotSure(true)
        store.setLanguagesNotSure(false)
        #expect(store.languages.isEmpty && store.languageWait != nil, "unticking leaves a blank, which waits again")
    }

    @Test("a stage page with no plan says why in words, never a silent empty proposal")
    func noProposalSaysWhy() {
        #expect(SetupStagePage.noProposalReason(languages: [], error: nil).contains("Not sure"))
        #expect(SetupStagePage.noProposalReason(languages: ["es"], error: "engine refused").contains("engine refused"))
        #expect(SetupStagePage.noProposalReason(languages: ["es"], error: nil).contains("still being made"))
    }

    @Test("the step list and the page say AI and ML Models")
    func modelsAndServicesName() {
        #expect(SetupStep.whatFicheroRuns.title() == "AI and ML Models")
        #expect(WhatFicheroRuns.title == "AI and ML Models")
    }

    @Test("AI and ML Models: five cards in the owner's order; every named thing is a link; Connect... is hidden (#5830)")
    func modelsCards() {
        #expect(WhatFicheroRuns.places.map(\.place) == [.thisMac, .anotherMac, .cloud, .acenet, .huggingface])
        #expect(WhatFicheroRuns.places.map(\.title) == [
            "On this Mac", "Another Mac of mine", "In the cloud", "ACENET", "Hugging Face"])
        #expect(WhatFicheroRuns.places.map(\.button) == [nil, nil, "Add a Key…", "Sign In…", "Add a Token…"],
                "Another Mac has no Connect... until pairing for reading exists (#5830)")
        #expect(WhatFicheroRuns.places[0].body.hasPrefix("Free and private: your pages never leave this Mac."))
        for link in ["https://kraken.re", "https://developer.apple.com/documentation/vision",
                     "https://huggingface.co/models", "https://github.com/ml-explore/mlx"] {
            #expect(WhatFicheroRuns.places[0].body.contains("(\(link))"), "\(link)")
        }
        #expect(WhatFicheroRuns.places[2].body.hasSuffix("says what it will cost."))
        #expect(WhatFicheroRuns.footnote == "You can change this later in Settings, and for each project.")
    }

    @Test("Add… opens Settings' own sheet on that provider; Add Another Provider… opens it to choose")
    func addOpensTheSharedSheet() {
        #expect(AddProviderRequest(providerType: "openrouter").providerType == "openrouter")
        #expect(AddProviderSheet.firstStep(preselectedType: "openrouter") == 2, "preselected: straight to its key")
        #expect(AddProviderSheet.firstStep(preselectedType: nil) == 1, "unfiltered: the list to choose from")
    }

    @Test("the welcome and the first project say what Fichero and a project are, in the owner's words")
    func copy() {
        #expect(FirstLaunchChoices.welcomeParagraphs.count == 3)
        #expect(FirstLaunchChoices.welcomeParagraphs[0].hasPrefix("Fichero is a Mac app to read and work with archives, historical documents, and manuscripts."))
        #expect(FirstLaunchChoices.welcomeParagraphs[2].hasSuffix("Your originals are never changed."))
        #expect(FirstLaunchChoices.handOffParagraphs[0].hasPrefix("Your work lives in projects."))
        #expect(FirstLaunchChoices.handOffParagraphs[1].hasSuffix("before any work starts."))
        #expect(FirstLaunchChoices.setUpNewProject == "Set Up a New Project…")
    }
}
