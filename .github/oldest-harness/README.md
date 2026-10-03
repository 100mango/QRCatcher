# Oldest-runtime XCTest feasibility

This isolated branch validates only the older UI-test infrastructure on Apple's
official iOS15.5 runtime. It builds a synthetic Objective-C test host and runs one
interaction/background test on the real320-point SE1 and iPad mini4 profiles.
It does not build or test Celluloid, QRCatcher or TouchColor, and cannot qualify
their compatibility. The later app lane will install unchanged SDK27 Release
products pinned to their final commits; source reconstruction with an older SDK
will not substitute for that evidence.

Only one standard public macOS26 runner is used, with a35-minute job ceiling.
The official runtime installer uses the image's preinstalled xcodes2.0.3 and the
Apple catalog/package previously installed and booted in run37109442046. No
helper download, account, agreement, credential, paid runner, cache or artifact
upload is involved. Test framework Mach-O floors are inspected before execution.
Only newly created synthetic simulators are shut down; no existing device erase.

The supporting producer/consumer modules supply shared pure validators only.
Neither their app-build entrypoint nor a product consumer is invoked here. There
is no final app-source manifest in this probe.

Sources: https://developer.apple.com/xcode/system-requirements and
https://devimages-cdn.apple.com/downloads/xcode/simulators/index2.dvtdownloadableindex
