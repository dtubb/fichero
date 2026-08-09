import SwiftUI
import UniformTypeIdentifiers
#if canImport(AppKit)
import AppKit
#endif
#if canImport(PDFKit)
import PDFKit
#endif

/// Transferable wrapper for sidebar row drags (#711).
///
/// Two reasons this exists rather than `.draggable(item.id)` directly:
///   1. `visibility(.ownProcess)` keeps the drag invisible to external
///      apps, preserving the #623 fix that prevented Finder from
///      depositing an HTML link artifact when dragging out of the sidebar.
///   2. Advertising a Transferable on the row makes AppKit's NSTableView
///      row-drag (which List uses under the hood) pull THIS payload
///      instead of synthesizing an empty `public.file-url` when it wins
///      the gesture arena over `.onDrag` — the root cause of #711's
///      "Files dropped: [\"\"]" leak when grabbing from icon/text.
///
/// The bridged NSItemProvider responds to `loadObject(ofClass: NSString.self)`
/// in-process, which is what `SidebarItemRow.handleRowDrop` already filters
/// for — so the drop pipeline didn't need migrating.
struct SidebarDragID: Transferable {
    let id: String
    /// Bare document id + context for cross-app exports (#4123). Nil for
    /// non-document rows — those stay in-process-only, as before.
    var documentId: String?
    var libraryId: UUID?
    var name: String = ""
    /// The document's transcript/content for text-editor drops.
    var transcript: String = ""
    /// 0-based PDF page index for PAGE rows (#4123): the export trims the
    /// parent's multi-page PDF to just this page. Nil = export the whole file.
    var pageIndex: Int?

    /// Rows that can export a real file: documents with a source file
    /// (folders and virtual rows can't).
    var exportsFile: Bool { documentId != nil }
    var exportsText: Bool { !transcript.isEmpty }

    init(id: String) {
        self.id = id
    }

    /// Full payload for a document row (#4123): dragging OUT of the app
    /// delivers a real file copy / rich text instead of the internal id.
    init(item: SidebarItem) {
        self.id = item.id
        if case .document(let doc) = item.itemType, doc.docType != .folder {
            self.documentId = doc.id
            self.libraryId = item.libraryId
            self.name = doc.name
            self.transcript = doc.pageContent ?? ""
            // `sequence` is 1-based (see ContentView+ReadingLayout).
            if doc.docType == .page {
                self.pageIndex = max(0, (doc.sequence ?? 1) - 1)
            }
        }
    }

    /// Same payload for a library-grid document (#4121 Export…) — grid cells
    /// hold a `Document` + window library rather than a `SidebarItem`.
    init(document: Document, libraryId: UUID?) {
        self.id = "doc:\(document.id)"
        if document.docType != .folder {
            self.documentId = document.id
            self.libraryId = libraryId
            self.name = document.name
            self.transcript = document.pageContent ?? ""
            if document.docType == .page {
                self.pageIndex = max(0, (document.sequence ?? 1) - 1)
            }
        }
    }

    static var transferRepresentation: some TransferRepresentation {
        // THE in-app payload (#4401 multi-drag): the id as a DataRepresentation
        // of the named custom type. A DataRepresentation because a multi-item
        // drag session drops ProxyRepresentations with .ownProcess visibility
        // (observed live: three dragged rows arrived as [public.data] only,
        // String:false) while data-style flavors survive. Default visibility —
        // external apps ignore an undeclared identifier; the file/RTF exports
        // below remain what they see. Read by name in readSidebarDropPayload.
        DataRepresentation(exportedContentType: .ficheroDragItem) { item in
            Data(item.id.utf8)
        }
        // In-process id STRING flavor — the sidebar move pipeline's payload
        // (#623/#711), still what single-item drags and chat read. FIRST among
        // the string flavors, and it must stay ahead of the transcript (#4401).
        //
        // It used to be last, so that "external consumers prefer the real
        // representations above instead of a doc:<uuid> clipping". That
        // reasoning does not apply to THIS representation: `.ownProcess`
        // visibility already hides it from every other application, so no
        // external consumer can see it at any position. Ordering therefore only
        // decides what OUR OWN reader gets — and it was deciding wrong.
        //
        // `handleRowDrop` identifies an internal drag positively, by asking each
        // provider for a string (#4401). `loadObject(ofClass: NSString.self)`
        // returns the FIRST representation an NSString can be made from, and the
        // transcript below is also `utf8PlainText`. So for any document with a
        // transcript — `exportsText` is `!transcript.isEmpty`, i.e. every
        // transcribed document, which is the whole Marshall corpus — the reader
        // got the TRANSCRIPT, never found an id, classified the drag
        // `.unreadableInternal`, and refused the move.
        //
        // That failed safe: nothing was duplicated and the refusal was visible.
        // But it meant transcribed documents could not be filed at all, which is
        // the ordinary act of organising a library. Putting the id first makes
        // the in-process read unambiguous while leaving the cross-app export
        // below exactly as it was.
        ProxyRepresentation(exporting: \.id)
            .visibility(.ownProcess)
        // Cross-app, best-first: a real copy of the source file (fetched via
        // the storage HTTP endpoints — the engine may be remote, NEVER a
        // local path), then the transcript as RTF for text editors.
        FileRepresentation(exportedContentType: .data) { item in
            SentTransferredFile(try await Self.exportSourceFile(for: item))
        }
        .exportingCondition { $0.exportsFile }
        .suggestedFileName(\.name)
        DataRepresentation(exportedContentType: .rtf) { item in
            try Self.transcriptRTFData(item.transcript)
        }
        .exportingCondition { $0.exportsText }
        // UTF-8 serves markdown editors; the in-app drop classifier excludes
        // this flavor so it cannot interfere with sidebar moves (#4123/#4124).
        DataRepresentation(exportedContentType: .utf8PlainText) { item in
            Data(item.transcript.utf8)
        }
        .exportingCondition { $0.exportsText }
    }

    /// Transcript → RTF bytes for rich-text pasteboard consumers.
    static func transcriptRTFData(_ transcript: String) throws -> Data {
        let attributed = NSAttributedString(string: transcript)
        return try attributed.data(
            from: NSRange(location: 0, length: attributed.length),
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        )
    }

    /// Fetch the document's source bytes through the library's storage
    /// service into a temp file named for Finder (#4123).
    static func exportSourceFile(for item: SidebarDragID) async throws -> URL {
        guard let documentId = item.documentId else {
            throw CocoaError(.fileNoSuchFile)
        }
        let storage = await MainActor.run { () -> StorageService? in
            let library = item.libraryId.flatMap { LibraryManager.shared.getLibrary(id: $0) }
                ?? LibraryManager.shared.globalLibrary
            return library?.storageService
        }
        guard let storage else { throw CocoaError(.fileNoSuchFile) }
        let (tempURL, disposition) = try await storage.fetchSourceFile(documentId)
        // Prefer the server's filename (its extension picks the app that
        // opens the copy); fall back to a sanitized row name — never a
        // transcript-sized string or embedded newlines.
        let fallback = String(
            item.name.replacingOccurrences(of: "\n", with: " ").prefix(64)
        ).trimmingCharacters(in: .whitespaces)
        let filename = Self.filename(fromContentDisposition: disposition)
            ?? (fallback.isEmpty ? tempURL.lastPathComponent : fallback)
        let named = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-drag-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: named, withIntermediateDirectories: true)
        let destination = named.appendingPathComponent(filename)
        try FileManager.default.moveItem(at: tempURL, to: destination)
        if let trimmed = Self.singlePagePDF(from: destination, pageIndex: item.pageIndex) {
            return trimmed
        }
        return destination
    }

    /// Page rows export just THEIR page (#4123): the storage endpoint returns
    /// the parent's whole source file, so trim it client-side. Nil (= keep the
    /// full file) unless this is a page row, the file is a real multi-page
    /// PDF, and extraction succeeds — a trim failure must never lose the drag.
    static func singlePagePDF(from url: URL, pageIndex: Int?) -> URL? {
        #if canImport(PDFKit)
        guard let pageIndex,
              let pdf = PDFDocument(url: url),
              pdf.pageCount > 1,
              let page = pdf.page(at: min(pageIndex, pdf.pageCount - 1)) else {
            return nil
        }
        let single = PDFDocument()
        single.insert(page, at: 0)
        let base = url.deletingPathExtension().lastPathComponent
        let pageURL = url.deletingLastPathComponent()
            .appendingPathComponent("\(base) page \(pageIndex + 1).pdf")
        guard single.write(to: pageURL) else { return nil }
        return pageURL
        #else
        return nil
        #endif
    }

    /// Minimal Content-Disposition filename parse: `filename="x.pdf"` /
    /// `filename=x.pdf`. Returns nil when absent or empty.
    static func filename(fromContentDisposition disposition: String?) -> String? {
        guard let disposition else { return nil }
        for part in disposition.split(separator: ";") {
            let trimmed = part.trimmingCharacters(in: .whitespaces)
            guard trimmed.lowercased().hasPrefix("filename=") else { continue }
            var value = String(trimmed.dropFirst("filename=".count))
            value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            // No path separators from a header into the filesystem.
            value = value.replacingOccurrences(of: "/", with: "-")
            return value.isEmpty ? nil : value
        }
        return nil
    }
}

extension View {
    /// The sidebar row's ONE platter — selection and drop target share the
    /// same full-row canvas (Daniel's preview review, 2026-08-08, #4563/#4568):
    ///
    ///   - drop target  → ENTIRE row solid accent, white content (Mail).
    ///     One style for every operation: move/copy/alias feedback belongs to
    ///     the CURSOR badge (the delegate's `dropUpdated` proposal), never to
    ///     the platter color — "the way the drop target changes for alias,
    ///     copy, move is the cursor".
    ///   - selected     → grey platter, accent name+icon (Finder). Painting
    ///     it ourselves replaces the native emphasized accent platter, which
    ///     read as a solid green block.
    ///   - otherwise    → clear.
    ///
    /// `.listRowBackground` is the List's own full-row canvas — full width,
    /// chevron and indent strip included (a label `.background` only tinted
    /// the label's frame: "just the name not the actual row"). Attached to
    /// the LABEL of each row shape, it scopes to THAT row; the #4229 subtree
    /// wash came from attaching at the DisclosureGroup level, where the
    /// group's frame is the folder plus its expanded children.
    @ViewBuilder
    func sidebarDropHighlight(
        _ active: Bool,
        selected: Bool = false,
        mergeAbove: Bool = false,
        mergeBelow: Bool = false
    ) -> some View {
        // Contiguous multi-selection reads as ONE platter (Daniel,
        // 2026-08-09: 'they should not have the divots between rows — the
        // rounded squircles should be around the entire selection'):
        // merged edges square off and bleed over the List's inter-row gap.
        let radius = SidebarConstants.cornerRadius
        self.listRowBackground(
            UnevenRoundedRectangle(
                topLeadingRadius: mergeAbove ? 0 : radius,
                bottomLeadingRadius: mergeBelow ? 0 : radius,
                bottomTrailingRadius: mergeBelow ? 0 : radius,
                topTrailingRadius: mergeAbove ? 0 : radius,
                style: .continuous
            )
            .fill(
                active
                    ? Color.accentColor
                    : selected ? SidebarConstants.selectedRowFill : Color.clear
            )
            .padding(.horizontal, 4)
            .padding(.top, mergeAbove ? -3 : 0)
            .padding(.bottom, mergeBelow ? -3 : 0)
            .allowsHitTesting(false)
        )
    }
}

extension SidebarConstants {
    /// Finder's sidebar selection grey — the platter for a selected row in
    /// EVERY focus state (#4563). Never the accent. tertiarySystemFill, not
    /// unemphasizedSelectedContentBackgroundColor (Daniel, 2026-08-09 #116:
    /// "grey might be too dark") — Finder's sidebar wash is lighter than the
    /// table-selection grey.
    static var selectedRowFill: Color {
        #if os(macOS)
        Color(nsColor: .tertiarySystemFill)
        #else
        Color(.secondarySystemFill)
        #endif
    }
}
