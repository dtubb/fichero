import FicheroAPIClient
import SwiftUI

/// AI and ML Models (Set Up Fichero's second screen, ruled and worded by the owner 2026-10-19, #5828;
/// `source.onboard.first-launch-three-screens`): five cards, each ticked to allow a place models may run, with the
/// button that connects it where there is one. The ticks are the engine's setting (`AppPlacesStore`).
enum WhatFicheroRuns {
    static let title = "AI and ML Models"
    static let intro = "Fichero reads your pages with artificial intelligence (AI) and machine learning (ML) models. "
        + "Some come with Fichero; others are downloaded when a project needs them, and run on your Mac. You can "
        + "also run models elsewhere: on another Mac running Fichero, with a cloud AI service, or on a computing "
        + "cluster."
    static let question = "Where may models run? Tick every place you'll allow."
    static let footnote = "You can change this later in Settings, and for each project."

    /// What a card's button opens (the existing sheets: one code path).
    enum Connect: Equatable {
        case addKey
        case signIn
        case addToken
    }

    /// What is already set up, read from the existing provider and cluster routes (`source.onboard.places-cap-projects`):
    /// shown on a card, never ticking it (the ticks are the person's choice).
    struct SetUp: Equatable {
        var keys: [String] = []
        var hasToken = false
        var clusters: [String] = []

        init(keys: [String] = [], hasToken: Bool = false, clusters: [String] = []) {
            self.keys = keys
            self.hasToken = hasToken
            self.clusters = clusters
        }

        init(providers: [Components.Schemas.ProviderResponse], clusters: [String]) {
            // Cloud providers only (`place` is the company that runs the model): a local one reports a key as present
            // because it needs none, and is no key (#5828).
            self.init(keys: providers.filter { $0.hasApiKey && $0.place == "provider" && $0.providerType != "huggingface" }.map(\.name),
                      hasToken: providers.contains { $0.hasApiKey && $0.providerType == "huggingface" },
                      clusters: clusters)
        }

        /// The sentence a card shows for what is set up, nil when nothing is.
        func line(for place: WhereTheWorkRuns) -> String? {
            switch place {
            case .cloud: keys.isEmpty ? nil : "Keys saved: " + keys.joined(separator: ", ")
            case .huggingface: hasToken ? "Token saved" : nil
            case .acenet: clusters.isEmpty ? nil : clusters.joined(separator: ", ")
            case .thisMac, .anotherMac: nil
            }
        }

        /// A saved Hugging Face token replaces "Add a Token…"; a key or a cluster leaves its button (add another).
        func hidesButton(for place: WhereTheWorkRuns) -> Bool { place == .huggingface && hasToken }
    }

    /// One place: its engine id, symbol, title, its words (markdown: every named thing is a link that opens in the
    /// browser), and the button beside it. Another Mac has none yet: reading on a paired Mac is #5830.
    struct Place: Equatable {
        let place: WhereTheWorkRuns
        let symbol: String
        let title: String
        let body: String
        let button: String?
        let connect: Connect?
    }

    static let places: [Place] = [
        Place(place: .thisMac, symbol: "laptopcomputer", title: "On this Mac",
              body: "Free and private: your pages never leave this Mac. Fichero comes with [Kraken](https://kraken.re) "
                + "and uses [Apple Vision](https://developer.apple.com/documentation/vision), Apple's own text "
                + "recognition. It can also download open-source vision language models (VLMs) from "
                + "[Hugging Face](https://huggingface.co/models), made for your script and language, and run them "
                + "here with [MLX](https://github.com/ml-explore/mlx). On a big archive it is slower, and this Mac's "
                + "memory limits how large a model it can run.",
              button: nil, connect: nil),
        Place(place: .anotherMac, symbol: "desktopcomputer", title: "Another Mac of mine",
              body: "A bigger Mac you own, set up as a [Fichero server](https://tubb.ca/apps/fichero/), does the "
                + "reading while you work here. Your pages go to your own Mac, and it costs nothing.",
              button: nil, connect: nil),
        Place(place: .cloud, symbol: "cloud", title: "In the cloud",
              body: "Larger models, such as [Claude](https://www.anthropic.com/claude), "
                + "[GPT](https://openai.com/api/) or [Gemini](https://ai.google.dev), often read difficult hands "
                + "better. The pages go to the provider, and each page costs a little. Fichero asks before any page "
                + "leaves this Mac and says what it will cost.",
              button: "Add a Key…", connect: .addKey),
        Place(place: .acenet, symbol: "server.rack", title: "ACENET",
              body: "[ACENet](https://www.ace-net.ca) is Atlantic Canada's research computing cluster, free for "
                + "researchers at member universities. For large batches and for training your own model. Your pages "
                + "go to your account on the cluster, and jobs wait in a queue.",
              button: "Sign In…", connect: .signIn),
        Place(place: .huggingface, symbol: "shippingbox", title: "Hugging Face",
              body: "Download open models made for your script from [Hugging Face](https://huggingface.co/models), "
                + "and run large batches or training on "
                + "[Hugging Face Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs). Downloading is "
                + "free; Jobs cost by the hour, and your pages go to Hugging Face.",
              button: "Add a Token…", connect: .addToken)
    ]
}

/// Add… on an account row (preselected), or Add Another Provider… (nil): the shared sheet's request.
struct AddProviderRequest: Identifiable, Equatable {
    let providerType: String?
    var id: String { providerType ?? "any" }
}

struct WhatFicheroRunsFields: View {
    let store: AppPlacesStore
    var setUp = WhatFicheroRuns.SetUp()
    /// Opens the existing sheet for a card's button.
    let connect: (WhatFicheroRuns.Connect) -> Void

    var body: some View {
        // A native List (no hand-rolled row collection); the cards are content to read before choosing, so no separators.
        List {
            Group {
                Text(WhatFicheroRuns.intro).fixedSize(horizontal: false, vertical: true)
                Text(WhatFicheroRuns.question).font(.headline)
                ForEach(WhatFicheroRuns.places, id: \.title) { card($0) }
                Text(WhatFicheroRuns.footnote).foregroundStyle(.secondary)
            }
            .listRowSeparator(.hidden)
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .frame(maxWidth: 560, alignment: .leading)
        // Outside the scroll view, so a refused Continue is seen without scrolling.
        .safeAreaInset(edge: .bottom, alignment: .leading) {
            if let message = store.errorMessage {
                Text(message).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
            }
        }
        .task { await store.load() }
    }

    private func card(_ place: WhatFicheroRuns.Place) -> some View {
        let isThisMac = place.place == .thisMac
        return HStack(alignment: .top, spacing: 12) {
            Toggle(place.title, isOn: Binding(
                get: { store.allows(place.place) },
                set: { allowed in Task { await store.set(place.place, allowed: allowed) } }))
                .setupCheckbox()  // a checkbox on the Mac, a switch on iOS
                .labelsHidden()
                .disabled(isThisMac)  // where the app is: always allowed
                .accessibilityLabel(place.title)
            VStack(alignment: .leading, spacing: 6) {
                Label(place.title, systemImage: place.symbol).font(.headline)
                Text(markdown: place.body).font(.callout).fixedSize(horizontal: false, vertical: true)
                if isThisMac, let line = store.thisMacLine {
                    Text(line).font(.callout).fixedSize(horizontal: false, vertical: true)
                }
                if let saved = setUp.line(for: place.place) {
                    Label(saved, systemImage: "checkmark.circle").font(.callout).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            if let button = place.button, let connectTo = place.connect, !setUp.hidesButton(for: place.place) {
                Button(button) { connect(connectTo) }
            }
        }
        .padding(14)
        .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.08), lineWidth: 1))
    }
}

extension Text {
    /// Markdown with links (each opens in the browser); the words as written if it does not parse.
    init(markdown: String) {
        self.init((try? AttributedString(markdown: markdown)) ?? AttributedString(markdown))
    }
}

/// Setup's body text: paragraphs, then an optional numbered list and a closing line, top- and left-aligned at a
/// readable width.
struct SetupBodyText: View {
    let paragraphs: [String]
    var numbered: [String] = []
    var closing: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(paragraphs, id: \.self) { Text($0).fixedSize(horizontal: false, vertical: true) }
            if !numbered.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(Array(numbered.enumerated()), id: \.offset) { index, item in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Text("\(index + 1).").monospacedDigit()
                            Text(item).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            if let closing { Text(closing).fixedSize(horizontal: false, vertical: true) }
        }
        .frame(maxWidth: 520, alignment: .topLeading)
    }
}

#Preview("AI and ML Models") {
    WhatFicheroRunsFields(store: AppPlacesStore(client: AppState().ficheroClient), connect: { _ in })
        .padding()
        .frame(width: 600, height: 700)
}

#Preview("Setup body text") {
    SetupBodyText(paragraphs: FirstLaunchChoices.handOffParagraphs)
        .padding()
}
