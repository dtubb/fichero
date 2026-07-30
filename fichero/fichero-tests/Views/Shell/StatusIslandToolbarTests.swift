@testable import Fichero
import Foundation
import Testing

/// The Xcode-style status island (#4036): ONE element beside the window title
/// that says what the app is doing — engine, imports, background work,
/// workflows, errors — instead of a spinner in the leading zone plus a pill
/// after the view-mode icons.
///
/// A bad connection must be VISIBLE, never blocking: these tests pin the
/// message precedence (so an error can't be hidden behind a progress line) and
/// the structural rule that the item is always declared (#3163).
struct StatusIslandToolbarTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

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

    // MARK: - Message precedence

    @Test("an idle, connected app reads Ready")
    func idleReadsReady() {
        #expect(resolve() == StatusIslandMessage(text: "Ready", isError: false))
    }

    /// The island shows the SAME short title the popover puts on the same
    /// failure (#4380) — not the engine's raw diagnosis, which on the
    /// debug-external path is a multi-line shell command the island rendered as
    /// a truncated fragment (#4366).
    @Test("every engine failure surfaces the mapped short title as an error")
    func engineFailuresSurfaceMappedTitle() {
        let failures: [EngineSession.Phase] = [
            .portConflict(pid: 4242),
            .authRejected(diagnosis: "Token rejected"),
            .unreachable(diagnosis: "No response"),
            .failed(diagnosis: "Engine exited"),
        ]
        for phase in failures {
            let status = resolve(enginePhase: phase, engineStatusTitle: "Can't Connect to Server")
            #expect(status.isError, "\(phase) must read as an error")
            #expect(status.text == "Can't Connect to Server")
        }
    }

    /// The island can never render a shell command: it renders whatever
    /// `ConnectionPresentation` produced, and that table contains none.
    @Test("no mapped engine status is a shell command")
    func noMappedEngineStatusIsAShellCommand() {
        let phases: [EngineSession.Phase] = [
            .setupNeeded,
            .starting,
            .ready,
            .portConflict(pid: 4242),
            .portConflict(pid: nil),
            .authRejected(diagnosis: "Token rejected"),
            .unreachable(diagnosis: "No response"),
            .failed(diagnosis: "Engine exited"),
        ]
        let ownerships: [ConnectionPresentation.EngineOwnership] = [.appManaged, .externalLocal, .remote]
        for phase in phases {
            for ownership in ownerships {
                let mapped = ConnectionPresentation.status(
                    phase: phase,
                    ownership: ownership,
                    accessError: nil,
                    authBroken: false
                )
                let status = resolve(enginePhase: phase, engineStatusTitle: mapped.title)
                #expect(!status.text.contains("PYTHONPATH"))
                #expect(!status.text.contains("python -m"))
                #expect(!status.text.isEmpty)
            }
        }
    }

    @Test("a booting engine says so, in the words the popover uses")
    func bootingEngineSaysSo() {
        let title = ConnectionPresentation.status(
            phase: .starting,
            ownership: .appManaged,
            accessError: nil,
            authBroken: false
        ).title
        #expect(title == "Starting engine…")
        #expect(resolve(enginePhase: .starting, engineStatusTitle: title)
            == StatusIslandMessage(text: "Starting engine…", isError: false))
    }

    /// The load-bearing precedence: an engine problem must not be masked by an
    /// import that is merely still spinning against a dead engine.
    @Test("an engine failure outranks in-flight import progress")
    func engineFailureOutranksImportProgress() {
        let status = resolve(
            enginePhase: .unreachable(diagnosis: "No response"),
            engineDiagnosis: "No response",
            isImporting: true,
            importProgress: "Importing 4 of 900…",
            backendWorkLabel: "Indexing — 40%",
            runningWorkflows: 3
        )
        #expect(status == StatusIslandMessage(text: "No response", isError: true))
    }

    @Test("an import error outranks other progress once the engine is fine")
    func importErrorOutranksProgress() {
        let status = resolve(
            importError: "Could not read 3 files",
            isImporting: true,
            importProgress: "Importing…",
            backendWorkLabel: "Indexing — 40%",
            runningWorkflows: 2
        )
        #expect(status == StatusIslandMessage(text: "Could not read 3 files", isError: true))
    }

    @Test("an import in flight reports its own progress")
    func importReportsProgress() {
        let status = resolve(isImporting: true, importProgress: "Importing 4 of 900…", runningWorkflows: 2)
        #expect(status == StatusIslandMessage(text: "Importing 4 of 900…", isError: false))
    }

    /// Importing with no progress string yet must not fall through to the
    /// workflow/idle text — the island would claim "Ready" mid-import.
    @Test("an import with no progress yet still says Importing")
    func importWithoutProgressStillSaysImporting() {
        #expect(resolve(isImporting: true) == StatusIslandMessage(text: "Importing…", isError: false))
    }

    @Test("backend work outranks workflow counts")
    func backendWorkOutranksWorkflows() {
        let status = resolve(backendWorkLabel: "Indexing — 40%", runningWorkflows: 5)
        #expect(status == StatusIslandMessage(text: "Indexing — 40%", isError: false))
    }

    @Test("running workflows are counted, and pluralised")
    func runningWorkflowsArePluralised() {
        #expect(resolve(runningWorkflows: 1).text == "Running 1 workflow…")
        #expect(resolve(runningWorkflows: 4).text == "Running 4 workflows…")
    }

    // MARK: - Structure

    /// #3163: a `ToolbarItem` that appears and disappears with state has
    /// crashed this app before (duplicate registration). The island's CONTENT
    /// varies; the item is declared unconditionally, exactly once.
    @Test("the island is one unconditionally-declared principal item")
    func islandIsOneUnconditionalItem() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        // Anchored on the DECLARATION form, not the bare symbol: prose that
        // merely mentions `ContentToolbarID.statusIsland` (the comments left
        // where the engine/activity items used to sit) is not a second item.
        let declaration = "ToolbarItem(id: ContentToolbarID.statusIsland"
        #expect(source.contains("\(declaration), placement: .principal)"))
        #expect(source.components(separatedBy: declaration).count - 1 == 1)
    }

    /// Engine and activity live INSIDE the island now. Leaving either declared
    /// as its own toolbar item would put the same control on screen twice.
    @Test("engine and activity are hosted only inside the island")
    func engineAndActivityAreHostedOnlyInTheIsland() throws {
        let toolbar = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(!toolbar.contains("ToolbarItem(id: ContentToolbarID.engineStatus"))
        #expect(!toolbar.contains("ToolbarItem(id: ContentToolbarID.activityStatus"))

        let island = try Self.appSource("Views/Shell/Toolbar/StatusIslandToolbarItem.swift")
        #expect(island.contains("EngineStatusToolbarItem()"))
        #expect(island.contains("ActivityStatusToolbarItem("))
    }

    @Test("the activity status popover opens the Activity window")
    func activityStatusOpensActivityWindow() throws {
        let source = try Self.appSource("Views/Shell/Toolbar/ActivityStatusToolbarItem.swift")

        #expect(source.contains("@Environment(\\.openWindow)"))
        #expect(source.contains("Text(libraryName)"))
        #expect(source.contains("selectLibrary(libraryId)"))
        #expect(source.contains("openWindow(id: ActivityWindowSelectionState.monitorWindowID)"))
    }
}
