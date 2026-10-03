import SwiftUI
import UniformTypeIdentifiers

struct QRExportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.png, .json] }
    let data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws {
        guard let data = configuration.file.regularFileContents else { throw CocoaError(.fileReadCorruptFile) }
        self.data = data
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}
struct QRExportRequest {
    let document: QRExportDocument
    let type: UTType
    let filename: String
}
