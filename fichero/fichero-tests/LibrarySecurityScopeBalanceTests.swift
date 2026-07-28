@testable import Fichero
import Foundation
import Testing

// `isAccessingSecurityScope` was `nonisolated(unsafe)` — which the compiler
// reports as having NO EFFECT — while two `nonisolated` methods read-modify-wrote
// it and `deinit` called one of them (#4216). An unbalanced start/stop doesn't
// crash: it silently loses file access, or holds a scope forever.
//
// It had NO test at all. The compiler warned about the isolation; nothing warned
// about the imbalance, which is the part that bites.
//
// WHAT THESE PROVE: the balance logic — that repeated starts don't stack, that a
// stop without a start is a no-op, and that the flag tracks state honestly.
// WHAT THEY DO NOT PROVE: sandbox behaviour. In an unsandboxed test build
// `startAccessingSecurityScopedResource()` returns false for an ordinary path,
// so the flag stays false and the guards are exercised on the not-held side.
// Demonstrating a real acquire needs a sandboxed build with a security-scoped
// URL, which this suite cannot produce.
@MainActor
@Suite("LibraryReference security-scope start/stop stay balanced (#4216)")
struct LibrarySecurityScopeBalanceTests {

    private func library() -> LibraryManager.LibraryReference {
        LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("scope-test.fichero"),
            document: FicheroDocument(),
            displayName: "Scope Test",
            startAccessing: false
        )
    }

    @Test("a fresh library holds no scope")
    func startsUnheld() {
        #expect(library().isAccessingSecurityScope == false)
    }

    // The guard is what stops a double-start: macOS reference-counts scoped
    // access, so a second acquire would need a second release that never comes.
    @Test("starting twice does not stack")
    func doubleStartIsIdempotent() {
        let reference = library()
        reference.startAccessingSecurityScope()
        let afterFirst = reference.isAccessingSecurityScope
        reference.startAccessingSecurityScope()
        #expect(reference.isAccessingSecurityScope == afterFirst, "a second start must not change state")
    }

    // The inverse: a stop with nothing held must not release someone else's
    // scope for the same URL, and must not flip the flag.
    @Test("stopping without starting is a no-op")
    func stopWithoutStartIsSafe() {
        let reference = library()
        reference.stopAccessingSecurityScope()
        #expect(reference.isAccessingSecurityScope == false)
    }

    @Test("repeated stops stay a no-op")
    func doubleStopIsSafe() {
        let reference = library()
        reference.startAccessingSecurityScope()
        reference.stopAccessingSecurityScope()
        reference.stopAccessingSecurityScope()
        #expect(reference.isAccessingSecurityScope == false)
    }

    // deinit calls stopAccessingSecurityScope from whatever thread drops the
    // last reference. This doesn't prove thread safety — it proves the teardown
    // path runs without trapping, which a MainActor-isolated method could not.
    @Test("a library can be released without trapping in deinit")
    func deinitRunsCleanly() {
        for _ in 0..<50 {
            let reference = library()
            reference.startAccessingSecurityScope()
        }
        #expect(Bool(true), "50 create/release cycles completed")
    }
}
