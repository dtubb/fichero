import FicheroAPIClient
import SwiftUI

extension RecipeSetupStore {
    /// The answer "Not sure" to Which hand (`HandList.not_sure`).
    static let notSureHand = "not-sure"

    /// The curated hands for the first script chosen and the period, as the engine keeps them; re-asked when either
    /// changes (`source.onboard.material.which-hand`).
    func loadHands() async {
        let script = scripts.first ?? "Latn"
        let when = period.trimmingCharacters(in: .whitespaces)
        do {
            if case .ok(let success) = try await client.api.listHandsApiRecipesHandsGet(
                query: .init(script: script, period: when.isEmpty ? nil : when)
            ) {
                handOptions = try success.body.json.items
            }
        } catch {
            if error.isCancellationError { return }
            handOptions = []
        }
    }

    /// Tick or untick a hand. "Not sure" stands alone: it clears the others, and a hand ticked clears it.
    func toggle(hand id: String) {
        if hands.contains(id) {
            hands.removeAll { $0 == id }
        } else if id == Self.notSureHand {
            hands = [id]
        } else {
            hands.removeAll { $0 == Self.notSureHand }
            hands.append(id)
        }
    }
}

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
            FlowLayout(spacing: 10) {
                ForEach(store.handOptions, id: \.id) { hand in
                    Toggle(hand.title, isOn: Binding(get: { store.hands.contains(hand.id) },
                                                     set: { _ in store.toggle(hand: hand.id) }))
                        .setupCheckbox()
                        .help("\(hand.centuries). \(hand.looks)")
                }
                Toggle("Not sure", isOn: Binding(get: { store.hands.contains(RecipeSetupStore.notSureHand) },
                                                 set: { _ in store.toggle(hand: RecipeSetupStore.notSureHand) }))
                    .setupCheckbox()
            }
            // A hand typed is kept as typed (and shown ticked).
            ForEach(store.hands.filter { id in id != RecipeSetupStore.notSureHand
                && !store.handOptions.contains { $0.id == id } }, id: \.self) { typed in
                Toggle(typed, isOn: Binding(get: { true }, set: { _ in store.toggle(hand: typed) })).setupCheckbox()
            }
            TextField("Another hand", text: $typedHand, prompt: Text("Another hand, as you would name it"))
                .onSubmit {
                    let hand = typedHand.trimmingCharacters(in: .whitespaces)
                    if !hand.isEmpty, !store.hands.contains(hand) { store.toggle(hand: hand) }
                    typedHand = ""
                }
        }
        .task(id: "\(store.scripts.first ?? "")|\(store.period)") {
            try? await Task.sleep(for: .milliseconds(300))  // the period as typed: ask once the person pauses
            guard !Task.isCancelled else { return }
            await store.loadHands()
        }
    }
}

#Preview("When, where, which hand") {
    RecipeWhenWhereHandFields(store: RecipeSetupStore(client: FicheroClient(libraryPath: nil)))
        .padding()
        .frame(width: 520)
}
