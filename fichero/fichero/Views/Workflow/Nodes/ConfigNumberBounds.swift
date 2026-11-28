import Foundation

/// The range, step and label of a schema-driven number field
/// (`DynamicConfigView`), read from the tool's served config schema.
enum ConfigNumberBounds {
    /// The declared range: `minimum`/`maximum`, the keys most tool schemas
    /// serve, else the short `min`/`max` a few still use. Nil when the schema
    /// does not declare both ends, or declares an empty or inverted range:
    /// there is then no range to offer, and `ClosedRange` traps on an
    /// inverted one.
    static func range(schema: [String: AnyCodableValue]) -> ClosedRange<Double>? {
        guard let lower = number(schema["minimum"]) ?? number(schema["min"]),
              let upper = number(schema["maximum"]) ?? number(schema["max"]),
              lower < upper else { return nil }
        return lower...upper
    }

    /// A step fine enough for the range: hundredths up to a span of 1, tenths
    /// up to 10, whole numbers above.
    static func step(for range: ClosedRange<Double>) -> Double {
        let span = range.upperBound - range.lowerBound
        if span <= 1 { return 0.01 }
        if span <= 10 { return 0.1 }
        return 1.0
    }

    /// The value written with as many decimals as the step has.
    static func label(_ value: Double, step: Double) -> String {
        let decimals = step < 0.1 ? 2 : step < 1 ? 1 : 0
        return String(format: "%.\(decimals)f", value)
    }

    private static func number(_ value: AnyCodableValue?) -> Double? {
        switch value {
        case .double(let number): return number
        case .int(let number): return Double(number)
        default: return nil
        }
    }
}
