import Foundation

/// The staged chain's cost estimate — a per-step breakdown and the aggregate
/// the bar's cost chip states.
///
/// A single `Double?` could not tell apart the three states Daniel needs kept
/// distinct (2026-09-05). A chain every step of which is priced quotes a
/// CEILING ("est. ≤ $X" — the models, item count and max_tokens are all
/// bounded). A chain with a step the registry cannot price quotes a FLOOR
/// instead ("est. ≥ $X", plus the unpriced tail): the known steps are a lower
/// bound on a total whose rest is unknown, and calling that a ceiling would be
/// a lie. A chain with NOTHING priced is "unpriced" — never the "US$0.00" a
/// price miss used to read as (Daniel's screenshot, 2026-08-28).
///
/// The per-step lines double as ROUTING TRUTH: read before a paid run, each
/// line names what a step will really cost, beside the model it will really
/// use (the view supplies the model name from the live step, so it can never
/// drift from what the sentence shows).
struct StagedChainCost: Equatable {

    /// One staged step's contribution.
    ///
    /// `estimate == nil` means the registry could NOT price this step — an
    /// unpriceable model (an alias the price table does not key), or a tool
    /// step with no workflow to price until the run materialises one. A zero
    /// `estimate` is a real, priced figure (a free on-device model) and is
    /// kept deliberately distinct from "unknown": free is a promise, unknown
    /// is a question.
    struct Line: Equatable, Identifiable {
        /// The `StagedWorkflowStep` id, so the view can join a line back to
        /// the live step it priced.
        let id: UUID
        let estimate: Double?

        var isPriced: Bool { estimate != nil }
    }

    /// One line per staged step, in run order.
    var lines: [Line]

    /// Sum over the steps that COULD be priced. Free (zero-priced) steps count
    /// toward it as the zero they are; unpriced steps are excluded, not read
    /// as zero.
    var pricedTotal: Double {
        lines.reduce(0) { $0 + ($1.estimate ?? 0) }
    }

    var pricedCount: Int { lines.lazy.filter(\.isPriced).count }
    var unpricedCount: Int { lines.lazy.filter { !$0.isPriced }.count }

    /// At least one step carried a price, so an amount can be shown.
    var hasPricedStep: Bool { pricedCount > 0 }

    /// Every step that has a price also carries a known amount — so the total
    /// is a true CEILING rather than a floor with an unknown remainder.
    var isCompletePricing: Bool { hasPricedStep && unpricedCount == 0 }

    /// The line for a given step, if the estimate has been computed for it.
    func line(forStepId id: UUID) -> Line? {
        lines.first { $0.id == id }
    }
}
