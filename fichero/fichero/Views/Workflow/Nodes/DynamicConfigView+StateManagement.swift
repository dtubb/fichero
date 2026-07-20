import SwiftUI

extension DynamicConfigView {

    // MARK: - State Management

    func initializeValues() {
        for (key, value) in config ?? [:] {
            applyConfigValue(value, forKey: key)
        }

        for (key, schemaValue) in toolInfo.configSchema {
            guard case .dictionary(let schema) = schemaValue else { continue }

            if config?[key] != nil { continue }

            if let defaultValue = getDefault(from: schema) {
                applyConfigValue(defaultValue, forKey: key)
            }
        }
    }

    /// Stores a decoded config value in the appropriately-typed dictionary for `key`.
    private func applyConfigValue(_ value: AnyCodableValue, forKey key: String) {
        switch value {
        case .string(let str):
            stringValues[key] = str
        case .int(let num):
            intValues[key] = num
        case .double(let num):
            doubleValues[key] = num
        case .bool(let flag):
            boolValues[key] = flag
        case .array(let items):
            let strings = items.compactMap { val -> String? in
                if case .string(let stringValue) = val { return stringValue }
                return nil
            }
            arrayValues[key] = strings
        default:
            break
        }
    }

    func updateConfig(key: String, value: AnyCodableValue) {
        if config == nil {
            config = [:]
        }
        config?[key] = value
    }

    func removeConfig(key: String) {
        config?.removeValue(forKey: key)
    }
}
