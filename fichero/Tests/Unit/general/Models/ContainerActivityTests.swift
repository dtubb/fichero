@testable import Fichero
import Foundation
import Testing

/// #4417: running Catalogue on a PDF's pages spun the PDF, and running it on a
/// folder's contents spun the folder.
///
/// `folderHasBusyChild` promoted any busy child into the parent's own spinner,
/// so parent and child rendered the identical indicator. A container is not
/// being processed — its contents are — and the conflation costs the one thing
/// the parent could usefully say: how far along its children are.
///
/// The aggregation was right and is kept. These tests pin the rendering split.
struct ContainerActivityTests {

    // MARK: - The defect, stated directly

    /// Daniel's case: four pages processing under one PDF. The PDF must not
    /// borrow the leaf spinner.
    @Test("a container whose children are working does not show the leaf spinner")
    func containerWithBusyChildrenDoesNotSpin() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: false, busyChildren: 4, totalChildren: 4
        )

        #expect(activity == .children(busy: 4, total: 4))
        #expect(!activity.showsLeafSpinner, "this is the indicator that was wrong")
        #expect(activity.isActive, "it still indicates — just not as a leaf")
    }

    /// The ambiguous case, and the reason this is a policy rather than a flag.
    /// The engine marks a parent `.processing` while its children work, and the
    /// client cannot tell that from the parent being a subject. Busy children
    /// win, because an aggregate says strictly more than a second spinner.
    @Test("busy children win even when the container is marked processing")
    func busyChildrenWinOverASelfProcessingFlag() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: true, busyChildren: 2, totalChildren: 4
        )

        #expect(!activity.showsLeafSpinner)
        #expect(activity == .children(busy: 2, total: 4))
    }

    /// The rule generalised: no container with a busy child ever renders the
    /// leaf spinner, whatever else is true of it.
    @Test("no container with a working child ever shows the leaf spinner")
    func noContainerWithWorkingChildrenSpins() {
        for selfProcessing in [true, false] {
            for busy in 1...5 {
                for total in busy...8 {
                    let activity = ContainerActivity.resolve(
                        isSelfProcessing: selfProcessing,
                        busyChildren: busy,
                        totalChildren: total
                    )
                    #expect(
                        !activity.showsLeafSpinner,
                        Comment(rawValue: "self=\(selfProcessing) busy=\(busy) total=\(total)"))
                }
            }
        }
    }

    // MARK: - Work ON the container is still shown

    /// "When a folder itself is the subject of work … then the folder
    /// legitimately shows its own activity." The folder-level catalogue stage
    /// (#4404, #4414) writes to the folder document with no child working.
    @Test("a container that is itself the subject shows its own state")
    func containerAsSubjectShowsOwnState() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: true, busyChildren: 0, totalChildren: 6
        )

        #expect(activity == .own)
        #expect(activity.showsLeafSpinner)
        #expect(activity.summary == "Processing")
    }

    /// The two states must stay distinguishable — the multi-level cataloguing
    /// model (#4399) depends on being able to tell them apart.
    @Test("work on the container and work on its contents are different states")
    func containerAndContentsAreDistinctStates() {
        let own = ContainerActivity.resolve(
            isSelfProcessing: true, busyChildren: 0, totalChildren: 3
        )
        let contents = ContainerActivity.resolve(
            isSelfProcessing: false, busyChildren: 1, totalChildren: 3
        )
        #expect(own != contents)
        #expect(own.showsLeafSpinner != contents.showsLeafSpinner)
        #expect(own.progress == nil)
        #expect(contents.progress != nil)
    }

    // MARK: - It clears immediately

    /// "A container whose children have all finished stops indicating
    /// immediately, without waiting for anything else."
    @Test("the aggregate clears the moment the last child finishes")
    func aggregateClearsWhenTheLastChildFinishes() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: false, busyChildren: 0, totalChildren: 4
        )
        #expect(activity == .idle)
        #expect(!activity.isActive)
        #expect(activity.progress == nil)
        #expect(activity.summary == nil)
    }

    @Test("a container with no children and nothing running is idle")
    func emptyContainerIsIdle() {
        #expect(
            ContainerActivity.resolve(isSelfProcessing: false, busyChildren: 0, totalChildren: 0)
                == .idle
        )
    }

    // MARK: - The aggregate says something useful

    /// The point of keeping the numbers: the parent becomes the one row that
    /// can summarise, instead of a redundant spinner.
    @Test("progress reports how many children are done")
    func progressReportsChildrenDone() {
        #expect(ContainerActivity.children(busy: 4, total: 4).progress == 0)
        #expect(ContainerActivity.children(busy: 1, total: 4).progress == 0.75)
        #expect(ContainerActivity.children(busy: 2, total: 4).progress == 0.5)
    }

    @Test("the summary names the contents, never the container itself")
    func summaryNamesTheContents() {
        let summary = ContainerActivity.children(busy: 1, total: 4).summary
        #expect(summary == "Processing contents — 3 of 4 done")
        #expect(summary?.contains("contents") == true, "it must not read as the container working")
    }

    /// A malformed count must not produce a nonsensical ratio — a progress bar
    /// outside 0…1 renders as a visual glitch, which reads as a bug in the run.
    @Test("progress stays within 0…1 whatever the counts")
    func progressStaysInRange() {
        for busy in 0...10 {
            for total in 0...10 {
                let activity = ContainerActivity.resolve(
                    isSelfProcessing: false, busyChildren: busy, totalChildren: total
                )
                if let progress = activity.progress {
                    #expect(progress >= 0 && progress <= 1, Comment(rawValue: "\(busy)/\(total)"))
                }
            }
        }
    }

    /// More busy children than the client knows about is possible while a
    /// container's cache is still filling. The total must absorb that rather
    /// than reporting "5 of 3".
    @Test("a total smaller than the busy count is corrected, not rendered")
    func inconsistentCountsAreCorrected() {
        let activity = ContainerActivity.resolve(
            isSelfProcessing: false, busyChildren: 5, totalChildren: 3
        )
        #expect(activity == .children(busy: 5, total: 5))
        #expect(activity.progress == 0)
    }

    // MARK: - Structural: the row no longer collapses child into parent

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// The row's spinner is now the policy's decision, and the old
    /// "any busy child ⇒ parent spins" branch is gone.
    @Test("the sidebar row decides through ContainerActivity")
    func rowDecidesThroughTheePolicy() throws {
        let row = try Self.codeOnly(Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift"))

        #expect(row.contains("ContainerActivity.resolve("))
        #expect(row.contains("containerActivity.showsLeafSpinner"))
        // The old shape: a folder-only aggregate returning true into the spinner.
        #expect(!row.contains("doc.docType == .folder, store.folderHasBusyChild"))
    }

    /// The aggregate has to render differently from the leaf, or the fix is
    /// only internal — a determinate ring against the indeterminate spinner.
    @Test("the container renders a determinate indicator, not the leaf spinner")
    func containerRendersADeterminateIndicator() throws {
        let label = try Self.codeOnly(
            Self.appSource("Views/Sidebar/ItemRow/SidebarItemRow+Label.swift"))
        #expect(label.contains("containerActivity.progress"))
        #expect(label.contains("ProgressView(value: progress)"))
    }
}
