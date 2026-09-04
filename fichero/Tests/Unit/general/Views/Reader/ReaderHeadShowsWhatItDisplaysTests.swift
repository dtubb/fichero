//
//  ReaderHeadShowsWhatItDisplaysTests.swift
//  FicheroTests
//
//  Daniel, live 2026-09-02: the reader pane head "has two proxy icons and
//  never says WHAT is displayed (document content vs which artifact)", and
//  with splits open "there is no way to pin a pane to what it currently
//  shows". These pin the three structural halves of that fix:
//
//   1. the artifact label names its MODEL, not a bare type and a date
//      (`ReaderArtifactLens.label` — pure, so it is tested for real);
//   2. the head's identity capsule carries ONE menu, which both NAMES what is
//      shown and offers every representation/artifact the two retired head
//      menus used to (source pin — SwiftUI menu trees are not renderable
//      off-screen, so the seam is what the source wires);
//   3. pin is a one-click TOGGLE in the shared pane chrome, not a row two
//      clicks deep inside the "+" split menu (source pin, PaneHead).
//

import Foundation
import SwiftUI
import Testing
@testable import Fichero

struct ReaderHeadShowsWhatItDisplaysTests {

    // MARK: - 1. The artifact label names the model

    @Test("an artifact is named by its type and the MODEL that wrote it")
    func artifactLabelNamesModel() {
        #expect(
            ReaderArtifactLens.label(
                type: "transcription", model: "claude-opus-5", relativeDate: "2 hours ago"
            ) == "Transcript — claude-opus-5"
        )
        #expect(
            ReaderArtifactLens.label(
                type: "translation", model: "gpt-5.6", relativeDate: "yesterday"
            ) == "Translation — gpt-5.6"
        )
    }

    @Test("with no recorded model the date is the fallback discriminator")
    func artifactLabelFallsBackToDate() {
        // A bare type would leave two rows of the same type reading
        // identically — the defect the model name fixes in the normal case.
        #expect(
            ReaderArtifactLens.label(
                type: "summary", model: nil, relativeDate: "3 days ago"
            ) == "Summary · 3 days ago"
        )
        #expect(
            ReaderArtifactLens.label(
                type: "summary", model: "   ", relativeDate: "3 days ago"
            ) == "Summary · 3 days ago"
        )
    }

    @Test("an unknown artifact type still reads legibly")
    func artifactLabelUnknownType() {
        #expect(
            ReaderArtifactLens.label(
                type: "diplomatic", model: "mlx-local", relativeDate: "now"
            ) == "Diplomatic — mlx-local"
        )
    }

    // MARK: - Source access

    private func source(_ relativePath: String) throws -> String {
        let repoRoot = try AppSource.root()
            .deletingLastPathComponent()   // fichero/ (product dir)
            .deletingLastPathComponent()   // repo root
        return try String(
            contentsOf: repoRoot.appendingPathComponent(relativePath), encoding: .utf8
        )
    }

    private var readingPaneViewPath: String {
        "fichero/fichero/Views/Reader/Page/ReadingPaneView.swift"
    }
    private var artifactLensPath: String {
        "fichero/fichero/Views/Reader/Page/Lenses/ReadingPaneView+ArtifactLens.swift"
    }
    private var paneHeadPath: String {
        "fichero/fichero/Views/Shell/PaneHead/PaneHead.swift"
    }
    private var chromeMenuPath: String {
        "fichero/fichero/Views/Shell/PaneHead/PaneChromeMenu.swift"
    }
    private var selectorPath: String {
        "fichero/fichero/Views/Shell/PaneHead/PaneKindSelector.swift"
    }

    // MARK: - 2. The head says what it is showing

    @Test("the reader's selector is handed a label naming what is displayed")
    func readerSelectorNamesWhatIsShown() throws {
        let pane = try source(readingPaneViewPath)
        #expect(
            pane.contains("shownLabel: readerShownLabel"),
            """
            The reader's PaneKindSelector must pass `shownLabel` — without it \
            the head is one glyph that reads the same whether the pane shows \
            the document's content, a translation, or a named artifact.
            """
        )
    }

    @Test("the selector renders the shown label beside its one glyph")
    func selectorRendersShownLabel() throws {
        let selector = try source(selectorPath)
        #expect(selector.contains("var shownLabel: String?"))
        #expect(
            selector.contains("Text(shownLabel)"),
            "A `shownLabel` the selector never renders is a value that changes nothing."
        )
    }

    @Test("the View menu gains the Showing submenu of representations + artifacts")
    func viewMenuCarriesShowingSubmenu() throws {
        let pane = try source(readingPaneViewPath)
        #expect(pane.contains("extraLensMenu: { self.readerShowingMenu() }"))

        let lens = try source(artifactLensPath)
        #expect(lens.contains("func readerShowingMenu() -> AnyView"))
        // Every row the two retired head menus offered survives here.
        #expect(lens.contains("Section(\"Representations\")"))
        // Artifacts are sectioned BY RUN now (Daniel, 2026-09-04) — one
        // section per producing pass, not one flat "Artifacts" wall.
        #expect(lens.contains("ForEach(artifactLensGroups) { group in"))
        #expect(lens.contains("Section(group.header)"))
        #expect(
            lens.contains("readerRepresentationChoices") && lens.contains("artifactLensGroups"),
            "The submenu must read the SAME choice lists the retired menus read."
        )
    }

    @Test("the Showing submenu can start and stop an artifact comparison")
    func showingSubmenuDrivesTheCompareLens() throws {
        let lens = try source(artifactLensPath)
        #expect(lens.contains("Menu(isComparingArtifacts ? \"Add to Comparison\" : \"Compare With\")"))
        #expect(
            lens.contains("Button(\"Stop Comparing\") { stopComparingArtifacts() }"),
            "A lens you can enter and not leave is a trap."
        )
        #expect(
            lens.contains("return \"Comparing \\(artifactCompareIds.count) artifacts\""),
            "The head SAYS what it is showing — a comparison included."
        )
    }

    @Test("the compare lens outranks every other reading of the page")
    func compareLensOutranksTheOtherLenses() throws {
        let tabs = try source("fichero/fichero/Views/Reader/Page/ReadingPaneView+Tabs.swift")
        #expect(tabs.contains("if isComparingArtifacts {"))
        #expect(tabs.contains("artifactCompareContent"))
    }

    @Test("the Showing submenu is absent when there is nothing to point the pane at")
    func showingSubmenuAbsentWhenEmpty() throws {
        let lens = try source(artifactLensPath)
        #expect(
            lens.contains(
                "guard !readerRepresentationChoices.isEmpty || !artifactLensGroups.isEmpty"
            ),
            """
            A submenu whose only row is the state you are already in is the \
            menu lying (dead-simple-UX): it must not render at all.
            """
        )
    }

    @Test("the two retired head menus are gone — one control, not three")
    func retiredHeadMenusAreGone() throws {
        let pane = try source(readingPaneViewPath)
        #expect(
            !pane.contains("self.readerRepresentationControl"),
            "The representation menu folded into the View menu's Showing submenu."
        )
        #expect(
            !pane.contains("self.artifactLensControl"),
            "The artifact-lens menu folded into the View menu's Showing submenu."
        )
        // The CSV chip is an ACTION on what is shown, not a third way to
        // choose it, so it stays in the controls capsule.
        #expect(pane.contains("self.readerTableExportControl"))
    }

    // MARK: - 3. Pin is a visible toggle in the shared pane chrome

    @Test("pin is a one-click toggle in the pane head, not a row inside the + menu")
    func pinIsAHeadToggle() throws {
        let head = try source(paneHeadPath)
        #expect(head.contains("private var pinToggle: some View"))
        #expect(head.contains("accessibilityIdentifier(\"paneHeadPinToggle\")"))
        #expect(
            head.contains("pinToggle"),
            "The toggle must actually be placed in the controls capsule."
        )
    }

    @Test("the + menu no longer carries a duplicate pin row")
    func splitMenuHasNoPinRow() throws {
        let chrome = try source(chromeMenuPath)
        #expect(
            !chrome.contains("isPinned"),
            """
            Two places to pin the same pane is two places to disagree about \
            whether it is pinned — PaneChromeMenu is the SPLIT menu now.
            """
        )
        let head = try source(paneHeadPath)
        #expect(head.contains("PaneChromeMenu(splitActions: splitAxisActions)"))
    }

    @Test("pin state stays per-PANE, so two split readers pin independently")
    func pinStateIsPerPane() throws {
        let pane = try source(readingPaneViewPath)
        #expect(
            pane.contains("@State var isPinned = false"),
            """
            @SceneStorage here would be per-WINDOW: pinning the left reader \
            would drag the right one with it, which is exactly the "both panes \
            mirror the same thing" report.
            """
        )
        // Same rule for what the pane is POINTED at.
        #expect(pane.contains("@State var readerRepresentation: String?"))
        #expect(pane.contains("@State var artifactLens: ReaderArtifactLens?"))
    }
}
