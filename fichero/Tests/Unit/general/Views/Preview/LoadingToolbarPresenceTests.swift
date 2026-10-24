import Foundation
import Testing
@testable import Fichero

/// #Every-Frame-Perfect: the bottom reader toolbar must exist from the FIRST
/// frame of an image preview. It used to mount only inside ZoomableImagePreview
/// once the display image decoded, so the thumbnail/skeleton frames had no
/// bottom bar and the toolbar "flipped in" when the original arrived
/// (Daniel, 2026-08-23). StorageDisplayImageCanvas now holds the bottom edge
/// with an inert ReaderToolbar while `image == nil`.
struct LoadingToolbarPresenceTests {
    @Test func loadingFramesKeepAnInertReaderToolbar() throws {
        let source = try AppSource.text("Views/Preview/DocumentCanvas.swift")
        // The pin is structural, not stylistic: an interim ReaderToolbar,
        // gated on the not-yet-loaded state, disabled so it cannot act.
        #expect(source.contains("if image == nil {"))
        let interim = source.range(of: "if image == nil {").map { source[$0.upperBound...] }
        let window = interim.map { String($0.prefix(600)) } ?? ""
        #expect(window.contains("ReaderToolbar("),
                "the loading frames lost their bottom bar — the toolbar will flip in again")
        #expect(window.contains(".disabled(true)"),
                "the interim toolbar must be inert; live controls over a skeleton can act on nothing")
    }
}

/// #6010: the What to show glyph is on every page's bar, regions or not.
struct WhatToShowAlwaysThereTests {
    @Test func theGateNeverHidesTheGlyph() throws {
        let source = try AppSource.text("Views/Reader/ReaderToolbar.swift")
        let menu = source.range(of: "private var whatToShowMenu: some View {").map { String(source[$0.upperBound...].prefix(400)) } ?? ""
        #expect(!menu.contains("if textBoxesEnabled != nil"), "the glyph is gated on a display switch again: it goes missing on a page with none")
        #expect(menu.contains("Menu {"))
    }

    @Test func aPageWithNoRegionsStillHasTheImageSwitch() {
        #expect(ReaderToolbar.whatToShowHasSwitches(hasTextBoxes: false, hasAnnotations: false, hasImage: true))
        #expect(!ReaderToolbar.whatToShowHasSwitches(hasTextBoxes: false, hasAnnotations: false, hasImage: false))
    }
}

/// #6032: a folder's empty cached children are fetched again, so its canvas appears once items exist.
struct FolderChildrenEmptyCacheTests {
    @Test func anEmptyCacheIsNotTrusted() throws {
        let source = try AppSource.text("Models/DocumentStore.swift")
        #expect(source.contains("if let cached = childrenCache[documentId], !cached.isEmpty {"))
    }
}
