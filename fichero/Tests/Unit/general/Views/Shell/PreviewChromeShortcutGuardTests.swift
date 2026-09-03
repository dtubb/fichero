import Foundation
import Testing

/// The bars' labels follow the window toolbar's own text mode (Daniel,
/// 2026-08-31: "when the top toolbar has show text on, they should also show
/// text"). `ToolbarTextModeSync` is an `NSViewRepresentable` over AppKit KVO,
/// so what is testable is the WIRING: it must be mounted by BOTH bars — a bar
/// shown alone still has to follow — and it must read the toolbar's display
/// mode as "anything but icon-only means labels".
struct ToolbarTextModeSyncMountGuardTests {
    private func workflowBarSource() throws -> String {
        let url = try AppSource.root().appendingPathComponent(
            "Views/Shell/ContentView/Layout/ContentView+WorkflowBar.swift"
        )
        return try String(contentsOf: url, encoding: .utf8)
    }

    @Test("both the annotation bar and the workflow bar mount the sync")
    func bothBarsMountIt() throws {
        let source = try workflowBarSource()
        let mounts = source.components(
            separatedBy: ".background { ToolbarTextModeSync(showsLabels: $showWorkflowBarLabels) }"
        ).count - 1
        #expect(mounts == 2, "one bar lost the toolbar sync (\(mounts) mounts)")
        // Both insets are the mount points; neither may quietly drop it.
        #expect(source.contains("var annotationBarInset: some View"))
        #expect(source.contains("AnnotationBar("))
        #expect(source.contains("showsLabels: showWorkflowBarLabels"))
    }

    @Test("anything but icon-only means labels, on attach and on every change")
    func displayModeMapsToLabels() throws {
        // The observer lives in its own file (file-length budget); the
        // mounts stay in ContentView+WorkflowBar.swift.
        let url = try AppSource.root().appendingPathComponent(
            "Views/Shell/ContentView/Layout/ToolbarTextModeSync.swift"
        )
        let source = try String(contentsOf: url, encoding: .utf8)
        let mappings = source.components(separatedBy: "displayMode != .iconOnly").count - 1
        // Attach read + KVO callback + the PUSH half (apply(showsLabels:)
        // writes displayMode from the bars' context menu, 2026-09-02) —
        // losing any of the three desyncs a direction.
        #expect(mappings == 3, "the display-mode mapping lost a site (\(mappings))")
        // String KVO: Swift 6 refuses a key path to the main-actor property.
        #expect(source.contains("addObserver(self, forKeyPath: Self.keyPath"))
        // Idempotent: re-attaching to the same toolbar must not stack observers.
        #expect(source.contains("guard let toolbar, toolbar !== observedToolbar else { return }"))
        #expect(source.contains("if showsLabels != labelled { showsLabels = labelled }"))
    }
}

/// Markup-row shortcuts (Daniel, 2026-08-31): every tool gets ⌘⌥ + a mnemonic.
/// SwiftUI resolves duplicate shortcuts SILENTLY — the loser simply stops
/// working — so the letters must be unique, and none may be "l", which
/// `ImagePreviewMenuCommands` already spends on the Loupe over this very
/// surface.
struct PreviewMarkupShortcutUniquenessTests {
    /// Every single-character key literal following `marker`.
    private func letters(after marker: String, in source: String) -> [String] {
        var found: [String] = []
        var search = source.startIndex..<source.endIndex
        while let range = source.range(of: marker, range: search) {
            let rest = source[range.upperBound...]
            if let first = rest.first, rest.dropFirst().first == "\"" {
                found.append(String(first))
            }
            search = range.upperBound..<source.endIndex
        }
        return found
    }

    private func headSource() throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Shell/PaneHead/PreviewHeadControls.swift"
            ), encoding: .utf8
        )
    }

    @Test("no two preview-head controls claim the same ⌘⌥ letter")
    func lettersAreUnique() throws {
        let source = try headSource()
        // `key:` args feed toolButton's shortcut; the highlight split-button
        // and the zoom-controls toggle bind theirs directly.
        let keys = letters(after: "key: \"", in: source)
            + letters(after: ".keyboardShortcut(\"", in: source)
        #expect(keys.count >= 9, "the markup row lost its shortcuts (\(keys.count))")
        let duplicates = Set(keys.filter { key in keys.filter { $0 == key }.count > 1 })
        #expect(duplicates.isEmpty, "duplicate ⌘⌥ letters collide silently: \(duplicates.sorted())")
    }

    @Test("no markup shortcut is \"l\" — the Loupe owns it on this surface")
    func loupeLetterIsReserved() throws {
        let source = try headSource()
        let keys = letters(after: "key: \"", in: source)
            + letters(after: ".keyboardShortcut(\"", in: source)
        #expect(!keys.contains("l"))

        // The reservation is only meaningful while the Loupe still binds it.
        let menus = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "App/Menus/ImagePreviewMenuCommands.swift"
            ), encoding: .utf8
        )
        #expect(menus.contains(".keyboardShortcut(\"l\", modifiers: [.command, .option])"))
    }
}

/// The annotation bar's SHAPE (Daniel, 2026-08-31): the three selection tools
/// first — text, rectangular, words — then Draw Region, then the marks that
/// put something on the page, then the edit verbs. Order is a ruling, not a
/// preference, so a later edit that reshuffles the row has to argue with a
/// test rather than land quietly.
struct PreviewMarkupRowOrderGuardTests {
    private func headSource() throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Shell/PaneHead/PreviewHeadControls.swift"
            ), encoding: .utf8
        )
    }

    @Test("the markup row lists its tools in the ruled order")
    func ruledOrder() throws {
        let source = try headSource()
        // Marks as they appear in `body` — identifiers for the plain tool
        // buttons, property names for the three composed ones. Each name's
        // FIRST occurrence is its call site in `body`; the declarations
        // follow further down the file.
        let ordered = [
            "previewMarkupTextSelect",
            "previewMarkupSelect",
            "previewMarkupWordSelect",
            "previewMarkupDrawRegion",
            "previewMarkupLine",
            "highlightSplitButton",
            "noteButton",
            "previewMarkupStar",
            "previewMarkupCheck",
            "editVerbs",
        ]
        var previous = source.startIndex
        for name in ordered {
            guard let found = source.range(of: name, range: previous..<source.endIndex) else {
                Issue.record("the markup row lost \(name), or it moved out of order")
                return
            }
            previous = found.upperBound
        }
    }

    @Test("Select Words says it marquees WORDS, not pixels")
    func wordSelectTooltipIsHonest() throws {
        let source = try headSource()
        // Daniel: "select words is really rectangular selection…" — both
        // rectangular tools are marquees, so the tooltip must name what this
        // one comes away holding.
        #expect(source.contains("Select Words — marquee a rectangle"))
        #expect(source.contains("WORD boxes"))
    }

    @Test("Delete and Combine appear only while regions are selected")
    func editVerbsFollowTheSelection() throws {
        let source = try headSource()
        // The verbs act on the selection, so the bar must not offer them
        // against nothing (ruling 2). Combine additionally needs two.
        #expect(source.contains("let selection = RegionSelection.shared"))
        #expect(source.contains("if !selection.isEmpty {"))
        #expect(source.contains("if selection.count >= 2 {"))
    }
}

/// Text Note, Check and Highlight over a SELECTION (Daniel, 2026-08-31,
/// rulings 3–5). Each is a wiring the row and the canvas must agree on, and
/// each was reported as "doesn't work" precisely because one end was missing.
struct PreviewMarkupSelectionVerbGuardTests {
    private func source(_ path: String) throws -> String {
        try String(
            contentsOf: AppSource.root().appendingPathComponent(path), encoding: .utf8
        )
    }

    @Test("a saved note asks for its text, and an abandoned one is deleted")
    func noteTextEntryIsWired() throws {
        let head = try source("Views/Shell/PaneHead/PreviewHeadControls.swift")
        let canvas = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Annotations.swift"
        )
        // Canvas end: the note box announces itself once saved.
        #expect(canvas.contains("name: .previewNoteTextEntry, object: firstSavedId"))
        // Row end: the popover opens on that seam and commits through the
        // SAME annotation path the box came from.
        #expect(head.contains("static let previewNoteTextEntry"))
        #expect(head.contains("publisher(for: .previewNoteTextEntry)"))
        #expect(head.contains("annotationStore.updateText(id: annotationId, text: value)"))
        // Cancel/Esc/click-away must not leave a blank note on the page.
        #expect(head.contains("guard !committed, let annotationId, let annotationStore"))
        #expect(head.contains("annotationStore.delete(id: annotationId)"))
    }

    @Test("Check and Highlight act on the selection before falling back")
    func selectionVerbsComeFirst() throws {
        let viewer = try source("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
        // Ruling 5: selected words are painted; only an empty selection arms
        // the drag. Ruling 4: a check lands on the selection when there is
        // one, else the sticky tool waits for a click.
        #expect(viewer.contains("if !highlightSelectedBoxes() { requestAnnotation(.highlight) }"))
        #expect(viewer.contains("case .check: _ = checkSelectedBoxes()"))
        // The check button has to POST for the canvas to hear it at all —
        // sticky-mode-only was why checks needed a separate click.
        let head = try source("Views/Shell/PaneHead/PreviewHeadControls.swift")
        #expect(head.contains("object: PreviewMarkupTool.check.rawValue"))
    }

    @Test("selection marks snap to one strip per line, from either selection seam")
    func selectionResolvesLikeHighlight() throws {
        let canvas = try source(
            "Views/Preview/ImageViewer/Regions/ZoomableImagePreviewMac+Annotations.swift"
        )
        // Region selection first, reader text selection second — the two
        // seams a highlight already knew about.
        #expect(canvas.contains("let selection = RegionSelection.shared"))
        #expect(canvas.contains("return linkedSelectionBoxes.map {"))
        // Per-line strips, via the helper the drag path and word-promotion
        // both use — not one page-blotting union.
        #expect(canvas.contains("AnnotationWordSnap.snappedRects("))
        // The check cycle is the CLICK path's cycle, not a second one.
        #expect(canvas.contains("RegionInteractionLayer.sameExtent("))
    }
}

/// The quiet bar's what-to-show menu (2026-08-31) is the ONE owner of the
/// page's display switches. Four entries, exact wording, and the annotation
/// switch on by default — Daniel's container had the key stuck at 0, so every
/// mark the markup row drew saved correctly and rendered invisible.
struct PreviewWhatToShowMenuGuardTests {
    @Test("the menu offers exactly the four display switches")
    func fourSwitchesByName() throws {
        let toolbar = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Reader/ReaderToolbar.swift"
            ), encoding: .utf8
        )
        for title in [
            "Show Annotations", "Show Word Bounding Boxes", "Show Regions", "Show Text Inline",
        ] {
            #expect(toolbar.contains("Toggle(\"\(title)\", isOn:"), "missing \(title)")
        }
        let toggles = toolbar.components(separatedBy: "Toggle(\"Show ").count - 1
        #expect(toggles == 4, "the what-to-show menu grew or lost a switch (\(toggles))")
    }

    @Test("annotation overlays default to ON")
    func annotationsDefaultOn() throws {
        let viewer = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift"
            ), encoding: .utf8
        )
        #expect(viewer.contains("@AppStorage(\"preview.annotationsEnabled\") var annotationsEnabled = true"))
    }

    @Test("no file owns both the image and the PDF word-box switch")
    func noCrossCanvasDesync() throws {
        // The head's old "regions" button wrote BOTH keys while the bottom
        // menu wrote one, so the two chromes disagreed about which switch was
        // which. Each key gets exactly one declaring owner, and never the same.
        let root = try AppSource.root()
        var imageOwners: [String] = []
        var pdfOwners: [String] = []
        let enumerator = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        )
        while let url = enumerator?.nextObject() as? URL {
            guard url.pathExtension == "swift",
                  let source = try? String(contentsOf: url, encoding: .utf8) else { continue }
            let name = url.lastPathComponent
            // The image switch is per-pane @State since 2026-09-02; its
            // ownership marker is the one seed-read of the shared default.
            if source.contains(".object(forKey: \"imagePreview.ocrBoxesEnabled\")") { imageOwners.append(name) }
            if source.contains("@AppStorage(\"pdfPreview.ocrBoxesEnabled\")") { pdfOwners.append(name) }
        }
        #expect(imageOwners.count == 1, "image word-box switch has \(imageOwners.count) owners: \(imageOwners)")
        #expect(pdfOwners.count == 1, "PDF word-box switch has \(pdfOwners.count) owners: \(pdfOwners)")
        #expect(
            Set(imageOwners).isDisjoint(with: Set(pdfOwners)),
            "one file drives both canvases' word boxes — that is the desync bug"
        )
    }
}
