import Foundation

/// The one way an Activity row writes a run's time
/// (`activity.window.absolute-times`, #5432): absolute, never "just now".
///
/// Today's runs show their clock time ("14:32"), yesterday's say so
/// ("Yesterday 09:10"), anything older adds its date. A time the app could not
/// read is `nil` and shows as `unknown`: the rows used to put "now" in its
/// place, which made every row read "just now".
enum ActivityTimeText {
    static let unknown = "Time unknown"

    static func absolute(
        _ date: Date?,
        now: Date = Date(),
        calendar: Calendar = .autoupdatingCurrent,
        locale: Locale = .autoupdatingCurrent
    ) -> String {
        guard let date else { return unknown }
        let clock = date.formatted(
            Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, calendar: calendar, timeZone: calendar.timeZone)
        )
        if calendar.isDate(date, inSameDayAs: now) { return clock }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
           calendar.isDate(date, inSameDayAs: yesterday) {
            return "Yesterday \(clock)"
        }
        var day = Date.FormatStyle(locale: locale, calendar: calendar, timeZone: calendar.timeZone)
            .day().month(.abbreviated)
        if calendar.component(.year, from: date) != calendar.component(.year, from: now) {
            day = day.year()
        }
        return "\(date.formatted(day)) \(clock)"
    }
}
