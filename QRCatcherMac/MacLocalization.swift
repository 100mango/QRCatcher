import Foundation

func QRL(_ key: String) -> String { NSLocalizedString(key, comment: "") }
func QRF(_ key: String, _ arguments: CVarArg...) -> String {
    String(format: QRL(key), locale: Locale.current, arguments: arguments)
}
