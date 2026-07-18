import SwiftUI

extension DynamicConfigView {

    // MARK: - State Management

    // swiftlint:disable:next cyclomatic_complexity
    func initializeValues() {
        for (key, value) in config ?? [:] {
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

        for (key, schemaValue) in toolInfo.configSchema {
            guard case .dictionary(let schema) = schemaValue else { continue }

            if config?[key] != nil { continue }

            if let defaultValue = getDefault(from: schema) {
                switch defaultValue {
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
