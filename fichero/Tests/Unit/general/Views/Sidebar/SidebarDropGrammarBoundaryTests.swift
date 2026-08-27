import Foundation
import SwiftUI
import UniformTypeIdentifiers
import XCTest

@testable import Fichero

/// Adversarial coverage of the drop GRAMMAR — the pure functions every drop
/// surface routes through. The existing suites (`SidebarDropPayloadTests`,
/// `LibraryItemDropProposalTests`, `LibraryHeaderDropRoutingTests`) cover the
/// happy shapes of each; this one walks the boundaries: the full modifier ×
/// kind matrix, every `LibraryItemDrag.Kind`, malformed and hostile JSON, and
/// the counting rules in the failure message.
///
/// Nothing here reads source text. Every assertion constructs the real inputs
/// and checks the real answer (#4492's lesson).
@MainActor
final class SidebarDropGrammarBoundaryTests: XCTestCase {

    private static func mods(_ option: Bool, _ command: Bool) -> SidebarDropModifiers {
        SidebarDropModifiers(option: option, command: command)
    }

    private static let everyKind: [SidebarItemKind] = [
        .document, .savedSearch, .conversation, .workflow,
        .chain, .schedule, .trigger, .folder, .unknown
    ]

    // MARK: - The full modifier × kind matrix

    /// The grammar is four modifier states across nine kinds. Only `.document`
    /// has copy/alias endpoints; everything else moves whatever is held. Stated
    /// exhaustively so a new kind cannot quietly acquire a copy endpoint.
    func testEveryModifierCombinationForEveryKind() {
        for kind in Self.everyKind {
            for option in [false, true] {
                for command in [false, true] {
                    let resolved = sidebarDropOperation(
                        modifiers: Self.mods(option, command), kind: kind
                    )
                    let expected: SidebarDropOperation
                    if kind == .document && option {
                        expected = command ? .alias : .copy
                    } else {
                        expected = .move
                    }
                    XCTAssertEqual(
                        resolved, expected,
                        "kind: \(kind), option: \(option), command: \(command)"
                    )
                }
            }
        }
    }

    /// ⌘ ALONE is not part of the grammar — it is the Finder shortcut for
    /// nothing here, and must not be mistaken for the alias gesture (which is
    /// ⌘⌥). Without this, dropping a document while reaching for ⌘-anything
    /// could silently make a reference instead of moving.
    func testCommandWithoutOptionIsStillAMove() {
        XCTAssertEqual(
            sidebarDropOperation(modifiers: Self.mods(false, true), kind: .document),
            .move
        )
    }

    /// Both spellings of the grammar entry point must agree — the overload is
    /// the one every surface actually calls.
    func testTheSampledOverloadAgreesWithTheExplicitOne() {
        for option in [false, true] {
            for command in [false, true] {
                XCTAssertEqual(
                    sidebarDropOperation(modifiers: Self.mods(option, command), kind: .document),
                    sidebarDropOperation(optionHeld: option, commandHeld: command, kind: .document)
                )
            }
        }
    }

    // MARK: - The badge must never contradict the outcome

    /// The #4401 invariant, over the WHOLE matrix rather than the three cases
    /// the proposal suite spot-checks: whatever badge the cursor shows for an
    /// in-app drag, the operation the drop performs has to be the same verb.
    func testTheBadgeAgreesWithTheOutcomeAcrossTheWholeMatrix() {
        for option in [false, true] {
            for command in [false, true] {
                let modifiers = Self.mods(option, command)
                let performed = sidebarDropOperation(modifiers: modifiers, kind: .document)
                let proposed = libraryItemDropProposedOperation(
                    isInAppDrag: true, modifiers: modifiers
                )
                switch performed {
                case .move:
                    XCTAssertEqual(proposed, .move)
                case .copy:
                    XCTAssertEqual(proposed, .copy)
                case .alias:
                    #if os(macOS)
                    XCTAssertEqual(proposed, .alias)
                    #else
                    XCTAssertEqual(proposed, .copy)
                    #endif
                }
            }
        }
    }

    /// An EXTERNAL drag is a copy no matter which keys are held — the bytes are
    /// ingested and the original stays put, so `+` is the truthful badge and a
    /// held ⌥ must not turn it into a move badge over an import.
    func testAnExternalDragIsAlwaysBadgedCopyWhateverIsHeld() {
        for option in [false, true] {
            for command in [false, true] {
                XCTAssertEqual(
                    libraryItemDropProposedOperation(
                        isInAppDrag: false, modifiers: Self.mods(option, command)
                    ),
                    .copy,
                    "option: \(option), command: \(command)"
                )
            }
        }
    }

    // MARK: - The internal id predicate, at its edges

    /// `doc:` with nothing after it carries no document, in every spelling a
    /// pasteboard can hand over.
    func testABarePrefixIsNeverAnInternalID() {
        for candidate in ["doc:", " doc: ", "\ndoc:\n", "\t doc:\t"] {
            XCTAssertFalse(
                isInternalSidebarItemID(candidate),
                "\(candidate.debugDescription) carries no document id"
            )
        }
    }

    /// The prefix is case-SENSITIVE and anchored. A transcript that happens to
    /// contain the substring must not be mistaken for an id, or dropping a
    /// chat excerpt onto a folder would try to reparent a document that does
    /// not exist.
    func testThePrefixIsAnchoredAndCaseSensitive() {
        XCTAssertFalse(isInternalSidebarItemID("DOC:abc"))
        XCTAssertFalse(isInternalSidebarItemID("Doc:abc"))
        XCTAssertFalse(isInternalSidebarItemID("xdoc:abc"))
        XCTAssertFalse(isInternalSidebarItemID("see doc:abc for details"))
        XCTAssertTrue(isInternalSidebarItemID("doc:abc"))
    }

    /// Interior whitespace is NOT trimmed away — only the ends are — so a
    /// two-line clipping whose first line is an id does not qualify. Recorded
    /// because the trimming is easy to over-read as "sanitises anything".
    func testOnlyTheEndsAreTrimmed() {
        XCTAssertTrue(isInternalSidebarItemID("  doc:abc\n"))
        XCTAssertTrue(
            isInternalSidebarItemID("doc: abc"),
            "a space after the colon still leaves characters, so this qualifies"
        )
    }

    // MARK: - The library pane's JSON payload, at its edges

    private func dragJSON(
        kind: LibraryItemDrag.Kind,
        id: String,
        documentId: String?,
        text: String = "body"
    ) throws -> String {
        let drag = LibraryItemDrag(kind: kind, id: id, documentId: documentId, text: text)
        let data = try JSONEncoder().encode(drag)
        return try XCTUnwrap(String(bytes: data, encoding: .utf8))
    }

    /// Every kind that IS a reparentable node resolves; every kind that is not
    /// refuses. Stated over the complete enum so a new kind has to choose.
    func testEveryLibraryDragKindEitherResolvesOrIsRefused() throws {
        let reparentable: [LibraryItemDrag.Kind] = [.document, .page, .group]
        let refused: [LibraryItemDrag.Kind] = [.artifact, .note, .annotation]

        for kind in reparentable {
            let json = try dragJSON(kind: kind, id: "row-1", documentId: "doc-1")
            XCTAssertEqual(
                internalSidebarItemID(fromLibraryDragJSON: json), "doc:doc-1",
                "\(kind) is a document node and must be movable"
            )
        }
        for kind in refused {
            let json = try dragJSON(kind: kind, id: "row-1", documentId: "doc-1")
            XCTAssertNil(
                internalSidebarItemID(fromLibraryDragJSON: json),
                "\(kind) has no place in the document tree"
            )
        }
    }

    /// `documentId` wins over `id` when both are present — a page row's row-id
    /// is not a document id, and reparenting by it would target nothing.
    func testDocumentIDIsPreferredOverTheRowID() throws {
        let json = try dragJSON(kind: .page, id: "page-row-9", documentId: "pdf-4")
        XCTAssertEqual(internalSidebarItemID(fromLibraryDragJSON: json), "doc:pdf-4")
    }

    /// With no `documentId` the row id is the document id — the shape a plain
    /// folder row vends.
    func testTheRowIDIsUsedWhenNoDocumentIDIsCarried() throws {
        let json = try dragJSON(kind: .document, id: "folder-2", documentId: nil)
        XCTAssertEqual(internalSidebarItemID(fromLibraryDragJSON: json), "doc:folder-2")
    }

    /// An EMPTY identifier is refused rather than turned into the meaningless
    /// `"doc:"`, which would then pass `isInternalSidebarItemID`'s prefix test
    /// downstream and address no document at all.
    func testAnEmptyIdentifierIsRefusedNotTurnedIntoABarePrefix() throws {
        let json = try dragJSON(kind: .document, id: "", documentId: "")
        XCTAssertNil(internalSidebarItemID(fromLibraryDragJSON: json))

        let onlyEmptyRowID = try dragJSON(kind: .document, id: "", documentId: nil)
        XCTAssertNil(internalSidebarItemID(fromLibraryDragJSON: onlyEmptyRowID))
    }

    /// Malformed, truncated and simply-not-ours JSON must all decline quietly.
    /// A crash here would be a crash during a drag, with the pointer captured.
    func testHostileStringsDeclineWithoutCrashing() {
        let hostile = [
            "",
            "{",
            "{}",
            "not json at all",
            "[{\"kind\":\"document\",\"id\":\"a\",\"text\":\"t\"}]",
            "{\"kind\":\"spaceship\",\"id\":\"a\",\"text\":\"t\"}",
            "{\"kind\":\"document\"}",
            "{\"kind\":null,\"id\":null,\"text\":null}",
            String(repeating: "{", count: 5_000)
        ]
        for candidate in hostile {
            XCTAssertNil(
                internalSidebarItemID(fromLibraryDragJSON: candidate),
                "\(candidate.prefix(40).debugDescription) must not resolve to a document"
            )
        }
    }

    /// A pasteboard hands strings back with whatever whitespace the source put
    /// on them; the leading-brace test runs on the TRIMMED string, so a padded
    /// payload still resolves.
    func testAPaddedJSONPayloadStillResolves() throws {
        let json = try dragJSON(kind: .document, id: "d1", documentId: "d1")
        XCTAssertEqual(
            internalSidebarItemID(fromLibraryDragJSON: "\n  \(json)  \n"), "doc:d1"
        )
    }

    // MARK: - Mixed multi-item payloads

    /// A multi-select drag can span both panes at once (a sidebar row and a
    /// library tile). Both shapes must resolve, together, in order — the
    /// destination is not allowed to know which pane a row came from.
    func testAMixedSidebarAndLibraryMultiSelectionResolvesInOrder() throws {
        let libraryRow = try dragJSON(kind: .document, id: "b", documentId: "b")
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:a", libraryRow, "doc:c"],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .internalItems(["doc:a", "doc:b", "doc:c"]))
    }

    /// A mixed drag where SOME rows are unreparentable (an annotation dragged
    /// alongside a document) keeps the documents and drops the rest, rather
    /// than refusing the whole gesture.
    func testUnreparentableRowsAreDroppedNotTheWholeDrag() throws {
        let annotation = try dragJSON(kind: .annotation, id: "ann-1", documentId: "doc-1")
        let payload = classifySidebarDropPayload(
            loadedIDs: ["doc:keep", annotation],
            hasExternalPayload: false,
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .internalItems(["doc:keep"]))
    }

    /// A drag of ONLY unreparentable rows carries the in-process flavour but no
    /// usable id, so it lands on `.unreadableInternal` — reported, never
    /// imported. Re-ingesting an annotation as a document is the data-loss
    /// shape #4401 is about.
    func testADragOfOnlyUnreparentableRowsIsRefusedNotImported() throws {
        let annotation = try dragJSON(kind: .annotation, id: "ann-1", documentId: "doc-1")
        let payload = classifySidebarDropPayload(
            loadedIDs: [annotation],
            hasExternalPayload: true,
            carriesOwnProcessFlavor: true
        )
        XCTAssertEqual(payload, .unreadableInternal)
        XCTAssertNotEqual(payload, .externalFiles)
    }

    // MARK: - The capability pre-check

    /// The pre-check decides only whether a string read is worth attempting. It
    /// must answer NO for an empty provider set, or an empty drop would take
    /// the internal route and report "couldn't read what was dragged".
    func testTheCapabilityPrecheckIsFalseForNoProviders() {
        XCTAssertFalse(sidebarDropMightCarryInternalID([]))
    }

    /// One NAMED-flavor provider anywhere in the set is enough — a multi-item
    /// drag mixes provider shapes. Rewritten for #4569 (67dccf9bf): a plain-
    /// text registration no longer reads as possibly-internal — a Finder drag
    /// of a .txt registers utf8-plain-text as CONTENT beside its file-url,
    /// and counting it produced "Couldn't read what was dragged" on ordinary
    /// text files. Ours is identified by NAME (ficheroDragItem) or by the
    /// degraded bare-data envelope; prose is just prose.
    func testOneNamedFlavorProviderAnywhereIsEnough() {
        let fileOnly = SidebarDropProviderCapabilities(
            canLoadURL: true, canLoadString: false,
            registeredTypeIdentifiers: [UTType.fileURL.identifier]
        )
        let stringy = SidebarDropProviderCapabilities(
            canLoadURL: false, canLoadString: true,
            registeredTypeIdentifiers: [UTType.utf8PlainText.identifier]
        )
        let named = SidebarDropProviderCapabilities(
            canLoadURL: false, canLoadString: false,
            registeredTypeIdentifiers: [UTType.ficheroDragItem.identifier]
        )
        XCTAssertFalse(sidebarDropMightCarryInternalID([fileOnly, fileOnly]))
        XCTAssertFalse(
            sidebarDropMightCarryInternalID([fileOnly, stringy]),
            "a text registration is content, not our flavor (#4569)"
        )
        XCTAssertTrue(sidebarDropMightCarryInternalID([fileOnly, named]))
        XCTAssertTrue(sidebarDropMightCarryInternalID([named, fileOnly]))
    }

    /// The capability-shaped route still answers its own (narrower) question.
    /// Its three plain-text identifiers are load-bearing: dropping any one of
    /// them makes every internal drag classify as external files (#4124).
    func testTheCapabilityRouteToleratesAllThreePlainTextIdentifiers() {
        for identifier in [
            UTType.text.identifier, UTType.plainText.identifier, UTType.utf8PlainText.identifier
        ] {
            let provider = SidebarDropProviderCapabilities(
                canLoadURL: false, canLoadString: true, registeredTypeIdentifiers: [identifier]
            )
            XCTAssertEqual(
                classifySidebarDropProviders([provider]), .internalTextOnly,
                "\(identifier) is one of the three internal text flavours"
            )
        }
    }

    func testTheCapabilityRouteCallsAnEmptySetUnsupported() {
        XCTAssertEqual(classifySidebarDropProviders([]), .unsupported)
    }

    /// A provider that can load neither a URL nor a string, and registers only
    /// plain-text identifiers, is a shape with nothing readable in it.
    func testAProviderWithNothingReadableIsUnsupported() {
        let empty = SidebarDropProviderCapabilities(
            canLoadURL: false, canLoadString: false,
            registeredTypeIdentifiers: [UTType.plainText.identifier]
        )
        XCTAssertEqual(classifySidebarDropProviders([empty]), .unsupported)
    }

}
