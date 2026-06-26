//
//  PDFHandlingTests.swift
//  FicheroTests
//
//  Unit tests for 0.0.2 PDF-as-container behaviour (#568, #566, #567):
//    - Document.isNavigableContainer — which documents double-click navigates into
//    - PDFThumbnailView.renderThumbnail — per-page local rendering
//
//  These tests guard the contract that:
//    - PDFs are containers (double-click drills into their pages)
//    - A page Document's thumbnail renders *that specific page*, not page 0
//    - Out-of-range pageIndex and missing files return nil rather than crashing
//

import AppKit
@testable import Fichero
import Foundation
import PDFKit
import SwiftUI
import Testing

// MARK: - Document.isNavigableContainer

struct DocumentNavigationTests {

    private func makeDoc(
        docType: DocType = .file,
        fileType: FileType? = nil
    ) -> Document {
        Document(docType: docType, fileType: fileType, name: "test")
    }

    @Test("Folders are navigable containers")
    func folderIsNavigable() {
        #expect(makeDoc(docType: .folder).isNavigableContainer)
    }

    @Test("PDFs are navigable containers (pages drill-in, #568)")
    func pdfIsNavigable() {
        #expect(makeDoc(docType: .file, fileType: .pdf).isNavigableContainer)
    }

    @Test("Images are not navigable — double-click should preview")
    func imageIsNotNavigable() {
        #expect(!makeDoc(docType: .file, fileType: .image).isNavigableContainer)
    }

    @Test("Text files are not navigable")
    func textIsNotNavigable() {
        #expect(!makeDoc(docType: .file, fileType: .text).isNavigableContainer)
    }

    @Test("Word documents are not navigable")
    func wordIsNotNavigable() {
        #expect(!makeDoc(docType: .file, fileType: .word).isNavigableContainer)
    }

    @Test("Files with no fileType are not navigable")
    func untypedFileIsNotNavigable() {
        #expect(!makeDoc(docType: .file, fileType: nil).isNavigableContainer)
    }

    @Test("Page children of a PDF are not themselves navigable")
    func pageChildIsNotNavigable() {
        // A PDF page is a leaf for navigation purposes — previewing it shows
        // the page itself. Drilling into a page would have no meaning.
        #expect(!makeDoc(docType: .page, fileType: nil).isNavigableContainer)
    }

    @Test("Chunks are not navigable")
    func chunkIsNotNavigable() {
        #expect(!makeDoc(docType: .chunk, fileType: nil).isNavigableContainer)
    }

    @Test("All FileType cases have a stable navigability contract")
    func allFileTypesStable() {
        // Exactly one file type (.pdf) is navigable today.
        // If a new container format is added, update this test deliberately.
        let navigable = FileType.allCases.filter { fileType in
            Document(docType: .file, fileType: fileType, name: "x").isNavigableContainer
        }
        #expect(navigable == [.pdf])
    }
}

// MARK: - PDFThumbnailView.renderThumbnail

struct PDFThumbnailRenderingTests {

    /// Build a multi-page PDF at a temp path. Each page is a different solid
    /// color so we can distinguish which page was rendered (pages are tiny
    /// NSImage sources drawn straight onto a PDFPage).
    fileprivate static func makeMultiPagePDF(
        pageColors: [NSColor],
        size: CGSize = CGSize(width: 100, height: 140)
    ) throws -> URL {
        let pdf = PDFDocument()
        for (index, color) in pageColors.enumerated() {
            let image = NSImage(size: size)
            image.lockFocus()
            color.setFill()
            NSRect(origin: .zero, size: size).fill()
            image.unlockFocus()
            guard let page = PDFPage(image: image) else {
                throw NSError(domain: "PDFHandlingTests", code: index)
            }
            pdf.insert(page, at: index)
        }
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("fichero-pdf-test-\(UUID().uuidString).pdf")
        guard pdf.write(to: url) else {
            throw NSError(domain: "PDFHandlingTests", code: -1)
        }
        return url
    }

    @Test("Rendering page 0 of a single-page PDF produces a non-nil image")
    func rendersSinglePage() async throws {
        let url = try Self.makeMultiPagePDF(pageColors: [.red])
        defer { try? FileManager.default.removeItem(at: url) }

        let data = try Data(contentsOf: url)
        let image = await PDFThumbnailView.renderThumbnail(
            from: data,
            pageIndex: 0,
            size: CGSize(width: 200, height: 280)
        )
        #expect(image != nil)
    }

    @Test("Rendering pageIndex 1 of a 3-page PDF returns the second page, not the first")
    func rendersCorrectPageByIndex() async throws {
        // Distinct colors so average-pixel sampling can tell page 0 from page 1.
        let url = try Self.makeMultiPagePDF(pageColors: [.red, .green, .blue])
        defer { try? FileManager.default.removeItem(at: url) }

        let data = try Data(contentsOf: url)
        let page0 = await PDFThumbnailView.renderThumbnail(
            from: data, pageIndex: 0, size: CGSize(width: 60, height: 80)
        )
        let page1 = await PDFThumbnailView.renderThumbnail(
            from: data, pageIndex: 1, size: CGSize(width: 60, height: 80)
        )

        try #require(page0 != nil)
        try #require(page1 != nil)

        // Sanity: both are valid NSImages with the requested aspect.
        #expect(page0!.size.width > 0 && page0!.size.height > 0)
        #expect(page1!.size.width > 0 && page1!.size.height > 0)

        // Regression guard for #568: renderer must honor pageIndex.
        // Two pages of *different* solid colours must produce pixel-different
        // images. If pageIndex were ignored (always rendering page 0) the TIFF
        // representations would be identical.
        let tiff0 = page0!.tiffRepresentation
        let tiff1 = page1!.tiffRepresentation
        try #require(tiff0 != nil)
        try #require(tiff1 != nil)
        #expect(tiff0 != tiff1, "pageIndex: 0 and pageIndex: 1 rendered the same bytes — renderer is ignoring pageIndex")
    }

    @Test("Out-of-range pageIndex returns nil, does not crash")
    func outOfRangePageIndexReturnsNil() async throws {
        let url = try Self.makeMultiPagePDF(pageColors: [.red])
        defer { try? FileManager.default.removeItem(at: url) }

        let data = try Data(contentsOf: url)
        let image = await PDFThumbnailView.renderThumbnail(
            from: data,
            pageIndex: 99,
            size: CGSize(width: 200, height: 280)
        )
        #expect(image == nil)
    }

    @Test("Negative pageIndex returns nil")
    func negativePageIndexReturnsNil() async throws {
        let url = try Self.makeMultiPagePDF(pageColors: [.red])
        defer { try? FileManager.default.removeItem(at: url) }

        let data = try Data(contentsOf: url)
        let image = await PDFThumbnailView.renderThumbnail(
            from: data,
            pageIndex: -1,
            size: CGSize(width: 200, height: 280)
        )
        #expect(image == nil)
    }

    @Test("Invalid/empty data returns nil rather than throwing")
    func invalidDataReturnsNil() async {
        let image = await PDFThumbnailView.renderThumbnail(
            from: Data(),
            pageIndex: 0,
            size: CGSize(width: 200, height: 280)
        )
        #expect(image == nil)
    }
}

// MARK: - PDFPageView Zoom Behavior (#588)

/// Regression guard for #588: PDFKit's `autoScales` property keeps re-fitting
/// the document to the pane on every layout pass, which silently undoes user
/// pinch-zoom. The fix is a notification observer on `.PDFViewScaleChanged`
/// that disables `autoScales` as soon as any scale change happens — either
/// PDFKit's initial fit computation or the user's first pinch. These tests
/// exercise the coordinator's scale-change handler directly.
///
/// `@MainActor` because `PDFView`, `PDFPageView`, and `PDFPageView.Coordinator`
/// all touch AppKit/SwiftUI main-actor state.
@MainActor
struct PDFPageViewZoomTests {

    private func makeCoordinator(owner: PDFPageView) -> PDFPageView.Coordinator {
        PDFPageView.Coordinator(
            owner: owner,
            loupeEnabled: .constant(false),
            cursorPosition: .constant(CGPoint(x: 0.5, y: 0.5)),
            lockedPosition: .constant(CGPoint(x: 0.5, y: 0.5))
        )
    }

    @Test("#1164 pageDidChange defers selection callback outside PDFKit notification")
    func pageDidChangeDefersCallback() async throws {
        let url = try PDFThumbnailRenderingTests.makeMultiPagePDF(pageColors: [.red, .green])
        defer { try? FileManager.default.removeItem(at: url) }

        let view = PDFView()
        guard let document = PDFDocument(url: url),
              let secondPage = document.page(at: 1) else {
            Issue.record("Test PDF should contain a second page")
            return
        }
        view.document = document
        view.go(to: secondPage)

        var receivedIndex: Int?
        let owner = PDFPageView(documentId: url.path, pageIndex: 0) { index in
            receivedIndex = index
        }
        let coordinator = makeCoordinator(owner: owner)

        coordinator.pageDidChange(Notification(name: .PDFViewPageChanged, object: view))

        #expect(receivedIndex == nil, "PDF page callbacks must not mutate SwiftUI selection synchronously")
        await Task.yield()
        #expect(receivedIndex == 1)
    }

    @Test("#588 scaleDidChange disables autoScales so user pinch-zoom sticks")
    func scaleDidChangeDisablesAutoScales() throws {
        let url = try PDFThumbnailRenderingTests.makeMultiPagePDF(pageColors: [.red])
        defer { try? FileManager.default.removeItem(at: url) }

        let view = PDFView()
        view.document = PDFDocument(url: url)
        view.autoScales = true

        let owner = PDFPageView(documentId: url.path, pageIndex: 0)
        let coordinator = makeCoordinator(owner: owner)

        let notification = Notification(name: .PDFViewScaleChanged, object: view)
        coordinator.scaleDidChange(notification)

        #expect(
            view.autoScales == false,
            "autoScales must be false after any scale change, otherwise PDFKit will snap user zoom back to fit-to-pane on the next layout"
        )
    }

    @Test("#588 scaleDidChange preserves the user's current scaleFactor")
    func scaleDidChangePreservesScaleFactor() throws {
        let url = try PDFThumbnailRenderingTests.makeMultiPagePDF(pageColors: [.red])
        defer { try? FileManager.default.removeItem(at: url) }

        let view = PDFView()
        view.document = PDFDocument(url: url)
        view.autoScales = false
        view.scaleFactor = 2.5

        let owner = PDFPageView(documentId: url.path, pageIndex: 0)
        let coordinator = makeCoordinator(owner: owner)

        let notification = Notification(name: .PDFViewScaleChanged, object: view)
        coordinator.scaleDidChange(notification)

        #expect(view.autoScales == false)
        #expect(view.scaleFactor == 2.5, "handler must not modify scaleFactor")
    }

    @Test("#588 scaleDidChange ignores notifications whose object is not a PDFView")
    func scaleDidChangeIgnoresNonPDFViewNotifications() {
        let owner = PDFPageView(documentId: "/tmp/unused.pdf", pageIndex: 0)
        let coordinator = makeCoordinator(owner: owner)
        let notification = Notification(name: .PDFViewScaleChanged, object: "not a PDFView")
        coordinator.scaleDidChange(notification)
    }
}
