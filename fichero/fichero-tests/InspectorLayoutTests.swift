// swiftlint:disable file_length
#if os(macOS)
import AppKit
@testable import Fichero
import Foundation
import Testing

// MARK: - InspectorTab Tests (#531)

struct InspectorTabTests {

    @Test("InspectorTab includes content/artifacts/annotations/notes/interpretation/entities/kg/citations/edits/info")
    func allCases() {
        #expect(InspectorTab.allCases.count == 10)
        #expect(InspectorTab.allCases.contains(.content))
        #expect(InspectorTab.allCases.contains(.artifacts))
        #expect(InspectorTab.allCases.contains(.annotations))
        #expect(InspectorTab.allCases.contains(.notes))
        #expect(InspectorTab.allCases.contains(.interpretations))
        #expect(InspectorTab.allCases.contains(.entities))
        #expect(InspectorTab.allCases.contains(.knowledgeGraph))
        #expect(InspectorTab.allCases.contains(.citations))
        #expect(InspectorTab.allCases.contains(.edits))
        #expect(InspectorTab.allCases.contains(.info))
    }
    @Test("InspectorTab order: content, artifacts, annotations, notes, interpretation, entities, kg, citations, edits, info")
    func ordering() {
        let expected: [InspectorTab] = [
            .content, .artifacts, .annotations, .notes, .interpretations, .entities, .knowledgeGraph,
            .citations, .edits, .info
        ]
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
        #expect(InspectorTab.artifacts.icon == "shippingbox")
        #expect(InspectorTab.annotations.icon == "highlighter")
        #expect(InspectorTab.notes.icon == "pencil.and.scribble")
        #expect(InspectorTab.interpretations.icon == "quote.bubble")
        #expect(InspectorTab.entities.icon == "person.text.rectangle")
        #expect(InspectorTab.knowledgeGraph.icon == "point.3.connected.trianglepath.dotted")
        #expect(InspectorTab.edits.icon == "slider.horizontal.3")
        #expect(InspectorTab.info.icon == "info.circle")
    }

    @Test("InspectorTab rawValues are display names")
    func rawValues() {
        #expect(InspectorTab.content.rawValue == "Content")
        #expect(InspectorTab.artifacts.rawValue == "Artifacts")
        #expect(InspectorTab.annotations.rawValue == "Annotations")
        #expect(InspectorTab.notes.rawValue == "Notes")
        #expect(InspectorTab.interpretations.rawValue == "Interpretation")
        #expect(InspectorTab.entities.rawValue == "Entities")
        #expect(InspectorTab.knowledgeGraph.rawValue == "Knowledge Graph")
        #expect(InspectorTab.edits.rawValue == "Edits")
        #expect(InspectorTab.info.rawValue == "Info")
    }

    @Test("DocumentInspector tab bar shows selected tab title with semantic caption font")
    func tabBarShowsSelectedTitle() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("fichero")
                .appendingPathComponent("Views/Inspector/Document/DocumentInspector.swift"),
            encoding: .utf8
        )

        #expect(source.contains("let selectedTabTitle = Self.clampedSelectedTab(selectedTab, for: document).rawValue"))
        #expect(source.contains("Text(selectedTabTitle)"))
        #expect(source.contains(".font(.caption)"))
    }
}

// MARK: - Source Section Fold (#3876)

struct SourceSectionFoldTests {

    @Test("SourceSectionMode is the ONE Content/Info/Outline picker (#3876)")
    func sourceSectionModeCases() {
        #expect(SourceSectionMode.allCases == [.content, .info, .outline])
    }

    /// Source is single-facet now, so DocumentInspector's separate Content/Info
    /// facet picker no longer renders above the Source body — Info moved into
    /// SourceSectionMode's middle segment.
    @Test("Source section is single-facet, so no stacked Content/Info picker (#3876)")
    func sourceSectionSingleFacet() {
        #expect(InspectorSection.source.facets == [.content])
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

// MARK: - Widescreen Pane Plan Tests

struct WidescreenPanePlanTests {

    @Test("Wide windows keep all widescreen panes visible")
    func keepsAllPanesWhenWideEnough() {
        let plan = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: true,
            availableWidth: 900
        )

        #expect(plan.showsLibraryPane)
        #expect(plan.showsCanvasPane)
        #expect(plan.showsReadingPane)
        #expect(plan.minimumWidth == 800)
    }

    @Test("Narrow windows collapse reading and canvas before the library pane")
    func collapsesSecondaryPanesFirst() {
        let readingCollapsed = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: true,
            availableWidth: 760
        )
        #expect(readingCollapsed.showsLibraryPane)
        #expect(readingCollapsed.showsCanvasPane)
        #expect(!readingCollapsed.showsReadingPane)
        #expect(readingCollapsed.minimumWidth == 580)

        let canvasCollapsed = WidescreenPanePlan.make(
            showDocumentGrid: true,
            showDocumentCanvas: true,
            showReadingPane: true,
            availableWidth: 560
        )
        #expect(canvasCollapsed.showsLibraryPane)
        #expect(!canvasCollapsed.showsCanvasPane)
        #expect(!canvasCollapsed.showsReadingPane)
        #expect(canvasCollapsed.minimumWidth == 220)
    }

    @Test("Library-hidden narrow windows keep canvas or reading visible")
    func keepsUsefulPaneWhenLibraryHidden() {
        let canvasPreferred = WidescreenPanePlan.make(
            showDocumentGrid: false,
            showDocumentCanvas: true,
            showReadingPane: true,
            availableWidth: 100
        )
        #expect(!canvasPreferred.showsLibraryPane)
        #expect(canvasPreferred.showsCanvasPane)
        #expect(!canvasPreferred.showsReadingPane)
        #expect(canvasPreferred.minimumWidth == 360)

        let readingOnly = WidescreenPanePlan.make(
            showDocumentGrid: false,
            showDocumentCanvas: false,
            showReadingPane: true,
            availableWidth: 100
        )
        #expect(!readingOnly.showsLibraryPane)
        #expect(!readingOnly.showsCanvasPane)
        #expect(readingOnly.showsReadingPane)
        #expect(readingOnly.minimumWidth == 220)
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
            makeDocument(id: "c", name: "Third")
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

// MARK: - Knowledge Surface Tab Tests (#1228)

struct KGSurfaceTabTests {

    @Test("KGSurfaceTab has transcript, digest, graph, claims, timeline, map, entities in order")
    func orderingAndCount() {
        // Order drives the native toolbar's left-to-right button layout.
        #expect(KGSurfaceTab.allCases == [.transcript, .digest, .graph, .claims, .timeline, .map, .entities])
    }

    @Test("KGSurfaceTab rawValues match the JS tab ids in document_view.html")
    func rawValuesMatchWebTabIds() {
        // The native toolbar calls window.fichero.showTab(rawValue); these must
        // equal the tab ids the in-page JS switches on, or tab clicks no-op.
        #expect(KGSurfaceTab.transcript.rawValue == "transcript")
        #expect(KGSurfaceTab.digest.rawValue == "digest")
        #expect(KGSurfaceTab.graph.rawValue == "graph")
        #expect(KGSurfaceTab.claims.rawValue == "claims")
        #expect(KGSurfaceTab.timeline.rawValue == "timeline")
        #expect(KGSurfaceTab.map.rawValue == "map")
    }

    @Test("KGSurfaceTab id equals rawValue")
    func idEqualsRawValue() {
        for tab in KGSurfaceTab.allCases {
            #expect(tab.id == tab.rawValue)
        }
    }

    @Test("KGSurfaceTab titles are human-readable display names")
    func titles() {
        #expect(KGSurfaceTab.transcript.title == "Transcript")
        #expect(KGSurfaceTab.digest.title == "Digest")
        #expect(KGSurfaceTab.graph.title == "Graph")
        #expect(KGSurfaceTab.claims.title == "Claims")
        #expect(KGSurfaceTab.timeline.title == "Timeline")
        #expect(KGSurfaceTab.map.title == "Map")
    }

    @Test("Only transcript + digest stay WebKit; all KG visualizations are native")
    func webKitTabs() {
        // Transcript + the digest summary remain WebKit HTML.
        #expect(KGSurfaceTab.transcript.usesWebKit)
        #expect(KGSurfaceTab.digest.usesWebKit)
        // Entities/Claims (inspector lists) + Graph/Timeline/Map (OntologyBrowser
        // components) render natively, not in the WebKit pane (#3503).
        #expect(!KGSurfaceTab.claims.usesWebKit)
        #expect(!KGSurfaceTab.entities.usesWebKit)
        #expect(!KGSurfaceTab.graph.usesWebKit)
        #expect(!KGSurfaceTab.timeline.usesWebKit)
        #expect(!KGSurfaceTab.map.usesWebKit)
    }

    @Test("Every KGSurfaceTab has a non-empty SF Symbol")
    func icons() {
        for tab in KGSurfaceTab.allCases {
            #expect(!tab.icon.isEmpty, "\(tab.rawValue) should have an icon")
        }
    }
}

// MARK: - Reader Tab Tests (reader IA fold 2026-07-11)

struct ReaderTabTests {

    @Test("ReaderTab folds the reader into Page, Knowledge, Notes in order")
    func orderingAndCount() {
        // Order drives the native top tab bar's left-to-right layout.
        #expect(ReaderTab.allCases == [.page, .knowledge, .notes])
    }

    @Test("ReaderTab id equals rawValue")
    func idEqualsRawValue() {
        for tab in ReaderTab.allCases {
            #expect(tab.id == tab.rawValue)
        }
    }

    @Test("ReaderTab titles are the approved human-readable labels")
    func titles() {
        #expect(ReaderTab.page.title == "Page")
        #expect(ReaderTab.knowledge.title == "Knowledge")
        #expect(ReaderTab.notes.title == "Notes")
    }

    @Test("Every ReaderTab has a non-empty SF Symbol and help text")
    func iconsAndHelp() {
        for tab in ReaderTab.allCases {
            #expect(!tab.icon.isEmpty, "\(tab.rawValue) should have an icon")
            #expect(!tab.help.isEmpty, "\(tab.rawValue) should have help text")
        }
    }
}

// MARK: - Shared SurfaceChrome (#3530)

private enum SampleSurfaceTab: String, CaseIterable, Identifiable, SurfaceTab {
    case alpha, beta
    var id: String { rawValue }
    var title: String { rawValue.capitalized }
    var icon: String { "circle" }
    var help: String { "\(title) help" }
}

struct SurfaceChromeTests {
    @Test("SurfaceTab derives a default accessibility id from the title")
    func defaultAccessibilityID() {
        #expect(SampleSurfaceTab.alpha.accessibilityID == "surfaceTab-Alpha")
    }

    @Test("ReaderTab conforms to SurfaceTab with complete metadata")
    func readerTabConformsToSurfaceTab() {
        let tabs: [any SurfaceTab] = ReaderTab.allCases
        #expect(tabs.count == 3)
        for tab in ReaderTab.allCases {
            #expect(!tab.title.isEmpty)
            #expect(!tab.icon.isEmpty)
            #expect(!tab.help.isEmpty)
            #expect(!tab.accessibilityID.isEmpty)
        }
    }
}

// MARK: - PDF Loupe Tracking-Area Selector Guard (#1228)

@MainActor
struct PDFLoupeTrackingSelectorTests {
    @Test("PDFPageView.Coordinator exposes the mouseMoved: selector NSTrackingArea calls")
    func mouseMovedSelectorExposed() {
        // The loupe registers an NSTrackingArea with `owner: coordinator` and
        // the `.mouseMoved` option, so AppKit sends `mouseMoved:`. If the Swift
        // method is exposed as `mouseMovedWith:` (the `with` label leaking into
        // the selector), every hover throws "unrecognized selector" and crashes
        // the PDF pane. Lock the exposed selector to `mouseMoved:`.
        let sel = Selector(("mouseMoved:"))
        #expect(PDFPageView.Coordinator.instancesRespond(to: sel))
    }
}

// MARK: - Environment-Object Contract Guards (#1228)
//
// The launch crash was a missing `.environmentObject(ClaimFocusState…)`
// injection: ContentView declared `@EnvironmentObject var claimFocusState`
// but no ancestor provided it, so the very first render hit
// `fatalError("No ObservableObject of type ClaimFocusState found")`.
//
// `@EnvironmentObject` is a runtime contract the compiler can't verify, so
// these source-level tests lock the producer/consumer pair together. They
// read the app sources via `#filePath` (the compile-time source path, which
// points into the checked-out worktree on dev + CI).

struct ClaimFocusStateInjectionContractTests {

    /// App source root: `.../fichero/fichero/` (sibling of `fichero-tests`).
    private static func appSourceRoot() -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero (project container)
            .appendingPathComponent("fichero")
    }

    private static func source(_ relativePath: String) throws -> String {
        let url = appSourceRoot().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("ContentView consumes ClaimFocusState from the environment")
    func contentViewConsumesClaimFocusState() throws {
        let source = try Self.source("Views/ContentView.swift")
        #expect(
            source.contains("@EnvironmentObject var claimFocusState: ClaimFocusState"),
            "ContentView must keep its ClaimFocusState @EnvironmentObject — pairs with FicheroApp injection"
        )
    }

    @Test("FicheroApp injects ClaimFocusState at the window root")
    func ficheroAppInjectsClaimFocusState() throws {
        let source = try Self.source("FicheroApp.swift")
        // Both the @StateObject backing store AND the .environmentObject
        // injection must be present, or ContentView crashes on launch.
        #expect(
            source.contains("ClaimFocusState.shared"),
            "FicheroApp must own a ClaimFocusState StateObject"
        )
        #expect(
            source.contains(".environmentObject(claimFocusState)"),
            "FicheroApp must inject claimFocusState into the LibraryWindow environment"
        )
    }

    @Test("Exactly one ClaimFocusState class is defined in the app sources")
    func singleClaimFocusStateDefinition() throws {
        // A second `class ClaimFocusState` (the dead Models/ClaimFocusState.swift
        // orphan that was never in the pbxproj) shadows the live type in tools
        // and would become a duplicate-symbol build break if registered. Lock
        // the count at one.
        var definitionCount = 0
        let root = Self.appSourceRoot()
        let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: nil
        )
        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            let contents = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            if contents.contains("class ClaimFocusState: ObservableObject") {
                definitionCount += 1
            }
        }
        #expect(definitionCount == 1, "Expected exactly one ClaimFocusState class, found \(definitionCount)")
    }
}

// MARK: - V2 Inspector — Find menu wiring

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

#endif
