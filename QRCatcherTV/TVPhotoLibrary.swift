import Photos
import UIKit
import ImageIO
import Combine

@MainActor
final class TVPhotoLibrary: ObservableObject {
    @Published private(set) var assets: [PHAsset] = []
    @Published private(set) var status = QRL("Choose Photos to read a QR image stored in your photo library.")
    @Published private(set) var hasMore = false
    private var fetch: PHFetchResult<PHAsset>?
    private var shown = 0
    private var requesting = false
    func requestAccess() {
        guard !requesting else { return }
        let current = PHPhotoLibrary.authorizationStatus(for: .readWrite)
        if current == .authorized || current == .limited { reload(); return }
        requesting = true
        status = QRL("Waiting for Photos permission. Respond to the system request to continue.")
        #if DEBUG
        print("TV_PHOTOS_AUTH_REQUEST", current.rawValue)
        #endif
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { result in
            Task { @MainActor in
                self.requesting = false
                #if DEBUG
                print("TV_PHOTOS_AUTH_RESULT", result.rawValue)
                #endif
                guard result == .authorized || result == .limited else {
                    self.status = QRL("Photos access is unavailable. You can change access in Settings, then choose Retry."); self.assets = []; return
                }
                self.reload()
            }
        }
    }
    func reload() {
        let options = PHFetchOptions(); options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
        fetch = PHAsset.fetchAssets(with: .image, options: options); shown = 0; assets = []; more()
        status = assets.isEmpty ? QRL("No photos are available in this library. Add a QR image to Photos, then choose Retry.") : QRL("Choose a photo. Only the selected image is decoded.")
    }
    func more() {
        guard let fetch else { return }
        let end = min(fetch.count, shown + 40)
        if end > shown { for index in shown..<end { assets.append(fetch.object(at: index)) } }
        shown = end; hasMore = shown < fetch.count
    }
    static func imageResource(for asset: PHAsset) -> PHAssetResource? {
        let values = PHAssetResource.assetResources(for: asset)
        return values.first { $0.type == .fullSizePhoto } ?? values.first { $0.type == .photo }
    }
}

/// PhotoKit streams the selected resource into a strict 50 MiB buffer. Cancelling
/// a selection releases accumulated bytes and cancels the actual PhotoKit request.
final class TVPhotoRead: @unchecked Sendable {
    private let lock = NSLock()
    private var bytes = Data()
    private var request: PHAssetResourceDataRequestID?
    private var finished = false
    private var deadline: DispatchWorkItem?
    private let completion: @Sendable (Result<Data, Error>) -> Void
    init(resource: PHAssetResource, completion: @escaping @Sendable (Result<Data, Error>) -> Void) {
        self.completion = completion
        let options = PHAssetResourceRequestOptions(); options.isNetworkAccessAllowed = true
        let id = PHAssetResourceManager.default().requestData(for: resource, options: options, dataReceivedHandler: { [weak self] data in self?.receive(data) }, completionHandler: { [weak self] error in self?.complete(error) })
        lock.lock(); request = id; let cancelled = finished; lock.unlock()
        if cancelled { PHAssetResourceManager.default().cancelDataRequest(id); return }
        let timeout = DispatchWorkItem { [weak self] in
            self?.finish(.failure(URLError(.timedOut)), cancelRequest: true)
        }
        lock.lock(); let alreadyFinished = finished; if !alreadyFinished { deadline = timeout }; lock.unlock()
        if !alreadyFinished { DispatchQueue.global().asyncAfter(deadline: .now() + 45, execute: timeout) }
    }
    func cancel() { finish(.failure(CancellationError()), cancelRequest: true) }
    private func receive(_ chunk: Data) {
        lock.lock()
        guard !finished else { lock.unlock(); return }
        guard chunk.count <= 50 * 1024 * 1024 - bytes.count else {
            lock.unlock(); finish(.failure(NSError(domain: "QRCatcher.Image", code: 1, userInfo: [NSLocalizedDescriptionKey: QRL("Choose an image smaller than 50 MB.")])), cancelRequest: true); return
        }
        bytes.append(chunk); lock.unlock()
    }
    private func complete(_ error: Error?) {
        lock.lock(); let data = bytes; lock.unlock()
        finish(error.map { .failure($0) } ?? .success(data), cancelRequest: false)
    }
    private func finish(_ result: Result<Data, Error>, cancelRequest: Bool) {
        lock.lock()
        guard !finished else { lock.unlock(); return }
        finished = true; bytes = Data(); let id = request; let timeout = deadline; deadline = nil; lock.unlock()
        timeout?.cancel()
        if cancelRequest, let id { PHAssetResourceManager.default().cancelDataRequest(id) }
        completion(result)
    }
}

private final class PhotoIdentifierBox: @unchecked Sendable {
    private let lock = NSLock(); private var identifier: String?
    func set(_ value: String?) { lock.lock(); identifier = value; lock.unlock() }
    func get() -> String? { lock.lock(); defer { lock.unlock() }; return identifier }
}

@MainActor
enum TVPhotoExport {
    static func saveAndVerify(png: Data, payload: String) async throws -> String {
        let authorization = await PHPhotoLibrary.requestAuthorization(for: .readWrite)
        guard authorization == .authorized || authorization == .limited else { throw ExportError.permission }
        let placeholder = PhotoIdentifierBox()
        let identifier: String = try await withCheckedThrowingContinuation { continuation in
            PHPhotoLibrary.shared().performChanges({
                let request = PHAssetCreationRequest.forAsset()
                request.addResource(with: .photo, data: png, options: nil)
                placeholder.set(request.placeholderForCreatedAsset?.localIdentifier)
            }, completionHandler: { success, error in
                if success, let value = placeholder.get() { continuation.resume(returning: value) }
                else { continuation.resume(throwing: error ?? CocoaError(.fileWriteUnknown)) }
            })
        }
        var asset: PHAsset?
        for _ in 0..<10 {
            asset = PHAsset.fetchAssets(withLocalIdentifiers: [identifier], options: nil).firstObject
            if asset != nil { break }
            try await Task.sleep(nanoseconds: 300_000_000)
        }
        guard let asset, let resource = TVPhotoLibrary.imageResource(for: asset) else { throw ExportError.refetch }
        var read: TVPhotoRead?
        defer { withExtendedLifetime(read) {} }
        let data: Data = try await withCheckedThrowingContinuation { continuation in
            read = TVPhotoRead(resource: resource) { continuation.resume(with: $0) }
        }
        func dimensions(_ bytes: Data) -> [Int]? {
            guard let source = CGImageSourceCreateWithData(bytes as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
                  let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
                  let width = properties[kCGImagePropertyPixelWidth] as? Int,
                  let height = properties[kCGImagePropertyPixelHeight] as? Int else { return nil }
            return [width, height]
        }
        guard let expected = dimensions(png), dimensions(data) == expected,
              try await QRDecodeWorker.shared.decode(load: { data }).contains(payload) else { throw ExportError.refetch }
        return identifier
    }
    enum ExportError: LocalizedError {
        case refetch, permission
        var errorDescription: String? {
            switch self {
            case .refetch: return QRL("Photos reported a save, but the exported QR image could not be fetched and verified. Check Photos before trying again.")
            case .permission: return QRL("Photos access is required to save and verify this QR image. Change access in Settings, then try again.")
            }
        }
    }
}
