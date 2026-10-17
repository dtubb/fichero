import AppKit
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
        VStack(alignment: .leading, spacing: 12) {
            Text("Add a cluster").font(.title3)
            if cluster == nil {
                Form {
                    TextField("Name", text: $name, prompt: Text("Rorqual"))
                    TextField("Host", text: $hostAlias, prompt: Text("rorqual.alliancecan.ca"))
                    TextField("User name", text: $username)
                    TextField("Project folder", text: $remoteBaseDir, prompt: Text("/project/def-yourgroup/you"))
                    TextField("Account", text: $account, prompt: Text("def-yourgroup"))
                    TextField("Partition (leave empty for the site's own)", text: $partition)
                }
                if let problem { Text(problem).foregroundStyle(.red) }
                HStack {
                    Spacer()
                    Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                    Button("Save") { Task { await save() } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(name.isEmpty || hostAlias.isEmpty || username.isEmpty || remoteBaseDir.isEmpty)
                }
            } else if let cluster {
                keySteps(cluster)
            }
        }
        .padding(20)
        .frame(minWidth: 460)
        .sheet(isPresented: $signingIn) {
            if let cluster {
                HpcSignInSheet(clusterId: cluster.id, clusterName: cluster.name, service: service)
            }
        }
    }

    @ViewBuilder
    private func keySteps(_ cluster: HpcSignInService.Cluster) -> some View {
        Text("\(cluster.name) is saved. Its key is made here and never leaves this Mac.").font(.callout)
        if let publicKey {
            Text("1. Add this public key to your account on the cluster (on the Alliance: My Account › SSH Keys). "
                + "A new key can take a few minutes to reach the clusters.").font(.callout)
            Text(publicKey).font(.caption.monospaced()).textSelection(.enabled).lineLimit(3)
            HStack {
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(publicKey, forType: .string)
                }
                Link("Open the account page", destination: URL(string: "https://ccdb.alliancecan.ca/ssh_authorized_keys")!)
            }
            Text("2. Then sign in. You will be asked for your second factor; approve the push on your phone.")
                .font(.callout)
            HStack {
                Button("Sign in…") { signingIn = true }
                Button("Check") { Task { checkResult = await service.check(clusterId: cluster.id) } }
            }
            if let checkResult {
                Text(checkResult.ok ? "Everything answered." : "Something did not answer:").font(.callout)
                ForEach(checkResult.steps) { step in
                    Text("\(step.name): \(step.state)\(step.state == "failed" ? " — \(step.answer)" : "")").font(.caption)
                }
            }
        } else {
            ProgressView("Making the key…")
        }
        HStack {
            Spacer()
            Button("Done") { onDone(); dismiss() }.keyboardShortcut(.defaultAction)
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
