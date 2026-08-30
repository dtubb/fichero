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
        #expect(ReaderRepresentation.title(for: "table") == "Table")
        #expect(ReaderRepresentation.title(for: "diplomatic") == "Diplomatic")
    }

    @Test("the table family is offered ONLY when the scope has a table artifact")
    func tableOfferedOnlyWhenPresent() {
        // Accounts → Spreadsheet (CSV) writes artifact_type "table"
        // (table_extract); with one present the switcher offers Table…
        #expect(ReaderRepresentation.availableTypes(
            in: ["transcription", "table"]
        ) == ["transcription", "table"])
        // …and with none it never does (a toggle to nowhere is the menu lying).
        #expect(!ReaderRepresentation.availableTypes(
            in: ["transcription", "translation"]
        ).contains("table"))
    }

    @Test("the annotations reading is a markup review, never an artifact type")
    func annotationsReading() {
        // Daniel, 2026-08-30 ruling 5 ("see annotations somewhere" — the
        // Marked idea): "Annotations" joins the switcher through the scope's
        // ANNOTATIONS, gated by scopeHasAnnotations — an artifact type named
        // "annotations" must never smuggle it in.
        #expect(!ReaderRepresentation.availableTypes(in: ["annotations"]).contains("annotations"))
        #expect(ReaderRepresentation.title(for: ReaderRepresentation.annotationsType) == "Annotations")
    }

    @Test("the CSV export names itself after the document, filesystem-safe")
    func exportFilename() {
        #expect(ReaderTableCSVExport.filename(forDocumentNamed: "Ledger 1933") == "Ledger 1933.csv")
        #expect(ReaderTableCSVExport.filename(forDocumentNamed: "a/b: c") == "a-b- c.csv")
        #expect(ReaderTableCSVExport.filename(forDocumentNamed: "  ") == "Table.csv")
    }

    @Test("the export vends the sidebar's artifact-promote payload with provenance")
    func exportVendsLibraryDrag() {
        let export = ReaderTableCSVExport(
            filename: "Ledger 1933.csv",
            csv: "a,b\n1,2\n",
            artifactId: "art-1",
            sourceDocumentId: "page-1",
            nodeName: "Ledger 1933"
        )
        let drag = export.libraryDrag
        // The sidebar's classifier promotes `.artifact` drags into folders,
        // stamping source_artifact_id (drag.id) and source_document_id
        // (drag.documentId) on the created node — "you know where it came from".
        #expect(drag.kind == .artifact)
        #expect(drag.id == "art-1")
        #expect(drag.documentId == "page-1")
        #expect(drag.text == "a,b\n1,2\n")
        #expect(drag.name == "Ledger 1933")
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
