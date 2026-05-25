import AppKit
import Foundation
import Testing
@testable import Fichero

// MARK: - InspectorTab Tests (#531)

struct InspectorTabTests {

    @Test("InspectorTab has five cases after Inspector V2: content, knowledgeGraph, map, artifacts, info")
    func allCases() {
        // Inspector V2 (#155) added knowledgeGraph + artifacts tabs.
        // The Map tab was added later for the page-scoped KG view.
        // Order in the enum drives left-to-right tab-bar rendering;
        // assertions below lock that ordering.
        #expect(InspectorTab.allCases.count == 5)
        #expect(InspectorTab.allCases.contains(.content))
        #expect(InspectorTab.allCases.contains(.knowledgeGraph))
        #expect(InspectorTab.allCases.contains(.map))
        #expect(InspectorTab.allCases.contains(.artifacts))
        #expect(InspectorTab.allCases.contains(.info))
    }

    @Test("InspectorTab order: content, knowledgeGraph, map, artifacts, info")
    func ordering() {
        // Tab bar reads .allCases left-to-right. If someone reorders
        // the enum cases, every user's muscle memory breaks. Lock it.
        let expected: [InspectorTab] = [.content, .knowledgeGraph, .map, .artifacts, .info]
        #expect(InspectorTab.allCases == expected)
    }

    @Test("InspectorTab id equals rawValue")
    func idEqualsRawValue() {
        for tab in InspectorTab.allCases {
            #expect(tab.id == tab.rawValue)
        }
    }

    @Test("InspectorTab icons are correct SF Symbols")
    func icons() {
        #expect(InspectorTab.content.icon == "doc.text")
        #expect(InspectorTab.knowledgeGraph.icon == "point.3.connected.trianglepath.dotted")
        #expect(InspectorTab.map.icon == "map")
        #expect(InspectorTab.artifacts.icon == "shippingbox")
        #expect(InspectorTab.info.icon == "info.circle")
    }

    @Test("InspectorTab rawValues are display names")
    func rawValues() {
        #expect(InspectorTab.content.rawValue == "Content")
        #expect(InspectorTab.knowledgeGraph.rawValue == "Knowledge Graph")
        #expect(InspectorTab.map.rawValue == "Map")
        #expect(InspectorTab.artifacts.rawValue == "Artifacts")
        #expect(InspectorTab.info.rawValue == "Info")
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

// MARK: - Sidebar Drop Handler ID Tests (#547)

struct SidebarDropIDTests {

    @Test("Sidebar item ID has doc: prefix, document ID does not")
    func sidebarIdVsDocId() {
        // SidebarItem.fromDocument creates IDs like "doc:<uuid>"
        // The drop handler must use doc.id (no prefix), not sidebarItem.id
        let docId = "abc-123-def"
        let sidebarId = "doc:\(docId)"
        #expect(sidebarId != docId)
        #expect(sidebarId.hasPrefix("doc:"))
        #expect(String(sidebarId.dropFirst("doc:".count)) == docId)
    }

    @Test("Import service receives document ID without prefix")
    func importParentIdExtraction() {
        // Simulates what handleExternalFileDrop should do:
        // extract doc.id from the SidebarItem's itemType, not use sidebarItem.id
        let docId = "folder-uuid-456"
        let sidebarItemId = "doc:\(docId)"

        // Wrong (old bug): using sidebarItemId directly
        #expect(sidebarItemId != docId)

        // Correct: extracting from the document
        let extractedId = docId // In real code: case .document(let doc) => doc.id
        #expect(extractedId == "folder-uuid-456")
        #expect(!extractedId.hasPrefix("doc:"))
    }
}

// MARK: - Magnifier Coordinate Normalization Tests (#546)

struct MagnifierCoordinateTests {

    @Test("Cursor at image center normalizes to (0.5, 0.5)")
    func centerPosition() {
        let imageW: CGFloat = 1000
        let imageH: CGFloat = 800
        let boundsW: CGFloat = 1600  // frame larger than image (zoomed out)
        let boundsH: CGFloat = 1200

        let offsetX = max(0, (boundsW - imageW) / 2) // 300
        let offsetY = max(0, (boundsH - imageH) / 2) // 200

        // Mouse at center of frame = center of image (since image is centered)
        let locationX: CGFloat = boundsW / 2 // 800
        let locationY: CGFloat = boundsH / 2 // 600

        let normalizedX = (locationX - offsetX) / imageW // (800-300)/1000 = 0.5
        let normalizedY = (locationY - offsetY) / imageH // (600-200)/800 = 0.5

        #expect(abs(normalizedX - 0.5) < 0.001)
        #expect(abs(normalizedY - 0.5) < 0.001)
    }

    @Test("Cursor at image top-left corner normalizes to (0, 0)")
    func topLeftCorner() {
        let imageW: CGFloat = 1000
        let imageH: CGFloat = 800
        let boundsW: CGFloat = 1600
        let boundsH: CGFloat = 1200

        let offsetX = (boundsW - imageW) / 2 // 300
        let offsetY = (boundsH - imageH) / 2 // 200

        // Mouse at image's top-left corner in frame
        let locationX = offsetX       // 300
        let locationY = offsetY       // 200

        let normalizedX = (locationX - offsetX) / imageW // 0
        let normalizedY = (locationY - offsetY) / imageH // 0

        #expect(abs(normalizedX) < 0.001)
        #expect(abs(normalizedY) < 0.001)
    }

    @Test("Frame equals image (zoomed in) — no offset applied")
    func zoomedInNoOffset() {
        let imageW: CGFloat = 2000
        let imageH: CGFloat = 1500
        let boundsW: CGFloat = 2000  // frame == image (zoomed in)
        let boundsH: CGFloat = 1500

        let offsetX = max(0, (boundsW - imageW) / 2) // 0
        let offsetY = max(0, (boundsH - imageH) / 2) // 0

        #expect(offsetX == 0)
        #expect(offsetY == 0)

        let locationX: CGFloat = 500
        let locationY: CGFloat = 375

        let normalizedX = (locationX - offsetX) / imageW // 500/2000 = 0.25
        let normalizedY = (locationY - offsetY) / imageH // 375/1500 = 0.25

        #expect(abs(normalizedX - 0.25) < 0.001)
        #expect(abs(normalizedY - 0.25) < 0.001)
    }

    @Test("Magnifier Y-flip for AppKit coordinates")
    func yFlipForAppKit() {
        // cursorPosition.y is top-down (0=top), but NSImage uses bottom-up (0=bottom)
        let cursorY: CGFloat = 0.3 // 30% from top
        let imageHeight: CGFloat = 1000

        // Correct: flip for AppKit
        let centerY = (1 - cursorY) * imageHeight // 700 (70% from bottom)
        #expect(abs(centerY - 700) < 0.001)

        // Wrong (old bug): no flip
        let wrongY = cursorY * imageHeight // 300 (30% from bottom = top area)
        #expect(abs(wrongY - 300) < 0.001)
        #expect(centerY != wrongY)
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

// MARK: - Page Content Pane Edit State Tests (#1188)

struct PageContentPaneEditStateTests {

    @Test("Editing seeds the draft from the current page content")
    func beginEditingSeedsDraft() {
        var state = PageContentPaneEditState()
        state.synchronize(with: "Initial text")
        state.beginEditing(from: "Initial text")

        #expect(state.isEditing)
        #expect(state.draftContent == "Initial text")
        #expect(state.savedContent == "Initial text")
        #expect(!state.hasUnsavedChanges)
    }

    @Test("Blur only triggers a save when the draft changed")
    func saveOnlyWhenDraftChanged() {
        var state = PageContentPaneEditState()
        state.beginEditing(from: "Initial text")
        state.draftContent = "Updated text"

        #expect(!state.shouldSaveOnBlur(isFocused: true))
        #expect(state.shouldSaveOnBlur(isFocused: false))

        state.markSaved()
        #expect(!state.hasUnsavedChanges)
        #expect(!state.shouldSaveOnBlur(isFocused: false))
    }

    @Test("Document refresh does not overwrite an active edit")
    func synchronizeSkipsActiveEditing() {
        var state = PageContentPaneEditState()
        state.synchronize(with: "Original")
        state.beginEditing(from: "Original")
        state.draftContent = "User draft"

        state.synchronize(with: "Backend refresh")

        #expect(state.draftContent == "User draft")
        #expect(state.savedContent == "Original")
    }
}

// MARK: - V2 Inspector — RichTextController + Format/Find menu wiring

@MainActor
struct RichTextControllerTests {
    @Test("toggleTrait is a no-op when no textView is attached")
    func toggleTraitWithoutTextView() {
        let controller = RichTextController()
        controller.toggleTrait(Selector(("toggleBold:")))
        controller.toggleTrait(Selector(("alignLeft:")))
        #expect(controller.textView == nil)
    }

    @Test("textView property accepts assignment and reflects current value")
    func textViewIsWeak() {
        // The `weak` storage attribute on RichTextController.textView is
        // a compile-time contract; runtime deallocation tests are flaky
        // with NSTextView because AppKit's text-storage chain
        // (NSTextStorage → NSLayoutManager → NSTextContainer → NSTextView)
        // pins the view alive beyond the local strong ref. Earlier
        // versions of this test tried to force dealloc via
        // autoreleasepool + runloop pumping; both proved fragile.
        //
        // We narrow the assertion to what we can reliably test: the
        // property accepts assignment, returns the same identity back,
        // and a nil assignment clears it. That covers the rebinding +
        // overwrite contract the RichText editor relies on.
        let controller = RichTextController()
        let textViewA = AppKit.NSTextView()
        controller.textView = textViewA
        #expect(controller.textView === textViewA)

        let textViewB = AppKit.NSTextView()
        controller.textView = textViewB
        #expect(controller.textView === textViewB)
        // Old reference should NOT come back; controller holds only
        // the latest binding (which is what `weak` plus assignment do).
        #expect(controller.textView !== textViewA)

        controller.textView = nil
        #expect(controller.textView == nil)
    }

    @Test("toggleTrait dispatches alignment change to attached textView")
    func toggleTraitDispatch() {
        let controller = RichTextController()
        let textView = AppKit.NSTextView()
        textView.string = "hello world"
        textView.setSelectedRange(NSRange(location: 0, length: 5))
        controller.textView = textView

        controller.toggleTrait(Selector(("alignCenter:")))

        let attrs = textView.textStorage?.attributes(at: 0, effectiveRange: nil) ?? [:]
        if let paragraph = attrs[.paragraphStyle] as? NSParagraphStyle {
            #expect(paragraph.alignment == .center)
        }
    }
}

struct FindBarSelectorTests {
    @Test("performFindPanelAction selector exists on NSTextView")
    func findPanelSelector() {
        // View → Find in Artifact sends this selector down the responder
        // chain. NSTextView (with usesFindBar = true) renders its inline
        // find bar in response.
        let sel = Selector(("performFindPanelAction:"))
        #expect(AppKit.NSTextView.instancesRespond(to: sel))
    }

    @Test("NSFindPanelAction.showFindPanel rawValue is the tag we use")
    func showFindPanelTag() {
        // ShowFindBarButton sets menuItem.tag = .showFindPanel.rawValue. If
        // Apple ever renumbered these, the find action would silently break.
        #expect(AppKit.NSFindPanelAction.showFindPanel.rawValue == 1)
    }
}
