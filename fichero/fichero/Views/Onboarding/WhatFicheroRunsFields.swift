import FicheroAPIClient
import SwiftUI

/// Models & Services (section 7d, ruled 2026-10-11, #5668; `source.onboard.app.what-fichero-runs`): what Fichero runs
/// on this Mac, and with what; then the accounts that add to it, each added through Settings' own add-provider sheet
/// (`AddProviderSheet`), one code path. It replaces "AI is optional".
enum WhatFicheroRuns {
    static let title = "Where the work runs"
    /// The page's opening, under its title (Daniel's words, 2026-10-11).
    static let intro = "Fichero does its work with models: programs trained to read handwriting, find the lines on "
        + "a page, or recognise names. They run in one of two places."

    /// The two places a model runs, side by side.
    struct Place: Equatable {
        let symbol: String
        let title: String
        let body: String
    }

    static let places: [Place] = [
        Place(symbol: "laptopcomputer", title: "On this Mac",
              body: "Free and private: your pages never leave this Mac. Fichero comes with Kraken and uses Apple's "
                + "own text recognition, and it can download larger models made for your script and language. On a "
                + "big archive it is slower, and this Mac's memory limits how large a model it can run."),
        Place(symbol: "cloud", title: "In the cloud",
              body: "Larger models, such as Claude, GPT or Gemini, often read difficult hands better. The pages go to "
                + "the provider, and each page costs a little. Fichero asks before any page leaves this Mac and says "
                + "what it will cost.")
    ]

    static let accountsTitle = "Accounts"
    static let addAnother = "Add Another Provider…"
    static let accountsFootnote = "You can add accounts later in Settings › AI."

    /// What comes with Fichero, in one line (no table of engine names).
    static let comesWith = "Fichero comes with readers for handwriting and print, a line finder and a name finder; "
        + "it downloads others for your language when you need them."

    /// The two accounts it suggests, by the engine's provider type, each with what it is for.
    struct Account: Equatable {
        let providerType: String
        let title: String
        let purpose: String
    }

    static let accounts: [Account] = [
        Account(providerType: "huggingface", title: "Hugging Face",
                purpose: "A free account. Fichero uses it to find and download models for your material."),
        Account(providerType: "openrouter", title: "OpenRouter",
                purpose: "One account for many cloud models, paid as you go. Pages leave this Mac.")
    ]

    /// One suggested account's row: added (with the account's name) or not.
    struct AccountRow: Equatable {
        let account: Account
        /// The added provider's name; nil until it is added.
        let addedAs: String?
    }

    /// The suggested accounts as the providers list has them.
    static func accountRows(providers: [Components.Schemas.ProviderResponse]) -> [AccountRow] {
        accounts.map { account in
            AccountRow(account: account, addedAs: providers.first { $0.providerType == account.providerType }?.name)
        }
    }
}

/// Add… on an account row (preselected), or Add Another Provider… (nil): the shared sheet's request.
struct AddProviderRequest: Identifiable, Equatable {
    let providerType: String?
    var id: String { providerType ?? "any" }
}

struct WhatFicheroRunsFields: View {
    let providers: [Components.Schemas.ProviderResponse]
    /// Opens Settings' add-provider sheet: for that provider, or (nil) to choose one.
    let add: (String?) -> Void

    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    /// Where models may run (#5828): view state only until #5810 makes it the engine's setting.
    @State private var runsAt = WhereTheWorkRuns.default

    var body: some View {
        // A grouped Form: the accounts are native rows, and the form scrolls itself (#5776).
        Form {
            Section {
                Picker("Models may run on", selection: $runsAt) {
                    ForEach(WhereTheWorkRuns.allCases) { choice in
                        Text(choice.title).tag(choice)
                    }
                }
                #if os(macOS)
                .pickerStyle(.radioGroup)
                #endif
                Text(runsAt.detail).foregroundStyle(.secondary)
            }
            Section {
                Text(WhatFicheroRuns.intro)
                    .fixedSize(horizontal: false, vertical: true)
                // Side by side, the same height; stacked at compact width. (ViewThatFits stacked them always: a
                // wrapping text's ideal width is its one-line length, so the row never "fit".)
                if horizontalSizeClass == .compact {
                    VStack(alignment: .leading, spacing: 12) { places }
                } else {
                    HStack(alignment: .top, spacing: 12) { places }
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(WhatFicheroRuns.comesWith)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Section {
                ForEach(WhatFicheroRuns.accountRows(providers: providers), id: \.account.providerType) { row in
                    accountRow(row)
                }
                Button(WhatFicheroRuns.addAnother) { add(nil) }
            } header: {
                Text(WhatFicheroRuns.accountsTitle)
            } footer: {
                Text(WhatFicheroRuns.accountsFootnote)
            }
        }
        .formStyle(.grouped)
        .frame(maxWidth: 560, alignment: .leading)
    }

    private var places: some View {
        ForEach(WhatFicheroRuns.places, id: \.title) { place in
            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: place.symbol)
                    .font(.largeTitle)
                    .foregroundStyle(Color.accentColor)
                    .accessibilityHidden(true)
                Text(place.title).font(.headline)
                Text(place.body).font(.callout).fixedSize(horizontal: false, vertical: true)
            }
            .padding(14)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .background(Color(platformColor: .textBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.primary.opacity(0.08), lineWidth: 1))
        }
    }

    private func accountRow(_ row: WhatFicheroRuns.AccountRow) -> some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.account.title).font(.callout.weight(.medium))
                Text(row.account.purpose).font(.callout).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer()
            if let name = row.addedAs {
                Label(name, systemImage: "checkmark.circle.fill")
                    .font(.callout)
                    .foregroundStyle(.green)
            } else {
                Button("Add…") { add(row.account.providerType) }
            }
        }
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

#Preview("Models & Services") {
    WhatFicheroRunsFields(providers: [], add: { _ in })
        .padding()
        .frame(width: 560, height: 600)
}

#Preview("Setup body text") {
    SetupBodyText(paragraphs: [FirstLaunchChoices.handOffIntro], numbered: FirstLaunchChoices.handOffSteps,
                  closing: FirstLaunchChoices.handOffClosing)
        .padding()
}
