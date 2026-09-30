import SwiftUI

// MARK: - Options kept per pane (#5280)
//
// Two Library panes used to share the Metadata menu, the content lines and the Show kind: one
// app-wide key each, so a change in one pane changed the other. Each pane now reads its own entry
// (`PaneScopedOption`), falling back to the shared value; a change writes both.

extension LibraryView {
    var rowAttributesRaw: String {
        get { PaneScopedOption.value(rowAttributesByPaneJSON, pane: paneLeafId, shared: rowAttributesSharedRaw) }
        nonmutating set {
            rowAttributesByPaneJSON = PaneScopedOption.setting(newValue, in: rowAttributesByPaneJSON, pane: paneLeafId)
            rowAttributesSharedRaw = newValue
        }
    }

    var rowContentLinesRaw: Int {
        get { PaneScopedOption.value(rowContentLinesByPaneJSON, pane: paneLeafId, shared: rowContentLinesSharedRaw) }
        nonmutating set {
            rowContentLinesByPaneJSON = PaneScopedOption.setting(newValue, in: rowContentLinesByPaneJSON, pane: paneLeafId)
            rowContentLinesSharedRaw = newValue
        }
    }

    var showKindRaw: String {
        get { PaneScopedOption.value(showKindByPaneJSON, pane: paneLeafId, shared: showKindSharedRaw) }
        nonmutating set {
            showKindByPaneJSON = PaneScopedOption.setting(newValue, in: showKindByPaneJSON, pane: paneLeafId)
            showKindSharedRaw = newValue
        }
    }

    var rowAttributesBinding: Binding<String> {
        Binding(get: { rowAttributesRaw }, set: { rowAttributesRaw = $0 })
    }

    var rowContentLinesBinding: Binding<Int> {
        Binding(get: { rowContentLinesRaw }, set: { rowContentLinesRaw = $0 })
    }
}
