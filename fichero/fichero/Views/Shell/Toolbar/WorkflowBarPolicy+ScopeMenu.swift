import Foundation

// The subject token's MENU (Daniel, 2026-08-29 evening, from the live
// sentence bar): the chip that NAMES the scope is clickable to CHANGE it —
// switch from the selected page to one of its artifacts, or back to the
// browser selection. Choosing writes an explicit override that outranks the
// automatic ladder until cleared; "Automatic" restores the ladder. All pure
// policy here — the token itself lives in `WorkflowBar+ChainRail`.
extension WorkflowBarPolicy {

    /// One entry in the subject chip's menu.
    struct ScopeOption: Identifiable, Equatable {
        let id: String
        let label: String
        /// nil = Automatic — clear the override and follow the ladder.
        let scope: RunScope?
        /// Rows nested under this one. Non-empty only when a document has so
        /// many artifacts that a flat list would be a wall of text; the row
        /// then becomes a submenu whose own scope still aims by TYPE.
        var children: [ScopeOption] = []
    }

    /// One artifact of the inspected document, reduced to what the menu needs
    /// to NAME it and tell it apart from its siblings. A plain value so the
    /// menu stays a pure function — the host lifts these off whatever store
    /// already holds the document's artifacts.
    struct ArtifactChoice: Equatable, Identifiable {
        let id: String
        let artifactType: String
        /// The type's human name as the producing surface knows it; nil falls
        /// back to `artifactTypeDisplayName`.
        var displayName: String?
        var provider: String?
        var model: String?
        var stepName: String?
        var createdAt: Date?
    }

    /// Resolution with an explicit override. The override wins while the
    /// thing it names is still on screen; a stale override (its selection
    /// gone, its document left) silently yields back to the ladder rather
    /// than scoping a run to something invisible.
    static func resolveRunScope(
        _ snapshot: SelectionSnapshot,
        override chosen: RunScope?
    ) -> RunScope {
        if let chosen, overrideStillVisible(chosen, in: snapshot) {
            return chosen
        }
        return resolveRunScope(snapshot)
    }

    /// Per-rung visibility for an override — each case is checked against
    /// the live seam it was minted from.
    static func overrideStillVisible(
        _ chosen: RunScope,
        in snapshot: SelectionSnapshot
    ) -> Bool {
        switch chosen {
        case .marqueeSelection(let documentId, let rect, _):
            return snapshot.marqueeDocumentId == documentId && snapshot.marqueeRect == rect
        case .regions(let ids, _):
            return snapshot.regionIds == ids
        case .artifact(let documentId, let artifactId, _, _, _, _):
            if let artifactId {
                return snapshot.artifactId == artifactId
                    && snapshot.artifactDocumentId == documentId
            }
            // Chosen by TYPE: valid while its document is still the one
            // being inspected.
            return snapshot.detailDocumentId == documentId
        case .documents(let ids):
            return snapshot.browserSelection == ids
        case .detailDocument(let id, _):
            return snapshot.detailDocumentId == id
        case .nothing:
            return false
        }
    }

    /// The artifact types the menu offers explicitly — the `artifacts_source`
    /// vocabulary (transcription, transcription_review, translation).
    static let artifactScopeTypes = ["transcription", "transcription_review", "translation"]

    /// "transcription_review" → "Transcription Review".
    static func artifactTypeDisplayName(_ type: String) -> String {
        switch type {
        case "transcription": return "Transcription"
        case "transcription_review": return "Transcription Review"
        case "translation": return "Translation"
        default:
            return type.split(separator: "_").map(\.capitalized).joined(separator: " ")
        }
    }

    /// The subject menu: Automatic first, then every rung the ladder could
    /// resolve RIGHT NOW, then the inspected document's artifacts by type so
    /// a run can be aimed at an artifact explicitly. Every option is labeled
    /// with the same naming the chip itself uses.
    static func scopeMenuOptions(
        from snapshot: SelectionSnapshot,
        artifactTypes: [String] = artifactScopeTypes,
        now: Date = Date()
    ) -> [ScopeOption] {
        var options = [ScopeOption(id: "automatic", label: "Automatic", scope: nil)]
        func add(_ id: String, _ scope: RunScope, label: String? = nil) {
            guard let text = label ?? scopeDetail(scope) ?? targetLabel(scope.target) else { return }
            options.append(ScopeOption(id: id, label: text, scope: scope))
        }

        if let marqueeId = snapshot.marqueeDocumentId, let rect = snapshot.marqueeRect,
           rect.width > 0, rect.height > 0, marqueeId == snapshot.detailDocumentId {
            add("marquee", .marqueeSelection(
                documentId: marqueeId, rect: rect,
                documentName: snapshot.marqueeDocumentName ?? snapshot.detailDocumentName
            ))
        }
        if !snapshot.regionIds.isEmpty,
           snapshot.regionParentDocumentId == nil
            || snapshot.regionParentDocumentId == snapshot.detailDocumentId {
            add("regions", .regions(
                ids: snapshot.regionIds, parentName: snapshot.regionParentName
            ))
        }
        // The FOCUSED artifact — offered without the ladder's multi-select
        // guard, because picking it from the menu IS the deliberate choice
        // that guard exists to protect.
        if let artifactId = snapshot.artifactId,
           let documentId = snapshot.artifactDocumentId,
           documentId == snapshot.detailDocumentId {
            // Named with the same provenance as its siblings when the host
            // knows it — "the focused one" is only useful if you can see
            // WHICH one it is.
            let known = snapshot.detailArtifacts.first { $0.id == artifactId }
            let names = artifactLabels(snapshot.detailArtifacts, now: now)
            add("artifact", .artifact(
                documentId: documentId, artifactId: artifactId,
                displayName: snapshot.artifactDisplayName ?? "Artifact",
                documentName: snapshot.artifactDocumentName,
                artifactType: snapshot.artifactType,
                stepName: snapshot.artifactStepName
            ), label: known.flatMap { names[$0.id] })
        }
        if !snapshot.browserSelection.isEmpty {
            add("documents", .documents(ids: snapshot.browserSelection))
        }
        if let detailId = snapshot.detailDocumentId,
           snapshot.browserSelection != [detailId] {
            add("detail", .detailDocument(id: detailId, name: snapshot.detailDocumentName),
                label: snapshot.detailDocumentName ?? "This document")
        }
        if let detailId = snapshot.detailDocumentId {
            options.append(contentsOf: artifactOptions(
                documentId: detailId, snapshot: snapshot,
                artifactTypes: artifactTypes, now: now
            ))
        }
        return options
    }

    /// Beyond this many artifact rows the flat list stops being a menu and
    /// starts being a wall; types with several artifacts collapse to
    /// submenus. Deliberately generous — a submenu costs a second gesture,
    /// so it is the exception, not the shape.
    static let artifactMenuFlatLimit = 8

    /// The artifact rows: the inspected document's ACTUAL artifacts, each
    /// named with the provenance that tells two passes apart, plus a bare
    /// by-TYPE row for every type it has none of yet (`artifacts_source`
    /// resolves at run time, so aiming at a type a future step will write is
    /// still a legitimate choice).
    static func artifactOptions(
        documentId: String,
        snapshot: SelectionSnapshot,
        artifactTypes: [String] = artifactScopeTypes,
        now: Date = Date(),
        labels: [String: String]? = nil
    ) -> [ScopeOption] {
        let names = labels ?? artifactLabels(snapshot.detailArtifacts, now: now)
        let grouped = Dictionary(grouping: snapshot.detailArtifacts, by: \.artifactType)
        var rowsByType: [(type: String, rows: [ScopeOption])] = []
        for type in orderedTypes(artifactTypes, present: snapshot.detailArtifacts) {
            let matches = (grouped[type] ?? []).sorted {
                ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast)
            }
            guard !matches.isEmpty else {
                rowsByType.append((type, [typeOption(type, documentId: documentId, snapshot: snapshot)]))
                continue
            }
            // The focused artifact already has its own rung above; repeating
            // it here would be the same row twice under the same label.
            let rows = matches
                .filter { $0.id != focusedArtifactId(in: snapshot) }
                .map {
                    artifactOption(
                        $0, documentId: documentId, snapshot: snapshot,
                        label: names[$0.id] ?? artifactChoiceLabel($0, now: now)
                    )
                }
            guard !rows.isEmpty else { continue }
            rowsByType.append((type, rows))
        }
        let flat = rowsByType.flatMap(\.rows)
        guard flat.count > artifactMenuFlatLimit else { return flat }
        return rowsByType.map { entry -> ScopeOption in
            guard entry.rows.count > 1 else { return entry.rows[0] }
            var parent = typeOption(entry.type, documentId: documentId, snapshot: snapshot)
            parent.children = entry.rows
            return parent
        }
    }

    /// The artifact the ladder already offers as its own rung, if any — the
    /// one row the by-type list must not repeat.
    static func focusedArtifactId(in snapshot: SelectionSnapshot) -> String? {
        guard let artifactId = snapshot.artifactId,
              let documentId = snapshot.artifactDocumentId,
              documentId == snapshot.detailDocumentId else { return nil }
        return artifactId
    }

    /// The canonical `artifacts_source` types first — the pipeline's own order
    /// — then any other type the document actually carries, newest type
    /// first, so a `regions` pass nobody enumerated still gets a row.
    static func orderedTypes(_ known: [String], present: [ArtifactChoice]) -> [String] {
        var ordered = known
        let extras = present
            .sorted { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
        for choice in extras where !ordered.contains(choice.artifactType) {
            ordered.append(choice.artifactType)
        }
        return ordered
    }

    /// Aim by TYPE — no concrete artifact, resolved when the run starts.
    static func typeOption(
        _ type: String, documentId: String, snapshot: SelectionSnapshot
    ) -> ScopeOption {
        let scope = RunScope.artifact(
            documentId: documentId, artifactId: nil,
            displayName: artifactTypeDisplayName(type),
            documentName: snapshot.detailDocumentName,
            artifactType: type, stepName: nil
        )
        return ScopeOption(
            id: "artifact-type-\(type)",
            label: scopeDetail(scope) ?? artifactTypeDisplayName(type),
            scope: scope
        )
    }

    /// Aim at ONE artifact, named by what produced it and when.
    static func artifactOption(
        _ choice: ArtifactChoice,
        documentId: String,
        snapshot: SelectionSnapshot,
        label: String
    ) -> ScopeOption {
        ScopeOption(
            id: "artifact-\(choice.id)",
            label: label,
            scope: .artifact(
                documentId: documentId, artifactId: choice.id,
                displayName: choice.displayName ?? artifactTypeDisplayName(choice.artifactType),
                documentName: snapshot.detailDocumentName,
                artifactType: choice.artifactType, stepName: choice.stepName
            )
        )
    }

    /// Every artifact's menu label, made UNIQUE. Cached re-runs mint
    /// duplicates — Daniel's engine log, 2026-09-03: three Detect Regions
    /// artifacts for one page inside four minutes, same model, same minute —
    /// and two rows that read identically are two rows you cannot choose
    /// between. Only the colliding ones grow a tail, so the common case stays
    /// clean.
    static func artifactLabels(
        _ choices: [ArtifactChoice], now: Date = Date()
    ) -> [String: String] {
        let base = choices.map { ($0.id, artifactChoiceLabel($0, now: now)) }
        var counts: [String: Int] = [:]
        for entry in base { counts[entry.1, default: 0] += 1 }
        var result: [String: String] = [:]
        for entry in base {
            result[entry.0] = counts[entry.1, default: 0] > 1
                ? "\(entry.1) · \(shortId(entry.0))"
                : entry.1
        }
        return result
    }

    /// Enough of an artifact id to separate two otherwise identical rows, and
    /// no more — a menu is not the place to print a UUID.
    static func shortId(_ id: String) -> String {
        String(id.replacingOccurrences(of: "-", with: "").prefix(6))
    }

    /// "Regions — Apple Vision, 2:14 PM" (Daniel, 2026-09-03). The type says
    /// WHAT, the agent says WHO, the time says WHICH PASS — the three facts
    /// that make one of five transcriptions pickable. An artifact with no
    /// recorded producer says so rather than borrowing a plausible name.
    static func artifactChoiceLabel(_ choice: ArtifactChoice, now: Date = Date()) -> String {
        let name = normalized(choice.displayName) ?? artifactTypeDisplayName(choice.artifactType)
        var parts = [agentName(model: choice.model, provider: choice.provider)]
        if let createdAt = choice.createdAt {
            parts.append(provenanceTime(createdAt, now: now))
        }
        return "\(name) — \(parts.joined(separator: ", "))"
    }

    /// Who produced it: the model where one was recorded (shortened the same
    /// way the model chip shortens it), else the provider under its human
    /// name, else an honest admission.
    static func agentName(model: String?, provider: String?) -> String {
        if let model = normalized(model) { return ModelChipToolbarItem.shorten(model) }
        if let provider = normalized(provider) { return providerDisplayName(provider) }
        return "unknown model"
    }

    /// Engine provider slugs under the names a person would use for them.
    /// Unknown slugs pass through unchanged — a provider the client has never
    /// heard of is still better named by its own id than by a guess.
    private static let providerDisplayNames: [String: String] = [
        "apple": "Apple Vision",
        "apple_vision": "Apple Vision",
        "apple_intelligence": "Apple Intelligence",
        "pymupdf": "PDF text layer",
        "pdf_text": "PDF text layer",
        "manifest-importer": "manifest import",
        "rule": "rule",
        "manual": "manual",
        "local": "local model"
    ]

    static func providerDisplayName(_ provider: String) -> String {
        providerDisplayNames[provider.lowercased()] ?? provider
    }

    /// Short enough for a menu row, precise enough to separate two passes:
    /// the clock for today, the day for this year, the year beyond that.
    static func provenanceTime(
        _ date: Date, now: Date = Date(), calendar: Calendar = .current
    ) -> String {
        let formatter = DateFormatter()
        formatter.locale = .autoupdatingCurrent
        if calendar.isDate(date, inSameDayAs: now) {
            formatter.dateStyle = .none
            formatter.timeStyle = .short
        } else if calendar.component(.year, from: date)
                    == calendar.component(.year, from: now) {
            formatter.setLocalizedDateFormatFromTemplate("MMMd")
        } else {
            formatter.setLocalizedDateFormatFromTemplate("MMMdyyyy")
        }
        return formatter.string(from: date)
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
