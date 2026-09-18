import Foundation
import Testing

/// #4705 `m2p.library-is-always-navigator`: the shrinking-allowlist
/// guardrail named in `docs/contributor_manual/specs/ui/modes-to-panes.md`.
///
/// The regular-width Library leaf's mode router (`ContentView+Navigation.
/// swift`'s `contentView`) still mounts several bespoke full-width takeover
/// views today — `allowedTakeovers` below is that full list, MINUS
/// `WorkflowEditor(` (increment 2, moved to the Preview pane),
/// `OntologyBrowser(` (increment 3, the whole KG sidebar mode + its
/// intercept deleted), and `BatchRunView(`/`ChainEditorView(`/
/// `ScheduleDetailView(`/`TriggerDetailView(`/`ActivityWindowLauncherView(`
/// (increment 4a — the first four moved to the Preview pane exactly like
/// `WorkflowEditor`; the last one is a genuine deletion, replaced by
/// `ActivityDetailView` mounted directly). Each later increment drops one
/// more token from this allowlist; when it is empty (increment 8), the
/// Library pane never mounts a mode surface at all.
///
/// This scans ONLY the `.workflow` case's REGULAR-width branch — not the
/// whole file, and not the compact-flow branch inside the same case, which
/// still legitimately mounts `WorkflowEditor(` (the Hard constraint: compact
/// stays a push-stack takeover; `contentView` is also the compact/iOS root,
/// `ContentView+CompactReader.swift:90`). A whole-file scan would either
/// vacuously pass (missing the real regression) or false-positive on the
/// compact arm — the fixture check below proves the extraction actually
/// isolates the two branches, per the guardrails-must-match-granularity rule.
struct LibraryPaneNeverMountsModeSurfaceTests {

    /// Tokens still permitted anywhere in `contentView`'s router — every
    /// bespoke takeover view the #4705 review inventoried, minus
    /// `WorkflowEditor(` (increment 2), `OntologyBrowser(` (increment 3), and
    /// `BatchRunView(`/`ChainEditorView(`/`ScheduleDetailView(`/
    /// `TriggerDetailView(`/`ActivityWindowLauncherView(` (increment 4a).
    /// Shrinks by one more when increment 5 lands.
    private static let allowedTakeovers = [
        "ResearchWorkspaceView(", "ComparisonDetailView(",
    ]

    /// The bare identifier — not just a constructor call — must not appear
    /// anywhere in the app target once a file defining it is deleted: a
    /// lingering type reference (a property type, a static member access
    /// without `(`, an extension) would compile against nothing and is
    /// exactly the gap a `(`-only scan misses (the #4705 `GraphSimulation`
    /// build break — a type was still needed by a SURVIVING file — is the
    /// opposite failure mode of this same lesson: check what a file DEFINES,
    /// not just who calls its named type, before deleting it).
    /// `ActivityWindowLauncherView` (increment 4a) joins `OntologyBrowser`
    /// (increment 3) here.
    private static let deletedBareIdentifiers = ["OntologyBrowser", "ActivityWindowLauncherView"]

    private static let navigationFile = "Views/Shell/ContentView/ContentView+Navigation.swift"

    struct ExtractionFailure: Error, CustomStringConvertible {
        let message: String
        init(_ message: String) { self.message = message }
        var description: String { message }
    }

    /// The text between an opening `{` at `openBraceAt` (a UTF-16 offset
    /// into `source`) and its matching `}`, by simple depth counting — the
    /// same approach `ModelRowSourceGuardrailTests.balancedBody` uses.
    /// Sufficient here: this file holds no `{`/`}` inside string literals
    /// near the range being walked.
    private static func balancedBlock(in source: NSString, openBraceAt: Int) -> NSRange? {
        var depth = 0
        var index = openBraceAt
        let length = source.length
        while index < length {
            let char = source.character(at: index)
            if char == 0x7B { // "{"
                depth += 1
            } else if char == 0x7D { // "}"
                depth -= 1
                if depth == 0 {
                    return NSRange(location: openBraceAt, length: index - openBraceAt + 1)
                }
            }
            index += 1
        }
        return nil
    }

    /// The `.workflow` case's body, split into (compact branch, regular
    /// branch): `if Self.shouldUseCompactNavigationFlow(...) { <compact> }
    /// else { <regular> }`. Entirely `NSString`/UTF-16-offset based — no
    /// mixing with `String.Index`, which is where a brace-balance helper
    /// like this most often goes subtly wrong.
    private static func workflowCaseBranches(in source: String) throws -> (compact: String, regular: String) {
        let ns = source as NSString

        let caseMarker = "case .workflow(let workflow):"
        let caseRange = ns.range(of: caseMarker)
        guard caseRange.location != NSNotFound else {
            throw ExtractionFailure("could not find `\(caseMarker)` in \(navigationFile)")
        }
        let bodyStart = caseRange.location + caseRange.length

        let nextCaseMarker = "case .chain"  // prefix: matches the arm alone or leading a grouped arm (#4705 inc. 4a merged it)
        let searchFromNextCase = NSRange(location: bodyStart, length: ns.length - bodyStart)
        let nextCaseRange = ns.range(of: nextCaseMarker, options: [], range: searchFromNextCase)
        guard nextCaseRange.location != NSNotFound else {
            throw ExtractionFailure("could not find `\(nextCaseMarker)` to bound the `.workflow` case body")
        }
        let caseBody = ns.substring(with: NSRange(location: bodyStart, length: nextCaseRange.location - bodyStart))
        let caseBodyNS = caseBody as NSString

        let ifMarker = "if Self.shouldUseCompactNavigationFlow"
        let ifRange = caseBodyNS.range(of: ifMarker)
        guard ifRange.location != NSNotFound else {
            throw ExtractionFailure("could not find `\(ifMarker)` inside the `.workflow` case")
        }
        let searchFromIf = NSRange(
            location: ifRange.location + ifRange.length,
            length: caseBodyNS.length - (ifRange.location + ifRange.length)
        )
        let compactBraceRange = caseBodyNS.range(of: "{", options: [], range: searchFromIf)
        guard compactBraceRange.location != NSNotFound,
              let compactBlockRange = balancedBlock(in: caseBodyNS, openBraceAt: compactBraceRange.location)
        else {
            throw ExtractionFailure("could not brace-balance the compact-flow block")
        }
        let compactBlock = caseBodyNS.substring(with: compactBlockRange)

        let afterCompact = compactBlockRange.location + compactBlockRange.length
        let elseMarker = "else {"
        let searchFromCompactEnd = NSRange(location: afterCompact, length: caseBodyNS.length - afterCompact)
        let elseRange = caseBodyNS.range(of: elseMarker, options: [], range: searchFromCompactEnd)
        guard elseRange.location != NSNotFound else {
            throw ExtractionFailure("could not find the `else` branch after the compact-flow block")
        }
        // `elseRange` covers "else {"; its brace is the last character.
        let elseBraceLocation = elseRange.location + elseRange.length - 1
        guard let regularBlockRange = balancedBlock(in: caseBodyNS, openBraceAt: elseBraceLocation) else {
            throw ExtractionFailure("could not brace-balance the regular-width else block")
        }
        let regularBlock = caseBodyNS.substring(with: regularBlockRange)

        return (compact: compactBlock, regular: regularBlock)
    }

    @Test("the regular-width .workflow arm never mounts WorkflowEditor(")
    func regularWidthWorkflowArmNeverMountsEditor() throws {
        let root = try AppSource.root()
        let url = root.appendingPathComponent(Self.navigationFile)
        let source = try String(contentsOf: url, encoding: .utf8)
        let branches = try Self.workflowCaseBranches(in: source)

        // Fixture / positive control (guardrails-must-match-granularity):
        // the compact branch DOES legitimately mount WorkflowEditor(, so if
        // this assertion ever failed, the extraction above is broken and the
        // regular-branch assertion below would be meaningless.
        #expect(
            branches.compact.contains("WorkflowEditor("),
            "fixture check failed: the compact-flow branch should still mount WorkflowEditor( — if not, this test's brace extraction is broken and cannot be trusted"
        )

        #expect(
            !branches.regular.contains("WorkflowEditor("),
            "the regular-width .workflow arm mounts WorkflowEditor( — #4705 increment 2 moved the canvas to the Preview pane"
        )
    }

    @Test("the remaining takeover tokens are still an honest allowlist (none silently retired early)")
    func allowedTakeoversStillPresentSomewhereInTheRouter() throws {
        let root = try AppSource.root()
        let url = root.appendingPathComponent(Self.navigationFile)
        let source = try String(contentsOf: url, encoding: .utf8)
        for token in Self.allowedTakeovers {
            #expect(
                source.contains(token),
                "\(token) is no longer in ContentView+Navigation.swift — drop it from allowedTakeovers so this guardrail's shrinking list stays honest"
            )
        }
    }

    /// #4705 increment 3: `OntologyBrowser` itself — not just its
    /// constructor call — must not appear ANYWHERE in the app target's real
    /// code. A `(`-only scan misses a lingering type reference (a stored
    /// property's type, a static member access, an extension declaration) —
    /// exactly the gap that would have hidden `KnowledgeGraphViewModeSection`
    /// still referencing `OntologyBrowser.ViewMode` if that struct had not
    /// also been deleted alongside it.
    @Test("OntologyBrowser (bare identifier) does not appear anywhere in the app target")
    func deletedTypesDoNotLingerAnywhere() throws {
        let root = try AppSource.root()
        guard let enumerator = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: nil
        ) else {
            Issue.record("Could not enumerate \(root.path)")
            return
        }

        var offenders: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            let source = AppSource.codeOnly(try String(contentsOf: url, encoding: .utf8))
            for identifier in Self.deletedBareIdentifiers where source.contains(identifier) {
                offenders.append("\(relative): \(identifier)")
            }
        }

        #expect(
            offenders.isEmpty,
            "A deleted #4705-increment-3 type still appears in real code: \(offenders.joined(separator: ", "))"
        )
    }
}
