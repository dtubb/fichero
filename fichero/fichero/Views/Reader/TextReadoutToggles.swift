import SwiftUI

/// The Display menu's page text readouts (#6422, `HoverReadout`): Show Text on Hover and Show Text of the Selection,
/// both off by default, for this Mac.
struct TextReadoutToggles: View {
    @AppStorage(HoverReadout.hoverKey) private var showsOnHover = false
    @AppStorage(HoverReadout.selectionKey) private var showsSelection = false

    var body: some View {
        Toggle("Show Text on Hover", isOn: $showsOnHover)
            .accessibilityIdentifier("previewShowTextOnHover")
        Toggle("Show Text of the Selection", isOn: $showsSelection)
            .accessibilityIdentifier("previewShowTextOfSelection")
    }
}

#Preview("Text readout toggles") {
    Form {
        TextReadoutToggles()
    }
    .formStyle(.grouped)
    .frame(width: 320)
}
