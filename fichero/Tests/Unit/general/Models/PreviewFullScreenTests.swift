//
//  PreviewFullScreenTests.swift
//  FicheroTests
//
//  preview.full-screen-page (#6560): the Mac Preview head offers full screen for one page or image, and ← → turn the
//  page there. See docs/contributor_manual/specs/ui/preview-surface.md.
//

#if canImport(AppKit)
import AppKit
#endif
@testable import Fichero
import Foundation
import Testing

struct PreviewFullScreenTests {
    @Test("one page or image offers full screen")
    func aPageOrAnImageOffersFullScreen() {
        let image = Document(id: "i", docType: .file, fileType: .image, name: "0970.jpg")
        let page = Document(id: "p", docType: .page, name: "Page 3")
        #expect(PreviewFullScreen.canEnter(shown: image, selectionCount: 1))
        #expect(PreviewFullScreen.canEnter(shown: page, selectionCount: 0))
    }

    @Test("a folder, a multiple selection, a non-page file or nothing offers no full screen")
    func otherSelectionsOfferNone() {
        let image = Document(id: "i", docType: .file, fileType: .image, name: "0970.jpg")
        #expect(!PreviewFullScreen.canEnter(shown: Document(id: "f", docType: .folder, name: "Box 3"), selectionCount: 1))
        #expect(!PreviewFullScreen.canEnter(shown: image, selectionCount: 2))
        #expect(!PreviewFullScreen.canEnter(shown: Document(id: "t", docType: .file, fileType: .pdf, name: "a.pdf"),
                                            selectionCount: 1))
        #expect(!PreviewFullScreen.canEnter(shown: nil, selectionCount: 0))
    }

    @Test("a swipe turns one page: the reader's while it is up, the window's otherwise")
    func oneOwnerForTheSwipe() {
        #expect(!PreviewFullScreen.windowTakesTheSwipe(readerIsUp: true))
        #expect(PreviewFullScreen.windowTakesTheSwipe(readerIsUp: false))
    }

    #if canImport(AppKit)
    @Test("← is the previous page and → the next; with a modifier, or any other key, the key is not ours")
    func arrowKeysTurnThePage() {
        #expect(KeyboardPageStep.step(keyCode: 123, modifiers: []) == -1)
        #expect(KeyboardPageStep.step(keyCode: 124, modifiers: [.function, .numericPad]) == 1)
        #expect(KeyboardPageStep.step(keyCode: 124, modifiers: .command) == nil)
        #expect(KeyboardPageStep.step(keyCode: 123, modifiers: .shift) == nil)
        #expect(KeyboardPageStep.step(keyCode: 53, modifiers: []) == nil)  // Esc leaves; it is not a page step
    }
    #endif
}
