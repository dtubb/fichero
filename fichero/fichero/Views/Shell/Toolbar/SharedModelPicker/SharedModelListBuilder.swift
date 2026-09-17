import Foundation

// The ONE way a model surface turns the provider cache into a pickable list.
//
// The spec (docs/contributor_manual/specs/ui/model-selector-consistency.md,
// RATIFIED 2026-09-15): ~7 model pickers each built their own list, and they
// drifted — the workflow bar showed two rows where the chip showed a dozen
// (Daniel, 2026-09-04). This is the extraction of the workflow bar's builder
// (`WorkflowBarPolicy.pinnableModels`, already the correct one) into a
// standalone pure function every surface can call, so the lists cannot
// disagree about what exists.
//
// PURE by contract: it takes `[LLMProvider]` and the tier defaults as plain
// values and reads NO SwiftUI environment. This matters because the document
// island fetches its own provider cache OUTSIDE the `LibraryWorkspaceRoot`
// environment tree (#4448) — a builder that reached for an injected service
// would be nil there. Inputs in, list out, testable without a view.

/// Catalog pricing for one model, per million tokens. A struct rather than a
/// tuple so a choice stays `Equatable` (a view can skip a redraw when the list
/// has not changed). Absent when the catalog says nothing — absent beats
/// invented (the chip's rule, 2026-08-29).
struct SharedModelPricing: Equatable {
    let inputPerMillion: Double
    let outputPerMillion: Double

    // The memberwise initializer Swift synthesizes is identical to the one that
    // used to be written out here, so it was deleted rather than maintained.
}

/// One configured model as any picker surface renders it: the family it
/// belongs to (`provider`/`model` drive `ModelFamilyMark`), a shortened
/// display name, the Settings tier it is the default for when it is one, the
/// catalog's vision verdict, and its price when known.
///
/// `provider` + `model` is the identity: the same model id served directly and
/// through a router is two different calls at two different prices, so the two
/// are never collapsed to one row.
struct SharedModelChoice: Equatable, Identifiable {
    let provider: String
    let model: String
    /// The name a toolbar shows — `openrouter/anthropic/claude-sonnet-5` reads
    /// as `claude-sonnet-5`. Precomputed with the ONE shortening rule the whole
    /// feature shares (`ModelChipToolbarItem.shorten`).
    let displayName: String
    /// A short annotation for the leading rows: the Settings tier this model is
    /// the default for ("Vision", "Text", "Large", "Small"). Nil for the long
    /// tail of configured models.
    var tier: String?
    /// Whether the catalog says this model reads images. `nil` means the
    /// catalog does not say — which is NOT a "no" (Daniel, 2026-09-01): a model
    /// newer than the catalog has no flag. Only a definite `false` may grey a
    /// row for a vision selection, and never remove it.
    var supportsVision: Bool?
    /// Per-million pricing when the catalog carries it. The builder never
    /// invents this; a surface with a pricing table attaches it (see
    /// `withPricing`).
    var pricing: SharedModelPricing?

    /// `provider/model` — stable and unique across the list (the dedupe key).
    var id: String { "\(provider)/\(model)" }

    /// A copy of this choice with pricing attached, or cleared when the table
    /// has no row. Lets the pure builder stay pricing-free while a surface that
    /// has fetched a catalog folds prices in afterward.
    func withPricing(_ pricing: SharedModelPricing?) -> SharedModelChoice {
        var copy = self
        copy.pricing = pricing
        return copy
    }
}

/// The shared, pure list-builder. Extracted verbatim in behaviour from
/// `WorkflowBarPolicy.pinnableModels` (the surfaces are rewired to call this in
/// a later increment; the original stays until then).
enum SharedModelListBuilder {

    /// One Settings tier and the concrete model configured for it.
    struct TierDefault: Equatable {
        let tier: String
        let provider: String
        let model: String

        init(tier: String, provider: String, model: String) {
            self.tier = tier
            self.provider = provider
            self.model = model
        }
    }

    /// Every model a surface can offer: the configured tiers first — the
    /// shortlist a user reaches for — then everything else the engine reports,
    /// alphabetically within its provider.
    ///
    /// Deduped on provider+model, never on model alone: the same model id
    /// served directly and through a router is two different calls at two
    /// different prices.
    ///
    /// `providers` empty (the cache has not answered yet) falls back to the
    /// tiers alone, so the list is never emptier than it was before the fetch.
    static func build(
        providers: [LLMProvider],
        tierDefaults: [TierDefault]
    ) -> [SharedModelChoice] {
        var seen = Set<String>()
        var choices: [SharedModelChoice] = []

        func visionFlag(provider: String, model: String) -> Bool? {
            guard let entry = providers.first(where: { $0.id == provider }) else {
                // Not in the cache: the catalog says NOTHING about it, which is
                // not the same as saying no.
                return nil
            }
            if let detail = entry.modelDetails.first(where: { $0.modelId == model }) {
                return detail.supportsVision
            }
            return entry.supportsVision
        }

        func append(provider: String, model: String, tier: String?) {
            let model = model.trimmingCharacters(in: .whitespaces)
            guard !model.isEmpty else { return }
            let key = "\(provider)/\(model)"
            guard !seen.contains(key) else { return }
            seen.insert(key)
            choices.append(SharedModelChoice(
                provider: provider,
                model: model,
                displayName: ModelChipToolbarItem.shorten(model),
                tier: tier,
                supportsVision: visionFlag(provider: provider, model: model),
                pricing: nil
            ))
        }

        for tier in tierDefaults {
            append(provider: tier.provider, model: tier.model, tier: tier.tier)
        }
        for provider in providers {
            for model in provider.models.sorted() {
                append(provider: provider.id, model: model, tier: nil)
            }
        }
        return choices
    }
}
