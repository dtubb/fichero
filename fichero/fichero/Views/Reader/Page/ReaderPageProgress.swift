import Foundation

/// Per-page work-in-progress and live-content logic for the reader (#4357).
///
/// Pure over the documents the store already holds, so the two rules that make
/// the reader honest are unit-testable without a WKWebView:
/// 1. **Only pages in the run's scope show progress** — the busy set comes from
///    the EXISTING source (`DocumentStore.isDocumentBusy`, i.e. #4295's run
///    target record), never from a second notion of "working".
/// 2. **Patch, never reload** — the reader is updated by sending only the pages
///    whose content actually changed, so a live run never re-renders the
///    WKWebView (which would lose scroll position and flash).
enum ReaderPageProgress {
    /// Page numbers whose page document a run is currently writing.
    ///
    /// A page child with no `sequence` has no position to highlight, so it is
    /// skipped rather than guessed at — showing a spinner on the wrong page is
    /// worse than showing none.
    static func busyPageNumbers(
        children: [Document],
        isBusy: (String) -> Bool
    ) -> Set<Int> {
        var numbers: Set<Int> = []
        for child in children where child.docType == .page {
            guard let sequence = child.sequence, isBusy(child.id) else { continue }
            numbers.insert(sequence)
        }
        return numbers
    }

    /// Live `page number -> content` for the pages the reader may need patched:
    /// the pages a run is (or was) writing this session. Restricting it to those
    /// keeps a 500-page document from shipping its whole transcript on every
    /// change-stream event.
    static func livePageContent(
        children: [Document],
        pages: Set<Int>
    ) -> [Int: String] {
        var content: [Int: String] = [:]
        for child in children where child.docType == .page {
            guard let sequence = child.sequence, pages.contains(sequence) else { continue }
            content[sequence] = child.pageContent ?? ""
        }
        return content
    }

    /// The subset of `latest` that differs from what was last sent to the web
    /// view. An unchanged page produces no JS call at all.
    static func changedPatches(
        latest: [Int: String],
        lastSent: [Int: String]
    ) -> [Int: String] {
        latest.filter { number, text in lastSent[number] != text }
    }

    /// The pages the reader keeps patching for the rest of the session: every
    /// page a run has touched since load. A page must stay in this set after its
    /// run reaches a terminal state, or the final write (the one that actually
    /// lands the transcription) would never reach the reader.
    static func trackedPages(
        alreadyTracked: Set<Int>,
        busy: Set<Int>
    ) -> Set<Int> {
        alreadyTracked.union(busy)
    }
}
