import Foundation

/// What the capability bar should offer for the current selection — the whole
/// decision, with no SwiftUI in it, so it is unit-testable without a window
/// (the `LibraryToolbarPolicy` shape).
///
/// The bar exists because Fichero ships ~90 tools, ~50 workflows and chaining,
/// and showed none of it outside the node editor. The fix is not a curated
/// list: every workflow already declares, server-side, what it can be run on
/// (`accepted_inputs`) and whether it needs a vision model. So the bar is a
/// PROJECTION of the selection through those declarations — select a page and
/// the vision verbs appear; select a passage and only the verbs that take text
/// do. Ninety tools collapse to the handful that can act on this thing.
///
/// This is the same rule as "verbs act on the selection you can see", applied
/// to discovery rather than to menus.
enum WorkflowBarPolicy {

    /// What the bar is pointed at right now.
    enum Target: Equatable {
        case nothing
        /// Documents — pages, files, or a folder's worth of them.
        case documents(count: Int)
        /// A passage selected in the Reader. Carries the text so a verb can be
        /// handed the selection itself rather than the document around it.
        case text(String)

        /// The engine's vocabulary for this target, matched against a
        /// workflow's `acceptedInputs`.
        var inputKind: String? {
            switch self {
            case .nothing:   return nil
            case .documents: return "documents"
            case .text:      return "text"
            }
        }
    }

    /// One family of verbs — a folder of workflows, collapsed to a single
    /// toolbar button with its variants in a submenu. Families come from the
    /// engine's `folder_path`, so the grouping needs no client-side curation
    /// and stays right when presets are added.
    struct VerbFamily: Identifiable, Equatable {
        let id: String
        let title: String
        let symbol: String
        let workflows: [WorkflowSidebarItem]
    }

    /// Verbs that can act on `target`, grouped into families.
    ///
    /// Filtering, in order:
    ///   1. the workflow must be directly runnable — a component that only runs
    ///      inside a parent is not a verb the user can point at anything;
    ///   2. it must accept this kind of target;
    ///   3. an empty target offers nothing, because a verb with nothing to act
    ///      on is a button that lies.
    static func families(
        from workflows: [WorkflowSidebarItem],
        target: Target
    ) -> [VerbFamily] {
        guard let kind = target.inputKind else { return [] }
        if case .documents(let count) = target, count == 0 { return [] }

        let applicable = workflows.filter { workflow in
            workflow.canRunDirectly && workflow.acceptedInputs.contains(kind)
        }

        let grouped = Dictionary(grouping: applicable) { folderKey($0.folderPath) }
        return grouped
            .compactMap { key, items -> VerbFamily? in
                // A family with nothing runnable in it is a button that lies.
                guard !items.isEmpty else { return nil }
                return VerbFamily(
                    id: key,
                    title: familyTitle(key),
                    symbol: symbol(forFamily: key),
                    workflows: items.sorted { $0.sortOrder < $1.sortOrder }
                )
            }
            // Pipeline order, not alphabetical (Daniel, 2026-08-28: "the route
            // that we would work" — regions, then transcription, then
            // translation). Alphabetical put Books first and Detect Regions
            // sixth, which is the reverse of how anyone processes a document.
            .sorted { lhs, rhs in
                let lhsRank = pipelineRank(lhs.id)
                let rhsRank = pipelineRank(rhs.id)
                return lhsRank == rhsRank ? lhs.title < rhs.title : lhsRank < rhsRank
            }
    }

    /// Where a family sits in the order work actually happens: prepare the
    /// image, find the regions, read them, clean the reading, translate it,
    /// describe and extract from it, then catalogue, organise and export.
    /// Families nobody anticipated sort after the known route rather than
    /// interleaving into it at random.
    static let pipelineOrder = [
        "Image Editing",
        "Detect Regions",
        "Transcribe",
        "Clean Up",
        "Translate",
        "Describe",
        "Extract",
        "Extract Data",
        "Catalogue",
        "Organize",
        "Books",
        "Convert",
        "Export"
    ]

    static func pipelineRank(_ key: String) -> Int {
        pipelineOrder.firstIndex(where: { $0.caseInsensitiveCompare(key) == .orderedSame })
            ?? pipelineOrder.count
    }

    /// A workflow's family key: its top-level folder. `/Detect Regions/VLM`
    /// and `/Detect Regions` are one family — nesting below the first level is
    /// organisation, not a different verb.
    static func folderKey(_ folderPath: String) -> String {
        let trimmed = folderPath.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let first = trimmed.split(separator: "/").first, !first.isEmpty else {
            return "Other"
        }
        return String(first)
    }

    static func familyTitle(_ key: String) -> String { key }

    /// Family icons. Unknown families get a neutral symbol rather than being
    /// hidden: a preset in a folder nobody anticipated must still be runnable.
    static func symbol(forFamily key: String) -> String {
        switch key.lowercased() {
        case "transcribe":     return "text.viewfinder"
        case "detect regions": return "rectangle.dashed"
        case "extract", "extract data": return "square.on.square.badge.person.crop"
        case "catalogue":      return "books.vertical"
        case "clean up":       return "wand.and.sparkles"
        case "describe":       return "text.bubble"
        case "organize":       return "folder.badge.gearshape"
        case "convert":        return "arrow.triangle.2.circlepath"
        case "export":         return "square.and.arrow.up"
        case "image editing":  return "photo"
        case "books":          return "book"
        default:               return "play.circle"
        }
    }

    /// What the run will act on, stated before it starts — the target chip.
    /// A paid eight-step chain over a folder should never be ambiguous about
    /// its scope.
    static func targetLabel(_ target: Target) -> String? {
        switch target {
        case .nothing:
            return nil
        case .documents(let count):
            return count == 1 ? "1 item" : "\(count) items"
        case .text(let text):
            let words = text.split(whereSeparator: \.isWhitespace).count
            return words == 1 ? "1 word" : "\(words) words"
        }
    }

    /// Why the bar is empty, when it is — an empty bar with no explanation
    /// reads as a broken app rather than as "nothing applies here".
    static func emptyReason(
        from workflows: [WorkflowSidebarItem],
        target: Target
    ) -> String? {
        switch target {
        case .nothing:
            return "Select something to see what you can run on it."
        case .documents(let count) where count == 0:
            return "Select something to see what you can run on it."
        case .text:
            guard families(from: workflows, target: target).isEmpty else { return nil }
            return "No workflow accepts a text selection yet."
        default:
            guard families(from: workflows, target: target).isEmpty else { return nil }
            return "No workflow accepts this selection."
        }
    }
}
