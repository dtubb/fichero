@testable import Fichero
import Foundation
import Testing

// #3276, both halves.
//
// A: the app hard-coded `extractText: false` / `autoEmbed: false` on every
// drag-drop and menu import, silently overriding the engine's documented `True`
// — so nothing a user dropped was findable until a workflow reprocessed it. The
// same two fields were hard-coded `true` one file away in DocumentService. Two
// app-side copies of a decision that belongs to the engine, disagreeing.
//
// B: `importFiles` returned a bare `[Document]` and threw only when EVERY file
// failed. A ten-file drop that lost three returned normally; the per-file errors
// went into `ImportService.lastError`, which no view has ever read. "Dropped 10,
// silently got 7" — the case #2384 was written to remove, surviving because only
// the total-failure branch was ever wired.
@MainActor
@Suite("Import reports what it actually achieved (#3276)")
struct ImportPartialFailureTests {

    private func failure(_ name: String) -> ImportError {
        ImportError(
            url: URL(fileURLWithPath: "/tmp/\(name)"),
            error: NSError(
                domain: "test",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "disk full"]
            )
        )
    }

    // MARK: - B: the partial case must be distinguishable from a clean one

    @Test("a clean import produces NO message — not an empty one")
    func cleanImportHasNoMessage() {
        let outcome = ImportOutcome(documents: [], failures: [], attempted: 3)

        #expect(outcome.isComplete)
        // An empty string assigned into a banner renders as an alert that says
        // nothing, which is a silent failure wearing a dialog.
        #expect(outcome.partialFailureMessage == nil)
    }

    @Test("7 of 10 says seven of ten, and says why")
    func partialImportReportsBothCounts() throws {
        let outcome = ImportOutcome(
            documents: [],
            failures: (1...3).map { failure("f\($0)") },
            attempted: 10
        )

        #expect(!outcome.isComplete)
        let message = try #require(outcome.partialFailureMessage)
        #expect(message.contains("7 of 10"))
        #expect(message.contains("3 failed"))
        // The first reason travels with the count: "3 failed" alone tells the
        // user nothing they can act on.
        #expect(message.contains("disk full"))
    }

    @Test("every file failing reads as none imported, not as '0 of N'")
    func totalFailureReadsAsNoneImported() throws {
        let outcome = ImportOutcome(
            documents: [],
            failures: (1...4).map { failure("f\($0)") },
            attempted: 4
        )

        let message = try #require(outcome.partialFailureMessage)
        #expect(message.contains("None of the 4"))
    }

    @Test("attempted is tracked separately because a folder succeeds without a Document")
    func attemptedIsNotDerivedFromCounts() throws {
        // One folder (contributes no Document) plus one failed file. Deriving
        // the denominator as documents.count + failures.count would say "1",
        // under-reporting the batch and turning "1 of 2 failed" into "1 of 1".
        let outcome = ImportOutcome(
            documents: [],
            failures: [failure("bad.png")],
            attempted: 2
        )

        let message = try #require(outcome.partialFailureMessage)
        #expect(message.contains("1 of 2"))
    }

    @Test("a single-item batch that fails still reports, not silently returns")
    func singleFailureIsReported() {
        let outcome = ImportOutcome(
            documents: [],
            failures: [failure("only.png")],
            attempted: 1
        )

        #expect(outcome.partialFailureMessage != nil)
    }

    // MARK: - B: every call site must READ the outcome, not discard it

    // These are source assertions rather than behavioural ones because the
    // failure they guard is an OMISSION — a call site that goes back to
    // `_ = try await importFiles(...)` compiles, passes every behavioural test,
    // and silently loses files again. There is nothing to observe at runtime
    // when the reporting is simply absent.

    private func source(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // Services
            .deletingLastPathComponent()   // fichero-tests
            .deletingLastPathComponent()   // fichero
            .appendingPathComponent("fichero/\(relativePath)")
        let text = try String(contentsOf: url, encoding: .utf8)
        // An unreadable or empty file must fail loudly rather than let every
        // `contains` below pass vacuously.
        #expect(!text.isEmpty, "\(relativePath) is empty — this guard would measure nothing")
        return text
    }

    @Test("no import call site discards the outcome")
    func everyImportCallSiteReadsTheOutcome() throws {
        let callSites = [
            "Views/Sidebar/ItemRow/SidebarItemRow+DropHandlers.swift",
            "Views/Sidebar/Sections/SidebarView+LibraryHeaderHelpers.swift",
            "Views/Sidebar/Components/SidebarActions.swift",
            "Views/Shell/ContentView/Actions/ContentView+ActionsImport.swift",
            "Views/Library/LibraryView+BottomActionBar.swift"
        ]

        for path in callSites {
            let text = try source(path)
            #expect(
                text.contains("partialFailureMessage"),
                "\(path) imports files without reporting the partial case (#3276)"
            )
            #expect(
                !text.contains("_ = try await importService.importFiles")
                    && !text.contains("_ = try await library.importService.importFiles"),
                "\(path) discards the import outcome again (#3276)"
            )
        }
    }

    // MARK: - A: the engine's defaults must not be overridden app-side

    @Test("the app no longer hard-codes extract/embed off on the import path")
    func importPathDoesNotOverrideEngineDefaults() throws {
        for path in ["Services/ImportService.swift", "Services/ImportService+Ingest.swift"] {
            let text = try source(path)
            #expect(
                !text.contains("extractText: Bool = false"),
                "\(path) re-decides the engine's extract_text default (#3276)"
            )
            #expect(
                !text.contains("autoEmbed: Bool = false"),
                "\(path) re-decides the engine's auto_embed default (#3276)"
            )
        }
    }

    @Test("no import path hard-codes the engine's defaults in EITHER direction")
    func documentServiceAlsoDefersToTheEngine() throws {
        // DocumentService.ingestFolder defaulted these to `true` — the right
        // value, arrived at by a second app-side copy of the engine's decision.
        // A copy that happens to agree today is still a copy.
        let text = try source("Services/DocumentService.swift")
        #expect(!text.contains("extractText: Bool = true"))
        #expect(!text.contains("autoEmbed: Bool = true"))
    }
}
