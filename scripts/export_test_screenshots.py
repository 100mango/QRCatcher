#!/usr/bin/env python3
"""Stream only bounded, named synthetic XCTest JPEGs after tests have finished."""
import base64
import json
import pathlib
import subprocess

NAMES = ("synthetic-scan-result", "synthetic-history", "privacy-open-diagnostic", "privacy-return-diagnostic")


def records(value):
    if isinstance(value, dict):
        if "exportedFileName" in value:
            yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


for result, device in (("TestResults.xcresult", "large-phone"), ("CompactTestResults.xcresult", "SE3")):
    if not pathlib.Path(result, "Info.plist").is_file():
        continue
    destination = pathlib.Path("build", "test-screenshots", device)
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", result, "--output-path", str(destination)], check=True)
    manifest = json.loads((destination / "manifest.json").read_text())
    count = 0
    for attachment in records(manifest):
        label = " ".join(value for value in attachment.values() if isinstance(value, str))
        name = next((name for name in NAMES if name in label), None)
        if name is None:
            continue
        path = (destination / attachment["exportedFileName"]).resolve()
        assert path.is_relative_to(destination.resolve()), "Unexpected attachment path"
        data = path.read_bytes()
        assert data.startswith(b"\xff\xd8") and len(data) <= 500 * 1024, "Evidence must be a bounded JPEG"
        encoded = base64.b64encode(data).decode("ascii")
        print(f"SCREENSHOT_BEGIN:{device}-{name}")
        print(f"SCREENSHOT_BYTES:{len(data)}")
        for index in range(0, len(encoded), 4096):
            print("SCREENSHOT_CHUNK:" + encoded[index:index + 4096])
        print(f"SCREENSHOT_END:{device}-{name}")
        count += 1
    print(f"Exported {count} named synthetic screenshots from {result}")
    if count == 0:
        # Retain enough schema evidence to diagnose an exporter change; do not
        # silently claim that the requested screenshots were captured.
        print(json.dumps(manifest, ensure_ascii=False)[:20000])
        raise SystemExit("No expected named screenshot attachments were exported")
