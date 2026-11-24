@testable import Fichero
import Testing

/// `models.settings.window-replaces-ai-panes` (#6588): nothing a person could do in Settings' AI panes is lost, because every
/// tab is drawn in exactly one place, and Settings keeps a link to the window.
struct AISettingsPlacementTests {
    @Test("every AI tab is found in the window or kept in Settings, none in both and none in neither")
    func everyTabHasOnePlace() {
        let all = AISettingsTab.allCases.map(\.resolved)
        for tab in Set(all) {
            let places = [AISettingsPlacement.settings, .window].filter { $0.tabs.contains(tab) }
            #expect(places.count == 1, "\(tab) is in \(places)")
        }
    }

    @Test("the window holds the providers, the defaults and the downloads; Settings keeps Advanced only")
    func whatMoved() {
        #expect(AISettingsPlacement.window.tabs == [.defaults, .providers, .downloads])
        #expect(AISettingsPlacement.settings.tabs == [.advanced])
    }

    @Test("the dropped Local LLM tab still resolves to the providers tab, which the window holds")
    func oldSelectionResolves() {
        #expect(AISettingsTab.localLLM.resolved == .providers)
        #expect(AISettingsPlacement.window.tabs.contains(AISettingsTab.localLLM.resolved))
    }

    @Test("the window's sidebar lists the moved panes as one item in its Providers section")
    func windowItem() {
        #expect(ModelsWindowModel.Item.aiSettings.section == .providers)
        #expect(ModelsWindowModel.sidebar([]).first { $0.section == .providers }?.entries.first?.item == .aiSettings)
    }
}
