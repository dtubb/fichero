import CoreGraphics
import Foundation

/// A page's `page_region` attribute as the app shows it (`image.enhance.page-region-shown-in-the-app`, #6187): the box as
/// fractions of the upright frame, and how it was found, in words. Pure, so the Inspector row and the outline are tested without
/// a view. The engine's `box` is `[x, y, w, h]`; a person's box carries `by: "person"` and says "yours".
struct PageRegionSummary: Equatable {
    let box: CGRect
    let method: String
    let confidence: Double?
    let byPerson: Bool

    init?(pageRegion: Any?) {
        guard let region = pageRegion as? [String: Any], let raw = region["box"] as? [Any], raw.count == 4 else { return nil }
        let numbers = raw.compactMap { ($0 as? NSNumber)?.doubleValue }
        guard numbers.count == 4, numbers[2] > 0, numbers[3] > 0 else { return nil }
        box = CGRect(x: numbers[0], y: numbers[1], width: numbers[2], height: numbers[3])
        method = (region["method"] as? String) ?? ""
        confidence = (region["confidence"] as? NSNumber)?.doubleValue
        byPerson = (region["by"] as? String) == "person" || method == "person"
    }

    /// How much of the frame the page takes, 0…1.
    var share: Double { box.width * box.height }

    /// "61 % of the frame, Vision, sure" (a person's: "61 % of the frame, yours").
    var words: String {
        let percent = Int((share * 100).rounded())
        if byPerson { return "\(percent) % of the frame, yours" }
        var parts = ["\(percent) % of the frame"]
        if !method.isEmpty { parts.append(method.prefix(1).uppercased() + method.dropFirst()) }
        if let confidence { parts.append(confidence >= 0.8 ? "sure" : "unsure") }
        return parts.joined(separator: ", ")
    }
}
