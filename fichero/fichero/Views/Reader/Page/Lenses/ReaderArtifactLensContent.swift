import CoreTransferable
import FicheroAPIClient
import OSLog
import SwiftUI
import UniformTypeIdentifiers

//  Extracted for file_length (#5113): the ReadingPaneView extension that renders the lens is
//  not the menu that chooses it. Checklist applied — path free, cut above the attached doc
//  comment, no `#if`, no file-scope `private`, imports from the source verbatim.

extension ReadingPaneView {

    /// The head's CSV-out chip, shown ONLY while a table representation is
    /// on screen and its artifact loaded: drag it to the Desktop/Excel for a
    /// real .csv, or click for a save panel (the sandbox-proof rung — a
    /// pasteboard sandbox-extension denial was seen on container-tmp drags,
    /// so the click path must always exist).
    @ViewBuilder
    var readerTableExportControl: some View {
        if let export = readerTableExport {
            Button {
                isExportingTableCSV = true
            } label: {
                Image(systemName: "square.and.arrow.down")
                    .foregroundStyle(Color.secondary)
                    .readerIconTarget()
            }
            .buttonStyle(.plain)
            .draggable(export)
            .help("Drag out as a CSV file (or onto a sidebar folder to make a library node), or click to save…")
            .accessibilityLabel("Save table as CSV")
            .accessibilityIdentifier("readerTableExportChip")
        }
    }

    /// Fetch the FULL newest table artifact for the scope when a table
    /// representation is selected (list rows carry truncated content), so the
    /// chip has real bytes to vend the moment a drag starts.
    func loadReaderTableExport() async {
        readerTableExport = nil
        guard let representation = readerRepresentation,
              ReaderRepresentation.tableTypes.contains(representation),
              let doc = effectiveDocument,
              // #4860: THIS pane's own window's library.
              let service = LibraryManager.shared.getLibrary(id: windowState.libraryId)?.artifactService
        else { return }
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, includeDescendants: true
        ) else { return }
        guard let newest = artifacts
            .filter({ $0.artifactType == representation })
            .max(by: { $0.createdAt < $1.createdAt })
        else { return }
        guard let full = try? await service.getArtifact(id: newest.id),
              let content = full.content, !content.isEmpty
        else { return }
        let displayName = DocumentTitle.displayName(for: doc)
        readerTableExport = ReaderTableCSVExport(
            filename: ReaderTableCSVExport.filename(forDocumentNamed: displayName),
            csv: content,
            artifactId: full.id,
            sourceDocumentId: full.documentId,
            nodeName: displayName
        )
    }

    /// What this pane is SHOWING, in words (Daniel, 2026-09-02: the reader
    /// head "never says WHAT is displayed — document content, or which
    /// artifact"). Rendered beside the head's one glyph.
    ///
    /// Only the Content lens has a choice to state: the knowledge surfaces
    /// ARE their lens, so they name themselves. Precedence matches the
    /// renderer's own (`ReadingPaneView+Tabs`): the artifact lens outranks
    /// the representation switcher, which outranks the live content.
    var readerShownLabel: String {
        guard readerTab == .page else { return readerLensBinding.wrappedValue.title }
        if isComparingArtifacts {
            return "Comparing \(artifactCompareIds.count) artifacts"
        }
        if let artifactLens { return artifactLens.label }
        if let readerRepresentation {
            return ReaderRepresentation.title(for: readerRepresentation)
        }
        return ReaderLens.page.title
    }

    /// The "Showing" submenu of the head's View menu (Daniel, 2026-09-02:
    /// the View menu "should gain a submenu listing the artifacts AVAILABLE
    /// for the current document … so you can point the pane at any of them").
    ///
    /// This is ONE menu where the head used to carry two more controls beside
    /// the selector — a text menu of representations and a `doc.on.doc` menu
    /// of artifacts. Three menus a divider apart, none of which said what was
    /// on screen. Every row they offered is here; nothing was dropped.
    ///
    /// Absent entirely when the document has neither representations nor
    /// artifacts: a submenu whose only row is the state you are already in is
    /// the menu lying (dead-simple-UX).
    func readerShowingMenu() -> AnyView {
        guard !readerRepresentationChoices.isEmpty || !artifactLensGroups.isEmpty else {
            return AnyView(EmptyView())
        }
        return AnyView(
            Menu {
                Button {
                    stopComparingArtifacts()
                    readerRepresentation = nil
                    artifactLens = nil
                } label: {
                    Self.showingRow(
                        title: ReaderLens.page.title,
                        isCurrent: readerRepresentation == nil && artifactLens == nil,
                        icon: "doc.text"
                    )
                }
                showingRepresentationsSection
                showingCompareSection
                showingArtifactSections
            } label: {
                Label("Showing: \(readerShownLabel)", systemImage: "eye")
            }
        )
    }

    /// The representation rows. Extracted for the SAME reason `showingRow` is:
    /// this file's menu builder has collapsed the type checker before, and it
    /// now carries four sections instead of two. Bounded sub-expressions are
    /// the LibraryWindow.body rule applied here.
    @ViewBuilder
    var showingRepresentationsSection: some View {
        if !readerRepresentationChoices.isEmpty {
            Section("Representations") {
                ForEach(readerRepresentationChoices, id: \.self) { type in
                    Button {
                        stopComparingArtifacts()
                        artifactLens = nil
                        readerRepresentation = type
                    } label: {
                        Self.showingRow(
                            title: ReaderRepresentation.title(for: type),
                            isCurrent: artifactLens == nil && readerRepresentation == type,
                            icon: "text.alignleft"
                        )
                    }
                }
            }
        }
    }

    /// Starting, widening and leaving a comparison (Daniel, 2026-09-04). The
    /// pane must already be pointed at one artifact — that one is the baseline
    /// — and the rows are offered only while there is something left to add: a
    /// compare menu over a document with one result is the menu lying.
    @ViewBuilder
    var showingCompareSection: some View {
        if isComparingArtifacts {
            Section("Comparing") {
                Button("Stop Comparing") { stopComparingArtifacts() }
            }
        }
        if artifactLens != nil, !artifactCompareCandidates.isEmpty,
           artifactCompareIds.count < Self.maxCompareColumns {
            Menu(isComparingArtifacts ? "Add to Comparison" : "Compare With") {
                ForEach(artifactCompareCandidates, id: \.artifactId) { choice in
                    Button(choice.label) { compareArtifact(with: choice) }
                }
            }
        }
    }

    /// The artifact rows, BY RUN (Daniel, 2026-09-04), newest run first: one
    /// section per producing pass, each headed by the workflow's name and when
    /// it ran, so three reviews from tonight's run read as tonight's run rather
    /// than as three loose rows with no timestamps.
    @ViewBuilder
    var showingArtifactSections: some View {
        ForEach(artifactLensGroups) { group in
            Section(group.header) {
                ForEach(group.choices, id: \.artifactId) { choice in
                    Button {
                        stopComparingArtifacts()
                        artifactLens = choice
                    } label: {
                        Self.showingRow(
                            title: choice.label,
                            isCurrent: artifactLens == choice,
                            icon: "doc.on.doc"
                        )
                    }
                }
            }
        }
    }

    /// One checkmarked row. Extracted and explicitly typed: the inline
    /// conditional inside three nested ForEach builders is exactly the shape
    /// that has collapsed this file's type checker before.
    @ViewBuilder
    static func showingRow(title: String, isCurrent: Bool, icon: String) -> some View {
        if isCurrent {
            Label(title, systemImage: "checkmark")
        } else {
            Label(title, systemImage: icon)
        }
    }

    /// Load the artifact choices for the shown document, grouped BY RUN.
    ///
    /// `resetSelection` is false on a REFRESH (a run finished while the same
    /// document is open): clearing the lens there would yank the artifact the
    /// user is reading out from under them every time a background pass lands.
    /// The lens is instead re-resolved against the fresh rows and dropped only
    /// if its artifact is genuinely gone.
    func loadArtifactLensChoices(resetSelection: Bool = true) async {
        let previousLens = artifactLens
        if resetSelection {
            artifactLens = nil
            readerRepresentation = nil
        }
        artifactLensGroups = []
        readerRepresentationChoices = []
        guard let doc = effectiveDocument else { return }
        // The pane's OWN injected service first (2026-09-02): the OLD
        // currentLibraryId lookup was the app-global pointer, and in a
        // multi-library window it named a different library than this pane —
        // the artifact fetch answered for the wrong scope and the "Showing"
        // submenu rendered empty (Daniel: "reader view has no artefact
        // submenu"). The fallback (headless hosts with no injected service)
        // now reads THIS pane's own window's library too (#4860) — it must
        // stay a fallback, but it must not go back to being wrong when it
        // fires.
        let library = LibraryManager.shared.getLibrary(id: windowState.libraryId)
        guard let service = paneArtifactService ?? library?.artifactService
        else { return }
        // ONE fetch answers both head controls: the whole scope's artifacts
        // (pages included) drive the representation switcher; the document's
        // OWN artifacts drive the per-artifact lens, as before.
        // forceRefresh (Daniel, 2026-09-04: three reviews finished seconds ago
        // were in the artifacts panel and absent from this menu). The service
        // caches per document, so without this the submenu shows whatever the
        // document showed when it was FIRST opened, forever.
        guard let artifacts = try? await service.getArtifacts(
            forDocumentId: doc.id, forceRefresh: true, includeDescendants: true
        ) else { return }
        readerRepresentationChoices = ReaderRepresentation.availableTypes(
            in: artifacts.map(\.artifactType)
        )
        // "Annotations" joins the switcher whenever the SCOPE has any markup
        // (Daniel, 2026-08-30 ruling 5). The annotations list route matches a
        // node exactly (a page annotation stores the page's id), so the scope
        // check asks about the shown node AND the descendant nodes the
        // artifact fetch just named — capped, first hit wins.
        if let library, await Self.scopeHasAnnotations(
            documentId: doc.id,
            descendantIds: artifacts.map(\.documentId),
            annotationService: library.annotationService
        ) {
            readerRepresentationChoices.append(ReaderRepresentation.annotationsType)
        }
        artifactLensGroups = ReaderArtifactMenu.groups(
            from: artifacts.filter { $0.documentId == doc.id },
            workflowName: { id in
                workflowStore?.workflows.first { $0.id == id }?.name
            }
        )
        // A refresh keeps the reader pinned to what it was reading — unless
        // that artifact is gone, in which case the pane says so by falling
        // back to the live content rather than showing a lens to nothing.
        if !resetSelection, let previousLens {
            let rows = ReaderArtifactMenu.flattened(artifactLensGroups)
            artifactLens = rows.first { $0.artifactId == previousLens.artifactId }
        }
    }

    /// Whether the reader scope carries ANY annotation (ruling 5's gate for
    /// the "Annotations" switcher entry). Asks the list endpoint directly —
    /// `AnnotationService.load` would overwrite the shared `annotations`
    /// state the inspector observes, and this check must not. The list route
    /// matches one node exactly, so the shown document is asked first, then
    /// the descendant nodes the artifact fetch named — capped, first hit
    /// wins, and failures read as "none" (the menu just stays smaller).
    @MainActor
    static func scopeHasAnnotations(
        documentId: String,
        descendantIds: [String],
        annotationService: AnnotationService
    ) async -> Bool {
        annotationService.syncLibraryPath()
        var candidates: [String] = [documentId]
        for id in descendantIds where id != documentId && !candidates.contains(id) {
            candidates.append(id)
            if candidates.count >= 9 { break }
        }
        for id in candidates {
            guard let response = try? await annotationService.client.api
                .listAnnotationsApiAnnotationsGet(.init(query: .init(documentId: id))),
                case .ok(let okResponse) = response,
                let body = try? okResponse.body.json
            else { continue }
            // swiftlint:disable:next empty_count - `count` is a response field, not a Collection
            if body.count > 0 { return true }
        }
        return false
    }
}

// ArtifactLensContentView retired 2026-08-30: the artifact lens rides the ONE
// WebKit renderer now (`?artifact_id=`, via the "artifact:<id>" representation
// channel) — tables parse, prose reads with the document's own typography.
