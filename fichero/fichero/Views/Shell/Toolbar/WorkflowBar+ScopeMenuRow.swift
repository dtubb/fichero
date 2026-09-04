import SwiftUI

// One row of the subject chip's scope menu. Its own file because the rail is
// at its line budget, and because the row has a real decision in it: a type
// the document has several artifacts of, on a document with too many to list
// flat, is a SUBMENU — the parent still aims by type, each child at one
// concrete pass named by what produced it (Daniel, 2026-09-03).
extension WorkflowBar {

    @ViewBuilder
    func scopeMenuRow(
        _ option: WorkflowBarPolicy.ScopeOption,
        select: @escaping (WorkflowBarPolicy.RunScope?) -> Void
    ) -> some View {
        if option.children.isEmpty {
            Button(option.label) { select(option.scope) }
        } else {
            Menu(option.label) {
                ForEach(option.children) { child in
                    Button(child.label) { select(child.scope) }
                }
            }
        }
    }
}
