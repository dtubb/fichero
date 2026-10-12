import FicheroAPIClient
import Foundation
@testable import Fichero
import Testing

/// The engine for these tests: only the transport is stubbed; the store, the service and the generated client are
/// the real ones. It answers Stop (the job's cancel) and Read Again (the run's read-again) and records each call.
private final class RunVerbsEngine: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var paths: [String] = []
    nonisolated(unsafe) static var refuse = false

    static func reset() {
        lock.lock()
        paths = []
        refuse = false
        lock.unlock()
    }

    static func recorded() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return paths
    }

    override static func canInit(with request: URLRequest) -> Bool { request.url?.host == "run-verbs.test" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        let path = request.url?.path ?? ""
        Self.lock.lock()
        Self.paths.append("\(request.httpMethod ?? "") \(path)")
        let refuse = Self.refuse
        Self.lock.unlock()
        var status = 200
        var json = #"{"detail":"no stub"}"#
        if refuse {
            status = 409
            json = #"{"detail":"the engine said no"}"#
        } else if path.hasSuffix("/cancel") {
            json = #"{"id":"job-1","state":"cancelled"}"#
        } else if path.hasSuffix("/read-again") {
            status = 202
            json = #"{"thread_id":"thread-new","from_thread_id":"thread-1","workflow_id":"wf","#
                + #""workflow_name":"Transcribe","pages":3,"stream_url":"https://run-verbs.test/api/x"}"#
        } else {
            status = 404
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// #5652 slice 3: Stop and Read Again act on a run through ONE target (`ActivityRunMenuTarget.make` / `.stage`),
/// which the Activity table's row buttons, its context menu, the menu bar, the details and the project's run strip all
/// render. What breaks without these: a menu item that is on when it can do nothing (or off with no reason), or a
/// press that reaches the wrong route, or says nothing when the engine refuses.
@MainActor
@Suite("Activity's Stop and Read Again (#5652 slice 3)", .serialized)
struct ActivityRunMenuTests {
    private func target(canStop: Bool, readAgainLabel: String?) -> ActivityRunMenuTarget {
        ActivityRunMenuTarget(
            rowId: "run-1", rowName: "Read the folder", canStop: canStop, readAgainLabel: readAgainLabel,
            stop: {}, readAgain: {}
        )
    }

    private func store() -> ActivityStore {
        RunVerbsEngine.reset()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RunVerbsEngine.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://run-verbs.test")!, libraryPath: "/tmp/run-verbs.fichero",
            session: URLSession(configuration: configuration)
        )
        return ActivityStore(service: ActivityService(ficheroClient: client))
    }

    /// Press one of a target's verbs and wait for what it reports: nil when the engine took it, else why not.
    private func press(_ verb: (ActivityRunMenuTarget) -> Void,
                       make: (@escaping @MainActor (String?) -> Void) -> ActivityRunMenuTarget) async -> String? {
        await withCheckedContinuation { continuation in
            verb(make { continuation.resume(returning: $0) })
        }
    }

    @Test("no run selected: both are off, and Stop says to select a run")
    func noRunSelected() {
        #expect(FocusedActivityRunButtons.stopDisabledReason(nil) == "Select a run in the Activity window")
        #expect(FocusedActivityRunButtons.readAgainDisabledReason(nil) == "Select a run in the Activity window")
        #expect(FocusedActivityRunButtons.readAgainTitle(nil) == "Read Again")
    }

    @Test("a running run can be stopped and has nothing to read again yet")
    func runningRun() {
        let running = target(canStop: true, readAgainLabel: nil)
        #expect(FocusedActivityRunButtons.stopDisabledReason(running) == nil)
        #expect(
            FocusedActivityRunButtons.readAgainDisabledReason(running)
                == "Only an ended run with pages to read again offers this"
        )
    }

    @Test("an ended run with pages left offers its own read-again label and cannot be stopped")
    func endedRunWithPagesLeft() {
        let ended = target(canStop: false, readAgainLabel: "Read the 3 pages that failed")
        #expect(
            FocusedActivityRunButtons.stopDisabledReason(ended)
                == "Only a run that is running or waiting can be stopped"
        )
        #expect(FocusedActivityRunButtons.readAgainDisabledReason(ended) == nil)
        #expect(FocusedActivityRunButtons.readAgainTitle(ended) == "Read the 3 pages that failed")
    }

    @Test("a stage's target offers Read Again on that stage's thread and never Stop")
    func stageTarget() {
        let target = ActivityRunMenuTarget.stage(
            threadId: "thread-2", offer: "Read the 5 pages that failed", store: nil, report: { _ in }
        )
        #expect(target.rowId == "thread-2")
        #expect(FocusedActivityRunButtons.readAgainTitle(target) == "Read the 5 pages that failed")
        #expect(FocusedActivityRunButtons.readAgainDisabledReason(target) == nil)
        #expect(FocusedActivityRunButtons.stopDisabledReason(target) != nil)
    }

    @Test("Stop on a row's target cancels that row's job, once, and reports that the engine took it")
    func stopCancelsTheRowsJob() async {
        let store = store()
        let outcome = await press({ $0.stop() }) { report in
            .make(rowId: "run-1", rowName: "Read the folder", canStop: true, jobId: "job-1",
                  runThreadId: "thread-1", readAgainLabel: nil, store: store, report: report)
        }
        #expect(outcome == nil)
        #expect(RunVerbsEngine.recorded() == ["POST /api/activity/jobs/job-1/cancel"])
    }

    @Test("Read Again on a row's target asks the engine to read that run's pages again")
    func readAgainReadsTheRunAgain() async {
        let store = store()
        let outcome = await press({ $0.readAgain() }) { report in
            .make(rowId: "run-1", rowName: "Read the folder", canStop: false, jobId: "job-1",
                  runThreadId: "thread-1", readAgainLabel: "Read the 3 pages that failed", store: store, report: report)
        }
        #expect(outcome == nil)
        #expect(RunVerbsEngine.recorded() == ["POST /api/workflow-execution/threads/thread-1/read-again"])
    }

    @Test("Read Again on a stage's target reads that stage's thread again")
    func stageReadAgain() async {
        let store = store()
        let outcome = await press({ $0.readAgain() }) { report in
            .stage(threadId: "thread-7", offer: "Read the 2 pages that failed", store: store, report: report)
        }
        #expect(outcome == nil)
        #expect(RunVerbsEngine.recorded() == ["POST /api/workflow-execution/threads/thread-7/read-again"])
    }

    @Test("a refusal is said in words, with the run's name for Stop")
    func refusalIsSaid() async {
        let store = store()
        RunVerbsEngine.refuse = true
        let stopped = await press({ $0.stop() }) { report in
            .make(rowId: "run-1", rowName: "Read the folder", canStop: true, jobId: "job-1",
                  runThreadId: "thread-1", readAgainLabel: nil, store: store, report: report)
        }
        #expect(stopped?.hasPrefix("Couldn't stop Read the folder: ") == true)
        let readAgain = await press({ $0.readAgain() }) { report in
            .stage(threadId: "thread-7", offer: "Read the 2 pages that failed", store: store, report: report)
        }
        #expect(readAgain?.hasPrefix("Couldn't read the pages again: ") == true)
    }
}
