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
        "shownDocument", "selectedDocument", "pushedReaderDocument",
        "activeLocationDocument"
    ]

    /// Whether `expression` IS a raw `Document.name`, rather than merely
    /// containing one.
    ///
    /// Two accepted forms, and the second is the one that kept escaping:
    ///
    /// - the expression begins with the raw name (`doc.name`, `doc.name + x`);
    /// - a `??` chain whose LAST RESORT is the raw name
    ///   (`doc.pageThumbnailLabel ?? doc.name`).
    ///
    /// The `??` form reads as a defence and is not one. `pageThumbnailLabel` is
    /// `nil` exactly when a page has no sequence — the case with no page number
    /// to show — so it falls through to the storage name *precisely when it
    /// matters*. That is stated in this file's own doc comment as a lesson
    /// learned from #4416, and the matcher written alongside it still could not
    /// see the shape.
    ///
    /// A haystack (`"\(doc.name) \(excerpt)"`) and a comparator
    /// (`lhs.name.compare(…)`) match neither form and stay unflagged.
    static func isRawNameExpression(_ expression: String) -> Bool {
        expression
            .components(separatedBy: "??")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .contains { segment in
                Self.documentBindings.contains { binding in
                    Self.startsWithRawName(segment, prefix: "\(binding).name")
                        || Self.startsWithRawName(segment, prefix: "\(binding)?.name")
                }
            }
    }

    /// Whether `line` renders a `Document`'s raw `name` through a display API.
    ///
    /// Line-scoped by itself. `leaks(in:)` hands it a LOGICAL line — a display
    /// call joined with its continuations — because SwiftUI wraps arguments
    /// onto their own lines constantly, and a `Label(` on one line with its
    /// `page.name` argument on the next reads as clean to a per-line matcher.
    static func rendersARawName(_ line: String) -> Bool {
        // Renaming EDITS the real name — the one place the raw value is right.
        guard !line.contains("editingName") else { return false }
        guard Self.displayAPIs.contains(where: line.contains) else { return false }

        return Self.documentBindings.contains { binding in
            Self.mentions("\(binding).name", in: line)
                || Self.mentions("\(binding)?.name", in: line)
        }
    }

    /// Whether `line` MANUFACTURES a display string out of a `Document`'s raw
    /// `name` — a helper that returns it, for a `Text(…)` one hop away.
    ///
    /// ## The blind spot this closes
    ///
    /// `rendersARawName` is line-scoped, and that was stated as a virtue: the
    /// display call and its argument are written together. They are — *when the
    /// argument is the value*. They are not when the argument is a call:
    ///
    ///     Text(documentNameForPath(filePath))      // no `.name` on this line
    ///     …
    ///     private func documentNameForPath(…) -> String {
    ///         for doc in … { return doc.name }     // no display API on this line
    ///     }
    ///
    /// Neither line trips the matcher, so the sweep that "scanned 587 files"
    /// and reported the whole app clean was reporting on a shape the app had
    /// already moved past. #4416 fixed every place that *rendered* a raw name
    /// and left the places that *produce* one, which is the same defect one
    /// call frame up — and exactly the class the original fix set out to kill.
    ///
    /// Honest about what it is: a heuristic. It fires on a returned expression
    /// that BEGINS with a document binding, so a search haystack
    /// (`return "\(doc.name) \(excerpt)"`) and a comparator
    /// (`return lhs.name.compare(…)`) are not display strings and are not
    /// flagged. It does NOT cover a raw name assigned into a model field
    /// (`SidebarItem(name: doc.pageThumbnailLabel ?? doc.name)`) — that is a
    /// real remaining leak, but changing it changes what the sidebar calls
    /// every page, which is a design call and not a guardrail's to make
    /// silently. It is reported rather than quietly allowlisted, because an
    /// allowlist is how a known leak becomes a forgotten one.
    static func producesARawName(_ line: String) -> Bool {
        guard !line.contains("editingName") else { return false }
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("return ") else { return false }
        let returned = String(trimmed.dropFirst("return ".count))
            .trimmingCharacters(in: .whitespaces)

        return Self.isRawNameExpression(returned)
    }

    // MARK: - The shape a line cannot see: bound here, displayed there

    /// The identifier `line` assigns to, and whether the value is a raw name.
    ///
    /// Covers `let x =`, `var x =` and a bare reassignment `x =`. The last one
    /// matters in both directions: it can taint a name, and — the case that
    /// caught a false positive in this matcher's own fixture — it can CLEAR
    /// one, because `var name = doc.name` followed by
    /// `name = DocumentTitle.displayName(for: doc)` renders the composed title,
    /// not the raw one. A checker that flagged that would be crying wolf at
    /// code that is already right.
    ///
    /// `nil` when the line assigns nothing — including `var x: String {`, which
    /// has no `=` and is a computed property, and `if a.count == 1, let x = y`,
    /// whose first `=` belongs to a comparison.
    static func boundName(_ line: String) -> (name: String, isRaw: Bool)? {
        var rest = line.trimmingCharacters(in: .whitespaces)
        for keyword in ["let ", "var "] where rest.hasPrefix(keyword) {
            rest = String(rest.dropFirst(keyword.count))
        }
        guard let equals = rest.firstIndex(of: "="),
              rest[rest.index(after: equals)...].first != "="  // `==`, a comparison
        else { return nil }

        var declared = String(rest[rest.startIndex..<equals])
        if let colon = declared.firstIndex(of: ":") { declared = String(declared[..<colon]) }
        let identifier = declared.trimmingCharacters(in: .whitespaces)
        guard let first = identifier.first, first.isLetter || first == "_",
              identifier.allSatisfy({ $0.isLetter || $0.isNumber || $0 == "_" })
        else { return nil }  // a destructure, a member assignment, or `+=`

        let value = String(rest[rest.index(after: equals)...])
            .trimmingCharacters(in: .whitespaces)
        return (identifier, Self.isRawNameExpression(value))
    }

    /// Whether `line` opens a new member, and so ends the scope of any local
    /// binding above it.
    ///
    /// Without this the taint set would be file-scoped, and a `let name =
    /// doc.name` in one helper would flag a `Text(name)` in an unrelated one
    /// fifty lines below — a false positive, and a check that cries wolf gets
    /// disabled.
    static func beginsAMember(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasSuffix("{") else { return false }
        return trimmed.contains("func ") || trimmed.contains("var ")
    }

    /// How many lines of a wrapped call to join before giving up. A display
    /// call whose argument list runs longer than this is not the shape being
    /// hunted, and joining further only invents false positives.
    static let continuationLimit = 8

    /// `lines[index]` joined with its continuations when it opens a display
    /// call it does not close. Any other line is returned as-is.
    static func logicalLine(at index: Int, in lines: [String]) -> String {
        var text = lines[index]
        guard Self.displayAPIs.contains(where: text.contains) else { return text }

        var depth = Self.parenDepth(text)
        var cursor = index + 1
        while depth > 0, cursor < lines.count, cursor - index <= Self.continuationLimit {
            text += " " + lines[cursor].trimmingCharacters(in: .whitespaces)
            depth += Self.parenDepth(lines[cursor])
            cursor += 1
        }
        return text
    }

    private static func parenDepth(_ line: String) -> Int {
        line.reduce(0) { depth, character in
            character == "(" ? depth + 1 : (character == ")" ? depth - 1 : depth)
        }
    }

    /// Every raw-name leak in one file's lines, as `(line index, shape)`.
    ///
    /// File-scoped on purpose. The two line-scoped matchers above answer
    /// "is THIS line a leak", and a display name that is bound on one line and
    /// used on another is a leak that no single line contains. This pass
    /// carries the binding forward — within its member — so
    ///
    ///     let name = document.pageThumbnailLabel ?? document.name
    ///     …
    ///     return name
    ///
    /// is caught, which is exactly `tileAccessibilityLabel`: the tile's visible
    /// `Text` was fixed to compose through `DocumentTitle`, and the VoiceOver
    /// label three lines below it was not. Sighted users read "Page 1" while
    /// VoiceOver said `fichero_upload_c84fgjke.pdf`, on the same tile.
    static func leaks(in lines: [String]) -> [(index: Int, shape: String)] {
        var tainted: Set<String> = []
        var found: [(index: Int, shape: String)] = []

        for (index, line) in lines.enumerated() {
            if Self.beginsAMember(line) { tainted.removeAll() }
            if line.contains("editingName") { continue }

            // Renders is tested BEFORE the assignment branch: `let label =
            // Text(doc.name)` is both, and it is the leak that matters.
            let logical = Self.logicalLine(at: index, in: lines)
            if Self.rendersARawName(logical) { found.append((index, "renders")); continue }

            if let bound = Self.boundName(line) {
                if bound.isRaw { tainted.insert(bound.name) } else { tainted.remove(bound.name) }
                continue
            }

            if Self.producesARawName(line) { found.append((index, "produces")); continue }
            guard !tainted.isEmpty else { continue }

            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("return "),
               tainted.contains(where: {
                   Self.startsWithRawName(
                       String(trimmed.dropFirst("return ".count))
                           .trimmingCharacters(in: .whitespaces),
                       prefix: $0)
               }) {
                found.append((index, "returns a name bound above"))
                continue
            }

            if Self.displayAPIs.contains(where: logical.contains),
               tainted.contains(where: { Self.mentions($0, in: logical) }) {
                found.append((index, "renders a name bound above"))
            }
        }
        return found
    }

    /// `expression` begins with exactly `prefix` as a whole identifier, so
    /// `doc.nameComponents.first` is not read as `doc.name`. Same boundary rule
    /// as `mentions`, anchored at the start because that is what distinguishes
    /// "the value IS the name" from "the name is one ingredient".
    private static func startsWithRawName(_ expression: String, prefix: String) -> Bool {
        guard expression.hasPrefix(prefix) else { return false }
        let after = expression.index(expression.startIndex, offsetBy: prefix.count)
        guard after < expression.endIndex else { return true }
        let next = expression[after]
        return !next.isLetter && !next.isNumber && next != "_"
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

    /// The producer matcher fires, on the two shapes that actually survived
    /// #4416 by hiding one call frame above a `Text(…)`.
    ///
    /// A guardrail added to close a blind spot has to prove it closes THAT
    /// blind spot, not a nearby one — so the offenders here are the real lines,
    /// copied from the files they were found in, and the allowed list is every
    /// nearby shape that must keep working. Without this, narrowing the matcher
    /// later would go quiet instead of failing.
    @Test("the raw-name producer matcher catches helpers that manufacture a name")
    func theProducerMatcherFires() {
        let offenders = [
            "            return doc.name",                            // ActivityProgressView
            "        return activeLocationDocument?.name ?? toolbarTitle",  // ContentView
            "return document.name",
            "        return page?.name ?? \"Untitled\""
        ]
        for line in offenders {
            #expect(Self.producesARawName(line), Comment(rawValue: "missed: \(line)"))
        }

        let allowed = [
            "return DocumentTitle.displayName(for: doc)",
            "return \"\\(doc.name) \\(excerpt)\"",           // a search haystack, not a render
            "return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending",
            "return BookmarkItem(id: id, name: doc.name)",  // assignment, not a returned name
            "return doc.nameComponents.first",              // not `doc.name`
            "return provider.name",                         // a provider's own name
            "let title = doc.name"                          // not a returned display string
        ]
        for line in allowed {
            #expect(!Self.producesARawName(line), Comment(rawValue: "false positive: \(line)"))
        }
    }

    /// The file-scoped pass fires on the three shapes no single line contains.
    ///
    /// Each fixture is the real code, copied from the file it was found in, so
    /// a later narrowing fails HERE rather than going quiet over 907 files.
    @Test("the file-scoped pass catches a wrapped call, a bound name, and a ?? fallback")
    func theFileScopedPassFires() {
        // LibraryThumbnailViews.tileAccessibilityLabel — bound, then returned.
        let boundThenReturned = [
            "    private var tileAccessibilityLabel: String {",
            "        let name = document.pageThumbnailLabel ?? document.name",
            "        if document.docType == .folder { return \"\\(name), folder\" }",
            "        return name",
            "    }"
        ]
        #expect(
            Self.leaks(in: boundThenReturned).map(\.index) == [3],
            "a name bound above and returned below is still a leaked name")

        // LibraryView+TableColumns — a Label whose argument wrapped onto its
        // own line, which is how it survived a per-line matcher.
        let wrappedCall = [
            "            Label(",
            "                page.pageThumbnailLabel.map { \"Page \\($0)\" } ?? page.name,",
            "                systemImage: \"doc.richtext\"",
            "            )"
        ]
        #expect(
            Self.leaks(in: wrappedCall).map(\.index) == [0],
            "a display call reports at the line a human opens, not at its argument")

        // A binding rendered rather than returned.
        #expect(
            Self.leaks(in: [
                "    var body: some View {",
                "        let name = doc.name",
                "        Text(name)"
            ]).map(\.index) == [2])
    }

    /// The other half of the same guardrail: what it must NOT say.
    ///
    /// A check that cries wolf gets disabled, so the shapes that are already
    /// right are pinned as firmly as the shapes that are wrong.
    @Test("the file-scoped pass stays quiet on composed titles and out-of-scope bindings")
    func theFileScopedPassStaysQuiet() {
        // The fixed shapes must go quiet, or the sweep below is unpassable.
        #expect(Self.leaks(in: [
            "    private var tileAccessibilityLabel: String {",
            "        let name = DocumentTitle.displayName(for: document)",
            "        return name",
            "    }"
        ]).isEmpty)
        #expect(Self.leaks(in: [
            "            Label(",
            "                DocumentTitle.displayName(for: page),",
            "                systemImage: \"doc.richtext\"",
            "            )"
        ]).isEmpty)

        // A binding cannot leak past the member it was declared in, and a
        // rebinding to a composed title clears it.
        #expect(Self.leaks(in: [
            "    private var searchHaystack: String {",
            "        let name = doc.name",
            "        return \"\\(name) \\(excerpt)\"",
            "    }",
            "    private var title: some View {",
            "        Text(name)",
            "    }"
        ]).isEmpty, "a binding in one member must not flag an identifier in the next")
        #expect(Self.leaks(in: [
            "    var body: some View {",
            "        var name = doc.name",
            "        name = DocumentTitle.displayName(for: doc)",
            "        Text(name)"
        ]).isEmpty, "a reassignment to a composed title clears the taint")
    }

    /// `??` is what the matcher was blind to, stated on its own.
    @Test("a ?? fallback to a raw name is a raw name")
    func fallbackToARawNameIsARawName() {
        #expect(Self.isRawNameExpression("document.pageThumbnailLabel ?? document.name"))
        #expect(Self.isRawNameExpression("page.pageThumbnailLabel.map { \"Page \\($0)\" } ?? page.name"))
        #expect(Self.isRawNameExpression("doc.name"))
        #expect(Self.isRawNameExpression("doc?.name ?? \"Untitled\""))

        #expect(!Self.isRawNameExpression("DocumentTitle.displayName(for: doc)"))
        #expect(!Self.isRawNameExpression("provider.name ?? \"\""))
        #expect(!Self.isRawNameExpression("\"\\(doc.name) \\(excerpt)\""))
        #expect(!Self.isRawNameExpression("doc.nameComponents.first ?? doc.title"))
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
    /// Directories a user-facing name can be decided in.
    ///
    /// The second half of the same blind spot. The first sweep read `Views/`
    /// only, on the reasoning that rendering happens in views — true of the
    /// `Text(…)` call and false of the string it is handed. `Models/` and
    /// `Services/` build display strings too, and were scanned by nothing.
    /// "587 files scanned" sounded like coverage; it was the count of one
    /// directory.
    /// `App/` and `Intents/` join them: an App Intent's dialog and an app-level
    /// window title are read by a human as surely as a `Text` is. `Resources/`
    /// holds no Swift and is deliberately absent — a directory with no files
    /// would trip the per-directory floor below.
    static let sweptDirectories = ["Views", "Models", "Services", "App", "Intents"]

    /// The whole class, in one sweep: rendered, produced, or bound-then-used.
    ///
    /// One test rather than three, because the pass that carries a binding
    /// across lines cannot be split by shape without running the file three
    /// times. Each offender names its own shape, so the failure still says
    /// which matcher fired and where.
    @Test("no surface renders, produces, or binds a document's raw name")
    func noSurfaceLeaksARawDocumentName() throws {
        let scan = try Self.sweep()

        // Population floor (#4487): a sweep that read no files, or read them
        // and never once saw the token it hunts, is BLIND rather than clean —
        // and blind reports success forever. `.name` on a document binding is
        // ubiquitous and legitimate in most of its uses; zero of them means the
        // reader changed, not the app.
        #expect(
            scan.filesRead > 500,
            Comment(rawValue: "BLIND: read \(scan.filesRead) files across \(Self.sweptDirectories)"))
        #expect(
            scan.rawNameMentions > 0,
            "BLIND: not one document `.name` seen in the whole app source")

        #expect(
            scan.offenders.isEmpty,
            Comment(rawValue: """
                A document's raw `name` is the engine's storage artifact for every page child \
                (#4416). Compose through `DocumentTitle.displayName(for:parent:)` instead.

                \(scan.offenders.joined(separator: "\n"))
                """))
    }

    private struct Scan {
        var offenders: [String] = []
        var filesRead = 0
        var rawNameMentions = 0
    }

    /// Read every swept directory and report each leak as `file:line (shape)
    /// source` a human can go open.
    private static func sweep() throws -> Scan {
        let root = try AppSource.root()
        var scan = Scan()

        for directory in Self.sweptDirectories {
            let files = FileManager.default
                .enumerator(at: root.appendingPathComponent(directory), includingPropertiesForKeys: nil)?
                .compactMap { $0 as? URL }
                .filter { $0.pathExtension == "swift" }
                // Vendored and built copies of the tree exist only in a worktree
                // that has been built in, so a sweep that counts them reports a
                // different population on two machines.
                .filter { !$0.path.contains("/.build/") && !$0.path.contains("/DerivedData/") } ?? []
            // Per-directory, not just overall: a renamed directory would
            // otherwise drop out of the sweep while the total stayed healthy.
            #expect(!files.isEmpty, Comment(rawValue: "swept nothing in \(directory)/"))
            scan.filesRead += files.count

            for file in files {
                let lines = Self.codeOnly(try String(contentsOf: file, encoding: .utf8))
                    .split(separator: "\n", omittingEmptySubsequences: false)
                    .map(String.init)

                scan.rawNameMentions += lines.filter { line in
                    Self.documentBindings.contains { Self.mentions("\($0).name", in: line) }
                }.count

                for leak in Self.leaks(in: lines) {
                    scan.offenders.append(
                        "\(file.lastPathComponent):\(leak.index + 1) (\(leak.shape)) "
                        + lines[leak.index].trimmingCharacters(in: .whitespaces))
                }
            }
        }

        return scan
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
