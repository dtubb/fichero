import SwiftUI

/// Picker for switching between a document's representations (#2264).
///
/// A standard menu `Picker` bound to ``RepresentationStore.selection`` over its
/// `available` kinds. Hidden when only one representation exists (the bare image)
/// — nothing to switch to. Renderable kinds are selectable; any modelled-but-not-
/// yet-wired kind is shown disabled so the menu still advertises what the page
/// *has* without pretending it can display it yet.
struct RepresentationPicker: View {
    @Bindable var store: RepresentationStore

    var body: some View {
        if store.available.count > 1 {
            Picker("Representation", selection: $store.selection) {
                ForEach(store.available) { rep in
                    Label(rep.title, systemImage: rep.systemImage)
                        .tag(rep)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .fixedSize()
            .help("Switch how this page is shown")
        }
    }
}

#Preview("Representation picker") {
    RepresentationPicker(store: RepresentationStore())
        .padding()
}
