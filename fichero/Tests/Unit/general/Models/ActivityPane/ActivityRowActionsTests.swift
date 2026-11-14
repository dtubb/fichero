//
//  ActivityRowActionsTests.swift — `activity.pane.row-actions-on-the-table` (#6441, #6583): the states table is the
//  fixture; the Mail rule for several rows; one button per row; the outcome counted in the status bar.
//

@testable import Fichero
import Testing

struct ActivityRowActionsTests {
    typealias F = ActivityPaneFixture
    typealias Verb = ActivityPaneVerb

    /// The spec's states table: each state and the verbs it allows.
    static let table: [(ActivityMonitorRow.Phase, Set<Verb>)] = [
        (.waiting, [.pause, .stop, .delete]),
        (.running, [.pause, .stop, .delete]),
        (.paused, [.resume, .stop, .delete]),
        (.cancelled, [.retry, .archive, .delete]),
        (.failed, [.retry, .archive, .delete]),
        (.done, [.archive, .delete]),
        (.partial, [.retry, .archive, .delete]),
        (.notRun, [])
    ]

    @Test("every state allows exactly its verbs from the states table")
    func statesTable() {
        for (phase, verbs) in Self.table {
            let row = F.row("x", phase)
            #expect(Set(Verb.allCases.filter { $0.allows(row) }) == verbs, "\(phase)")
        }
        var stopping = F.row("s", .running)
        stopping.transientState = "Stopping"
        #expect(Set(Verb.allCases.filter { $0.allows(stopping) }) == [.stop, .delete])
        var archived = F.row("a", .done)
        archived.isArchived = true
        #expect(Set(Verb.allCases.filter { $0.allows(archived) }) == [.putBack, .delete])
        #expect(Verb.allCases.allSatisfy { !$0.allows(F.page("p", .failed, doc: "d")) }, "a file goes with its run")
    }

    @Test("Mail rule: failed + paused + running enables Delete, Stop, Continue and Pause (the running one allows it)")
    func mailRule() {
        let rows = [F.row("f", .failed), F.row("p", .paused), F.row("r", .running)]
        #expect(Set(Verb.allCases.filter { $0.isEnabled(for: rows) }) == [.delete, .stop, .resume, .pause, .retry, .archive])
        #expect(!Verb.putBack.isEnabled(for: rows))
        let (targets, skipped) = Verb.resume.split(rows)
        #expect(targets.map(\.id) == ["p"] && skipped == 2)
        #expect(Verb.deleteNeedsConfirmation(rows), "Delete with a running row asks once: Stop then Delete")
        #expect(Verb.outcome(.delete, done: 4, skipped: 1) == "Deleted 4 · 1 skipped")
        #expect(Verb.outcome(.archive, done: 2, skipped: 0) == "Archived 2")
    }

    @Test("one button per row: the failed row's fix, else its state's verb; none when the state has no verb")
    func oneButton() {
        #expect(F.row("r", .running).paneButton == .verb(.pause))
        #expect(F.row("p", .paused).paneButton == .verb(.resume))
        #expect(F.row("f", .failed).paneButton == .verb(.retry))
        #expect(F.row("d", .done).paneButton == nil)
        var keyMissing = F.row("k", .failed)
        keyMissing.failure = .init(kind: "missing-key", words: "", fix: "", actions: ["open-settings"])
        #expect(keyMissing.paneButton == .settings)
        #expect(Verb.resume.title == "Continue", "Continue, never Resume")
    }
}
