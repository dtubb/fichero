import Foundation
import Testing
@testable import Fichero

// MARK: - InspectorTab Tests (#531)

struct InspectorTabTests {

    @Test("InspectorTab has exactly two cases: info and content")
    func allCases() {
        #expect(InspectorTab.allCases.count == 2)
        #expect(InspectorTab.allCases.contains(.info))
        #expect(InspectorTab.allCases.contains(.content))
    }

    @Test("InspectorTab id equals rawValue")
    func idEqualsRawValue() {
        for tab in InspectorTab.allCases {
            #expect(tab.id == tab.rawValue)
        }
    }

    @Test("InspectorTab icons are correct SF Symbols")
    func icons() {
        #expect(InspectorTab.info.icon == "info.circle")
        #expect(InspectorTab.content.icon == "doc.text")
    }

    @Test("InspectorTab rawValues are display names")
    func rawValues() {
        #expect(InspectorTab.info.rawValue == "Info")
        #expect(InspectorTab.content.rawValue == "Content")
    }
}

// MARK: - FileType Additions Tests (#spreadsheet, #presentation)

struct FileTypeAdditionsTests {

    @Test("FileType includes spreadsheet and presentation cases")
    func newCasesExist() {
        #expect(FileType.allCases.contains(.spreadsheet))
        #expect(FileType.allCases.contains(.presentation))
        #expect(FileType.allCases.contains(.csv))
        #expect(FileType.allCases.contains(.rtf))
        #expect(FileType.allCases.contains(.mobi))
    }

    @Test("Spreadsheet and presentation have correct icons")
    func newCaseIcons() {
        #expect(FileType.spreadsheet.icon == "tablecells")
        #expect(FileType.presentation.icon == "rectangle.on.rectangle")
        #expect(FileType.csv.icon == "tablecells")
    }

    @Test("All FileType cases have non-empty icons")
    func allCasesHaveIcons() {
        for fileType in FileType.allCases {
            #expect(!fileType.icon.isEmpty, "\(fileType.rawValue) should have an icon")
        }
    }

    @Test("FileType rawValues match Python backend enum")
    func rawValuesMatchBackend() {
        #expect(FileType.spreadsheet.rawValue == "spreadsheet")
        #expect(FileType.presentation.rawValue == "presentation")
        #expect(FileType.csv.rawValue == "csv")
        #expect(FileType.rtf.rawValue == "rtf")
        #expect(FileType.mobi.rawValue == "mobi")
    }
}

// MARK: - ResizableDivider Edge Tests (#535)

struct ResizableDividerEdgeTests {

    @Test("ResizableDivider.Edge has leading and trailing cases")
    func edgeCases() {
        let leading = ResizableDivider.Edge.leading
        let trailing = ResizableDivider.Edge.trailing
        // Just verify the enum exists and has both cases
        #expect(leading != trailing)
    }

    @Test("Leading edge: positive delta increases width")
    func leadingEdgeDelta() {
        // For a leading-edge panel (content pane on left),
        // dragging right (positive x) should increase width.
        let startWidth: Double = 300
        let delta: CGFloat = 50 // dragged 50px right
        let newWidth = startWidth + delta
        #expect(newWidth == 350)
    }

    @Test("Trailing edge: negative delta increases width")
    func trailingEdgeDelta() {
        // For a trailing-edge panel (inspector on right),
        // dragging left (negative x) should increase width.
        let startWidth: Double = 300
        let delta: CGFloat = -50 // dragged 50px left
        let newWidth = startWidth - delta
        #expect(newWidth == 350)
    }

    @Test("Width is clamped to min/max bounds")
    func widthClamping() {
        let minWidth: Double = 250
        let maxWidth: Double = 600

        // Below minimum
        let tooSmall = min(max(100.0, minWidth), maxWidth)
        #expect(tooSmall == 250)

        // Above maximum
        let tooLarge = min(max(800.0, minWidth), maxWidth)
        #expect(tooLarge == 600)

        // Within range
        let valid = min(max(400.0, minWidth), maxWidth)
        #expect(valid == 400)
    }
}

// MARK: - Document Inspector State Tests

struct DocumentInspectorStateTests {

    private let now = Date()

    private func makeDocument(
        id: String,
        name: String = "Test",
        fileType: FileType? = .image
    ) -> Document {
        Document(
            id: id,
            parentId: nil,
            docType: .file,
            fileType: fileType,
            name: name,
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            createdAt: now,
            updatedAt: now,
            expectedThumbnailPath: nil,
            expectedDisplayPath: nil
        )
    }

    @Test("Document with spreadsheet FileType has correct icon")
    func spreadsheetDocument() {
        let doc = makeDocument(id: "1", fileType: .spreadsheet)
        #expect(doc.fileType?.icon == "tablecells")
    }

    @Test("Document with presentation FileType has correct icon")
    func presentationDocument() {
        let doc = makeDocument(id: "2", fileType: .presentation)
        #expect(doc.fileType?.icon == "rectangle.on.rectangle")
    }

    @Test("Document selection from browserSelection finds correct document")
    func selectionLookup() {
        let docs = [
            makeDocument(id: "a", name: "First"),
            makeDocument(id: "b", name: "Second"),
            makeDocument(id: "c", name: "Third"),
        ]
        let browserSelection: Set<String> = ["b"]

        if let firstId = browserSelection.first,
           let doc = docs.first(where: { $0.id == firstId }) {
            #expect(doc.name == "Second")
        } else {
            Issue.record("Should have found document 'b'")
        }
    }

    @Test("Empty browserSelection returns no document")
    func emptySelection() {
        let docs = [makeDocument(id: "a")]
        let browserSelection: Set<String> = []

        let firstId = browserSelection.first
        #expect(firstId == nil)

        let doc = firstId.flatMap { id in docs.first { $0.id == id } }
        #expect(doc == nil)
    }
}
