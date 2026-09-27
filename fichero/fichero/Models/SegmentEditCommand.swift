import Foundation

/// The editor's attribute verbs as a PLAN, before anything is sent (#4941):
/// `source.editor.set-kind`, `set-direction`, `set-language-script`.
///
/// A pure decision over a `SegmentSelection`, the same shape as `RegionEditTarget`:
/// the rules live where a test can reach them instead of inside a view method, and
/// the view's only job is to send what the plan says.
///
/// ONE ENGINE ACTION PER SEGMENT, AND THAT IS A FINDING RATHER THAN A CHOICE. The
/// engine's `segment.update` takes ONE `segment_id` and one `expected_version`, and the
/// only bulk segment route (`POST /api/segments/bulk`) CREATES. So "set these five lines
/// to `heading`" is five audited actions today — and five undo steps, which means ⌘Z
/// after a selection-wide edit reverts one line at a time. That is wrong for the person
/// and the fix is on the engine (a `segment.update_many` taking a version per id, one
/// audit row, one inverse), not here. Recorded in the spec rather than papered over by
/// grouping the requests client-side, which would make the undo story lie.
enum SegmentEditCommand {
    /// The attribute a verb changes. Values are sent as given: the ENGINE owns the
    /// vocabulary (`assert_known_direction`, `assert_known_script`, BCP 47 for
    /// language) and refuses what it does not know with a sentence naming the list.
    /// Checking here too would be a second copy of that vocabulary, and the second copy
    /// is the one that drifts.
    enum Attribute: Equatable {
        case kind(String)
        case direction(String)
        case language(String)
        case script(String)
        case furniture(Bool)

        /// The `segment.update` field this attribute sets.
        var field: String {
            switch self {
            case .kind: "kind"
            case .direction: "direction"
            case .language: "language"
            case .script: "script"
            case .furniture: "is_furniture"
            }
        }
    }

    /// One `PUT /api/segments/{id}` the plan asks for.
    struct Update: Equatable {
        let segmentId: String
        let expectedVersion: Int
        let attribute: Attribute
    }

    /// Why nothing is sent. Each case is a refusal a person should be told about,
    /// not a silent no-op.
    enum Refusal: Error, Equatable {
        /// Nothing is selected. The refusal every editor verb has and that is easiest
        /// to drop, because "do nothing" looks like correct behaviour until somebody
        /// asks why their click had no effect.
        case nothingSelected
        /// The selection is on another page from the one on screen — the shape a stale
        /// selection takes after the person navigated away.
        case selectionIsOnAnotherPage
        /// A selected segment has no known version, so an `expected_version` would be
        /// invented. All or nothing, as with delete: half the lines changed and half
        /// refused is worse than neither.
        case versionsUnknown
    }

    /// The updates to send, or the refusal.
    ///
    /// `shownDocumentId` is the page on screen. Required rather than read from the
    /// selection, because the check that matters is that the two AGREE — a selection
    /// cannot vouch for itself.
    ///
    /// `@MainActor` because `SegmentSelection` is: reading it from anywhere else would
    /// be a data race on the thing every view writes to.
    @MainActor
    static func plan(
        _ attribute: Attribute,
        for selection: SegmentSelection,
        shownDocumentId: String?
    ) -> Result<[Update], Refusal> {
        guard !selection.isEmpty else { return .failure(.nothingSelected) }
        guard let shown = shownDocumentId, selection.documentId == shown else {
            return .failure(.selectionIsOnAnotherPage)
        }
        guard let versions = selection.expectedVersions else {
            return .failure(.versionsUnknown)
        }
        // Pick order, kept: the engine does not care, and a person reading the audit log
        // sees the lines in the order they chose them.
        let updates = selection.segmentIds.compactMap { id -> Update? in
            guard let version = versions[id] else { return nil }
            return Update(segmentId: id, expectedVersion: version, attribute: attribute)
        }
        return .success(updates)
    }
}
