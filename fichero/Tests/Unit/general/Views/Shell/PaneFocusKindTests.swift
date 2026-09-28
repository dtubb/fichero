@testable import Fichero
import Testing

/// Which pane Split / Close / New Tab act on (#4942). What breaks without this: a click in the
/// Segments pane focuses nothing Split can name, so ⊞ splits whatever was focused before.
struct PaneFocusKindTests {
    @Test("every focused pane that is a pane-list leaf names its kind; sidebar and inspector name none")
    func focusNamesItsKind() {
        #expect(PaneFocus.segments.paneKind == .segments)
        #expect(PaneFocus.content.paneKind == .library)
        #expect(PaneFocus.preview.paneKind == .preview)
        #expect(PaneFocus.reading.paneKind == .reading)
        #expect(PaneFocus.chat.paneKind == .chat)
        #expect(PaneFocus.sidebar.paneKind == nil)
        #expect(PaneFocus.inspector.paneKind == nil)
        #expect(PaneFocus.segments.paneTitle == "Segments")
    }
}
