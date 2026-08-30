@testable import Fichero
import Foundation
import Testing

// Coverage for the schedule-formatting logic extracted from ScheduleEditorView
// (#1993). Edge cases: unit boundaries + singular/plural for intervals; each
// recognised cron pattern, the invalid field count, and the custom fallback.

@Suite("ScheduleFormatting (#1993)")
struct ScheduleFormattingTests {

    // MARK: - formatInterval

    @Test("seconds below a minute render as seconds")
    func intervalSeconds() {
        #expect(ScheduleFormatting.formatInterval(0) == "0 seconds")
        #expect(ScheduleFormatting.formatInterval(45) == "45 seconds")
        #expect(ScheduleFormatting.formatInterval(59) == "59 seconds")
    }

    @Test("minute / hour / day boundaries flip at 60 / 3600 / 86400")
    func intervalBoundaries() {
        #expect(ScheduleFormatting.formatInterval(60) == "1 minute")
        #expect(ScheduleFormatting.formatInterval(3599) == "59 minutes")
        #expect(ScheduleFormatting.formatInterval(3600) == "1 hour")
        #expect(ScheduleFormatting.formatInterval(86399) == "23 hours")
        #expect(ScheduleFormatting.formatInterval(86400) == "1 day")
    }

    @Test("singular vs plural units")
    func intervalPluralization() {
        #expect(ScheduleFormatting.formatInterval(120) == "2 minutes")
        #expect(ScheduleFormatting.formatInterval(7200) == "2 hours")
        #expect(ScheduleFormatting.formatInterval(172_800) == "2 days")
    }

    // MARK: - describeCron

    @Test("recognised cron patterns get plain-language descriptions")
    func cronKnownPatterns() {
        #expect(ScheduleFormatting.describeCron("0 * * * *") == "Every hour at minute 0")
        #expect(ScheduleFormatting.describeCron("0 0 * * *") == "Every day at midnight")
        #expect(ScheduleFormatting.describeCron("0 0 * * 0") == "Every Sunday at midnight")
        #expect(ScheduleFormatting.describeCron("0 0 1 * *") == "First day of every month at midnight")
    }

    @Test("wrong field count is rejected")
    func cronInvalid() {
        #expect(ScheduleFormatting.describeCron("") == "Invalid cron expression")
        #expect(ScheduleFormatting.describeCron("0 0 *") == "Invalid cron expression")
        #expect(ScheduleFormatting.describeCron("0 0 * * * *") == "Invalid cron expression")
    }

    @Test("unrecognised but valid cron falls back to Custom schedule")
    func cronCustom() {
        #expect(ScheduleFormatting.describeCron("30 9 * * 1") == "Custom schedule")
        #expect(ScheduleFormatting.describeCron("*/5 * * * *") == "Custom schedule")
    }

    @Test("regression: day-at-midnight (dow=*) and Sunday (dow=0) don't collide")
    func cronSundayNotShadowed() {
        // The dow=* check precedes the dow=0 check; both must still resolve to
        // their own description rather than one shadowing the other.
        #expect(ScheduleFormatting.describeCron("0 0 * * *") != ScheduleFormatting.describeCron("0 0 * * 0"))
    }
}
