import Foundation

/// One serial executor for expensive imported-image work across every app window.
/// Callers await this actor directly, so their cancellation reaches the executing
/// task. ImageIO/Core Image calls are synchronous and cannot be interrupted midway;
/// canceled work is checked before load/decode and after completion, and no second
/// heavy operation begins until the current one finishes.
actor QRDecodeWorker {
    static let shared = QRDecodeWorker()
    private let operation: @Sendable (Data) throws -> [String]

    init(operation: @escaping @Sendable (Data) throws -> [String] = { try QRImageCodec.decode(data: $0) }) {
        self.operation = operation
    }

    func decode(load: @Sendable () throws -> Data) throws -> [String] {
        try Task.checkCancellation()
        let data = try load()
        try Task.checkCancellation()
        let values = try operation(data)
        try Task.checkCancellation()
        return values
    }
}
