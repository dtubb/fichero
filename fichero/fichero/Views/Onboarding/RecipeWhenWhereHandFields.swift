import FicheroAPIClient
import SwiftUI

/// About the material's last three questions (section 7d, #5668): when it was written, where, and in which hand.
/// The hands are the engine's curated list for the script and century, each with when it was written and what it
/// looks like; any other is typed and kept as typed, and "Not sure" is an answer.
struct RecipeWhenWhereHandFields: View {
    @Bindable var store: RecipeSetupStore
    @State private var typedHand = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            LabeledContent("When written") {
                TextField("When written", text: $store.period, prompt: Text("e.g. 16th century, or 1650–1700"))
                    .labelsHidden()
            }
            LabeledContent("Where written") {
                TextField("Where written", text: $store.place, prompt: Text("e.g. Popayán"))
                    .labelsHidden()
            }
            Text("Which hand").font(.headline)
            if !RecipeSetupStore.asksWhichHand(materials: store.materials) {
                Text("Print and typescript have no hand.").font(.caption).foregroundStyle(.secondary)
            } else {
                handChoices
            }
        }
        .task(id: "\(store.scripts.first ?? "")|\(store.period)|\(store.languages.joined(separator: ","))") {
            try? await Task.sleep(for: .milliseconds(300))  // the period as typed: ask once the person pauses
            guard !Task.isCancelled else { return }
            await store.loadHands()
        }
    }

    @ViewBuilder private var handChoices: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("A hand is a style of handwriting, such as Secretary or Kurrent. It helps Fichero find readers made for it. "
                 + "The hands listed are Fichero's own for your script and century; any other you type is kept as you typed it.")
                .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            FlowLayout(spacing: 10) {
                ForEach(store.handOptions, id: \.id) { hand in
                    VStack(alignment: .leading, spacing: 1) {
                        Toggle(hand.title, isOn: Binding(get: { store.hands.contains(hand.id) },
                                                         set: { _ in store.toggle(hand: hand.id) }))
                            .setupCheckbox()
                        // Shown, not hover-only: the century and look are how a person tells the hands apart.
                        Text("\(hand.centuries). \(hand.looks)").font(.caption).foregroundStyle(.secondary)
                            .frame(maxWidth: 220, alignment: .leading)
                    }
                }
                Toggle("Not sure", isOn: Binding(get: { store.hands.contains(RecipeSetupStore.notSureHand) },
                                                 set: { _ in store.toggle(hand: RecipeSetupStore.notSureHand) }))
                    .setupCheckbox()
            }
            // A hand typed is kept as typed (and shown ticked).
            ForEach(store.hands.filter { id in id != RecipeSetupStore.notSureHand
                && !store.handOptions.contains { $0.id == id } }, id: \.self) { typed in
                VStack(alignment: .leading, spacing: 1) {
                    Toggle(typed, isOn: Binding(get: { true }, set: { _ in store.toggle(hand: typed) })).setupCheckbox()
                    Text("Not on Fichero's list; kept as written.").font(.caption).foregroundStyle(.secondary)
                }
            }
            TextField("Another hand", text: $typedHand, prompt: Text("Another hand, as you would name it"))
                .onSubmit {
                    let hand = typedHand.trimmingCharacters(in: .whitespaces)
                    if !hand.isEmpty, !store.hands.contains(hand) { store.toggle(hand: hand) }
                    typedHand = ""
                }
        }
    }
}

#Preview("When, where, which hand") {
    RecipeWhenWhereHandFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520)
}
