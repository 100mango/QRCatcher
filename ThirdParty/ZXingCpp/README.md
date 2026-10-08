# Pinned QR-only ZXing-C++

Official source: https://github.com/zxing-cpp/zxing-cpp
Release v3.1.1, commit 287c85df6f961c8efbfb5ffd736cd9457b8b890e.

Only the listed core/QR reader translation units and required headers are built.
Writers, other symbologies, examples, test dependencies and zint are disabled.
Upstream files are unmodified; Config/Version.h is derived from the upstream
CMake template with the recorded options. Every file hash is in source-manifest.
The app's bounded C ABI and CoreGraphics bridge are in Shared/PortableQR.

Apache 2.0 and embedded libzueci/Bjoern Hoehrmann notices are retained in source
and bundled in ThirdPartyNotices.txt. No upstream NOTICE file was present.

Reproducible local ASan/UBSan evaluation: python3 Tests/PortableQR/run_sanitizers.py
from the repository root, with already installed GCC/G++, Pillow and ReportLab.
This command downloads or installs nothing. It exercises the production C ABI
on 44 unique synthetic cases, including ECI, rotation, maximum size, malformed
input, and 32/33-symbol budget boundaries. LeakSanitizer is explicitly excluded
on the ptraced cloud host. Linux proof does not establish Apple load/runtime.
