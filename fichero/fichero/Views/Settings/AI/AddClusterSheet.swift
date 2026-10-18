import SwiftUI

/// Add a cluster, step by step (`compute.secret.ccdb-guided`, #5238, #5454): the cluster's details, Fichero makes the
/// key and shows its public half to add in the account page, then sign in (the second factor is answered in the sheet)
/// and an honest check. Nothing is submitted.
struct AddClusterSheet: View {
    @State var service: HpcSignInService
    var onDone: () -> Void = {}
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var hostAlias = ""
    @State private var username = ""
    @State private var remoteBaseDir = ""
    @State private var account = ""
    @State private var partition = ""
    @State private var cluster: HpcSignInService.Cluster?
    @State private var publicKey: String?
    @State private var problem: String?
    @State private var signingIn = false
    @State private var checkResult: (ok: Bool, steps: [HpcSignInService.CheckStep])?

    var body: some View {
        VStack(spacing: 0) {
            Text("Add a Cluster")
                .font(.headline)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
            Divider()
            Form {
                if cluster == nil {
                    Section {
                        TextField("Name", text: $name, prompt: Text("Rorqual"))
                        TextField("Host", text: $hostAlias, prompt: Text("rorqual.alliancecan.ca"))
                        TextField("User Name", text: $username)
                        TextField("Project Folder", text: $remoteBaseDir, prompt: Text("/project/def-yourgroup/you"))
                        TextField("Account", text: $account, prompt: Text("def-yourgroup"))
                        TextField("Partition", text: $partition, prompt: Text("Optional"))
                            .help("Leave empty to use the site's own partition.")
                    }
                    if let problem {
                        Section { Label(problem, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange) }
                    }
                } else if let cluster {
                    keySteps(cluster)
                }
            }
            .formStyle(.grouped)
            Divider()
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if cluster == nil {
                    Button("Save") { Task { await save() } }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.defaultAction)
                        .disabled(name.isEmpty || hostAlias.isEmpty || username.isEmpty || remoteBaseDir.isEmpty)
                } else {
                    Button("Done") { onDone(); dismiss() }
                        .buttonStyle(.borderedProminent)
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding()
        }
        .frame(width: 460, height: 420)
        .sheet(isPresented: $signingIn) {
            if let cluster {
                HpcSignInSheet(clusterId: cluster.id, clusterName: cluster.name, service: service)
            }
        }
    }

    @ViewBuilder
    private func keySteps(_ cluster: HpcSignInService.Cluster) -> some View {
        Section {
            Text("\(cluster.name) is saved. Its key is made here and never leaves this Mac.").font(.callout)
        }
        if let publicKey {
            Section("1. Add the Key to Your Account") {
                Text("Add this public key to your account on the cluster. A new key can take a few minutes to reach the clusters.")
                    .font(.callout)
                    .help("On the Alliance: My Account › SSH Keys.")
                Text(publicKey)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                    .lineLimit(3)
                    .accessibilityLabel("Public key")
                HStack {
                    Button("Copy") { PlatformPasteboard.writeString(publicKey) }
                        .accessibilityLabel("Copy the public key")
                    Link("Open the Account Page", destination: URL(string: "https://ccdb.alliancecan.ca/ssh_authorized_keys")!)
                }
            }
            Section("2. Sign In") {
                Text("You will be asked for your second factor.").font(.callout)
                HStack {
                    Button("Sign In…") { signingIn = true }
                    Button("Check") { Task { checkResult = await service.check(clusterId: cluster.id) } }
                }
                if let checkResult {
                    Label(checkResult.ok ? "Everything answered" : "Something did not answer",
                          systemImage: checkResult.ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                        .foregroundStyle(checkResult.ok ? .green : .orange)
                    ForEach(checkResult.steps) { step in
                        HStack(alignment: .firstTextBaseline) {
                            Image(systemName: Self.symbol(step.state)).foregroundStyle(Self.tint(step.state))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(step.name).font(.callout.weight(.semibold))
                                if step.state == "failed", !step.answer.isEmpty {
                                    Text(step.answer).font(.callout).foregroundStyle(.secondary)
                                }
                            }
                            Spacer()
                            Text(Self.words(step.state)).font(.caption.weight(.medium)).foregroundStyle(Self.tint(step.state))
                        }
                    }
                }
            }
        } else {
            Section { ProgressView("Making the key…") }
        }
    }

    static func words(_ state: String) -> String {
        switch state {
        case "passed": "Answered"
        case "failed": "Did not answer"
        default: "Not tried"
        }
    }

    static func symbol(_ state: String) -> String {
        switch state {
        case "passed": "checkmark.circle.fill"
        case "failed": "exclamationmark.triangle.fill"
        default: "minus.circle"
        }
    }

    static func tint(_ state: String) -> Color {
        switch state {
        case "passed": .green
        case "failed": .orange
        default: .secondary
        }
    }

    private func save() async {
        switch await service.addCluster(
            name: name, hostAlias: hostAlias, username: username, remoteBaseDir: remoteBaseDir, account: account,
            partition: partition)
        {
        case .success(let saved):
            cluster = saved
            publicKey = await service.makeKey(clusterId: saved.id)
        case .failure(.words(let words)):
            problem = words
        }
    }
}

#Preview("The form") {
    AddClusterSheet(service: AppState().hpcSignInService)
}
