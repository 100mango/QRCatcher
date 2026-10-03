import Foundation
import Vision
@available(watchOS 27.0, *)
func decodeWatchQR(_ data: Data) async throws -> [String] {
    var request = DetectBarcodesRequest()
    request.symbologies = [.qr]
    let observations = try await request.perform(on: data)
    return observations.compactMap { $0.payloadString }
}
