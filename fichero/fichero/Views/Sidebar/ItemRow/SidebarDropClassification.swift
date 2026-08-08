import Foundation
import UniformTypeIdentifiers

// MARK: - Sidebar drop classification (#4401)

/// What a sidebar drop carries, and therefore whether it is a MOVE or an
/// IMPORT. Pure, and deliberately in its own file: this decision is now shared
/// by the sidebar rows, the row-insertion path and the library-section header,
/// and it living inside one of those files is how the header ended up with a
/// second, divergent copy of it.

extension UTType {
    /// The ONE in-app drag flavor (#4401 multi-drag, live-repro 2026-08-04).
    ///
    /// Why it exists: the in-process id used to ride a
    /// `ProxyRepresentation(exporting: \.id).visibility(.ownProcess)` — and a
    /// MULTI-item drag session does not deliver that flavor. Daniel's console,
    /// dragging three sidebar rows onto a folder:
    ///
    ///     [0] UTIs: [public.data]  URL:false  String:false
    ///
    /// Only the `FileRepresentation(.data)` export survived the multi-item
    /// bridging; the ownProcess proxy string vanished, so the reader had
    /// nothing to read and the move was refused. Data-style representations
    /// DO survive (public.data arrived), so the id now ships as a
    /// `DataRepresentation` of this custom type at DEFAULT visibility — no
    /// proxy, no visibility dependence. External apps ignore an identifier
    /// they have no declaration for (the #623 Finder-artifact concern stays
    /// solved by the real file/RTF exports beside it).
    ///
    /// `conformingTo: .data` keeps every existing `[.item]`/`[.data]` drop
    /// list accepting these sessions. The identifier is named by BOTH the
    /// export side (SidebarDragID, LibraryItemDrag) and the read side
    /// (`readSidebarDropPayload`) — one representation, agreed on by name.
    ///
    /// The identifier MUST be declared in the app's Info.plist under
    /// `UTExportedTypeDeclarations` (`UTType(exportedAs:)` is documented as
    /// creating "a type your app owns", and exported ownership is declared
    /// there). This file's first version claimed an in-process round trip
    /// needed no declaration — falsified live 2026-08-04: the drag pasteboard
    /// goes through the system pasteboard server even inside one app, and an
    /// UNDECLARED identifier arrived degraded to bare `public.data`
    /// (empirical, not documented), so the reader classified an in-app .tif
    /// drag as external files and re-imported it as a duplicate. The
    /// declaration lives in `fichero/Info.plist`; keep the two identifiers in
    /// lock-step (pinned by `FicheroDragItemDeclarationTests`).
    static let ficheroDragItem = UTType(
        exportedAs: "app.fichero.fichero.drag-item",
        conformingTo: .data
    )
}

enum SidebarDropProviderRoute: Equatable {
    case internalTextOnly
    case externalFiles
    case unsupported
}

struct SidebarDropProviderCapabilities: Equatable {
    let canLoadURL: Bool
    let canLoadString: Bool
    let registeredTypeIdentifiers: [String]

    /// This provider carries OUR OWN drag flavor: the NAMED custom type, and
    /// only that. Registration-based on purpose — the `canLoadObject` probes
    /// over-answer (NSString bridges URLs) and under-answer (a Finder FOLDER
    /// answers false to BOTH URL and NSString, live-repro 2026-08-04), so
    /// they can never be the classifier.
    ///
    /// A plain-text registration used to count too ("the single-drag id
    /// proxy"). That was a legacy over-match once #4401 made BOTH in-app drag
    /// types export `ficheroDragItem` (`SidebarDragID` and `LibraryItemDrag`,
    /// Document.swift:155) — and it misread every Finder drag of a TEXT FILE,
    /// whose provider registers `public.utf8-plain-text` as CONTENT beside
    /// its file-url: the drop classified possibly-internal, the id read found
    /// no `doc:`, and the user got "Couldn't read what was dragged" for an
    /// ordinary .txt (live-repro 2026-08-08, empty.txt — #4569). Ours is
    /// identified by NAME; text is just text.
    var registersInternalFlavor: Bool {
        registeredTypeIdentifiers.contains(UTType.ficheroDragItem.identifier)
    }

    /// This provider registers NOTHING but bare `public.data` — no named
    /// flavor, no content type, no URL type. A genuine external drag always
    /// says what it is (`public.folder`, `public.jpeg`, `com.adobe.pdf`, a
    /// file-url); the one drag that arrives shaped like this is OUR OWN
    /// `ficheroDragItem` after the pasteboard degraded its undeclared custom
    /// identifier to its `public.data` conformance (live-repro 2026-08-04: an
    /// in-app .tif drag classified external and was re-imported as a hollow
    /// duplicate). Treated as possibly-internal, never as importable.
    var isUnidentifiedBareData: Bool {
        !registeredTypeIdentifiers.isEmpty
            && registeredTypeIdentifiers.allSatisfy { $0 == UTType.data.identifier }
    }

    /// This provider is an EXTERNAL file-system-ish payload: it registers
    /// something conforming to `public.item` or `public.url` (files, folders
    /// — `public.folder` → `public.directory` → `public.item` — content-typed
    /// drags like `public.jpeg`/`com.adobe.pdf`) and no internal flavor.
    /// `ExternalFileDropLoader` can obtain a real file URL from every one of
    /// these via its representation ladder against the registered identifier,
    /// regardless of what `canLoadObject` claims. Bare `public.data` with no
    /// other identifier is EXCLUDED: that is the degraded shape of our own
    /// drag flavor, and materializing it is the #4401 hollow-duplicate bug's
    /// third occurrence (2026-08-04).
    var registersExternalPayload: Bool {
        guard !registersInternalFlavor, !isUnidentifiedBareData else { return false }
        return registeredTypeIdentifiers.contains { identifier in
            guard let type = UTType(identifier) else { return false }
            return type.conforms(to: .item) || type.conforms(to: .url)
        }
    }
}

/// What a sidebar drop actually carries (#4401).
///
/// The old classifier decided "external" by ELIMINATION: any provider that
/// could load a URL, or registered any type identifier that was not one of
/// three plain-text ones, made the whole drop external. That was safe only
/// while an internal drag advertised nothing but its id.
///
/// #4123 then taught `SidebarDragID` to export a real file and RTF so a drag
/// OUT of the app would deposit something useful in Finder. A document row's
/// provider therefore began registering `public.data` and `public.rtf`, and
/// `canLoadObject(ofClass: URL.self)` began answering true — so every internal
/// document drag classified as EXTERNAL FILES and was handed to
/// `importService.importFiles`, which re-ingested it as a brand-new document.
///
/// That is both halves of the bug exactly: a second document appears, and it
/// is hollow because it was freshly imported and has never been processed. It
/// also explains why folders moved correctly — `SidebarDragID(item:)` only
/// sets `documentId` for non-folders, so a folder row exports no file, kept
/// the id-only shape, and stayed on the move path.
///
/// The fix is to identify an internal drag POSITIVELY, by the id it carries,
/// rather than by the absence of anything that looks external. Export
/// representations can then be added freely without silently re-routing moves.
enum SidebarDropPayload: Equatable {
    /// Our own ids — a MOVE. Never an import, whatever else the drag also
    /// advertises for the benefit of other applications.
    case internalItems([String])
    /// No internal id anywhere: a genuine drop from outside the app.
    case externalFiles
    /// The drag carries an internal flavour but no id could be read from it.
    /// Reported loudly, never treated as an import — re-ingesting something
    /// already in the library is the data-loss shape this issue is about.
    case unreadableInternal
    case unsupported
}

/// The sidebar's document-row id shape, `doc:<uuid>` (`SidebarItem.swift:193`).
/// A Finder drag can never produce one.
func isInternalSidebarItemID(_ candidate: String) -> Bool {
    let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("doc:") else { return false }
    return trimmed.count > "doc:".count
}

/// The LIBRARY pane's drag payload, recognised on the sidebar side.
///
/// There are two drag types for one concept. Sidebar rows vend `SidebarDragID`,
/// whose id is `doc:<uuid>`. Library rows, tiles, columns and table cells vend
/// `LibraryItemDrag`, whose `id` is the BARE document id and whose first string
/// representation is JSON (or the document's transcript). So dragging a document
/// out of the library pane onto a sidebar folder produced no `doc:` id, and the
/// #4401 classifier — correctly refusing to re-import something that started
/// inside the app — answered `.unreadableInternal`: "Couldn't read what was
/// dragged." Filing a document by dragging it to a sidebar folder, from the
/// pane where the documents actually are, could not be done at all.
///
/// The fix is deliberately on the RECEIVING side. Teaching `LibraryItemDrag` to
/// vend a `doc:`-prefixed string first would fix this and break chat: `ChatView`
/// and `ChatInspector` accept `.text`/`.plainText` and read the FIRST string,
/// which is how a dragged document attaches its transcript. Changing a drag
/// source to satisfy one destination is how #4123 caused #4401 in the first
/// place — a capability added for one direction changing the meaning of another.
///
/// Returns the `doc:`-prefixed form the rest of the sidebar pipeline expects, so
/// nothing downstream needs to know which pane the drag came from.
func internalSidebarItemID(fromLibraryDragJSON candidate: String) -> String? {
    let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.hasPrefix("{"), let data = trimmed.data(using: .utf8) else { return nil }
    guard let drag = try? JSONDecoder().decode(LibraryItemDrag.self, from: data) else { return nil }
    // Artifacts, notes and annotations are not documents and cannot be
    // reparented — the same exclusion `moveDraggedItems` already makes.
    switch drag.kind {
    case .document, .page, .group:
        break
    case .artifact, .note, .annotation:
        return nil
    }
    let identifier = drag.documentId ?? drag.id
    guard !identifier.isEmpty else { return nil }
    return "doc:\(identifier)"
}

// MARK: - Recognising OUR OWN export by its file URL alone (#4401)

/// The temp-directory prefix `SidebarDragID.exportSourceFile` writes into when
/// a document row is dragged. Distinct from `fichero-drop-`, which is where an
/// INBOUND external drop's bytes are staged — the two must not be confused.
let ficheroInternalDragExportPrefix = "fichero-drag-"

/// Is this URL a copy THIS APP just made of a document already in the library?
///
/// The provider-reading classifier above is the primary defence and identifies
/// an internal drag positively, by the id it carries. This predicate exists for
/// the one route that cannot ask: a `.dropDestination(for: URL.self)`, which is
/// handed resolved URLs and never sees the providers behind them.
///
/// That route is not hypothetical. `DropTargetModifiers` mounts such a
/// destination on the WHOLE `NavigationSplitView` — sidebar column and detail
/// column both — and since #4123 a document row exports a real file. So an
/// internal drag released anywhere the nested per-row handlers do not claim
/// (sidebar whitespace, the gaps between sections, the content pane) resolved
/// to that exported file and was IMPORTED: a second, hollow copy of a document
/// already in the library. That is #4401's exact shape, in the widest-scope
/// drop target in the app, and it is why the symptom outlived the fixes to the
/// row-level paths — those only cover drops that land on a row.
///
/// A URL under this prefix is by construction a copy of something already
/// stored. Re-ingesting it can never be right.
func isFicheroInternalDragExport(_ url: URL) -> Bool {
    url.pathComponents.contains { $0.hasPrefix(ficheroInternalDragExportPrefix) }
}

/// Split dropped URLs into the ones that are genuinely external and the ones
/// this app exported for its own drag. Pure, so the rule is testable without a
/// live drag — the gap that let this survive three rounds of fixes.
func partitionFicheroInternalDragExports(
    _ urls: [URL]
) -> (external: [URL], internalExports: [URL]) {
    var external: [URL] = []
    var internalExports: [URL] = []
    for url in urls {
        if isFicheroInternalDragExport(url) {
            internalExports.append(url)
        } else {
            external.append(url)
        }
    }
    return (external, internalExports)
}

/// Route a drop from what its providers actually yielded.
///
/// - Parameters:
///   - loadedIDs: strings successfully loaded from the providers, in order.
///   - hasExternalPayload: any provider registers an external file-system-ish
///     payload (`registersExternalPayload`) — files, folders, content-typed
///     drags. NOT `canLoadObject(URL.self)`, which Finder folders answer
///     false to (live-repro 2026-08-04).
///   - carriesOwnProcessFlavor: the drag advertises the in-process flavour, so
///     it started inside this app even if no id could be read.
func classifySidebarDropPayload(
    loadedIDs: [String],
    hasExternalPayload: Bool,
    carriesOwnProcessFlavor: Bool
) -> SidebarDropPayload {
    // Positive identification first, and it WINS over any file URL the drag
    // also happens to advertise. This ordering is the fix.
    //
    // Both in-app drag shapes count: a sidebar row's `doc:<uuid>` and a library
    // pane row/tile/cell's `LibraryItemDrag` JSON. The library pane is where the
    // documents are, so dragging one from there to a sidebar folder is the
    // ordinary way to file something — and it was answering "Couldn't read what
    // was dragged" because only the sidebar's own id shape was recognised.
    let internalIDs = loadedIDs.compactMap { candidate -> String? in
        if isInternalSidebarItemID(candidate) { return candidate }
        return internalSidebarItemID(fromLibraryDragJSON: candidate)
    }
    if !internalIDs.isEmpty {
        return .internalItems(internalIDs)
    }
    if carriesOwnProcessFlavor {
        // Started inside the app, but we could not read what it was. Do NOT
        // fall through to ingestion.
        return .unreadableInternal
    }
    if hasExternalPayload {
        return .externalFiles
    }
    return .unsupported
}

/// Could this drop carry one of OUR ids? A cheap pre-check that decides
/// whether to attempt a string read — never the route (#4401).
///
/// Deliberately separate from `classifySidebarDropProviders` rather than
/// folded into it: that function answers "does this look external by
/// capability", which is a fine question and still correctly answered. What it
/// cannot do is decide the route, because since #4123 an internal document
/// drag and a Finder file drag advertise the same capabilities. Conflating the
/// two questions is what let the routing regress silently.
///
/// An internal drag always REGISTERS a plain-text representation (the
/// `.draggable` String proxy and `LibraryItemDrag` both write
/// `public.utf8-plain-text`). A Finder file drag registers only URL types —
/// but it must be identified by that REGISTRATION, not by
/// `canLoadObject(ofClass: NSString.self)`. The documented contracts
/// (Apple Developer Documentation):
///  - `UTType.fileURL`: "The identifier for this type is public.file-url.
///    This type conforms to UTTypeURL" — so file-url registrations ARE url
///    registrations.
///  - `NSItemProviderWriting.writableTypeIdentifiersForItemProvider`: an
///    NSURL-backed provider registers `public.url` (class-level doc), plus
///    `public.file-url` for file:// URLs (instance-level doc).
/// UNDOCUMENTED, established empirically on this OS: NSString's
/// `readableTypeIdentifiersForItemProvider` includes `public.url`, so EVERY
/// file drag answers canLoadString == true and bridges its URL to a
/// "file:///…" string. Keying this predicate on canLoadString made every
/// pure Finder drop classify as `carriesOwnProcessFlavor`, and — because no
/// `doc:` id could be read out of a URL string — `classifySidebarDropPayload`
/// refused it as `.unreadableInternal` instead of importing it. The fix
/// keys on the DOCUMENTED conformance hierarchy (`UTType.conforms(to:)`
/// against the system-declared plain-text family), not on the undocumented
/// bridging, so it holds even if the NSString readable list changes. Same
/// heuristic as `dropInfoLooksLikeInAppDrag`, which already got this right.
func sidebarDropMightCarryInternalID(_ providers: [SidebarDropProviderCapabilities]) -> Bool {
    // Bare public.data counts: an undeclared custom flavor degrades to
    // exactly that shape on the real pasteboard (2026-08-04), and its BYTES
    // are still our envelope — so the reader must attempt the string read
    // rather than routing it to the importer.
    providers.contains { $0.registersInternalFlavor || $0.isUnidentifiedBareData }
}

/// Capability-shaped route. Still correct for what it answers, and still the
/// external-vs-unsupported decision — but NOT the internal-vs-external one.
/// See `classifySidebarDropPayload`, which routes on the id actually read.
func classifySidebarDropProviders(_ providers: [SidebarDropProviderCapabilities]) -> SidebarDropProviderRoute {
    guard !providers.isEmpty else { return .unsupported }

    let hasExternalProvider = providers.contains { provider in
        provider.canLoadURL
            || provider.registeredTypeIdentifiers.contains {
                // utf8PlainText is REQUIRED here (#4124): `.draggable`'s
                // String proxy registers public.utf8-plain-text — without it
                // every internal sidebar drag classified as external files,
                // the URL loads all failed, and row-onto-row moves never ran.
                $0 != UTType.text.identifier
                    && $0 != UTType.plainText.identifier
                    && $0 != UTType.utf8PlainText.identifier
            }
    }
    if hasExternalProvider {
        return .externalFiles
    }

    let hasInternalTextProvider = providers.contains { provider in
        provider.canLoadString
    }
    if hasInternalTextProvider {
        return .internalTextOnly
    }

    return .unsupported
}
