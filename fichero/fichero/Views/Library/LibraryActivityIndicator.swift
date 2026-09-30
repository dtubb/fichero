import SwiftUI

/// The library's activity indicator, resolved by the SAME rule as the sidebar's
/// (#4417).
///
/// #4417 was fixed in the sidebar only. `ContainerActivity` went in,
/// `folderHasBusyChild` stopped promoting a busy child into its parent's own
/// spinner, and a container started showing a determinate ring — "Processing
/// contents — 3 of 4 done" — instead of pretending to be the subject of the
/// work. The library list and table were never changed: they render on
/// `document.status == .processing` alone and have no idea their children
/// exist.
///
/// So the same folder, at the same moment, read as two different things
/// depending on which pane you looked at. The sidebar said "your contents are
/// 3 of 4 done"; the list said "I am processing". One of those is a claim about
/// the folder itself, and it is the false one — which is the whole argument of
/// the issue, applied to only one of the two surfaces that make it.
///
/// This is the sidebar-versus-library disagreement class: not a missed
/// instance, but a fix that reached the surface someone was looking at. The
/// rule now lives in one place and both panes ask it the same question.
struct LibraryActivityIndicator: View {
    let document: Document
    /// Compact surfaces (the list's 10pt status column) have no room for a
    /// ring's tooltip target; the table's Progress column does.
    var showsSummaryText = false

    @Environment(DocumentStore.self) private var documentStore

    private var activity: ContainerActivity { Self.activity(for: document, in: documentStore) }

    var body: some View {
        switch activity {
        case .own:
            // The leaf treatment, unchanged — this document really is the
            // subject of the work.
            ProgressView()
                .scaleEffect(showsSummaryText ? 0.6 : 0.55)
                .frame(width: showsSummaryText ? nil : 10, height: showsSummaryText ? nil : 10)
        case .children:
            aggregate
        case .idle:
            EmptyView()
        }
    }

    /// Deliberately the same determinate ring the sidebar uses, not a second
    /// design: a user who learns what the ring means in one pane must not have
    /// to relearn it in the other.
    @ViewBuilder
    private var aggregate: some View {
        let summary = activity.summary ?? ""
        HStack(spacing: 6) {
            ProgressView(value: activity.progress ?? 0)
                .progressViewStyle(.circular)
                .controlSize(.small)
                .scaleEffect(showsSummaryText ? 0.7 : 0.55)
                .frame(width: showsSummaryText ? nil : 10, height: showsSummaryText ? nil : 10)
                .tint(.secondary)
            if showsSummaryText {
                Text(summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .help(summary)
        .accessibilityLabel(summary)
    }

    /// The ONE resolution of what, if anything, this document shows.
    ///
    /// ## The leaf fast path (2026-09-01 — "scrolling list view feels slow")
    ///
    /// `childActivityCounts` is memoised per (revision, overrides) — but the
    /// memo is keyed by PARENT ID, so the first render pass after any store
    /// revision is one cache MISS per row, and each miss scans
    /// `currentDocuments` looking for children. Over a folder of N rows that is
    /// O(N²) on the main thread, and `revision` bumps on every refresh and every
    /// live-delivery splice — which is exactly while the user is scrolling.
    /// #4417's own note records the same scan costing 231ms before it was
    /// memoised; the memo removed the repeat cost, not the first-pass cost.
    ///
    /// A document that cannot HOLD children cannot have a busy one. For those
    /// rows `resolve` can only ever answer from `isSelfProcessing`, so asking
    /// the store is asking a question whose answer is already known. The
    /// predicate is the app's own `isNavigableContainer` (folder or PDF) — the
    /// same answer navigation and drop targeting use — so a surface can never
    /// disagree with itself about what holds things.
    ///
    /// The saving is not only the scan. `MailStyleRow` reads `documentStore`
    /// from the environment, and it is `@Observable`: touching
    /// `childActivityCounts` registers that row as a DEPENDENT of the store, so
    /// every store change re-ran every visible row's `body` regardless of the
    /// row's own `.equatable()` identity. A leaf row now reads no store
    /// property at all, so store churn no longer invalidates it.
    static func activity(for document: Document, in store: DocumentStore) -> ContainerActivity {
        guard document.isNavigableContainer else {
            // Still through the ONE resolver — with the counts a leaf provably
            // has — rather than re-deriving the rule here. A second copy of
            // "processing means spin" in this file is exactly the drift
            // `LibraryActivityAgreementTests` exists to catch, and skipping a
            // lookup is no reason to earn it.
            return ContainerActivity.resolve(
                isSelfProcessing: document.status == .processing,
                busyChildren: 0,
                totalChildren: 0
            )
        }
        let counts = store.childActivityCounts(of: document.id)
        return ContainerActivity.resolve(
            isSelfProcessing: document.status == .processing,
            busyChildren: counts.busy,
            totalChildren: counts.total
        )
    }
}

/// What a library row says about its item's state, in the List and in the Table's
/// Name cell (#5295, #5296): one rule, one component for both.
///
/// Nothing at rest. A finished item draws no mark: a green dot on every row said
/// nothing a row needs to say. A mark appears only while the item is queued or
/// being worked on, and stays if the work failed.
struct LibraryRowStatusMark: View {
    /// What a row that is not being worked on shows.
    enum Resting: Equatable {
        case nothing, queued, failed
    }

    let document: Document

    @Environment(DocumentStore.self) private var documentStore

    var body: some View {
        if LibraryActivityIndicator.activity(for: document, in: documentStore) != .idle {
            LibraryActivityIndicator(document: document)
        } else {
            switch Self.resting(for: document.status, isFolder: document.docType == .folder) {
            case .nothing:
                EmptyView()
            case .queued:
                Image(systemName: "clock")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .help("Queued")
                    .accessibilityLabel("Queued")
            case .failed:
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .help("Failed")
                    .accessibilityLabel("Failed")
            }
        }
    }

    /// `.processing` never reaches this: `ContainerActivity` has already taken
    /// it (the spinner, or the contents ring), so it has no resting mark.
    ///
    /// A folder has no resting mark: its own record is never run, so it sits at `pending` for good,
    /// and a clock beside every folder said "queued" about nothing (2026-09-30). Work on its contents
    /// shows through `ContainerActivity` instead.
    static func resting(for status: Status, isFolder: Bool = false) -> Resting {
        if isFolder { return .nothing }
        return switch status {
        case .completed, .processing: .nothing
        case .pending: .queued
        case .failed: .failed
        }
    }
}
