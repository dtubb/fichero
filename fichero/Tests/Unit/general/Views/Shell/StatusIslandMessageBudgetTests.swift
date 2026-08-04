@testable import Fichero
import Foundation
import Testing

/// #4366: island message length is a CONTRACT, not a styling accident.
///
/// The island is a narrow, fixed-ish slot in the toolbar. A message written for
/// a popover header arrives there as a fragment — the same failure as the
/// connection popover's "Start Exte…" button (#4380). So the strings are
/// written for the width, and this suite is what fails when a new one is not.
///
/// Two categories, deliberately handled differently:
///   - App-authored strings must fit natively. If one does not, a test fails —
///     it is never shortened for you, because the fix is to write it shorter.
///   - Strings from outside the app (an OS error, a backend task name) have no
///     length contract and cannot be pre-written, so they pass through ONE
///     named seam, `shortForm(_:)`, instead of being clipped by the renderer.
struct StatusIslandMessageBudgetTests {

    private func resolve(
        enginePhase: EngineSession.Phase = .ready,
        engineStatusTitle: String = "Connected",
        importError: String? = nil,
        isImporting: Bool = false,
        importProgress: String? = nil,
        backendWorkLabel: String? = nil,
        runningWorkflows: Int = 0
    ) -> StatusIslandMessage {
        StatusIslandMessage.resolve(
            enginePhase: enginePhase,
            engineStatusTitle: engineStatusTitle,
            importError: importError,
            isImporting: isImporting,
            importProgress: importProgress,
            backendWorkLabel: backendWorkLabel,
            runningWorkflows: runningWorkflows
        )
    }

    // MARK: - The budget is derived, not guessed

    /// The budget was derived from the island's declared width. If someone
    /// widens the island, this fails and forces a re-derivation rather than
    /// letting the number silently go stale.
    @Test("the island still declares the width the budget was derived from")
    func declaredWidthMatchesTheDerivation() throws {
        #expect(StatusIslandMessage.declaredMaxWidth == 260)
        let url = try AppSource.root()
            .appendingPathComponent("Views/Shell/Toolbar/StatusIslandToolbarItem.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        #expect(source.contains("maxWidth: StatusIslandMessage.declaredMaxWidth"))
        // The renderer's truncation is a backstop, never the length policy.
        #expect(source.contains(".truncationMode(.tail)"))
    }

    /// One budget, shared with the connection mapping, so the engine's short
    /// titles and the island's own strings are held to the same number.
    @Test("the island and the connection mapping share one budget")
    func oneBudgetShared() {
        #expect(StatusIslandMessage.budget == ConnectionPresentation.islandBudget)
        #expect(StatusIslandMessage.budget > 0)
    }

    // MARK: - App-authored strings must fit natively

    @Test("every app-authored island message is within budget")
    func everyAuthoredMessageFitsTheBudget() {
        for message in StatusIslandMessage.authoredMessages {
            #expect(
                message.count <= StatusIslandMessage.budget,
                "over budget (\(message.count) > \(StatusIslandMessage.budget)): \(message)")
            // And it must not need shortening — an authored string that only
            // fits BECAUSE shortForm clipped it has not been written short.
            #expect(StatusIslandMessage.shortForm(message) == message, Comment(rawValue: message))
        }
    }

    /// Every engine short title, across the whole mapping, must fit. These are
    /// app-authored too — they just live in `ConnectionPresentation`.
    @Test("every engine short title fits the island")
    func everyEngineShortTitleFits() {
        let phases: [EngineSession.Phase] = [
            .setupNeeded, .starting, .ready,
            .portConflict(pid: 4242), .portConflict(pid: nil),
            .authRejected(diagnosis: "x"), .unreachable(diagnosis: "x"), .failed(diagnosis: "x"),
        ]
        let errors: [AccessError?] = [
            nil, .unauthenticated, .staleBootstrapToken, .deviceAccessExpired,
            .forbidden(reason: "not_a_member", message: nil), .tlsPinFailure,
            .engineUnreachable, .transport("HTTPClientError.deadlineExceeded"),
        ]
        for phase in phases {
            for ownership in [ConnectionPresentation.EngineOwnership.appManaged, .externalLocal, .remote] {
                for error in errors {
                    for authBroken in [false, true] {
                        let mapped = ConnectionPresentation.status(
                            phase: phase, ownership: ownership,
                            accessError: error, authBroken: authBroken
                        )
                        let island = resolve(enginePhase: phase, engineStatusTitle: mapped.shortTitle)
                        #expect(
                            island.text.count <= StatusIslandMessage.budget,
                            "over budget: \(island.text)")
                        #expect(!island.text.isEmpty)
                    }
                }
            }
        }
    }

    /// The long popover titles are exactly what must NOT reach the island —
    /// this is the regression the short forms exist to prevent.
    @Test("the popover's long titles would not have fitted")
    func thePopoverTitlesWouldNotHaveFitted() {
        let mapped = ConnectionPresentation.status(
            phase: .authRejected(diagnosis: "x"),
            ownership: .appManaged,
            accessError: nil,
            authBroken: true
        )
        #expect(mapped.title == "Fichero Couldn't Authenticate to Its Server")
        #expect(mapped.title.count > StatusIslandMessage.budget)
        #expect(mapped.shortTitle.count <= StatusIslandMessage.budget)
        // Same state, still recognisable — a short form, not a stub.
        #expect(mapped.shortTitle == "Sign-in rejected")
    }

    // MARK: - Whatever the input, the island line fits

    @Test("an unbounded external string is shortened to fit, at one named seam")
    func externalStringsAreShortened() {
        let long = String(repeating: "Could not read that file ", count: 12)
        for message in [
            resolve(importError: long),
            resolve(isImporting: true, importProgress: long),
            resolve(backendWorkLabel: long),
        ] {
            #expect(message.text.count <= StatusIslandMessage.budget, Comment(rawValue: message.text))
            #expect(message.text.hasSuffix("…"))
        }
    }

    /// A short external string is passed through untouched — the seam can never
    /// shorten something that did not need it.
    @Test("a short external string is not touched")
    func shortExternalStringsArePassedThrough() {
        #expect(resolve(importError: "Could not read 3 files").text == "Could not read 3 files")
        #expect(resolve(backendWorkLabel: "Indexing — 40%").text == "Indexing — 40%")
        #expect(
            resolve(isImporting: true, importProgress: "Importing 4 of 900…").text
                == "Importing 4 of 900…"
        )
    }

    @Test("shortening prefers a word boundary so the line reads as a phrase")
    func shorteningPrefersAWordBoundary() {
        let shortened = StatusIslandMessage.shortForm(
            "Transcribing page 4 of the Marshall diaries volume seventeen"
        )
        #expect(shortened.count <= StatusIslandMessage.budget)
        #expect(shortened.hasSuffix("…"))
        // Cut between words, not mid-word.
        #expect(!shortened.dropLast().hasSuffix(" "))
        #expect(shortened.hasPrefix("Transcribing page 4 of the"))
    }

    /// A single very long word has no usable boundary; it still has to fit, and
    /// it must not collapse to a bare ellipsis.
    @Test("a single unbroken word still fits and still says something")
    func anUnbrokenWordStillFits() {
        let shortened = StatusIslandMessage.shortForm(String(repeating: "x", count: 200))
        #expect(shortened.count <= StatusIslandMessage.budget)
        #expect(shortened.count > 1)
        #expect(shortened.hasSuffix("…"))
    }

    @Test("shortening is idempotent")
    func shorteningIsIdempotent() {
        let once = StatusIslandMessage.shortForm(String(repeating: "word ", count: 40))
        #expect(StatusIslandMessage.shortForm(once) == once)
    }

    /// The property that matters: whatever any caller passes, the island's line
    /// is within budget. This is the assertion that makes truncation in the UI
    /// impossible rather than merely unlikely.
    @Test("no input of any length can produce an over-budget island line")
    func noInputEverExceedsTheBudget() {
        let monsters = [
            String(repeating: "a", count: 500),
            String(repeating: "long words here ", count: 40),
            "PYTHONPATH=src python -m fichero_server.api\n\nPlease start the API first",
            "  \n  padded and newlined  \n  ",
        ]
        for monster in monsters {
            let candidates = [
                resolve(importError: monster),
                resolve(isImporting: true, importProgress: monster),
                resolve(backendWorkLabel: monster),
                resolve(enginePhase: .failed(diagnosis: "x"), engineStatusTitle: "Can't connect to server"),
                resolve(runningWorkflows: 99),
                resolve(),
            ]
            for candidate in candidates {
                #expect(
                    candidate.text.count <= StatusIslandMessage.budget,
                    "over budget: \(candidate.text)")
                // Never an empty island either — blank reads as "fine".
                #expect(!candidate.text.isEmpty)
            }
        }
    }

    /// Whitespace and newlines are stripped: a multi-line payload must not
    /// render as a line with a hard return in it.
    @Test("a multi-line external string never reaches the island with a newline")
    func multiLineInputIsFlattened() {
        let message = resolve(importError: "first line\nsecond line\nthird line")
        #expect(!message.text.contains("\n"))
        #expect(message.text.count <= StatusIslandMessage.budget)
    }
}
