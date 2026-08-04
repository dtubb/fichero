import Foundation
import XCTest

@testable import Fichero

/// Adversarial coverage of library IDENTITY — the question "are these two URLs
/// the same library?", which #4517 answered with `canonicalLibraryKey` after a
/// raw `URL ==` opened a second Global.
///
/// The interesting part is that the answer is now given in TWO places with two
/// different rules: `canonicalLibraryKey` (standardize → resolve symlinks →
/// NFC) and `registryReconciliation` (NFC only). Everything below is pure, so
/// it runs without the singleton, the filesystem or the network.
@MainActor
final class LibraryCanonicalIdentityTests: XCTestCase {

    private func key(_ path: String) -> String {
        LibraryManager.canonicalLibraryKey(URL(fileURLWithPath: path))
    }

    // MARK: - The canonical key

    /// The #4517 defect itself: the same package reached as a file URL and as a
    /// directory URL. `appendingPathComponent` (Global, built during App init
    /// before the package exists) yields one; `URL(fileURLWithPath:)` after the
    /// engine created the package yields the other.
    func testDirectoryAndFileSpellingsOfOnePackageAgree() {
        let base = FileManager.default.temporaryDirectory
        let asFile = base.appendingPathComponent("Global.fichero")
        let asDirectory = URL(fileURLWithPath: asFile.path, isDirectory: true)
        XCTAssertEqual(
            LibraryManager.canonicalLibraryKey(asFile),
            LibraryManager.canonicalLibraryKey(asDirectory)
        )
    }

    /// A trailing slash is not an identity.
    func testATrailingSlashIsTheSameLibrary() {
        XCTAssertEqual(key("/tmp/Marshall.fichero"), key("/tmp/Marshall.fichero/"))
    }

    /// `.` and `..` components resolve — a path assembled by appending
    /// components must land on the same key as the direct one.
    func testRelativeComponentsResolveToTheSameKey() {
        XCTAssertEqual(key("/tmp/./Marshall.fichero"), key("/tmp/Marshall.fichero"))
        XCTAssertEqual(key("/tmp/other/../Marshall.fichero"), key("/tmp/Marshall.fichero"))
    }

    /// Repeated separators collapse.
    func testRepeatedSeparatorsCollapse() {
        XCTAssertEqual(key("/tmp//Marshall.fichero"), key("/tmp/Marshall.fichero"))
    }

    /// NFC/NFD: a filename typed on macOS arrives decomposed from the
    /// filesystem and composed from the backend. The same library either way
    /// (#3076). "Diarios de Fabián" with a combining acute is the real shape.
    func testDecomposedAndComposedNamesAreTheSameLibrary() {
        let composed = "/tmp/Fabi\u{00E1}n.fichero"       // á as one scalar
        let decomposed = "/tmp/Fabia\u{0301}n.fichero"    // a + combining acute
        XCTAssertNotEqual(
            composed.unicodeScalars.count, decomposed.unicodeScalars.count,
            "the two inputs really are different scalar sequences"
        )
        XCTAssertEqual(key(composed), key(decomposed))
    }

    /// The key is STABLE — computing it twice on the same URL gives the same
    /// answer. Trivial, and the reason a dictionary keyed on it works at all.
    func testTheKeyIsStable() {
        let url = URL(fileURLWithPath: "/tmp/Marshall.fichero")
        XCTAssertEqual(
            LibraryManager.canonicalLibraryKey(url),
            LibraryManager.canonicalLibraryKey(url)
        )
    }

    /// Different libraries keep different keys — the dedup must not be so
    /// eager that two real libraries collapse into one.
    func testDistinctLibrariesKeepDistinctKeys() {
        XCTAssertNotEqual(key("/tmp/A.fichero"), key("/tmp/B.fichero"))
        XCTAssertNotEqual(key("/tmp/one/A.fichero"), key("/tmp/two/A.fichero"))
    }

    /// CHARACTERISATION: the key is case-SENSITIVE. macOS volumes are
    /// case-INSENSITIVE by default, so `/tmp/Marshall.fichero` and
    /// `/tmp/marshall.fichero` are the same package on disk but two different
    /// keys here — a "Open Recent" entry recorded with different case would
    /// open the same library twice. Pinned as behaviour rather than asserted as
    /// correct, because case-folding a path is only right on the volumes that
    /// do it, and Foundation offers no per-volume answer for a path that does
    /// not exist yet.
    func testTheKeyIsCurrentlyCaseSensitive() {
        XCTAssertNotEqual(key("/tmp/Marshall.fichero"), key("/tmp/marshall.fichero"))
    }

    // MARK: - Reconciliation against the backend registry

    private func reconcile(
        open: [(id: UUID, path: String)],
        registry: [String],
        global: UUID = LibraryManager.globalLibraryId
    ) -> (pathsToOpen: [String], idsToDrop: [UUID]) {
        LibraryManager.registryReconciliation(
            openLibraries: open, registryPaths: registry, globalLibraryId: global
        )
    }

    /// The baseline: a registry that agrees with the open set changes nothing.
    func testAnAgreeingRegistryChangesNothing() {
        let id = UUID()
        let plan = reconcile(open: [(id, "/tmp/A.fichero")], registry: ["/tmp/A.fichero"])
        XCTAssertTrue(plan.pathsToOpen.isEmpty)
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    /// Global is never dropped, whatever the registry says — it is the app's
    /// own library and does not live in the backend's open set.
    func testGlobalIsNeverDropped() {
        let global = LibraryManager.globalLibraryId
        let plan = reconcile(
            open: [(global, "/tmp/Global.fichero")], registry: ["/tmp/Other.fichero"]
        )
        XCTAssertFalse(plan.idsToDrop.contains(global))
        XCTAssertEqual(plan.pathsToOpen, ["/tmp/Other.fichero"])
    }

    /// NFC normalisation is applied on BOTH sides, so a decomposed registry
    /// path matches a composed open one and the library is left alone.
    func testDecomposedRegistryPathsMatchComposedOpenOnes() {
        let id = UUID()
        let plan = reconcile(
            open: [(id, "/tmp/Fabi\u{00E1}n.fichero")],
            registry: ["/tmp/Fabia\u{0301}n.fichero"]
        )
        XCTAssertTrue(plan.pathsToOpen.isEmpty, "same library, differently normalised")
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    /// BUG (#see report): reconciliation compares RAW paths (NFC only) while
    /// `canonicalLibraryKey` — added by #4517 for exactly this question —
    /// additionally resolves symlinks and standardizes. A temporary library
    /// lives under `/var/folders/…`, which is a symlink to `/private/var/…`;
    /// whichever side reports the resolved form, the two spellings do not
    /// match, so the reconciler simultaneously DROPS the open library and
    /// schedules the same package to be opened again — a close-and-reopen that
    /// loses the library's UUID, and with it every window bound to it.
    func testSymlinkedPathsMustNotDropAndReopenTheSameLibrary() {
        let id = UUID()
        let plan = reconcile(
            open: [(id, "/var/folders/zz/T/Untitled-1.fichero")],
            registry: ["/private/var/folders/zz/T/Untitled-1.fichero"]
        )
        XCTExpectFailure(
            "BUG: registryReconciliation compares raw paths instead of "
            + "canonicalLibraryKey, so /var vs /private/var reads as two "
            + "libraries and the open one is dropped and reopened."
        ) {
            XCTAssertTrue(plan.idsToDrop.isEmpty, "the library is already open")
            XCTAssertTrue(plan.pathsToOpen.isEmpty, "it must not be opened a second time")
        }
    }

    /// The same defect in its trailing-slash form: `canonicalLibraryKey`
    /// standardizes it away, this comparison does not.
    func testATrailingSlashInTheRegistryMustNotLookLikeANewLibrary() {
        let id = UUID()
        let plan = reconcile(
            open: [(id, "/tmp/A.fichero")], registry: ["/tmp/A.fichero/"]
        )
        XCTExpectFailure(
            "BUG: same library, one spelled with a trailing slash — the "
            + "reconciler treats it as a different one."
        ) {
            XCTAssertTrue(plan.idsToDrop.isEmpty)
            XCTAssertTrue(plan.pathsToOpen.isEmpty)
        }
    }

    /// A registry listing the SAME path twice must not schedule two opens. The
    /// duplicate is absorbed downstream by `openLibrary`'s canonical dedup, but
    /// the plan itself is where the count is decided.
    func testADuplicatedRegistryEntryIsPlannedOnce() {
        let plan = reconcile(open: [], registry: ["/tmp/A.fichero", "/tmp/A.fichero"])
        XCTExpectFailure(
            "BUG (benign, absorbed by openLibrary's dedup): a duplicated "
            + "registry row plans the same library to be opened twice."
        ) {
            XCTAssertEqual(plan.pathsToOpen, ["/tmp/A.fichero"])
        }
    }

    /// A library the backend has closed is dropped, and its id — not its path
    /// — is what the caller acts on.
    func testALibraryMissingFromTheRegistryIsDroppedByID() {
        let stale = UUID()
        let kept = UUID()
        let plan = reconcile(
            open: [(stale, "/tmp/Gone.fichero"), (kept, "/tmp/Here.fichero")],
            registry: ["/tmp/Here.fichero"]
        )
        XCTAssertEqual(plan.idsToDrop, [stale])
        XCTAssertTrue(plan.pathsToOpen.isEmpty)
    }

    /// Opening and dropping happen in the SAME plan — a registry that has
    /// swapped one library for another must do both, or the sidebar shows the
    /// union of two states.
    func testASwappedRegistryOpensAndDropsInOnePlan() {
        let gone = UUID()
        let plan = reconcile(
            open: [(gone, "/tmp/Gone.fichero")], registry: ["/tmp/New.fichero"]
        )
        XCTAssertEqual(plan.idsToDrop, [gone])
        XCTAssertEqual(plan.pathsToOpen, ["/tmp/New.fichero"])
    }

    /// Two OPEN references to the same path (the #4517 double-open, before it
    /// is deduped) are both kept when the registry lists that path — the
    /// reconciler is not the place that resolves a duplicate open.
    func testTwoOpenReferencesToOnePathAreBothKept() {
        let first = UUID()
        let second = UUID()
        let plan = reconcile(
            open: [(first, "/tmp/A.fichero"), (second, "/tmp/A.fichero")],
            registry: ["/tmp/A.fichero"]
        )
        XCTAssertTrue(plan.idsToDrop.isEmpty)
        XCTAssertTrue(plan.pathsToOpen.isEmpty)
    }

    func testAnEmptyOpenSetOpensEverythingTheRegistryLists() {
        let plan = reconcile(open: [], registry: ["/tmp/A.fichero", "/tmp/B.fichero"])
        XCTAssertEqual(plan.pathsToOpen, ["/tmp/A.fichero", "/tmp/B.fichero"])
        XCTAssertTrue(plan.idsToDrop.isEmpty)
    }

    // MARK: - When reconciliation may run at all (#3988)

    /// The guard exists because a FAILED fetch leaves `libraries` at its stale
    /// value; reconciling then can false-drop a genuinely open library. Stated
    /// over the whole truth table so neither half can be relaxed alone.
    func testTheReconcileGuardOverItsWholeTruthTable() {
        XCTAssertTrue(
            LibraryManager.shouldReconcile(fetchError: nil, registryPaths: ["/tmp/A.fichero"])
        )
        XCTAssertFalse(
            LibraryManager.shouldReconcile(fetchError: nil, registryPaths: []),
            "empty is ambiguous between a real empty registry and a cold failed fetch"
        )
        XCTAssertFalse(
            LibraryManager.shouldReconcile(fetchError: "offline", registryPaths: ["/tmp/A.fichero"]),
            "a stale snapshot must never drive a drop"
        )
        XCTAssertFalse(
            LibraryManager.shouldReconcile(fetchError: "offline", registryPaths: [])
        )
    }

    /// An empty-string error is still an error object being present, and the
    /// guard reads presence rather than content.
    func testAnEmptyErrorStringStillBlocksReconciliation() {
        XCTAssertFalse(
            LibraryManager.shouldReconcile(fetchError: "", registryPaths: ["/tmp/A.fichero"])
        )
    }

    // MARK: - Load gating (#3986-B)

    /// `DocumentStore` swallows a load error into `error`/`isConnected` rather
    /// than throwing, so both have to agree before a library is marked loaded —
    /// otherwise a failed load is recorded as done forever and the sidebar
    /// stays empty until relaunch.
    func testALoadCountsAsSuccessfulOnlyWhenBothSignalsAgree() {
        struct LoadError: Error {}
        XCTAssertTrue(LibraryManager.libraryLoadSucceeded(error: nil, isConnected: true))
        XCTAssertFalse(LibraryManager.libraryLoadSucceeded(error: nil, isConnected: false))
        XCTAssertFalse(LibraryManager.libraryLoadSucceeded(error: LoadError(), isConnected: true))
        XCTAssertFalse(LibraryManager.libraryLoadSucceeded(error: LoadError(), isConnected: false))
    }
}
