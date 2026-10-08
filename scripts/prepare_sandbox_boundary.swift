import Foundation
import Security
import Darwin

let task = SecTaskCreateFromSelf(nil)!
let sandboxed = SecTaskCopyValueForEntitlement(task, "com.apple.security.app-sandbox" as CFString, nil) as? Bool ?? false
precondition(!sandboxed, "The same-user read control must run outside App Sandbox")
let folder = URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true).appendingPathComponent("QRCatcherBoundaryProbe-" + UUID().uuidString)
try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false, attributes: [.posixPermissions: 0o700])
let file = folder.appendingPathComponent("synthetic-read.txt")
let bytes = Data("synthetic sandbox read sentinel".utf8)
precondition(FileManager.default.createFile(atPath: file.path, contents: bytes, attributes: [.posixPermissions: 0o600]))
let readback = try Data(contentsOf: file)
precondition(readback == bytes)
let permissions = try FileManager.default.attributesOfItem(atPath: file.path)[.posixPermissions] as! NSNumber
precondition(permissions.intValue == 0o600)
let value: [String: Any] = ["folder":folder.path,"unsandboxed_read_control":true,"control_sandboxed":sandboxed,"control_user_id":getuid(),"file_mode":permissions.intValue]
let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
try data.write(to: URL(fileURLWithPath: CommandLine.arguments[1]), options: .atomic)
print("UNSANDBOXED_SAME_USER_READ_CONTROL:", String(decoding: data, as: UTF8.self))
