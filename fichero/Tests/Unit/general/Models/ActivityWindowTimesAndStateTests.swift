//
//  ActivityWindowTimesAndStateTests.swift
//  FicheroTests
//
//  Pure rules behind two Activity window behaviours
//  (docs/contributor_manual/specs/ui/activity-and-automatic-work.md):
//
//  - activity.window.absolute-times (#5432): every row said "just now". The
//    store read the engine's `started_at` (aware UTC WITH microseconds) through
//    a default `ISO8601DateFormatter`, which refuses fractional seconds, and
//    put `Date()` in its place; the rows then printed relative words. Times
//    are absolute now, and a time that cannot be read is shown as unknown.
//  - activity.window.honest-state (#5431): the footer said only "Couldn't load
//    activity from Local", even when the cause was a 401 from an engine whose
//    token had just changed. It names the cause now.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct ActivityWindowAbsoluteTimesTests {

    private static var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private static let britishEnglish = Locale(identifier: "en_GB")

    // WHY: this is the #5432 defect itself. An engine time of today's shape
    // (aware UTC, microseconds), an hour old, must read as its clock time. If
    // this goes red the window is back to "just now" for a run an hour old.
    @Test("activity.window.absolute-times: an hour-old engine time shows as its clock time")
    func hourOldEngineTimeShowsItsClockTime() throws {
        let now = try #require(parseEngineDate("2026-10-04T14:00:00+00:00"))
        let started = parseEngineDate("2026-10-04T13:00:00.123456+00:00")
        #expect(started != nil, "the engine's own time shape must parse")
        let text = ActivityTimeText.absolute(started, now: now, calendar: Self.utc, locale: Self.britishEnglish)
        #expect(text == "13:00")
    }

    // WHY: the ruling's shape ("Yesterday 09:10"). A run from yesterday
    // says so in words, with its clock time, never "1 day ago".
    @Test("activity.window.absolute-times: a run from yesterday says Yesterday and its clock time")
    func yesterdaySaysYesterday() throws {
        let now = try #require(parseEngineDate("2026-10-04T14:00:00+00:00"))
        let started = parseEngineDate("2026-10-03T10:10:00.5+00:00")
        let text = ActivityTimeText.absolute(started, now: now, calendar: Self.utc, locale: Self.britishEnglish)
        #expect(text == "Yesterday 10:10")
    }

    // WHY: an older run keeps its clock time beside its date; a bare date
    // would lose the absolute time the ruling asks for.
    @Test("activity.window.absolute-times: an older run shows its date and its clock time")
    func olderRunShowsDateAndClockTime() throws {
        let now = try #require(parseEngineDate("2026-10-04T14:00:00+00:00"))
        let started = parseEngineDate("2026-09-28T11:15:00+00:00")
        let text = ActivityTimeText.absolute(started, now: now, calendar: Self.utc, locale: Self.britishEnglish)
        #expect(text.hasSuffix("11:15"))
        #expect(text != "11:15", "a day other than today or yesterday names its date")
        #expect(!text.contains("ago"))
    }

    // WHY: the old fallback put "now" where a time could not be read, which is
    // a lie that looks like a fact. No time is shown as no time.
    @Test("activity.window.absolute-times: a time that could not be read is shown as unknown, never as now")
    func unknownTimeIsShownAsUnknown() {
        #expect(parseEngineDate("not a time") == nil)
        #expect(ActivityTimeText.absolute(nil) == ActivityTimeText.unknown)
    }
}

@MainActor
struct ActivityWindowHonestStateTests {

    // WHY: #5431's refusal was a 401 from an engine respawn's token change.
    // A footer that names only the library sends the reader looking at the
    // library; the cause is the credentials.
    @Test("activity.window.honest-state: a refused load names the credentials")
    func refusedLoadNamesTheCredentials() {
        let message = ActivityStore.runLoadFailureMessage(libraryName: "Local", error: AccessError.unauthenticated)
        #expect(message.contains("Local"))
        #expect(message.contains("refused the app's credentials"))
    }

    // WHY: an engine that is down is a different fix from a refused token;
    // the footer must tell them apart.
    @Test("activity.window.honest-state: an unreachable engine says it could not be reached")
    func unreachableEngineSaysSo() {
        let message = ActivityStore.runLoadFailureMessage(libraryName: "Local", error: URLError(.cannotConnectToHost))
        #expect(message.contains("could not be reached"))
    }
}
