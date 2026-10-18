import SwiftUI

/// The clusters set up for this Mac, each with Sign in (the second factor is answered in the sheet). Lives in
/// Settings › AI › Advanced until the Add-a-cluster form is built (#5740, #5238).
struct ClustersSettingsSection: View {
    @Environment(AppState.self) private var appState
    @State private var clusters: [HpcSignInService.Cluster] = []
    @State private var signingIn: HpcSignInService.Cluster?
    @State private var adding = false

    var body: some View {
        Group {
            Button("Add a Cluster…") { adding = true }
            ForEach(clusters) { cluster in
                HStack {
                    VStack(alignment: .leading) {
                        Text(cluster.name)
                        Text(cluster.host).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Sign in…") { signingIn = cluster }
                }
            }
        }
        .task { clusters = await appState.hpcSignInService.listClusters() }
        .sheet(isPresented: $adding) {
            AddClusterSheet(service: appState.hpcSignInService) {
                Task { clusters = await appState.hpcSignInService.listClusters() }
            }
        }
        .sheet(item: $signingIn) { cluster in
            HpcSignInSheet(clusterId: cluster.id, clusterName: cluster.name, service: appState.hpcSignInService)
        }
    }
}

#Preview("Two clusters") {
    ClustersSettingsSection()
        .environment(AppState())
        .padding()
        .frame(width: 420)
}
