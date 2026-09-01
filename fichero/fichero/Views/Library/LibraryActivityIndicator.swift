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

    /// The ONE resolution both the view and `isIdle` read, so the indicator
    /// and the call site that decides whether to mount it cannot disagree.
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

    /// Whether this document contributes any indicator at all, so a call site
    /// can keep rendering its own idle treatment (a status dot, a checkmark)
    /// without this view having to know about it.
    static func isIdle(_ document: Document, in store: DocumentStore) -> Bool {
        activity(for: document, in: store) == .idle
    }
}
