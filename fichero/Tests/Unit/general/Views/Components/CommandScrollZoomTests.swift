//
//  CommandScrollZoomTests.swift
//  FicheroTests
//
//  panes.chrome.command-scroll-zooms (owner 2026-11-13): ⌘ + scroll zooms, a plain scroll scrolls; the Icon grid steps
//  0.1 per scroll inside the pinch's range. See docs/contributor_manual/specs/ui/panes-workspaces.md.
//

@testable import Fichero
import Testing

struct CommandScrollZoomTests {
    @Test("⌘ + scroll up zooms in, down zooms out; without ⌘, or without movement, nothing")
    func stepNeedsCommand() {
        #expect(CommandScrollZoom.step(deltaY: 3, commandHeld: true) == 1)
        #expect(CommandScrollZoom.step(deltaY: -2, commandHeld: true) == -1)
        #expect(CommandScrollZoom.step(deltaY: 3, commandHeld: false) == nil)
        #expect(CommandScrollZoom.step(deltaY: 0, commandHeld: true) == nil)
    }

    @Test("the Icon grid moves 0.1 a step and stays within 0.5 and the pane's maximum")
    func iconScaleSteps() {
        #expect(LibraryView.iconScale(after: 1, from: 1.0, maximum: 5) == 1.1)
        #expect(LibraryView.iconScale(after: -1, from: 1.0, maximum: 5) == 0.9)
        #expect(LibraryView.iconScale(after: -1, from: 0.5, maximum: 5) == 0.5)
        #expect(LibraryView.iconScale(after: 1, from: 2.0, maximum: 2.0) == 2.0)
    }

    @Test("the page image, a PDF page and the Reader move 5% a step and stay in their own range (owner 2026-11-17)")
    func pageScaleSteps() {
        #expect(abs(CommandScrollZoom.scaled(1.0, step: 1, in: 0.5...3.0) - 1.05) < 0.0001)
        #expect(abs(CommandScrollZoom.scaled(1.0, step: -1, in: 0.5...3.0) - 1 / 1.05) < 0.0001)
        #expect(CommandScrollZoom.scaled(2.99, step: 1, in: 0.5...3.0) == 3.0)
        #expect(CommandScrollZoom.scaled(0.5, step: -1, in: 0.5...3.0) == 0.5)
    }
}
