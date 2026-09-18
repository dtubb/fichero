//
//  ModelRowSourceGuardrailTests.swift
//  FicheroTests
//
//  Pins `models.one-row` (docs/contributor_manual/specs/ui/
//  model-selector-consistency.md, RATIFIED 2026-09-15): the island, workflow
//  bar, chat and Settings render the SAME row component
//  (`SharedModelRow`) — no surface hand-draws its own.
//
//  Before this fix, `ModelChipToolbarItem` (the reference surface itself) had
//  a private `ModelPickerRow` that duplicated `SharedModelRow` byte-for-byte
//  in shape: a leading `isCurrent`-driven checkmark tick, `ModelFamilyMark`,
//  and a trailing provider label. This test scans every `.swift` file under
//  `Views/` for a struct with that exact shape and fails if one exists
//  anywhere but `SharedModelRow.swift` — so a reintroduced `ModelPickerRow`
//  (or any equivalent) fails a test instead of drifting silently again.
//

import Foundation
import Testing

struct ModelRowSourceGuardrailTests {

    /// The ONE file allowed to declare a model row shaped this way.
    private static let allowedFile = "Views/Shell/Toolbar/SharedModelPicker/SharedModelRow.swift"

    @Test("No surface under Views/ hand-draws a second model row")
    func noSecondModelRowStruct() throws {
        let root = try AppSource.root()
        let viewsRoot = root.appendingPathComponent("Views")
        guard let enumerator = FileManager.default.enumerator(
            at: viewsRoot, includingPropertiesForKeys: nil
        ) else {
            Issue.record("Could not enumerate \(viewsRoot.path)")
            return
        }

        var offenders: [String] = []
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            let relative = AppSource.relativePath(of: url, under: root)
            guard relative != Self.allowedFile else { continue }
            let source = AppSource.codeOnly(try String(contentsOf: url, encoding: .utf8))
            for candidate in Self.structBodies(in: source) where Self.rendersAModelRow(candidate.body) {
                offenders.append("\(relative): struct \(candidate.name)")
            }
        }

        #expect(
            offenders.isEmpty,
            // ONE literal, not `+`-joined pieces: #expect's message is `Comment?`, and a
            // `+` expression of literals does not type-check there (Swift Testing pitfall).
            "A second model-row struct exists outside SharedModelRow.swift: \(offenders.joined(separator: ", ")). Every picker surface must render SharedModelRow — the ONE row the spec requires."
        )
    }

    /// A struct's body counts as "a model row" when it renders the same THREE
    /// ingredients the reference row does: a leading current-selection tick
    /// (`checkmark`) gated on an `isCurrent` flag, plus the family mark. This
    /// is the exact shape `ModelChipToolbarItem`'s deleted `ModelPickerRow`
    /// had — reintroduce it (there or anywhere else) and this fails.
    private static func rendersAModelRow(_ body: String) -> Bool {
        body.contains("ModelFamilyMark(") && body.contains("isCurrent") && body.contains("checkmark")
    }

    /// Every `struct <Name>: ... View ... { ... }` declaration in the source,
    /// paired with its brace-balanced body.
    private static func structBodies(in source: String) -> [(name: String, body: String)] {
        guard let regex = try? NSRegularExpression(
            pattern: #"struct\s+(\w+)[^{]*:\s*[^{]*\bView\b[^{]*\{"#
        ) else { return [] }
        let ns = source as NSString
        var results: [(String, String)] = []
        for match in regex.matches(in: source, range: NSRange(location: 0, length: ns.length)) {
            guard let nameRange = Range(match.range(at: 1), in: source) else { continue }
            let name = String(source[nameRange])
            let openBraceLoc = match.range.location + match.range.length - 1
            guard let body = Self.balancedBody(in: ns, openBraceAt: openBraceLoc) else { continue }
            results.append((name, body))
        }
        return results
    }

    /// The text between a `{` at `openBraceAt` and its matching `}`, by simple
    /// depth counting — sufficient for these files, which hold no `{`/`}` inside
    /// string literals.
    private static func balancedBody(in source: NSString, openBraceAt: Int) -> String? {
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
                    return source.substring(
                        with: NSRange(location: openBraceAt, length: index - openBraceAt + 1)
                    )
                }
            }
            index += 1
        }
        return nil
    }
}
