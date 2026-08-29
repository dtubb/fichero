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
    /// Presentation metadata for one folder, as the ENGINE serves it
    /// (`GET /api/workflows/folders`). Order and glyph are data, not rules —
    /// a folder the engine has not described still appears, after the known
    /// route and with a fallback glyph, so a user's own folder is never
    /// hidden by the client's ignorance of it.
    struct FolderPresentation: Equatable {
        let sortOrder: Int
        let icon: String
    }

    static func families(
        from workflows: [WorkflowSidebarItem],
        target: Target,
        folders: [String: FolderPresentation] = [:]
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
                    symbol: folders[key]?.icon ?? symbol(forFamily: key),
                    workflows: items.sorted { $0.sortOrder < $1.sortOrder }
                )
            }
            // Pipeline order, not alphabetical (Daniel, 2026-08-28: "the route
            // that we would work" — regions, then transcription, then
            // translation). Alphabetical put Books first and Detect Regions
            // sixth, which is the reverse of how anyone processes a document.
            .sorted { lhs, rhs in
                let lhsRank = folders[lhs.id]?.sortOrder ?? pipelineRank(lhs.id)
                let rhsRank = folders[rhs.id]?.sortOrder ?? pipelineRank(rhs.id)
                return lhsRank == rhsRank ? lhs.title < rhs.title : lhsRank < rhsRank
            }
    }

    /// FALLBACK order, used only until `GET /api/workflows/folders` answers
    /// (first paint, or an engine too old to serve it). The engine owns this
    /// now; keeping a copy here means the bar is never scrambled during the
    /// beat before the fetch lands. Unknown families sort after the route.
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

    /// Scaled to match the served orders (10, 20, 30 …) so a mixed list —
    /// some folders described by the engine, some not — still sorts sensibly.
    static func pipelineRank(_ key: String) -> Int {
        let index = pipelineOrder.firstIndex {
            $0.caseInsensitiveCompare(key) == .orderedSame
        }
        return ((index ?? pipelineOrder.count) + 1) * 10
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
    /// A table, not a switch: this is data — the mapping a served folder
    /// record overrides anyway — and expressing it as control flow only made
    /// the function complex enough to trip the complexity rule.
    private static let familySymbols: [String: String] = [
        "transcribe": "text.viewfinder",
        "detect regions": "rectangle.dashed",
        "extract": "square.on.square.badge.person.crop",
        "extract data": "square.on.square.badge.person.crop",
        "catalogue": "books.vertical",
        "clean up": "wand.and.sparkles",
        "describe": "text.bubble",
        "organize": "folder.badge.gearshape",
        "convert": "arrow.triangle.2.circlepath",
        "export": "square.and.arrow.up",
        "image editing": "photo",
        "books": "book",
    ]

    static func symbol(forFamily key: String) -> String {
        familySymbols[key.lowercased()] ?? "play.circle"
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
