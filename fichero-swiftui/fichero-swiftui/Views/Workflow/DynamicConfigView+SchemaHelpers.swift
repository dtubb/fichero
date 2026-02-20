import SwiftUI

extension DynamicConfigView {

    // MARK: - Schema Helpers

    func getFieldSchema(for key: String) -> [String: AnyCodableValue]? {
        guard case .dictionary(let schema) = toolInfo.configSchema[key] else {
            return nil
        }
        return schema
    }

    func getType(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let type) = schema["type"] {
            return type
        }
        return nil
    }

    func getDescription(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let desc) = schema["description"] {
            return desc
        }
        return nil
    }

    func getDefault(from schema: [String: AnyCodableValue]) -> AnyCodableValue? {
        schema["default"]
    }

    func getEnum(from schema: [String: AnyCodableValue]) -> [String]? {
        if case .array(let values) = schema["enum"] {
            return values.compactMap {
                if case .string(let str) = $0 {
                    return str
                }
                return nil
            }
        }
        return nil
    }

    func isHidden(schema: [String: AnyCodableValue]) -> Bool {
        if case .bool(let hidden) = schema["x-hidden"] {
            return hidden
        }
        return false
    }

    func getGroup(from schema: [String: AnyCodableValue]) -> String? {
        if case .string(let group) = schema["x-group"] {
            return group
        }
        return nil
    }

    func getMin(from schema: [String: AnyCodableValue]) -> Double? {
        switch schema["min"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return nil
        }
    }

    func getMax(from schema: [String: AnyCodableValue]) -> Double? {
        switch schema["max"] {
        case .double(let val): return val
        case .int(let val): return Double(val)
        default: return nil
        }
    }
}
