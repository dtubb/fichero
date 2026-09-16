import SwiftUI

// The ONE model row every picker surface renders.
//
// Extracted from the document island's `ModelPickerRow` (the reference the
// spec adopts — docs/contributor_manual/specs/ui/model-selector-consistency.md,
// RATIFIED 2026-09-15), byte-for-byte in look: a leading tick for the current
// model, the family mark (`ModelFamilyMark`, the same glyph the chip wears),
// the shortened name over its per-million price, then a vision eye and the
// provider on the trailing edge. A model the current selection cannot use is
// greyed with the reason as its tooltip — marked, never hidden (2026-09-01).
//
// A concrete (non-generic) type on purpose: the island's first inline version
// was one giant generic tuple whose opaque-type metadata instantiation stalled
// the main thread 333ms on first open. A concrete row keeps the metadata
// trivial (the note above `ModelChipToolbarItem.modelPicker`).

/// One configured model in a shared picker list. Renders a `SharedModelChoice`
/// exactly as the island's picker did — any surface can drop it into a list.
struct SharedModelRow: View {
    /// The model to render — provider/model drive the family mark, the rest is
    /// the name, price, tier and vision annotations.
    let choice: SharedModelChoice
    /// True when this is the model the surface would use right now (draws the
    /// leading tick).
    let isCurrent: Bool
    /// Non-nil when the row is not pickable for the current selection — greys
    /// the row and becomes its tooltip, so the reason travels with the refusal.
    var disabledReason: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "checkmark")
                    .font(.system(size: 9, weight: .semibold))
                    .opacity(isCurrent ? 1 : 0)
                // The same family mark the chip wears — the row's logo is what
                // lets the eye find "the Claude one" without reading (Daniel,
                // 2026-08-29: "the popover should have icons as well").
                ModelFamilyMark(model: choice.model, provider: choice.provider)
                VStack(alignment: .leading, spacing: 1) {
                    Text(choice.displayName)
                        .font(.callout)
                    if let pricing = choice.pricing {
                        // The catalog's per-million figures, in/out — enough to
                        // tell the cheap step from the expensive one.
                        Text(String(format: "$%.2f in · $%.2f out / M",
                                    pricing.inputPerMillion, pricing.outputPerMillion))
                            .font(.system(size: 9))
                            .foregroundStyle(.tertiary)
                            .monospacedDigit()
                    }
                }
                Spacer(minLength: 12)
                if choice.supportsVision == true {
                    Image(systemName: "eye")
                        .font(.system(size: 9))
                        .foregroundStyle(.secondary)
                        .help("Can read images")
                }
                Text(choice.provider)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(disabledReason != nil)
        .opacity(disabledReason == nil ? 1 : 0.45)
        .help(disabledReason ?? "\(choice.model) — \(choice.provider)")
    }
}
