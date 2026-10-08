import XCTest
#if os(macOS)
@testable import QRCatcherMac
#elseif os(visionOS)
@testable import QRCatcherVision
#endif

final class QRBoundedImportReadTests: XCTestCase {
    private var directory: URL!
    override func setUpWithError() throws {
        directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try FileManager.default.removeItem(at: directory) }
    private func file(_ name: String = "synthetic.png", bytes: Int = 256 * 1024) throws -> URL {
        let url = directory.appendingPathComponent(name)
        try Data(repeating: 0x42, count: bytes).write(to: url)
        return url
    }
    func testActualBoundedSnapshotOwnsBytesAndRejectsMissingOrSymbolicURL() throws {
        let url = try file(bytes: 130_001), expected = try Data(contentsOf: url)
        XCTAssertEqual(try QRBoundedPhotoFile.read(url), expected)
        let link = directory.appendingPathComponent("link.png")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: url)
        XCTAssertThrowsError(try QRBoundedPhotoFile.read(link))
        XCTAssertThrowsError(try QRBoundedPhotoFile.read(directory))
        try FileManager.default.removeItem(at: url)
        XCTAssertThrowsError(try QRBoundedPhotoFile.read(url))
    }
    func testGrowingAndTruncatedSourcesNeverReturnPartialBytes() throws {
        for length in [QRBoundedPhotoFile.maximumBytes + 1, 10] {
            let url = try file(); var checks = 0; var mutationError: Error?
            XCTAssertThrowsError(try QRBoundedPhotoFile.read(url, isCancelled: {
                checks += 1
                if checks == 3 {
                    do {
                        let handle = try FileHandle(forWritingTo: url)
                        try handle.truncate(atOffset: UInt64(length)); try handle.close()
                    } catch { mutationError = error }
                }
                return false
            }))
            XCTAssertNil(mutationError)
        }
    }
    func testCancellationBetweenChunksIsMappedToCancellationError() throws {
        let url = try file(); var checks = 0
        do {
            _ = try QRBoundedPhotoFile.read(url, isCancelled: { checks += 1; return checks == 3 })
            XCTFail("Cancelled read returned a snapshot")
        } catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(checks, 3)
    }
}
