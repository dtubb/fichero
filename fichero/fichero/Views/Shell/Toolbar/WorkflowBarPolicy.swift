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
        "books": "book"
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

    // MARK: - Run-scope resolution (Daniel, 2026-08-29: the bar follows the
    // selection the user can SEE, wherever it is — inspector region rows,
    // a focused artifact, the browser list, or the previewed document).

    /// Everything the ladder needs, snapshotted as plain values so the
    /// decision is a pure function with no SwiftUI or stores in it.
    struct SelectionSnapshot: Equatable {
        /// An ephemeral marquee drawn in Preview — a crop that is not a
        /// persisted node. The topmost rung when present.
        var marqueeDocumentId: String?
        var marqueeRect: CGRect?
        var marqueeDocumentName: String?

        /// Region NODE ids selected in the inspector's regions list.
        var regionIds: [String] = []
        /// The page those regions belong to.
        var regionParentDocumentId: String?
        var regionParentName: String?

        /// The focused artifact (inspector list or a table's artifact row).
        var artifactId: String?
        var artifactDocumentId: String?
        /// e.g. "Transcription Review" — what the chip should NAME.
        var artifactDisplayName: String?
        var artifactType: String?
        var artifactStepName: String?
        var artifactDocumentName: String?
        /// The artifact was AIMED at from the inspector's "Run Workflow on
        /// This", not merely selected — a deliberate choice that outranks the
        /// multi-select guard below.
        var artifactPinned = false

        /// The library browser's effective selection (live or preserved).
        var browserSelection: [String] = []

        /// The previewed document — the last rung.
        var detailDocumentId: String?
        var detailDocumentName: String?

        /// Every artifact the inspected document actually HAS, newest-first
        /// is not required (the menu sorts), each carrying enough provenance
        /// to tell one Detect Regions pass from another (Daniel, 2026-09-03:
        /// "if there are multiple regions — which model produced it"). Empty
        /// when the host has none loaded; the menu then falls back to the
        /// by-TYPE rows, which still resolve at run time.
        var detailArtifacts: [ArtifactChoice] = []
    }

    /// What a run would act on, resolved. Distinct from `Target` (which
    /// drives verb FILTERING): the scope carries the ids and hints a run
    /// needs, plus enough names for the chip to state it honestly.
    enum RunScope: Equatable {
        /// An ephemeral marquee drawn on one document in Preview. Not yet a
        /// node: ▶ materializes it as a region child (`image.crop_child`)
        /// and runs on that — the engine takes crops as node config, never
        /// as run inputs, so an unpersisted rect cannot run directly.
        case marqueeSelection(documentId: String, rect: CGRect, documentName: String?)
        /// N region nodes of one page — region nodes are documents, so their
        /// ids run as ordinary `selected_doc_ids`.
        case regions(ids: [String], parentName: String?)
        /// One artifact of one document: the run targets the document and
        /// carries the artifact's type/step so an `artifacts_source` step
        /// reads THAT artifact rather than its default. `artifactId` is nil
        /// when the scope was chosen by TYPE from the subject menu rather
        /// than by focusing one concrete artifact.
        case artifact(
            documentId: String,
            artifactId: String?,
            displayName: String,
            documentName: String?,
            artifactType: String?,
            stepName: String?
        )
        case documents(ids: [String])
        case detailDocument(id: String, name: String?)
        case nothing

        /// The ids a run is dispatched with. For a marquee this is the SOURCE
        /// document — the run swaps in the materialized region child at
        /// ▶-press; consumers that only count or fall back (chip count, cost
        /// ceiling, "open result") are honest with the source id.
        var documentIds: [String] {
            switch self {
            case .marqueeSelection(let documentId, _, _): return [documentId]
            case .regions(let ids, _): return ids
            case .artifact(let documentId, _, _, _, _, _): return [documentId]
            case .documents(let ids): return ids
            case .detailDocument(let id, _): return [id]
            case .nothing: return []
            }
        }

        /// The bar's filtering target for this scope. Regions and artifacts
        /// are still documents to the engine's `accepted_inputs` vocabulary.
        var target: Target {
            switch self {
            case .marqueeSelection: return .documents(count: 1)
            case .regions(let ids, _): return .documents(count: ids.count)
            case .artifact: return .documents(count: 1)
            case .documents(let ids): return .documents(count: ids.count)
            case .detailDocument: return .documents(count: 1)
            case .nothing: return .nothing
            }
        }
    }

    /// The ladder (Daniel, 2026-08-29): Preview marquee > inspector region
    /// selection > inspector artifact selection > browser selection > detail
    /// document.
    ///
    /// Each upper rung is honored only while it is VISIBLE: region and
    /// artifact selections belong to the inspected document, so a selection
    /// whose document the user has since left drops out rather than silently
    /// scoping a run to something off-screen. A deliberate multi-select in
    /// the browser likewise outranks a lingering single-artifact focus —
    /// selecting five documents is unmistakably the selection you can see.
    static func resolveRunScope(_ snapshot: SelectionSnapshot) -> RunScope {
        if let marqueeDocumentId = snapshot.marqueeDocumentId,
           let rect = snapshot.marqueeRect,
           rect.width > 0, rect.height > 0,
           marqueeDocumentId == snapshot.detailDocumentId {
            return .marqueeSelection(
                documentId: marqueeDocumentId,
                rect: rect,
                documentName: snapshot.marqueeDocumentName ?? snapshot.detailDocumentName
            )
        }
        if !snapshot.regionIds.isEmpty,
           snapshot.regionParentDocumentId == nil
            || snapshot.regionParentDocumentId == snapshot.detailDocumentId {
            return .regions(ids: snapshot.regionIds, parentName: snapshot.regionParentName)
        }
        if let artifactId = snapshot.artifactId,
           let documentId = snapshot.artifactDocumentId,
           documentId == snapshot.detailDocumentId,
           snapshot.browserSelection.count <= 1 || snapshot.artifactPinned {
            return .artifact(
                documentId: documentId,
                artifactId: artifactId,
                displayName: snapshot.artifactDisplayName ?? "Artifact",
                documentName: snapshot.artifactDocumentName,
                artifactType: snapshot.artifactType,
                stepName: snapshot.artifactStepName
            )
        }
        if !snapshot.browserSelection.isEmpty {
            return .documents(ids: snapshot.browserSelection)
        }
        if let detailId = snapshot.detailDocumentId {
            return .detailDocument(id: detailId, name: snapshot.detailDocumentName)
        }
        return .nothing
    }

    /// The chip text for scopes the ladder resolves ABOVE the browser — the
    /// chip must NAME what it resolved to, not merely count it. Returns nil
    /// for document scopes, whose label needs store knowledge (typed nouns)
    /// the caller already owns.
    static func scopeDetail(_ scope: RunScope) -> String? {
        switch scope {
        case .marqueeSelection(_, _, let documentName):
            guard let documentName, !documentName.isEmpty else { return "a selection" }
            return "a selection of \(documentName)"
        case .regions(let ids, let parentName):
            let counted = ids.count == 1 ? "1 region" : "\(ids.count) regions"
            guard let parentName, !parentName.isEmpty else { return counted }
            return "\(counted) of \(parentName)"
        case .artifact(_, _, let displayName, let documentName, _, _):
            guard let documentName, !documentName.isEmpty else { return displayName }
            return "\(displayName) of \(documentName)"
        case .documents, .detailDocument, .nothing:
            return nil
        }
    }

    /// Why the bar is empty, when it is — an empty bar with no explanation
    /// reads as a broken app rather than as "nothing applies here".
    static func emptyReason(
        from workflows: [WorkflowSidebarItem],
        target: Target
    ) -> String? {
        // Two words, not a sentence (Daniel, 2026-08-29: "I don't like that
        // text — maybe just Nothing selected"). The bar's presence already
        // says what it is for; the empty state only needs to say why it is
        // empty.
        switch target {
        case .nothing, .documents(0):
            return "Nothing selected"
        case .text:
            guard families(from: workflows, target: target).isEmpty else { return nil }
            return "Nothing runs on a text selection yet"
        default:
            guard families(from: workflows, target: target).isEmpty else { return nil }
            return "Nothing runs on this selection"
        }
    }
}
