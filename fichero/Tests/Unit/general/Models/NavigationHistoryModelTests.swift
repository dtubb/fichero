@testable import Fichero
import Foundation
import Observation
import Testing

/// Recording a history entry does not re-render the window unless Back or Forward actually
/// becomes possible or impossible (`read.a-click-shows-its-folder-at-once`, #4228).
@MainActor
@Suite("Window history notifies views only when Back or Forward flips")
struct NavigationHistoryModelTests {

    private func entry(_ id: String) -> AppNavigationHistory.Entry {
        AppNavigationHistory.Entry(
            viewType: "library", viewItemId: id, selectedSidebarItemId: id,
            browserSelection: [], detailDocumentId: id
        )
    }

    /// True when reading Back and Forward, then running `change`, notified an observer.
    private func notifies(_ model: NavigationHistoryModel, _ change: () -> Void) -> Bool {
        var fired = false
        withObservationTracking {
            _ = model.canGoBack
            _ = model.canGoForward
        } onChange: {
            fired = true
        }
        change()
        return fired
    }

    @Test("a further entry while Back is already possible notifies nothing")
    func furtherEntryIsSilent() {
        let model = NavigationHistoryModel()
        model.push(entry("a"))
        model.push(entry("b"))
        #expect(model.canGoBack)
        #expect(!notifies(model) { model.push(entry("c")) })
    }

    @Test("the entry that makes Back possible notifies")
    func firstBackNotifies() {
        let model = NavigationHistoryModel()
        model.push(entry("a"))
        #expect(!model.canGoBack)
        #expect(notifies(model) { model.push(entry("b")) })
        #expect(model.canGoBack)
    }

    @Test("Back and Forward walk the same entries as the history")
    func backAndForward() {
        let model = NavigationHistoryModel()
        model.push(entry("a"))
        model.push(entry("b"))
        #expect(model.goBack() == entry("a"))
        #expect(!model.canGoBack)
        #expect(model.canGoForward)
        #expect(model.goForward() == entry("b"))
        #expect(!model.canGoForward)
    }
}
