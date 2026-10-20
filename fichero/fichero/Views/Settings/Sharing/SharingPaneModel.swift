import Foundation

/// What Settings › Sharing says and shows (`sharing.settings.three-panes`, #5928): the words and the rules, apart from the view,
/// so they are tested without a window.
enum SharingPaneText {
    static let switchTitle = "Share this Mac's projects"
    static let addDevice = "Add Device…"
    static let connect = "Connect to Another Mac…"

    /// The one grey line under the switch: what sharing is doing, the one error, or where the switch lives. Nothing when it is off.
    static func statusLine(isOn: Bool, isApplying: Bool, error: String?, engineIsLocal: Bool) -> String? {
        guard engineIsLocal else { return "Sharing is set on the Mac that runs this project" }
        if let error, !error.isEmpty { return error }
        if isApplying { return "Starting…" }
        return isOn ? "Sharing on your network and Tailscale" : nil
    }

    /// The Devices list is there while sharing is on; with it off the pane is the switch and Connect only.
    static func showsDevices(isOn: Bool, engineIsLocal: Bool) -> Bool { isOn && engineIsLocal }

    /// The one red line under the Address field: blank is fine (automatic); anything else must be https.
    static func addressProblem(_ draft: String) -> String? {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty || text.lowercased().hasPrefix("https://") ? nil : "Address must start with https://"
    }

    /// The − button removes what is selected, and only while something is.
    static func canRemove(selected: Int, engineIsLocal: Bool) -> Bool { selected > 0 && engineIsLocal }

    static func removeQuestion(count: Int, firstName: String?) -> String {
        count == 1 ? "Remove \(firstName ?? "this device")?" : "Remove \(count) devices?"
    }
}
