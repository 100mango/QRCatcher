import XCTest
import CoreData
#if os(visionOS)
@testable import QRCatcherVision
#else
@testable import QRCatcherMac
#endif

/// Close every fixture's persistent store before unlinking its SQLite directory.
/// Keeping references here also makes one-expression reopen assertions safe.
@MainActor
class QRManagedStoreTestCase: XCTestCase {
    private var histories: [MacHistory] = []
    private var adapters: [QRHistoryStore] = []
    private var cleanupURLs: [URL] = []
    func makeHistory(url: URL) -> MacHistory {
        let result = MacHistory(url: url); histories.append(result); return result
    }
    func makeLegacyStore(url: URL) -> QRHistoryStore {
        let result = QRHistoryStore(url: url); adapters.append(result); return result
    }
    func cleanupLater(_ url: URL) { cleanupURLs.append(url) }
    override func tearDownWithError() throws {
        for history in histories { try history.close() }
        for adapter in adapters {
            if let context = adapter.context {
                if context.hasChanges { try context.save() }
                context.reset()
                if let coordinator = context.persistentStoreCoordinator {
                    for store in coordinator.persistentStores { try coordinator.remove(store) }
                }
                context.persistentStoreCoordinator = nil
            }
        }
        histories.removeAll(); adapters.removeAll()
        for url in cleanupURLs.reversed() where FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        cleanupURLs.removeAll()
        try super.tearDownWithError()
    }
}
