# QRCatcher

已于AppStore上架  [AppStore 链接](https://itunes.apple.com/cn/app/qrcatcher/id993170818?mt=8)


一个简洁美观的二维码扫描应用

1. 主要功能:

	- 二维码扫描与解析
	- 扫描记录保存

2. 技术实现细节:

	- 利用AVFoundation进行扫描与解析
	- 利用CoreData进行数据存储,增删减除
	- 利用CAShapeLayer与UIBezierPath实现动画效果
	- 利用AutoLayout与SizeClasses进行界面布局


## Current modernization branch

The `codex/ios-modernization` draft preserves the original bundle ID and Core Data history while adopting iOS 27's scene lifecycle, camera permission/error handling, safe link opening, accessible layouts and persistent text/URL history. Deployment target: iOS 15.0; test runners require iOS 17+ with the current XCTest SDK.

Open `QRCatcher.xcworkspace` and run the shared `QRCatcher` scheme. CocoaPods is no longer required. Use `python3 scripts/generate_project.py` after changing the source-file inventory. Cloud CI verifies stable Xcode 27.0 and runs unit/UI tests before an unsigned device Release build.

See [release readiness and test coverage](docs/RELEASE_READINESS.md) for data compatibility, exact test scope and outstanding physical-device/signing/App Store gates. A successful simulator run alone is not a release approval.
