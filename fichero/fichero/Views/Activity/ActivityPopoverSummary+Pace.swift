import FicheroAPIClient
import Foundation

/// The live block's second line (`activity.window.row-subtitle`, #5960): counts, the time left from the engine's own pace, then the
/// model and where it runs; the cost at the right edge only when it is more than nothing. The engine sends the figures
/// (`seconds_left`, `cost_usd`); this only words them, and says nothing for a figure the engine does not have.
extension ActivityPopoverSummary {
    /// "about 12 min left"; "less than a minute left" under a minute and a half; "about 2 h left" past an hour. Nil without a pace.
    static func timeLeft(seconds: Double?) -> String? {
        guard let seconds, seconds > 0 else { return nil }
        if seconds < 90 { return "less than a minute left" }
        let minutes = Int((seconds / 60).rounded())
        if minutes < 60 { return "about \(minutes) min left" }
        let hours = (Double(minutes) / 60 * 2).rounded() / 2  // to the half hour
        let text = hours.truncatingRemainder(dividingBy: 1) == 0 ? String(Int(hours)) : String(format: "%.1f", hours)
        return "about \(text) h left"
    }

    /// "$0.40": the run's cost so far, only when it is more than nothing.
    static func costText(_ usd: Double?) -> String? {
        guard let usd, usd > 0 else { return nil }
        return usd < 0.01 ? "<$0.01" : String(format: "$%.2f", usd)
    }

    /// "7 of 20 pages · about 12 min left · Kraken · on this Mac": the line under the name.
    static func rowSubtitle(counts: String, secondsLeft: Double?, model: String?, place: String?) -> String {
        [counts, timeLeft(seconds: secondsLeft), subtitle(model: model, place: place)].compactMap { $0 }.joined(separator: " · ")
    }
}
