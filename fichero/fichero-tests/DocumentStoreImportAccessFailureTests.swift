@testable import Fichero
import Foundation
import Testing

/// #3919: the import path collapsed 401 and 403 into `DocumentStoreError
/// .unauthorized`, dropping the engine's body. A scoped library 403 carries the
/// only sentence that tells the user what actually went wrong ("Library path is
/// not in an allowed location…"), so the collapse turned an actionable
/// access/location failure into a generic "You don't have access to this."
///
/// These lock the split at the mapping, which is pure — the import call site
/// itself needs a live engine, so the classification is what's worth testing.
struct DocumentStoreImportAccessFailureTests {
    /// The engine's real denial body, verbatim from `validate_library_path_header`
    /// (fichero-engine `api/main.py`) — a bare string `detail`, no structured
    /// `reason`/`code`.
    private static let scopedLibraryDenial = Data(
        #"{"detail":"Library path is not in an allowed location or not a .fichero package."}"#.utf8
    )
    private static let scopedLibraryMessage =
        "Library path is not in an allowed location or not a .fichero package."

    @Test("a scoped library 403 keeps the engine's reason and asks for access, never sign-in")
    func scopedLibrary403SurvivesAsForbiddenWithTheEnginesReason() throws {
        let thrown = DocumentStore.importAccessFailure(statusCode: 403, body: Self.scopedLibraryDenial)

        // Lift it the way the UI does — proving the typed error survives the trip
        // rather than falling into the collapsed `.forbidden(nil, nil)` bucket.
        let access = try #require(AccessError.from(thrown))
        #expect(access == .forbidden(reason: nil, message: Self.scopedLibraryMessage))
        #expect(access.errorDescription == Self.scopedLibraryMessage)

        // The #3919 invariant: an access/location failure asks for access. It must
        // never route to the sign-in remedy that renders "Reset Sign-In & Retry" —
        // on an embedded loopback engine there is no sign-in to reset.
        #expect(access.recovery == .requestAccess)
        #expect(access.recovery != .signIn)
    }

    @Test("a 403 with a structured denial body keeps both reason and message")
    func structuredDenialBodyKeepsReasonAndMessage() throws {
        let body = Data(#"{"detail": {"reason": "not_a_member", "message": "Ask the owner for access."}}"#.utf8)
        let access = try #require(AccessError.from(DocumentStore.importAccessFailure(statusCode: 403, body: body)))
        #expect(access == .forbidden(reason: "not_a_member", message: "Ask the owner for access."))
        #expect(access.recovery == .requestAccess)
    }

    /// Edge: a bodyless 403 (or one the engine sends with no usable JSON) must
    /// still classify as an access failure rather than degrading to sign-in.
    @Test("a 403 with no body is still forbidden, not unauthenticated")
    func bodylessForbiddenStillAsksForAccess() throws {
        let access = try #require(AccessError.from(DocumentStore.importAccessFailure(statusCode: 403, body: nil)))
        #expect(access == .forbidden(reason: nil, message: nil))
        #expect(access.recovery == .requestAccess)
    }

    /// A 403 whose body carries the engine's stale-bootstrap-token marker routes
    /// to the restart remedy — the single classifier owns that call, so the
    /// import path can't drift from it.
    @Test("a 403 carrying the stale-token marker still routes to restart")
    func staleBootstrapTokenMarkerIsHonoured() throws {
        let body = Data(#"{"detail":"local bootstrap token is stale","code":"stale_bootstrap_token"}"#.utf8)
        let access = try #require(AccessError.from(DocumentStore.importAccessFailure(statusCode: 403, body: body)))
        #expect(access == .staleBootstrapToken)
        #expect(access.recovery == .restartEngine)
    }

    @Test("a 401 is unchanged — it stays the DocumentStore unauthorized bucket")
    func unauthenticated401KeepsTodaysBehaviour() throws {
        let thrown = DocumentStore.importAccessFailure(statusCode: 401, body: nil)
        let storeError = try #require(thrown as? DocumentStoreError)
        guard case .unauthorized = storeError else {
            Issue.record("A 401 must stay DocumentStoreError.unauthorized — got \(storeError)")
            return
        }
    }

    /// A 401 body is NOT re-classified: the 401 path is untouched by #3919, so a
    /// 401 carrying a marker still lands in the unauthorized bucket exactly as
    /// it did before. Guards against the split quietly widening.
    @Test("a 401 with a body is still not re-classified")
    func unauthenticated401IgnoresTheBody() throws {
        let body = Data(#"{"detail":"device token expired"}"#.utf8)
        let storeError = try #require(DocumentStore.importAccessFailure(statusCode: 401, body: body) as? DocumentStoreError)
        guard case .unauthorized = storeError else {
            Issue.record("A 401 must stay DocumentStoreError.unauthorized — got \(storeError)")
            return
        }
    }
}
