@testable import Fichero
import Foundation
import Testing

/// Spec `engine.stale-engines-ended-at-launch`: which "Fichero Server" processes the app ends at launch.
/// A pure decision over a process table; nothing here signals a process.
@Suite("Stale engine sweep (engine.stale-engines-ended-at-launch)")
struct StaleEngineSweepTests {
    private typealias Fact = StaleEngineSweep.ProcessFact
    private static let helper = "/Applications/Fichero.app/Contents/Helpers/Fichero Server.app/Contents/MacOS/Fichero Server"
    private static let otherCopy =
        "/Volumes/x/Downloads/Fichero 2.app/Contents/Resources/Fichero Server.app/Contents/MacOS/Fichero Server"
    private static let appBinary = "/Applications/Fichero.app/Contents/MacOS/Fichero"
    private let me: UInt32 = 501

    private func ended(_ table: [Fact], ownPID: Int32 = 100) -> [Int32] {
        StaleEngineSweep.pidsToEnd(table: table, currentUID: me, ownPID: ownPID)
    }

    @Test("an orphan helper (parent is launchd) is ended")
    func orphanHelperIsEnded() {
        #expect(ended([Fact(pid: 200, parentPID: 1, uid: 501, executablePath: Self.helper)]) == [200])
    }

    @Test("a helper whose parent has gone is ended")
    func helperWithDeadParentIsEnded() {
        #expect(ended([Fact(pid: 200, parentPID: 4242, uid: 501, executablePath: Self.helper)]) == [200])
    }

    @Test("the helper of a live app is kept")
    func helperOfALiveAppIsKept() {
        let table = [
            Fact(pid: 100, parentPID: 1, uid: 501, executablePath: Self.appBinary),
            Fact(pid: 200, parentPID: 100, uid: 501, executablePath: Self.helper),
        ]
        #expect(ended(table, ownPID: 999).isEmpty)
    }

    @Test("a helper from another bundle path with a live parent is kept")
    func otherBundleWithLiveParentIsKept() {
        let table = [
            Fact(pid: 50, parentPID: 1, uid: 501, executablePath: "/Volumes/x/Downloads/Fichero 2.app/Contents/MacOS/Fichero"),
            Fact(pid: 200, parentPID: 50, uid: 501, executablePath: Self.otherCopy),
        ]
        #expect(ended(table).isEmpty)
    }

    @Test("a dev uvicorn / python engine is kept, orphaned or not")
    func devEngineIsKept() {
        let table = [
            Fact(pid: 200, parentPID: 1, uid: 501, executablePath: "/Volumes/x/code/fichero/.venv/bin/python"),
            Fact(pid: 201, parentPID: 1, uid: 501, executablePath: "/opt/homebrew/Cellar/python@3.12/3.12.1/Frameworks/Python.framework/Versions/3.12/Resources/Python.app/Contents/MacOS/Python"),
            Fact(pid: 202, parentPID: 1, uid: 501, executablePath: "/usr/local/bin/uvicorn"),
        ]
        #expect(ended(table).isEmpty)
    }

    @Test("another user's helper is kept")
    func otherUsersHelperIsKept() {
        #expect(ended([Fact(pid: 200, parentPID: 1, uid: 502, executablePath: Self.helper)]).isEmpty)
    }

    @Test("this app's own pid is never ended")
    func ownPIDIsKept() {
        #expect(ended([Fact(pid: 100, parentPID: 1, uid: 501, executablePath: Self.helper)]).isEmpty)
    }

    @Test("an executable merely containing the name is not a helper")
    func lookalikeIsKept() {
        #expect(!StaleEngineSweep.isFicheroServerHelper(executablePath: "/tmp/Fichero Server.app/Contents/MacOS/other"))
        #expect(!StaleEngineSweep.isFicheroServerHelper(executablePath: "/Applications/Other.app/Contents/MacOS/Other"))
        #expect(StaleEngineSweep.isFicheroServerHelper(executablePath: Self.helper))
    }

    @Test("ps output is parsed with a path that holds spaces; junk lines are skipped")
    func parsesPsOutput() {
        let table = StaleEngineSweep.parseTable("    1     0     0 /sbin/launchd\n  200     1   501 \(Self.helper)\nnot a row\n")
        #expect(table.count == 2)
        #expect(table[1] == Fact(pid: 200, parentPID: 1, uid: 501, executablePath: Self.helper))
    }

    @Test("what was ended is reported once, in one line")
    func noticeIsOneLineAndOnce() {
        #expect(StaleEngineSweep.notice(ended: []) == nil)
        #expect(StaleEngineSweep.notice(ended: [7]) == "Ended 1 leftover Fichero Server from an earlier run.")
        #expect(StaleEngineSweep.notice(ended: [7, 8]) == "Ended 2 leftover Fichero Servers from an earlier run.")
        StaleEngineSweep.record(ended: [7])
        #expect(StaleEngineSweep.takeEnded() == [7])
        #expect(StaleEngineSweep.takeEnded().isEmpty)
    }
}
