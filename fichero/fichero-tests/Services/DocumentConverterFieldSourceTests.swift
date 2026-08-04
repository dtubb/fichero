import Foundation
import XCTest

/// #4515 / #4516 / #4514 — the class guard behind three bugs with one cause.
///
/// `DocumentService.convertToDocument` is the single wire→model converter.
/// It read `child_count`, `date_original`, `date_jdn` and `date_meta` out of
/// `additionalProperties`, where the generated decoder GUARANTEES they never
/// are: every key declared on the OpenAPI schema is consumed into its typed
/// property before extras is filled. So the reads returned nil forever —
/// `childCount` was always 0 (the sidebar guessed at disclosure triangles),
/// and `prototype_key` / `node_kind` / `alias_target_id` / `attributes` were
/// not read at all (the workflow icon, the alias badge and every read-only
/// predicate were dead code).
///
/// Hand-built test fixtures kept every consumer green, because they set the
/// LOCAL model directly and never crossed the converter. This test crosses it
/// statically instead: intersect the schema's typed key set with the keys the
/// converter reads out of extras, and require the intersection to be empty.
///
/// It is deliberately a SOURCE check rather than a behavioural one: the defect
/// is "a read names a key it must not", which is a property of the text. The
/// behavioural halves live with the surfaces (`DocumentReadOnlyPresentationTests`).
final class DocumentConverterFieldSourceTests: XCTestCase {

    /// Every key declared on `components.schemas.Document` — the set the
    /// generated decoder claims, and therefore the set extras can never hold.
    private func typedDocumentKeys() throws -> Set<String> {
        let url = try AppSource.sibling("fichero-api-client")
            .appendingPathComponent("Sources/FicheroAPIClient/openapi.json")
        let data = try Data(contentsOf: url)
        guard
            let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let components = root["components"] as? [String: Any],
            let schemas = components["schemas"] as? [String: Any],
            let document = schemas["Document"] as? [String: Any],
            let properties = document["properties"] as? [String: Any]
        else {
            XCTFail("BLIND: could not parse components.schemas.Document from openapi.json")
            return []
        }
        return Set(properties.keys)
    }

    /// Every string literal the given source reads out of `extras[...]`.
    /// Kept as a static function so the self-test below can run the SAME
    /// matcher over a synthesised violation.
    static func extrasKeys(in source: String) -> Set<String> {
        let pattern = #"extras\[\s*"([^"]+)"\s*\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        var keys: Set<String> = []
        for match in regex.matches(in: source, range: range) {
            if let keyRange = Range(match.range(at: 1), in: source) {
                keys.insert(String(source[keyRange]))
            }
        }
        return keys
    }

    /// BOTH wire→model converters. The diagnosis behind #4515 named only
    /// `DocumentService`'s; `ImportService+Conversions` carried the identical
    /// defect (`sort_order` from extras, so always 0). One of two identical
    /// converters being right is how the class comes back.
    private static let converterFiles = [
        "Services/DocumentService.swift",
        "Services/ImportService+Conversions.swift"
    ]

    private func converterSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        // Floor: if the function moved, this test is judging the wrong text.
        // Say BLIND rather than pass on a file that no longer holds it.
        XCTAssertTrue(
            source.contains("func convertToDocument("),
            "BLIND: convertToDocument is no longer in \(relativePath)"
        )
        return source
    }

    // MARK: - The guard

    func testConverterNeverReadsATypedKeyFromAdditionalProperties() throws {
        let typed = try typedDocumentKeys()
        // Floor: the schema really has a large declared surface. A parse that
        // silently returned two keys would make the intersection empty for the
        // wrong reason — clean tree and blind parser look identical otherwise.
        XCTAssertGreaterThan(
            typed.count, 30,
            "BLIND: only \(typed.count) typed Document keys parsed; expected the full schema"
        )
        XCTAssertTrue(typed.contains("child_count"))
        XCTAssertTrue(typed.contains("attributes"))
        XCTAssertTrue(typed.contains("prototype_key"))

        for file in Self.converterFiles {
            let read = Self.extrasKeys(in: try converterSource(file))
            let overlap = read.intersection(typed).sorted()
            XCTAssertTrue(
                overlap.isEmpty,
                """
                \(file): \(overlap.joined(separator: ", ")) are TYPED on the Document \
                schema, so the generated decoder never leaves them in \
                additionalProperties. Reading them from extras returns nil forever \
                (#4515). Read the typed property instead.
                """
            )
        }
    }

    /// The matcher must be observed to FIRE, or a green result proves nothing.
    /// Synthesised, not borrowed from the real source — a fixture that depends
    /// on the debt still existing stops testing anything the moment it is paid.
    func testMatcherCatchesASynthesisedViolation() throws {
        let typed = try typedDocumentKeys()
        let violation = #"let childCount = (extras["child_count"] as? Int) ?? 0"#
        let caught = Self.extrasKeys(in: violation).intersection(typed)
        XCTAssertEqual(
            caught, ["child_count"],
            "the matcher itself is broken: it did not flag the exact pre-fix line"
        )
    }

    func testMatcherIgnoresAGenuinelyUntypedKey() {
        let benign = #"let custom = extras["not_on_the_schema"] as? String"#
        XCTAssertEqual(Self.extrasKeys(in: benign), ["not_on_the_schema"])
    }

    // MARK: - The fields the drop actually cost us

    /// Each of these has a typed read now; a regression would delete the line,
    /// and the line's ABSENCE is what this asserts.
    func testConverterPopulatesTheFieldsThatWereSilentlyDropped() throws {
        // Property names, not receiver-qualified reads: the two converters name
        // their argument differently (`doc` / `generated`).
        for file in Self.converterFiles {
            let source = try converterSource(file)
            for read in [
                ".childCount",
                ".prototypeKey",
                ".nodeKind",
                ".aliasTargetId",
                ".sortOrder",
                ".isWorkspace",
                "convertAttributes("
            ] {
                XCTAssertTrue(
                    source.contains(read),
                    "\(file): convertToDocument no longer reads \(read) — the #4514/#4515/#4516 drop is back"
                )
            }
        }
    }
}
