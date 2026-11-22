import Foundation

/// `signin.own.setting-says-the-trade-off` (#6568): the Mac's switch, its words and where its state is kept.
enum OwnDevicesSwitch {
    static let label = "Sign in my own devices by themselves"
    static let caption = "Any device signed into this Apple ID can open this Mac's libraries without asking. "
        + "Leave it off on a shared Apple ID."
    private static let key = "app.fichero.ownDevices.enabled"

    static func isOn(_ defaults: UserDefaults = .standard) -> Bool { defaults.bool(forKey: key) }
    static func remember(_ enabled: Bool, _ defaults: UserDefaults = .standard) { defaults.set(enabled, forKey: key) }
}
