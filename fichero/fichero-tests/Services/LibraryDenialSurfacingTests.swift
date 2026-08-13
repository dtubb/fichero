//
//  LibraryDenialSurfacingTests.swift
//  FicheroTests
//
//  C3 — a 403'd library must be RECOVERABLE and EXPLAINED, not merely unloaded.
//
//  Daniel's library at ~/Mineria to 1980.fichero sits outside the engine's
//  library-path allowlist (`_is_allowed_library_path`, api/main.py), so every
//  library-scoped request 403s with
//
//      "Library path is not in an allowed location or not a .fichero package."
//
//  The engine wrote that sentence for the user. The app threw it away in three
//  separate places, and what reached the screen was an unloaded library and six
//  log lines that named no cause. Each test below fails against that code.
//

@testable import Fichero
import Foundation
import XCTest

// @MainActor: DocumentStore.isRetriableLoadFailure and
// LibraryManager.loadFailureReason are statics on MainActor types (statics
// inherit the type's isolation), so the test class must share it to call
// them synchronously.
@MainActor
final class LibraryDenialSurfacingTests: XCTestCase {

    private static let engineSentence =
        "Library path is not in an allowed location or not a .fichero package."

    // MARK: - The engine's sentence survives classification

    /// `AccessError.classify(_:)` re-derived a cause for an error that was
    /// ALREADY an `AccessError`, collapsing a resolved `.forbidden` into
    /// `.transport`. Re-deriving a cause we were handed is inventing one.
    func testAnAlreadyClassifiedErrorIsNotReclassified() {
        let denial = AccessError.forbidden(reason: "library_path_not_allowed", message: Self.engineSentence)
        XCTAssertEqual(AccessError.classify(denial), denial)

        for other: AccessError in [.unauthenticated, .staleBootstrapToken, .deviceAccessExpired,
                                   .tlsPinFailure, .engineUnreachable, .transport("boom")] {
            XCTAssertEqual(AccessError.classify(other), other, "\(other) must survive classification unchanged")
        }
    }

    /// The consequence of the bug above: a permission denial the engine will
    /// refuse identically forever landed in the RETRIABLE bucket and was retried
    /// three times before surfacing under the wrong case.
    func testAPermissionDenialIsNotRetried() {
        let denial = AccessError.forbidden(reason: nil, message: Self.engineSentence)
        XCTAssertFalse(
            DocumentStore.isRetriableLoadFailure(denial),
            "a 403 is definitive — retrying it three times only delays the explanation"
        )
        XCTAssertTrue(DocumentStore.isRetriableLoadFailure(AccessError.engineUnreachable))
    }

    /// A 403 body must classify to the engine's own words, not to a label of
    /// ours. This is the sentence the user has to read to know what to do.
    func testA403ClassifiesToTheEnginesOwnSentence() throws {
        let body = try XCTUnwrap(#"{"detail":"\#(Self.engineSentence)"}"#.data(using: .utf8))
        let classified = AccessError.classify(statusCode: 403, body: body)
        XCTAssertEqual(classified?.errorDescription, Self.engineSentence)
    }

    /// A denial that carried no usable body still must not be dressed up as one
    /// that did — the caller falls back to its own typed error with the real
    /// status code, never a generic "unexpected response".
    func testA403WithNoUsableBodyStillClassifiesAsForbidden() {
        XCTAssertEqual(AccessError.classify(statusCode: 403, body: nil), .forbidden(reason: nil, message: nil))
        XCTAssertNil(AccessError.classify(statusCode: 500, body: nil), "a 500 is not an access denial")
    }

    // MARK: - The load that the whole library hangs off

    /// `getRoots` is what `DocumentStore.loadCollections` calls, and it threw
    /// `DocumentServiceError.unexpectedResponse` for EVERY non-200 — discarding
    /// both the status code and the engine's sentence. `LibraryView` renders
    /// `LibraryAccessDeniedView` only when the store's error is an
    /// `AccessError`, so with the reason discarded the denial pane could never
    /// appear and the library rendered as merely empty.
    func testGetRootsCarriesADenialOutTyped() throws {
        let roots = try Self.appSource("Services/DocumentService+Roots.swift")
        XCTAssertTrue(roots.contains("func getRoots("), "getRoots not here — this guard measures nothing")
        XCTAssertTrue(
            roots.contains("AccessError.denial(statusCode: statusCode, payload: payload)"),
            "getRoots must read the engine's denial off the body and throw it typed"
        )
        XCTAssertTrue(
            roots.contains(#"DocumentServiceError.httpStatus(operation: "list roots""#),
            "a non-denial failure must still name the operation and the real status code"
        )
        XCTAssertFalse(
            roots.contains("DocumentServiceError.unexpectedResponse"),
            "no branch of getRoots may discard the status code"
        )
    }

    /// The rendering end of C3: the denial pane must be handed the library's
    /// path. "Not in an allowed location" tells the user their place is wrong
    /// without telling them which place, which is not an explanation.
    func testTheDenialPaneIsGivenTheLibraryPath() throws {
        let view = try Self.appSource("Views/Components/LibraryAccessDeniedView.swift")
        XCTAssertTrue(view.contains("var libraryPath: String?"), "the pane must accept the path")
        XCTAssertTrue(view.contains("if let libraryPath {"), "the pane must render it")

        let library = // LibraryView.swift was split 2026-08-13; scan all four parts.
            ((try Self.appSource("Views/Library/LibraryView.swift")) + (try Self.appSource("Views/Library/LibraryView+Body.swift")) + (try Self.appSource("Views/Library/LibraryView+ContentBranches.swift")) + (try Self.appSource("Views/Library/LibraryView+Insets.swift")))
        XCTAssertTrue(
            library.contains("libraryPath: libraryReference?.url.path"),
            "LibraryView must pass the failing library's path into the denial pane"
        )
    }

    // MARK: - The log line that named no cause

    /// "Library load failed — leaving unloaded for retry" was all six of Daniel's
    /// log lines said. `libraryLoadSucceeded` is a boolean that is false for two
    /// different reasons, and a boolean false for two reasons is a bug: the log
    /// must say WHICH, and when there is an error it must repeat the engine's
    /// sentence rather than a label of ours.
    func testTheLoadFailureReasonSaysWhich() {
        let denial = AccessError.forbidden(reason: nil, message: Self.engineSentence)
        XCTAssertEqual(
            LibraryManager.loadFailureReason(error: denial, isConnected: false),
            Self.engineSentence
        )
        XCTAssertTrue(
            LibraryManager.loadFailureReason(error: nil, isConnected: false).contains("never connected"),
            "a store that failed WITHOUT recording an error is a different fact and must read differently"
        )
        XCTAssertNotEqual(
            LibraryManager.loadFailureReason(error: denial, isConnected: false),
            LibraryManager.loadFailureReason(error: nil, isConnected: false),
            "the two ways the guard can fire must never produce the same sentence"
        )
    }

    /// The log line itself must carry the reason and the path, not just the
    /// display name — a name does not locate a library that was refused for
    /// WHERE it is.
    func testTheLoadFailureLogCarriesReasonAndPath() throws {
        let source = try Self.appSource("Models/LibraryManager+Helpers.swift")
        XCTAssertTrue(source.contains("Self.loadFailureReason(error: store.error"),
                      "the failure log must state the cause")
        XCTAssertTrue(source.contains("library.url.path"), "the failure log must state where the library is")
    }

    private static func appSource(_ relativePath: String) throws -> String {
        let source = try AppSource.text(relativePath)
        XCTAssertFalse(source.isEmpty, "\(relativePath) is empty — this guard measures nothing")
        return source
    }
}
