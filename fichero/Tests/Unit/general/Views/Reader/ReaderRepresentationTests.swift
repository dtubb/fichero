@testable import Fichero
import Testing
import XCTest

// The reader's representation switcher (Daniel, 2026-08-29): Content plus the
// representation types the scope actually HAS — never a toggle to nowhere.
struct ReaderRepresentationTests {
    @Test("only text representation types that exist are offered, in display order")
    func availableTypesFiltersAndOrders() {
        let types = ReaderRepresentation.availableTypes(
            in: ["translation", "segmentation", "transcription", "translation", "text_geometry"]
        )
        #expect(types == ["transcription", "translation"])
    }

    @Test("structural artifact types never appear")
    func structuralTypesExcluded() {
        #expect(ReaderRepresentation.availableTypes(
            in: ["segmentation", "grouping", "entities", "text_geometry"]
        ).isEmpty)
    }

    @Test("known types get reader-facing titles; unknown ones stay legible")
    func titles() {
        #expect(ReaderRepresentation.title(for: "transcription") == "Transcript")
        #expect(ReaderRepresentation.title(for: "translation") == "Translation")
        #expect(ReaderRepresentation.title(for: "diplomatic") == "Diplomatic")
    }
}

// A page maps to its parent; a region node maps to its parent too — the
// region-scoped reader is a view OF the parent (Daniel, 2026-08-29).
struct ReaderKGDocumentMappingTests {
    @Test("a page reads through its parent")
    func pageMapsToParent() {
        let page = Document(id: "p1", parentId: "pdf", docType: .page, name: "Page 1")
        #expect(ReadingPaneView.kgDocumentId(for: page) == "pdf")
    }

    @Test("a region node reads through its parent")
    func regionMapsToParent() {
        let doc = Document(
            id: "e1", parentId: "sheet", docType: .file, name: "1933-01-10",
            regionInParent: DocumentRegion(rect: [0, 0, 1, 0.5], space: "normalized")
        )
        #expect(ReadingPaneView.kgDocumentId(for: doc) == "sheet")
    }

    @Test("an ordinary file reads as itself")
    func fileMapsToItself() {
        let doc = Document(id: "f1", parentId: "folder", docType: .file, name: "Letter.pdf")
        #expect(ReadingPaneView.kgDocumentId(for: doc) == "f1")
    }
}

// Breadcrumb honesty (Daniel, 2026-08-29): N>1 selected must SAY "N items".
struct PaneCrumbMultiSelectionTests {
    @Test("the multi-selection crumb states the count and is not navigable")
    func multiSelectionCrumb() {
        let crumb = PaneCrumb.multiSelection(count: 3)
        #expect(crumb.title == "3 items")
        #expect(crumb.isNavigable == false)
    }
}

// A workflow node cannot HAVE a transcript — the reader must say so natively,
// never let the WebKit view promise one "yet" (Daniel, 2026-08-29 evening).
// Source pin: the guard is view composition XCTest cannot instantiate.
final class ReaderWorkflowNodeGuardTests: XCTestCase {
    func testWorkflowNodesAreGuardedBeforeAnyWebKitLoad() throws {
        let tabs = try String(contentsOf: AppSource.root()
            .appendingPathComponent("Views/Reader/Page/ReadingPaneView+Tabs.swift"))
        XCTAssertTrue(
            tabs.contains("doc.isWorkflowNode"),
            "the Page lens must branch on isWorkflowNode before the WebKit surface"
        )
        XCTAssertTrue(
            tabs.contains("Workflows Have No Transcript"),
            "the empty state states impossibility, not absence"
        )
        XCTAssertTrue(
            tabs.contains("Open in Workflow Editor"),
            "the empty state offers the surface that DOES show the node"
        )
    }
}
