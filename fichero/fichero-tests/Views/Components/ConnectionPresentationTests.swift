@testable import Fichero
import Foundation
import Testing

/// #4380 + #4372: one connection/loading state, derived ONCE, rendered
/// consistently everywhere.
///
/// During a single mid-session failure four surfaces used to disagree — the
/// sidebar pill said "Live updates paused / Reconnect", the engine popover said
/// "Can't Connect to Server" and then narrated a startup sequence it was not
/// observing, its primary button offered `PYTHONPATH=src python -m
/// fichero_server.api` under a label truncated to "Start Exte…", and the
/// library pane spun a spinner over a dead engine forever.
///
/// These tests are the thing that stops that happening again: they assert the
/// pure phase → presentation mapping every surface now reads, including the
/// failure and empty cases, so a surface cannot quietly grow its own copy.
struct ConnectionPresentationTests {
    private typealias Ownership = ConnectionPresentation.EngineOwnership
    private typealias Action = ConnectionPresentation.Action

    private static let allPhases: [EngineSession.Phase] = [
        .setupNeeded,
        .starting,
        .ready,
        .portConflict(pid: 4242),
        .portConflict(pid: nil),
        .authRejected(diagnosis: "Token rejected"),
        .unreachable(diagnosis: "No response"),
        .failed(diagnosis: "Engine exited"),
    ]

    private static let allOwnerships: [Ownership] = [.appManaged, .externalLocal, .remote]

    private static let allAccessErrors: [AccessError?] = [
        nil,
        .unauthenticated,
        .staleBootstrapToken,
        .deviceAccessExpired,
        .forbidden(reason: "not_a_member", message: nil),
        .tlsPinFailure,
        .engineUnreachable,
        .transport("HTTPClientError.deadlineExceeded"),
    ]

    private func status(
        _ phase: EngineSession.Phase,
        _ ownership: Ownership,
        accessError: AccessError? = nil,
        authBroken: Bool = false
    ) -> ConnectionPresentation.Display {
        ConnectionPresentation.status(
            phase: phase,
            ownership: ownership,
            accessError: accessError,
            authBroken: authBroken
        )
    }

    // MARK: - Every phase maps to something honest

    @Test("every phase × ownership × error produces a titled, symbolled status")
    func everyCombinationIsRenderable() {
        for phase in Self.allPhases {
            for ownership in Self.allOwnerships {
                for error in Self.allAccessErrors {
                    let mapped = status(phase, ownership, accessError: error)
                    #expect(!mapped.title.isEmpty, "\(phase)/\(ownership)/\(String(describing: error))")
                    #expect(!mapped.symbol.isEmpty)
                }
            }
        }
    }

    /// The fabricated narration is the headline defect: the app is not
    /// observing the engine's Python imports or its database open, so it must
    /// not claim to be. `.starting` says only that it is connecting.
    @Test("a starting engine narrates nothing it is not observing")
    func startingNarratesNothing() {
        let appManaged = status(.starting, .appManaged)
        #expect(appManaged.title == "Starting engine…")
        #expect(appManaged.detail.isEmpty)
        #expect(appManaged.action == nil)
        #expect(appManaged.isRecovering)
        #expect(!appManaged.isError)

        for ownership in [Ownership.externalLocal, .remote] {
            let mapped = status(.starting, ownership)
            #expect(mapped.title == "Connecting…")
            #expect(mapped.detail.isEmpty)
            #expect(mapped.action == nil)
        }
    }

    @Test("no mapped string ever narrates the engine's internal startup steps")
    func noFabricatedProgressNarration() {
        let fabrications = [
            "Loading runtime libraries",
            "Opening the database",
            "This can take a moment",
            "Almost ready",
        ]
        for phase in Self.allPhases {
            for ownership in Self.allOwnerships {
                for error in Self.allAccessErrors {
                    let mapped = status(phase, ownership, accessError: error)
                    for fabrication in fabrications {
                        #expect(!mapped.title.contains(fabrication))
                        #expect(!mapped.detail.contains(fabrication))
                    }
                }
            }
        }
    }

    /// A shell command is not a user action, and a raw transport error is not a
    /// sentence (#4269). Neither may appear in any rendered string.
    @Test("no mapped string is a shell command or a raw error type")
    func noShellCommandsOrRawErrors() {
        for phase in Self.allPhases {
            for ownership in Self.allOwnerships {
                for error in Self.allAccessErrors {
                    for authBroken in [false, true] {
                        let mapped = status(phase, ownership, accessError: error, authBroken: authBroken)
                        let strings = [mapped.title, mapped.detail, mapped.action?.title ?? ""]
                        for text in strings {
                            #expect(!text.contains("PYTHONPATH"))
                            #expect(!text.contains("python -m"))
                            #expect(!text.contains("HTTPClientError"))
                            #expect(!text.contains("URLError"))
                            #expect(!text.contains("Error Domain"))
                        }
                    }
                }
            }
        }
    }

    @Test("a ready engine is not an error and asks for nothing")
    func readyIsQuiet() {
        for ownership in Self.allOwnerships {
            let mapped = status(.ready, ownership)
            #expect(!mapped.isError)
            #expect(!mapped.isRecovering)
            #expect(mapped.action == nil)
        }
    }

    @Test("every failure phase reads as an error and offers at most one action")
    func failuresAreErrors() {
        let failures: [EngineSession.Phase] = [
            .portConflict(pid: 4242),
            .authRejected(diagnosis: "x"),
            .unreachable(diagnosis: "x"),
            .failed(diagnosis: "x"),
        ]
        for phase in failures {
            for ownership in Self.allOwnerships {
                let mapped = status(phase, ownership, accessError: .engineUnreachable)
                #expect(mapped.isError)
                #expect(mapped.symbol == "exclamationmark.triangle.fill")
            }
        }
    }

    // MARK: - Only offer what actually works

    /// The app owns the embedded engine, so "Restart Engine" is a real action;
    /// it does not own a developer-started or remote engine, so there the only
    /// truthful offer is to connect again.
    @Test("the offered action follows who owns the engine process")
    func actionFollowsOwnership() {
        #expect(status(.unreachable(diagnosis: "x"), .appManaged).action == .restartEngine)
        #expect(status(.unreachable(diagnosis: "x"), .externalLocal).action == .reconnect)
        #expect(status(.unreachable(diagnosis: "x"), .remote).action == .reconnect)
    }

    /// When the engine was started outside the app, the copy says exactly that
    /// — and prescribes no command to fix it.
    @Test("an externally started engine is described truthfully, with no command")
    func externalEngineIsDescribedTruthfully() {
        let mapped = status(.failed(diagnosis: "exited"), .externalLocal, accessError: .engineUnreachable)
        #expect(mapped.detail == "The engine you started outside the app has stopped.")
        #expect(mapped.action == .reconnect)
    }

    /// Recovery is automatic for the engine the app supervises (#4064/#4296),
    /// so the surface says so instead of parking a popover that outlives the
    /// failure.
    @Test("an app-managed failure says it is already reconnecting")
    func appManagedFailureSaysItIsRecovering() {
        let mapped = status(.unreachable(diagnosis: "x"), .appManaged, accessError: .engineUnreachable)
        #expect(mapped.isRecovering)
        #expect(mapped.detail.contains("Reconnecting"))
    }

    @Test("a port conflict names the holder and offers the conflict box")
    func portConflictNamesTheHolder() {
        let known = status(.portConflict(pid: 4242), .appManaged)
        #expect(known.detail.contains("4242"))
        #expect(known.action == .resolvePortConflict)

        // Under the App Sandbox the PID is unknowable (#3749) — the copy must
        // not invent one, and the action must still be offered.
        let unknown = status(.portConflict(pid: nil), .appManaged)
        #expect(!unknown.detail.contains("nil"))
        #expect(unknown.action == .resolvePortConflict)
    }

    // MARK: - Length is a contract (#4366)

    @Test("every rendered string fits its budget — no truncation by design")
    func everyStringFitsItsBudget() {
        for phase in Self.allPhases {
            for ownership in Self.allOwnerships {
                for error in Self.allAccessErrors {
                    for authBroken in [false, true] {
                        let mapped = status(phase, ownership, accessError: error, authBroken: authBroken)
                        #expect(
                            mapped.title.count <= ConnectionPresentation.titleBudget,
                            "title over budget: \(mapped.title)")
                        // #4366: the island form is held to the island's own,
                        // much tighter budget.
                        #expect(
                            mapped.shortTitle.count <= ConnectionPresentation.islandBudget,
                            "shortTitle over island budget: \(mapped.shortTitle)")
                        #expect(!mapped.shortTitle.isEmpty)
                        #expect(
                            mapped.detail.count <= ConnectionPresentation.detailBudget,
                            "detail over budget: \(mapped.detail)")
                        if let action = mapped.action {
                            #expect(
                                action.title.count <= ConnectionPresentation.labelBudget,
                                "label over budget: \(action.title)")
                        }
                    }
                }
            }
        }
    }

    // MARK: - The surfaces cannot drift apart

    /// The popover, the status island and the library pane all read the SAME
    /// call for the SAME failure, so by construction they cannot disagree. This
    /// pins that they do — and that the popover's action is the pill's word.
    @Test("the popover, island and library pane render one failure identically")
    func surfacesAgreeOnOneFailure() {
        let phase = EngineSession.Phase.unreachable(diagnosis: "No response")
        let popover = ConnectionPresentation.status(
            phase: phase,
            ownership: .externalLocal,
            accessError: .engineUnreachable,
            authBroken: false
        )
        let island = StatusIslandMessage.resolve(
            enginePhase: phase,
            // The island renders the SHORT form of the same state (#4366) —
            // same table, written for a 260pt line instead of a popover header.
            engineStatusTitle: popover.shortTitle,
            importError: nil,
            isImporting: false,
            importProgress: nil,
            backendWorkLabel: nil,
            runningWorkflows: 0
        )
        let pane = LibraryLoadPhase.resolve(
            enginePhase: phase,
            ownership: .externalLocal,
            hasLoadedSuccessfully: false,
            isFetching: false,
            isEmpty: true,
            engineDetail: popover.detail,
            loadErrorMessage: nil
        )
        #expect(island.text == popover.shortTitle)
        #expect(island.text.count <= ConnectionPresentation.islandBudget)
        #expect(island.isError)
        #expect(pane == .failed(message: popover.detail))
        // The sidebar's "Live updates paused / Reconnect" pill and the
        // popover's primary action are now the same word.
        #expect(popover.action?.title == "Reconnect")
    }

    // MARK: - Library load phase (#4372)

    @Test("connecting and loading are different answers, never both")
    func connectingAndLoadingAreDistinct() {
        let connecting = LibraryLoadPhase.resolve(
            enginePhase: .starting,
            ownership: .remote,
            hasLoadedSuccessfully: false,
            isFetching: false,
            isEmpty: true,
            engineDetail: "",
            loadErrorMessage: nil
        )
        #expect(connecting == .connecting)
        #expect(connecting.message == "Connecting…")

        let starting = LibraryLoadPhase.resolve(
            enginePhase: .starting,
            ownership: .appManaged,
            hasLoadedSuccessfully: false,
            isFetching: false,
            isEmpty: true,
            engineDetail: "",
            loadErrorMessage: nil
        )
        #expect(starting == .startingEngine)
        #expect(starting.message == "Starting engine…")

        let loading = LibraryLoadPhase.resolve(
            enginePhase: .ready,
            ownership: .appManaged,
            hasLoadedSuccessfully: false,
            isFetching: true,
            isEmpty: true,
            engineDetail: "",
            loadErrorMessage: nil
        )
        #expect(loading == .loadingDocuments)
        #expect(loading.message == "Loading documents…")
    }

    /// The #4372 bug in one assertion: a load that never got asked for, because
    /// the engine never answered, must NOT render as a spinner.
    @Test("a failed engine is the error affordance, never a spinner")
    func failedEngineNeverSpins() {
        let failures: [EngineSession.Phase] = [
            .portConflict(pid: nil),
            .authRejected(diagnosis: "x"),
            .unreachable(diagnosis: "x"),
            .failed(diagnosis: "x"),
        ]
        for phase in failures {
            let resolved = LibraryLoadPhase.resolve(
                enginePhase: phase,
                ownership: .appManaged,
                hasLoadedSuccessfully: false,
                isFetching: true,
                isEmpty: true,
                engineDetail: "The engine stopped responding.",
                loadErrorMessage: nil
            )
            #expect(resolved == .failed(message: "The engine stopped responding."))
            #expect(!resolved.showsSpinner)
            #expect(resolved.message == nil)
        }
    }

    @Test("an empty result is the empty state, not a spinner")
    func emptyIsNotASpinner() {
        let resolved = LibraryLoadPhase.resolve(
            enginePhase: .ready,
            ownership: .appManaged,
            hasLoadedSuccessfully: true,
            isFetching: false,
            isEmpty: true,
            engineDetail: "",
            loadErrorMessage: nil
        )
        #expect(resolved == .empty)
        #expect(!resolved.showsSpinner)
    }

    @Test("a loaded collection is neither spinner nor error")
    func loadedIsQuiet() {
        let resolved = LibraryLoadPhase.resolve(
            enginePhase: .ready,
            ownership: .appManaged,
            hasLoadedSuccessfully: true,
            isFetching: false,
            isEmpty: false,
            engineDetail: "",
            loadErrorMessage: nil
        )
        #expect(resolved == .loaded)
        #expect(!resolved.showsSpinner)
    }

    @Test("a collection-level failure wins over the empty answer")
    func collectionErrorBeatsEmpty() {
        let resolved = LibraryLoadPhase.resolve(
            enginePhase: .ready,
            ownership: .appManaged,
            hasLoadedSuccessfully: true,
            isFetching: false,
            isEmpty: true,
            engineDetail: "",
            loadErrorMessage: "Couldn't read this folder."
        )
        #expect(resolved == .failed(message: "Couldn't read this folder."))
        #expect(!resolved.showsSpinner)
    }

    @Test("every spinner state carries exactly one short line")
    func spinnerStatesCarryOneShortLine() {
        for phase in [LibraryLoadPhase.connecting, .startingEngine, .loadingDocuments] {
            let message = phase.message
            #expect(message != nil)
            #expect(phase.showsSpinner)
            #expect((message?.count ?? 0) <= ConnectionPresentation.titleBudget)
        }
    }

    // MARK: - Structural guards

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The popover is status chrome, not an onboarding screen: no illustration
    /// icons, no cycling message table, no shell command, no raw diagnosis.
    @Test("the connection popover renders the mapping and nothing of its own")
    func popoverRendersOnlyTheMapping() throws {
        let source = try Self.appSource("Views/Components/BackendConnection/BackendConnectionView.swift")
        #expect(!source.contains("startupMessages"))
        #expect(!source.contains("Image(platformImage:"))
        #expect(!source.contains("PYTHONPATH"))
        #expect(source.contains("connectionStatus"))
        #expect(source.contains("primaryActionButton"))
    }

    /// The library pane's loading line comes from the phase, not from two
    /// strings stacked on top of each other.
    @Test("the library pane shows one derived line, not two competing ones")
    func libraryPaneShowsOneLine() throws {
        let source = try Self.appSource("Views/Library/LibraryView+FilterAndBatch.swift")
        #expect(source.contains("libraryLoadPhase"))
        #expect(source.contains("loadingMessage"))
        #expect(!source.contains("Connecting to library data"))
        #expect(!source.contains("Loading Documents..."))
    }
}
