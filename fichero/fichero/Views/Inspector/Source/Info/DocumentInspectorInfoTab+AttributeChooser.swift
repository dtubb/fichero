import SwiftUI

// MARK: - Attribute chooser (#4481)

/// The half #4422 left dangling.
///
/// #4422 defaulted the Attributes strip to showing NOTHING and argued the case
/// well: six of the seven rows that used to appear described the app's own
/// bookkeeping. That default stands and is not touched here. But it shipped
/// without the chooser it promised — *"once there is a UI to choose one"* — and
/// with no chooser, "the default is nothing" means "the answer is always
/// nothing". All ten attributes rendered for nobody, forever.
///
/// This is that chooser. It writes through `InspectorAttributeChoiceStore` into
/// the `chosen:` parameter `visibleAttributes(for:chosen:)` already exposed, so
/// there is ONE visibility mechanism, not a second one beside it — and the
/// choice is per PROTOTYPE, so configuring a diary page configures every diary
/// page rather than that one item.
extension DocumentInspectorInfoTab {

    /// Always rendered, even — especially — when nothing is visible. An empty
    /// strip with no visible way to fill it is what made the feature
    /// unreachable in the first place; the affordance cannot itself be gated on
    /// the thing it configures.
    @ViewBuilder
    var attributesChooser: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Text("Attributes")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)

                Spacer(minLength: 0)

                Menu {
                    Section(chooserScopeLabel) {
                        ForEach(InspectorAttributeVisibility.selectable, id: \.self) { attribute in
                            Toggle(attribute.title, isOn: chooserBinding(for: attribute))
                        }
                    }

                    Divider()

                    Button("Show None") {
                        choiceStore.setChosen([], forPrototype: document.prototypeKey)
                    }
                    if choiceStore.hasChoice(forPrototype: document.prototypeKey) {
                        Button("Use Default") {
                            choiceStore.clearChoice(forPrototype: document.prototypeKey)
                        }
                    }
                } label: {
                    Label("Choose Attributes", systemImage: "line.3.horizontal.decrease.circle")
                        .labelStyle(.iconOnly)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Choose which attributes to show for \(chooserScopeLabel.lowercased())")
            }

            // The reason the strip is blank, said out loud. Without this the
            // inspector looks broken rather than unconfigured — the exact
            // reading that got #4481 filed.
            if visibleAttributes.isEmpty {
                Text("No attributes shown. Choose which to show.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    /// What this choice applies to, named honestly: the prototype, not the
    /// document in front of you.
    var chooserScopeLabel: String {
        guard let key = document.prototypeKey, !key.isEmpty else {
            return "Documents with no class"
        }
        return "Every “\(key)” document"
    }

    /// Toggling writes straight through to the store — no local mirror of the
    /// choice, so two inspectors open on the same prototype cannot disagree.
    func chooserBinding(for attribute: InspectorAttribute) -> Binding<Bool> {
        Binding(
            get: { choiceStore.isChosen(attribute, forPrototype: document.prototypeKey) },
            set: { _ in choiceStore.toggle(attribute, forPrototype: document.prototypeKey) }
        )
    }
}
