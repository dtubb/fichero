@testable import Fichero
import Foundation
import Testing

/// #4416: the island read
/// `Local › Page 1 — fichero_upload_c84fgjke.pdf - Page 1`
/// for a document the sidebar called `18590129.pdf`.
///
/// Two defects, one cause.
///
/// **The name.** `save_uploaded_file` writes `fichero_upload_<random><ext>` and
/// `ingest_file` derives `Document.name` from that path. The engine corrects it
/// back to the user's filename (#1104) — but only for the uploaded document.
/// Its page children come from the same temp path and are never fixed up, so a
/// page's `name` is a storage artifact. For archival material the filename is
/// often the only human-readable identity a scan has: `18590129.pdf` is the
/// date 1859-01-29.
///
/// **The doubling.** `toolbarTitle` composed `"Page 1 — <name>"` while the
/// breadcrumb separately appended a page label with a different separator.
struct DocumentTitleTests {

    private func page(
        id: String = "page-1",
        parentId: String? = "pdf-1",
        name: String = "fichero_upload_c84fgjke.pdf",
        sequence: Int? = 1
    ) -> Document {
        Document(id: id, parentId: parentId, docType: .page, name: name, sequence: sequence)
    }

    private func pdf(name: String = "18590129.pdf") -> Document {
        Document(id: "pdf-1", docType: .file, name: name)
    }

    // MARK: - The storage name never reaches the user

    /// The reported string, at its source.
    @Test("a page never shows the engine's upload temp name")
    func pageNeverShowsTheStorageName() {
        let name = DocumentTitle.displayName(for: page(), parent: pdf())

        #expect(!name.contains("fichero_upload"))
        #expect(name == "Page 1")
    }

    /// The rule, not the instance: no input containing a storage name can
    /// produce a title containing it. This is what makes the leak structurally
    /// impossible rather than fixed for one case.
    @Test("no document ever renders its storage name")
    func noDocumentEverRendersAStorageName() {
        let storage = "fichero_upload_c84fgjke.pdf"
        let candidates = [
            page(name: storage),
            page(name: storage, sequence: nil),
            Document(id: "d", docType: .file, name: storage),
            Document(id: "d", parentId: "pdf-1", docType: .file, name: storage)
        ]
        for document in candidates {
            for parent in [nil, pdf(), pdf(name: storage)] as [Document?] {
                let name = DocumentTitle.displayName(for: document, parent: parent)
                #expect(
                    !name.contains(DocumentTitle.storageNamePrefix),
                    Comment(rawValue: "\(document.id)/\(parent?.name ?? "no parent"): \(name)"))
                #expect(!name.isEmpty)
            }
        }
    }

    /// A file whose own name is real keeps it — this fix must not relabel
    /// everything, only refuse the storage artifact.
    @Test("a real filename is shown unchanged")
    func realFilenamesAreShownUnchanged() {
        #expect(DocumentTitle.displayName(for: pdf()) == "18590129.pdf")
        #expect(DocumentTitle.displayName(for: pdf(name: "NCM_Diary.pdf")) == "NCM_Diary.pdf")
    }

    /// A deliberately-set metadata title outranks the filename.
    @Test("a metadata title wins over the filename")
    func metadataTitleWins() {
        var document = pdf()
        document.metadata["title"] = AnyCodable("Marshall Diary, 29 January 1859")
        #expect(DocumentTitle.displayName(for: document) == "Marshall Diary, 29 January 1859")
    }

    @Test("a blank metadata title is ignored rather than shown")
    func blankMetadataTitleIsIgnored() {
        var document = pdf()
        document.metadata["title"] = AnyCodable("   ")
        #expect(DocumentTitle.displayName(for: document) == "18590129.pdf")
    }

    // MARK: - Honest degradation

    /// "A document whose source name is missing degrades to something honest,
    /// not to the storage id." Nothing here may fall back to an identifier.
    @Test("a nameless document degrades to a placeholder, never an id")
    func namelessDocumentDegradesHonestly() {
        let nameless = Document(id: "doc:66791833f63f49d9ace318594252f621", docType: .file, name: "")
        let name = DocumentTitle.displayName(for: nameless)

        #expect(name == DocumentTitle.placeholder)
        #expect(!name.contains("doc:"), "an internal id is not a name (#4398)")
        #expect(!name.contains("66791833"))
    }

    /// A page with no sequence cannot say "Page N", and its own name is the
    /// storage artifact — so it borrows the parent's real name rather than
    /// showing either.
    @Test("a page with no number falls back to its parent, not its storage name")
    func pageWithoutNumberFallsBackToParent() {
        let name = DocumentTitle.displayName(for: page(sequence: nil), parent: pdf())
        #expect(name == "18590129.pdf")
    }

    @Test("with no parent and no number, the placeholder stands")
    func noParentNoNumberIsPlaceholder() {
        #expect(
            DocumentTitle.displayName(for: page(parentId: nil, sequence: nil), parent: nil)
                == DocumentTitle.placeholder
        )
    }

    // MARK: - The page appears exactly once

    /// The window title is the LEAF. Composing "<page> — <document>" here while
    /// the breadcrumb also appends a page label is what produced the doubling.
    @Test("the window title names the page once and only the page")
    func windowTitleNamesThePageOnce() {
        let title = DocumentTitle.windowTitle(leaf: page(), parent: pdf(), selectedPageCount: 1)

        #expect(title == "Page 1")
        #expect(title.components(separatedBy: "Page").count - 1 == 1)
        #expect(!title.contains("—"), "the path belongs to the breadcrumb, not the title")
    }

    /// A multi-page selection reports the count, still without a filename.
    @Test("a multi-page selection reports its count")
    func multiPageSelectionReportsCount() {
        let title = DocumentTitle.windowTitle(leaf: page(), parent: pdf(), selectedPageCount: 4)
        #expect(title == "4 pages")
        #expect(!title.contains("fichero_upload"))
    }

    @Test("no selection at all still produces something honest")
    func noSelectionIsHonest() {
        #expect(DocumentTitle.windowTitle(leaf: nil) == DocumentTitle.placeholder)
    }

    // MARK: - Middle truncation keeps what identifies the file

    /// Truncating the tail drops the extension; truncating the head drops the
    /// date or folio that identifies an archival scan. Both ends carry meaning.
    @Test("a long name truncates in the middle, keeping start and extension")
    func longNamesTruncateInTheMiddle() {
        let long = "NCM_Diary_19240101_folio_17_recto_verso_scanned.pdf"
        let short = DocumentTitle.middleTruncated(long, limit: 24)

        #expect(short.count <= 24)
        #expect(short.hasPrefix("NCM_Diary_1924"))
        #expect(short.hasSuffix(".pdf"))
        #expect(short.contains("…"))
    }

    @Test("a name within budget is untouched")
    func shortNamesAreUntouched() {
        #expect(DocumentTitle.middleTruncated("18590129.pdf", limit: 40) == "18590129.pdf")
    }

    /// Whatever the input, the result fits — a truncator that can exceed its
    /// own limit is not one.
    @Test("no input can exceed the limit")
    func noInputExceedsTheLimit() {
        for name in [
            String(repeating: "x", count: 300),
            String(repeating: "x", count: 300) + ".pdf",
            "no-extension-at-all-but-still-extremely-long-indeed",
            "a.reallyveryverylongextensionthatisnotone"
        ] {
            for limit in [5, 12, 24, 40] {
                let short = DocumentTitle.middleTruncated(name, limit: limit)
                #expect(short.count <= limit, Comment(rawValue: "\(limit): \(short)"))
                #expect(!short.isEmpty)
            }
        }
    }

    // MARK: - Every surface reads the same composer

    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    // MARK: - The sweep, as a guardrail

    /// Display APIs — anything whose argument reaches a human, by eye or by
    /// VoiceOver. A window title and a tooltip are renders as surely as a
    /// `Text` is; the first sweep looked only for `Text(…)` and so let a
    /// `navigationTitle` and four `help`/`accessibilityLabel` calls through.
    static let displayAPIs = [
        "Text(", "Label(", "LabeledContent(",
        ".help(", ".navigationTitle(", ".navigationSubtitle(",
        ".accessibilityLabel(", ".accessibilityValue(",
        ".confirmationDialog(", ".alert(", ".searchable("
    ]

    /// Spellings this codebase uses for a `Document`-typed binding. Kept to
    /// known names on purpose: a bare `.name` would flag `provider.name` and
    /// `workflow.name`, which are real names their owners chose.
    static let documentBindings = [
        "document", "doc", "page", "parent", "leaf", "child",
        "shownDocument", "selectedDocument", "pushedReaderDocument"
    ]

    /// Whether `line` renders a `Document`'s raw `name` through a display API.
    ///
    /// Deliberately line-scoped: the display call and its argument are written
    /// together, and matching per line is what lets the failure name a spot a
    /// human can go fix.
    static func rendersARawName(_ line: String) -> Bool {
        // Renaming EDITS the real name — the one place the raw value is right.
        guard !line.contains("editingName") else { return false }
        guard Self.displayAPIs.contains(where: line.contains) else { return false }

        return Self.documentBindings.contains { binding in
            Self.mentions("\(binding).name", in: line)
                || Self.mentions("\(binding)?.name", in: line)
        }
    }

    /// Substring match on whole-identifier boundaries, so `document.name`
    /// does not also match `subdocument.name` or `document.nameComponents`.
    private static func mentions(_ needle: String, in line: String) -> Bool {
        var searchStart = line.startIndex
        while let found = line.range(of: needle, range: searchStart..<line.endIndex) {
            let beforeOK = found.lowerBound == line.startIndex || {
                let before = line[line.index(before: found.lowerBound)]
                return !before.isLetter && !before.isNumber && before != "." && before != "_"
            }()
            let afterOK = found.upperBound == line.endIndex || {
                let after = line[found.upperBound]
                return !after.isLetter && !after.isNumber && after != "_"
            }()
            if beforeOK, afterOK { return true }
            searchStart = found.upperBound
        }
        return false
    }

    /// The matcher fires. A guardrail that cannot fail is not a guardrail, and
    /// this one is a heuristic over source text — the thing most likely to rot
    /// into vacuous truth. Every shape that actually escaped the first sweep is
    /// listed here, so a future narrowing of the matcher fails HERE, loudly,
    /// rather than going quiet over the whole app.
    @Test("the raw-name matcher catches every shape that escaped the first sweep")
    func theMatcherFires() {
        let offenders = [
            "Text(document.name)",
            "Text(doc.name)",
            "Text(doc.pageThumbnailLabel ?? doc.name)",
            ".navigationTitle(doc.name)",
            ".navigationTitle(shownDocument?.name ?? \"Document\")",
            ".help(document.pageThumbnailLabel ?? document.name)",
            ".help(\"Bookmark “\\(document.name)”\")",
            ".accessibilityLabel(page.name)",
            ".accessibilityLabel(doc.docType == .folder ? \"\\(doc.name), folder\" : doc.name)"
        ]
        for line in offenders {
            #expect(Self.rendersARawName(line), Comment(rawValue: "missed: \(line)"))
        }

        let allowed = [
            "Text(DocumentTitle.displayName(for: document))",
            ".navigationTitle(DocumentTitle.displayName(for: doc))",
            "TextField(\"Name\", text: $editingName)",
            "Text(provider.name)",                     // a provider's own name
            "Text(workflow.name)",                     // a workflow's own name
            "let name = document.name",                // not a render
            "Text(subdocument.nameComponents.first)"   // not `document.name`
        ]
        for line in allowed {
            #expect(!Self.rendersARawName(line), Comment(rawValue: "false positive: \(line)"))
        }
    }

    /// No view renders a `Document`'s raw `name`.
    ///
    /// #4416 was reported on the island. The same read appeared in the reader,
    /// the inspector header, three grids, the editor header, chat scope, four
    /// pickers, the focused-document window, the pushed compact reader, the
    /// bookmark tooltip and the PDF page grid's VoiceOver label. Fixing the
    /// reported one and leaving the rest is how a defect class survives being
    /// fixed — so this reads the directory rather than a fixture list, and a
    /// view written next week is covered the day it exists.
    ///
    /// Two of the escapes were `pageThumbnailLabel ?? name`, which reads as a
    /// defence and is not one: the label is `nil` exactly when a page has no
    /// sequence — the case with no page number to show — so it fell through to
    /// the storage name precisely when it mattered.
    @Test("no view renders a document's raw name")
    func noViewRendersARawDocumentName() throws {
        let root = try AppSource.root().appendingPathComponent("Views")

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" } ?? []
        #expect(!files.isEmpty, "the sweep must actually read files")

        var offenders: [String] = []
        for file in files {
            let lines = Self.codeOnly(try String(contentsOf: file, encoding: .utf8))
                .split(separator: "\n", omittingEmptySubsequences: false)
            for (index, line) in lines.enumerated() where Self.rendersARawName(String(line)) {
                offenders.append("\(file.lastPathComponent):\(index + 1) \(line.trimmingCharacters(in: .whitespaces))")
            }
        }
        #expect(offenders.isEmpty, Comment(rawValue: offenders.joined(separator: "\n")))
    }

    /// "One function builds a document title, and every surface uses it."
    /// Comments are stripped: the ones in these files quote the old shape.
    @Test("the title and the breadcrumb both compose through DocumentTitle")
    func bothSurfacesComposeThroughDocumentTitle() throws {
        let state = try Self.codeOnly(
            AppSource.text("Views/Shell/ContentView/ContentView+StateDisplay.swift"))
        #expect(state.contains("DocumentTitle.windowTitle("))
        #expect(state.contains("DocumentTitle.displayName("))
        // The old composer, in its exact code form.
        #expect(!state.contains("\"\\(pageLabel) — \\($0.name)\""))

        let breadcrumb = try Self.codeOnly(AppSource.text("Models/BreadcrumbBuilder.swift"))
        #expect(breadcrumb.contains("DocumentTitle.displayName("))
        #expect(!breadcrumb.contains("Segment(name: $0.name"))
        #expect(!breadcrumb.contains("path.insert(doc.name"))
    }
}
