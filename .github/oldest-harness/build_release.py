#!/usr/bin/env python3
"""Build pinned Release simulator binaries with SDK27, without test app hooks."""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import time

from bundle_archive import pack

ALLOWED = {
    "Celluloid": ("100mango/Celluloid", "Celluloid.xcodeproj", "Celluloid", "Mango.Celluloid"),
    "QRCatcher": ("100mango/QRCatcher", "QRCatcher.xcodeproj", "QRCatcher", "100mango.QRCatcher"),
    "TouchColor": ("100mango/ColorPicker", "TouchColor.xcodeproj", "TouchColor", "com.mango.touchColor"),
}


def checked_sources(path):
    data = json.loads(path.read_text())
    if data.get("ready") is not True or len(data.get("sources", [])) != 3:
        raise ValueError("Final integrated source manifest is not approved for qualification")
    rows = data["sources"]
    if {r.get("name") for r in rows} != set(ALLOWED):
        raise ValueError("Unexpected app inventory")
    for row in rows:
        if tuple(row.get(k) for k in ("repository", "project", "scheme", "bundle")) != ALLOWED[row["name"]]:
            raise ValueError("App identity mismatch")
        if any(not isinstance(row.get(k), str) or not re.fullmatch("[0-9a-f]{40}", row[k]) for k in ("commit", "tree")):
            raise ValueError("Exact commit and tree required")
    return rows


def output(command, cwd=None):
    return subprocess.check_output(command, cwd=cwd, text=True, timeout=60).strip()


def verify_source(root, row):
    if output(["git", "rev-parse", "HEAD"], root) != row["commit"] or output(["git", "rev-parse", "HEAD^{tree}"], root) != row["tree"]:
        raise ValueError("Source checkout differs from pinned commit/tree")
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=root, check=True, timeout=30)
    if output(["git", "ls-files", "--others", "--exclude-standard"], root):
        raise ValueError("Untracked source files are not allowed in the production build")


def bounded_build(command, cwd, log, timeout=900):
    started = time.monotonic()
    print("BUILD_COMMAND", command, flush=True)
    with log.open("x") as stream:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print("PROCESS_REAP_TIMEOUT after owned-group SIGKILL; abandon this VM lane", flush=True)
            print("BUILD_TIMEOUT", timeout, "seconds", flush=True)
            raise
    print("BUILD_FINISHED", code, "seconds", round(time.monotonic() - started, 1), flush=True)
    with log.open(errors="replace") as stream:
        tail = deque(stream, maxlen=80) if code else deque((line for line in stream if "warning:" in line or "** BUILD" in line), maxlen=60)
    for line in tail:
        print(line.rstrip())
    if code:
        raise subprocess.CalledProcessError(code, command)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = checked_sources(args.sources)
    if output(["xcodebuild", "-version"]).splitlines() != ["Xcode 27.0", "Build version 27A266a"]:
        raise ValueError("Exact stable SDK27 toolchain required")
    args.output.mkdir(parents=False, exist_ok=False)
    print("PRODUCER_HOST", output(["sw_vers"]), output(["uname", "-m"]))
    print("PRODUCER_SDK", output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"]))
    if output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"]) != "27.0":
        raise ValueError("Exact iOS27 SDK required")
    apps, provenance = [], []
    for row in rows:
        root = args.checkout_root / row["name"]
        verify_source(root, row)
        derived = args.output / (row["name"] + "-build")
        bounded_build(["xcodebuild", "-project", row["project"], "-scheme", row["scheme"], "-configuration", "Release", "-sdk", "iphonesimulator", "-destination", "generic/platform=iOS Simulator", "-derivedDataPath", str(derived), "-clonedSourcePackagesDirPath", str(args.output / "SourcePackages"), "CODE_SIGNING_ALLOWED=NO", "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "build"], root, args.output / (row["name"] + "-build.log"))
        verify_source(root, row)
        app = derived / "Build/Products/Release-iphonesimulator" / (row["name"] + ".app")
        info = plistlib.loads((app / "Info.plist").read_bytes())
        for key, expected in [("CFBundleIdentifier", row["bundle"]), ("MinimumOSVersion", "15.0"), ("DTXcodeBuild", "27A266a"), ("DTSDKName", "iphonesimulator27.0")]:
            if info.get(key) != expected:
                raise ValueError("Built app metadata mismatch: " + key)
        binary = app / info["CFBundleExecutable"]
        arch = output(["xcrun", "lipo", "-archs", str(binary)])
        if arch != "arm64":
            raise ValueError("Only the arm64 simulator slice is expected")
        load_commands = output(["xcrun", "vtool", "-show-build", str(binary)])
        if not re.search(r"platform\s+IOSSIMULATOR", load_commands) or not re.search(r"sdk\s+27\.0(?:\s|$)", load_commands) or not re.search(r"minos\s+15\.0(?:\s|$)", load_commands):
            raise ValueError("Built app Mach-O platform, SDK or minimum mismatch")
        print("BINARY_LOAD_COMMANDS", row["name"], load_commands)
        provenance.append({**row, "configuration": "Release", "arch": arch, "sdk": "27.0", "minimum": "15.0", "xcode": "27.0 (27A266a)", "version": info.get("CFBundleShortVersionString"), "build": info.get("CFBundleVersion"), "macho": load_commands})
        apps.append(app)
    result = pack(apps, provenance, args.output / "sdk27-release-apps.zip")
    print("BOUNDED_BINARY_TRANSFER", json.dumps(result, sort_keys=True))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            stream.write("archive_sha256=" + result["sha256"] + "\n")


if __name__ == "__main__": main()
