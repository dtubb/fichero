import Foundation

// MARK: - How sure the machine is about WHERE a word is (2026-09-04)

/// `OCRGeometryBox.confidence` has been decoded since #4309 and read by
/// nothing. In Daniel's live library that is 7,595 boxes at 0.50 and 6,225 at
/// 0.30 drawn exactly as authoritatively as the 1,557 at 1.0 — a page whose
/// geometry is mostly guesswork looking, to the reader, like a page the
/// machine is sure of. The whole reason the boxes are drawn at all is to make
/// the transcription checkable rather than merely trusted, and a uniform
/// stroke over a 0.30 box quietly undoes that.
///
/// Pure and fixed, deliberately. There is no threshold slider: a knob here
/// would mean the same page reads as confident or doubtful depending on a
/// setting nobody remembers changing (dead-simple-UX — features are ON or
/// OFF), and the honest number is a property of the data, not a preference.
enum OCRBoxConfidence {

    /// At or above this, a box is drawn as an assertion about where the word
    /// is; below it, as the guess it is.
    ///
    /// 0.8 sits above every observed cluster except the certain one. The
    /// engines bucket their answers — 1.0 for a clean read, 0.5 and 0.3 for
    /// progressively worse ones — so any cut between 0.5 and 1.0 partitions
    /// the same way; 0.8 is chosen to leave room for an engine that reports a
    /// genuinely high 0.9 without demoting it.
    static let certainAtOrAbove = 0.8

    /// Whether a box should be drawn as uncertain.
    ///
    /// `nil` is NOT uncertain. A missing confidence means the producer does
    /// not report one — the alignment pass writes none at all — and dimming
    /// every box from a silent engine would state doubt the data never
    /// expressed. What is true of those boxes is a matter of PROVENANCE
    /// (measured / aligned / interpolated), which is a different axis and
    /// wants a different visual channel; see `isUncertain(_:)`'s callers,
    /// which use opacity and a dash for this one and leave the rest free.
    static func isUncertain(_ confidence: Double?) -> Bool {
        guard let confidence else { return false }
        return confidence < certainAtOrAbove
    }

    static func isUncertain(_ box: OCRGeometryBox) -> Bool {
        isUncertain(box.confidence)
    }

    /// How many of these boxes are drawn as guesses — the number the regions
    /// panel prints, so the doubt is countable and not only visible.
    static func uncertainCount(in boxes: [OCRGeometryBox]) -> Int {
        boxes.reduce(into: 0) { total, box in
            if isUncertain(box) { total += 1 }
        }
    }

    /// The regions panel's caption, or `nil` when every box is confident and
    /// there is nothing to warn about.
    ///
    /// Says how many of how many, because "12 uncertain" reads very
    /// differently over 15 boxes than over 1,500.
    static func summary(for boxes: [OCRGeometryBox]) -> String? {
        let uncertain = uncertainCount(in: boxes)
        guard uncertain > 0 else { return nil }
        return "\(uncertain) of \(boxes.count) below \(Int(certainAtOrAbove * 100))% confidence"
    }

    /// Stroke opacity for one box. The uncertain one is present but recessive:
    /// still findable, no longer an assertion.
    static func strokeOpacity(_ confidence: Double?) -> Double {
        isUncertain(confidence) ? 0.35 : 0.8
    }

    /// Whether the box's recognised TEXT may be drawn inside it.
    ///
    /// It may not, below the threshold. Inline text is the strongest claim
    /// this overlay makes — it prints what the machine believes the word says,
    /// in place of the word — and printing it over a box the machine is 30%
    /// sure of asserts twice: that the word is there, and that it is that
    /// word. The scan underneath stays readable instead, which is the answer
    /// the reader actually needs there.
    static func drawsInlineText(_ confidence: Double?) -> Bool {
        !isUncertain(confidence)
    }
}
