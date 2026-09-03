//
//  PreviewSelectionDefaultsTests.swift
//  FicheroTests
//
//  Daniel, 2026-09-02 (build 2026.09.01.2 feedback): "Selection should
//  default on … select text, select, select words, and draw region are all
//  not working properly. They seem disconnected from bounding box process."
//
//  Root causes pinned here:
//   1. the select tool required opening the markup bar first — now armed
//      per-window from the first click;
//   2. a promoted (drawn) region VANISHED on the next geometry reload: the
//      authority ladder re-ranked artifacts and a newer transcription
//      outranked the regions artifact just written — focusing the written
//      artifact outranks the ladder;
//   3. selecting regions in the artifacts browser lit indices into an
//      artifact the preview wasn't displaying — nothing showed;
//   4. the bounding-box toggle was one global switch, so hiding boxes in one
//      split pane hid them in the other.
//

@testable import Fichero
import Foundation
import Testing

struct PreviewSelectionDefaultsTests {

    private func appSource(_ relativePath: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    // MARK: - Select is the default tool

    @Test("a window opens with the select tool armed")
    func selectDefaultsOn() throws {
        let state = try appSource("Models/WindowState.swift")
        #expect(state.contains("var activeMarkupTool: PreviewMarkupTool? = .select"),
                "select must be armed without opening the markup bar first")
    }

    @Test("the default tool keeps the plain pointer, not a crosshair")
    func selectKeepsArrowCursor() throws {
        let overlays = try appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac+Overlays.swift")
        #expect(overlays.contains("case .select: NSCursor.arrow.set()"),
                "the default tool must not put a crosshair over every page")
    }

    @Test("the select tool band-selects on empty ground")
    func selectBandSelects() throws {
        let layer = try appSource("Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift")
        #expect(layer.contains("private var isBandSelecting: Bool"))
        #expect(layer.contains("func selectRegions(inBand band: [Double])"))
        // The degenerate band still deselects — click-away must keep working.
        #expect(layer.contains("handleTap(at: start, in: size)"))
    }

    @Test("double-clicking a marquee opens its naming popover")
    func doubleClickNamesMarquee() throws {
        let layer = try appSource("Views/Preview/ImageViewer/Regions/RegionInteractionLayer.swift")
        #expect(layer.contains("naming.arm(documentId: documentId, marqueeIndex: picked)"),
                "the pencil badge must not be the only way to name a drawn region")
    }

    // MARK: - Drawn regions stay visible

    @Test("promoting a marquee focuses the artifact it wrote")
    func promoteFocusesItsArtifact() throws {
        let regions = try appSource(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Regions.swift"
        )
        let focusCalls = regions.components(
            separatedBy: "FocusedArtifact.shared.select("
        ).count - 1
        #expect(focusCalls >= 2,
                "both promote paths must focus the written artifact, or the "
                + "authority ladder re-ranks it away on the next reload")
    }

    @Test("the focused artifact outranks the authority ladder")
    func focusOutranksLadder() throws {
        // The seam the fix depends on: OCRGeometrySelection consults
        // FocusedArtifact BEFORE the ranked probe. If this goes, the promote
        // fix silently stops working.
        let selection = try appSource("Models/OCRGeometrySelection.swift")
        let focusIndex = try #require(selection.range(of: "FocusedArtifact.shared"))
        let ladderIndex = try #require(selection.range(of: "for candidate in ranked(candidates)"))
        #expect(focusIndex.lowerBound < ladderIndex.lowerBound)
    }

    @Test("selecting a region row in the artifacts browser focuses that artifact")
    func artifactRowFocuses() throws {
        let panel = try appSource("Views/Inspector/Artifacts/ArtifactPanel+Regions.swift")
        #expect(panel.contains("FocusedArtifact.shared.select("),
                "row selection must point the preview at the artifact the "
                + "indices belong to, or the selection lights nothing")
        #expect(panel.contains("fullArtifact = full"))
    }

    // MARK: - Per-pane word boxes

    @Test("the image surface's box toggle is per-pane state")
    func boxToggleIsPerPane() throws {
        let viewer = try appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        #expect(viewer.contains("@State var ocrBoxesEnabled"))
        #expect(!viewer.contains("@AppStorage(\"imagePreview.ocrBoxesEnabled\")"),
                "shared storage is the desync: hiding boxes on the left split hid the right")
        // The default is still remembered for the next pane. (Asserted on the
        // write's key, not the full call — quoting the full literal trips the
        // UserDefaults-isolation guard on a string that never executes.)
        #expect(viewer.contains(".set(enabled, forKey: \"imagePreview.ocrBoxesEnabled\")"))
    }

    // MARK: - The rendition axis is visible

    @Test("the head shows ▲▼ rendition steppers when there is something to flip")
    func renditionSteppersExist() throws {
        let controls = try appSource("Views/Shell/PaneHead/PreviewHeadControls.swift")
        #expect(controls.contains("previewHeadRenditionPrevious"))
        #expect(controls.contains("previewHeadRenditionNext"))
        // Hidden when there is nothing to flip to — a stepper with one stop
        // is the menu lying, same rule as the renditions menu.
        #expect(controls.contains("if chrome.renditionNames.count > 1"))
    }

    @Test("up-to-parent no longer wears the bare up-chevron")
    func upToParentIsNotAChevron() throws {
        // Beside the page arrows the chevron read as "rendition up" — an
        // axis it isn't (Daniel, 2026-09-02).
        let controls = try appSource("Views/Shell/PaneHead/PreviewHeadControls.swift")
        #expect(controls.contains("arrow.turn.left.up"))
    }

    @Test("a dead vertical step says why in the log")
    func deadVerticalStepIsLogged() throws {
        let viewer = try appSource("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        #expect(viewer.contains("verticalStep ignored"),
                "a silent no-op is indistinguishable from a broken gesture")
    }

    // MARK: - Loupe

    @Test("option-click parks the loupe at the click")
    func optionClickParksLoupe() throws {
        let tracking = try appSource("Views/Preview/ImageViewer/TrackingImageView.swift")
        let mouseDown = try #require(
            tracking.components(separatedBy: "override func mouseDown").last
        )
        #expect(mouseDown.contains("modifierFlags.contains(.option)"))
    }

    // MARK: - Search results own the sibling walk

    @Test("while search results show, the sibling swipe walks the results")
    func swipeWalksSearchResults() throws {
        let stepping = try appSource(
            "Views/Shell/ContentView/Actions/ContentView+SelectionStepping.swift"
        )
        #expect(stepping.contains("func stepWithinSearchResults"))
        #expect(stepping.contains("guard activeSearchQuery != nil"),
                "the walk must engage ONLY while results are the visible surface")
        #expect(!stepping.contains("displayOrdered(searchResultDocuments"),
                "relevance IS the results' order — re-sorting walks a list that isn't on screen")

        let nav = try appSource(
            "Views/Shell/ContentView/Actions/ContentView+ActionsNavigation.swift"
        )
        #expect(nav.contains("stepWithinSearchResults(forward: true"))
        #expect(nav.contains("stepWithinSearchResults(forward: false"))
    }

    // MARK: - Show Sidebar never overflows

    @Test("the sidebar toggle is owned at .navigation placement on macOS")
    func sidebarToggleNeverOverflows() throws {
        let layout = try appSource(
            "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"
        )
        #expect(layout.contains(".toolbar(removing: .sidebarToggle)"))
        #expect(layout.contains("ToolbarItem(placement: .navigation)"),
                "the owned toggle must sit where the ≫ overflow can't reach")
        #expect(layout.contains(".ownSidebarToggle"))
    }

    // MARK: - Transient storage 404s retry quietly

    @Test("a shed thumbnail 404 gets bounded quiet retries, not a dead-end banner")
    func transientStorageMissRetries() throws {
        // The storage endpoints generate a missing rendition on request but
        // shed a 404 when the generation semaphore is saturated — the normal
        // state right after an import (search-lane root cause, 2026-09-02).
        let canvas = try appSource("Views/Preview/DocumentCanvas.swift")
        #expect(canvas.contains("isTransientStorageMiss"))
        #expect(canvas.contains("for attempt in 0 ..< 3"),
                "the retry must stay bounded")
        #expect(canvas.contains("Task.sleep"), "retries back off, never hammer")
    }

    // MARK: - Inline words never truncate

    @Test("the inline word fit corrects until it actually fits")
    func inlineWordsFitWithoutEllipses() throws {
        let overlay = try appSource("Views/Preview/ImageViewer/OCRGeometryOverlay.swift")
        #expect(overlay.contains("while measured.width > rect.width"),
                "the single ratio pass could land a hair over the box and truncate with …")
        #expect(overlay.contains("passes < 3"), "the correction must stay bounded — it runs per box, per frame")
    }
}

// MARK: - The picker reaches a staged preset (B6, 2026-09-02)

struct WorkflowPickerReachesPresetTests {
    private func item(
        accepts: Bool? = true, requiresVision: Bool = true
    ) -> WorkflowSidebarItem {
        WorkflowSidebarItem(
            id: "wf1", name: "Detect Regions", description: nil,
            nodeCount: 1, edgeCount: 0, isEnabled: true,
            folderPath: "/Detect Regions", sortOrder: 10, isSystem: true,
            isUntested: false, isDirectlyRunnable: true,
            acceptsModelOverride: accepts,
            createdAt: Date(), updatedAt: Date(),
            requiresVision: requiresVision
        )
    }

    private func choice(_ provider: String, _ model: String) -> WorkflowBarModelChoice {
        WorkflowBarModelChoice(provider: provider, model: model, label: model)
    }

    @Test("a single staged vision preset rides the picker's choice")
    func singlePresetTakesPicker() {
        let step = StagedWorkflowStep(kind: .workflow(item()))
        let picked = WorkflowBarPolicy.workflowStepPickerOverride(
            for: step, stagedCount: 1,
            visionTier: choice("apple", "apple-vision"),
            selectionPrefersVision: true
        )
        #expect(picked?.provider == "apple")
    }

    @Test("a multi-step chain never gets a run-wide preset override")
    func chainStaysUntouched() {
        let step = StagedWorkflowStep(kind: .workflow(item()))
        #expect(WorkflowBarPolicy.workflowStepPickerOverride(
            for: step, stagedCount: 2,
            visionTier: choice("apple", "apple-vision"),
            selectionPrefersVision: true
        ) == nil)
    }

    @Test("a preset that refuses overrides is never overridden")
    func declaredPinIsRespected() {
        let step = StagedWorkflowStep(kind: .workflow(item(accepts: false)))
        #expect(WorkflowBarPolicy.workflowStepPickerOverride(
            for: step, stagedCount: 1,
            visionTier: choice("apple", "apple-vision"),
            selectionPrefersVision: true
        ) == nil)
    }

    @Test("a pinned step keeps its pin")
    func pinWins() {
        var pinned = StagedWorkflowStep(kind: .workflow(item()))
        pinned.providerOverride = "openrouter"
        pinned.modelOverride = "google/gemini-2.5-flash"
        #expect(WorkflowBarPolicy.workflowStepPickerOverride(
            for: pinned, stagedCount: 1,
            visionTier: choice("apple", "apple-vision"),
            selectionPrefersVision: true
        ) == nil)
    }

    @Test("a text-only preset over a text selection stays off the vision picker")
    func textPresetUntouched() {
        let step = StagedWorkflowStep(kind: .workflow(
            item(requiresVision: false)
        ))
        #expect(WorkflowBarPolicy.workflowStepPickerOverride(
            for: step, stagedCount: 1,
            visionTier: choice("apple", "apple-vision"),
            selectionPrefersVision: false
        ) == nil)
    }
}

// MARK: - Re-clicking the current folder exits search (B10)

struct SidebarReselectExitsSearchTests {
    private func appSource(_ path: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8)
    }

    @Test("the sidebar posts on a no-reroute reselect; the shell exits search")
    func reselectExitsSearch() throws {
        let sidebar = try appSource("Views/Sidebar/Sections/SidebarView+ViewComponents.swift")
        #expect(sidebar.contains("sidebarReselectedCurrent"))
        let shell = try appSource("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift")
        #expect(shell.contains(".sidebarReselectedCurrent"))
        #expect(shell.contains("if activeSearchQuery != nil { clearTransientSearch() }"))
    }
}
