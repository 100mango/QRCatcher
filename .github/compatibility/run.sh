#!/bin/bash
# Supplemental compatibility harness. App sources and test targets stay frozen.
set -euo pipefail
stage="${1:?stage}"
cd "$GITHUB_WORKSPACE/app"
case "$APP_REPOSITORY" in
  100mango/Celluloid) project=Celluloid.xcodeproj; scheme=Celluloid; unit=CelluloidTests; ui=CelluloidUITests; generator=Scripts/generate_project.py; bundle=Mango.Celluloid ;;
  100mango/QRCatcher) project=QRCatcher.xcodeproj; scheme=QRCatcher; unit=QRCatcherTests; ui=QRCatcherUITests; generator=scripts/generate_project.py; bundle=100mango.QRCatcher ;;
  100mango/ColorPicker) project=TouchColor.xcodeproj; scheme=TouchColor; unit=TouchColorTests; ui=TouchColorUITests; generator=scripts/generate_project.py; bundle=Mango.TouchColor ;;
  *) echo 'Unexpected repository'; exit 1;;
esac
results="$RUNNER_TEMP/compatibility"
mkdir -p "$results"
command_log() {
  local label="$1"; shift
  set +e
  "$@" > "$results/$label.log" 2>&1
  local status=$?
  set -e
  echo "$label exit=$status"
  grep -E "Test Suite .* (passed|failed)|Executed [0-9]+ tests|error:|warning:|\\*\\* (BUILD|TEST)" "$results/$label.log" | tail -n 90 || true
  if [ "$status" -ne 0 ]; then tail -n 100 "$results/$label.log"; fi
  return "$status"
}
verify_source() {
  test "$(git rev-parse HEAD)" = "$APP_SHA"
  git diff --exit-code HEAD --
  echo "APP_PROVENANCE repository=$APP_REPOSITORY commit=$(git rev-parse HEAD) tree=$(git rev-parse 'HEAD^{tree}')"
}
case "$stage" in
  validate)
    verify_source
    sw_vers; uname -m; xcodebuild -version; xcodebuild -showsdks
    xcodebuild -version | grep '^Xcode 16.2$'
    xcodebuild -version | grep '^Build version 16C5032a$'
    python3 "$generator"
    verify_source
    xcrun simctl list runtimes -j > "$results/runtimes.json"
    xcrun simctl list devices available -j > "$results/devices.json"
    python3 - "$results" <<'PY'
import json, os, pathlib, sys
root=pathlib.Path(sys.argv[1])
runtimes=[r for r in json.loads((root/'runtimes.json').read_text())['runtimes'] if r.get('isAvailable') and r.get('platform')=='iOS' and 'beta' not in r['name'].lower()]
print('ACTUAL_IOS_RUNTIMES', json.dumps([{k:r[k] for k in ('identifier','version','buildversion')} for r in runtimes]))
# XCTest targets checked into all three projects require 17; preserve that boundary.
eligible=sorted((r for r in runtimes if tuple(map(int,r['version'].split('.'))) >= (17,)),key=lambda r:tuple(map(int,r['version'].split('.'))))
assert eligible, 'No stable runtime compatible with the unmodified XCTest targets'
runtime=eligible[0]
devices=json.loads((root/'devices.json').read_text())['devices'][runtime['identifier']]
device=next(d for d in devices if d.get('isAvailable') and d['name']==os.environ['DEVICE_NAME'])
evidence={'runtime':{k:runtime[k] for k in ('identifier','version','buildversion')},'device':{k:device[k] for k in ('name','udid','deviceTypeIdentifier')}}
(root/'selection.json').write_text(json.dumps(evidence,indent=2)+'\n')
print('SELECTED_ENVIRONMENT',json.dumps(evidence))
with open(os.environ['GITHUB_ENV'],'a') as f:f.write('SIMULATOR_ID='+device['udid']+'\n')
PY
    ;;
  build)
    command_log build xcodebuild -project "$project" -scheme "$scheme" -configuration Debug -destination "platform=iOS Simulator,id=$SIMULATOR_ID" -derivedDataPath "$results/DerivedData" build-for-testing CODE_SIGNING_ALLOWED=NO
    shasum -a 256 "$results/DerivedData/Build/Products/Debug-iphonesimulator/$scheme.app/$scheme"
    verify_source
    ;;
  prepare)
    xcrun simctl boot "$SIMULATOR_ID" || true
    xcrun simctl bootstatus "$SIMULATOR_ID" -b
    xcrun simctl spawn "$SIMULATOR_ID" launchctl print system >/dev/null
    if [ "$scheme" = Celluloid ]; then
      python3 Scripts/create_fixture.py
      xcrun simctl addmedia "$SIMULATOR_ID" /tmp/celluloid-fixture.png /tmp/celluloid-fixture-2.png
      xcrun simctl install "$SIMULATOR_ID" "$results/DerivedData/Build/Products/Debug-iphonesimulator/Celluloid.app"
      xcrun simctl privacy "$SIMULATOR_ID" grant photos "$bundle"
    elif [ "$scheme" = TouchColor ]; then
      python3 - "$results/red.png" <<'PY'
import struct,zlib,sys
w=h=200
chunk=lambda name,data:struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
open(sys.argv[1],'wb').write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\0\0'*w)*h))+chunk(b'IEND',b''))
PY
      xcrun simctl addmedia "$SIMULATOR_ID" "$results/red.png"
    fi
    ;;
  unit|ui)
    suite="$unit"; [ "$stage" != ui ] || suite="$ui"
    command_log "$stage" xcodebuild -project "$project" -scheme "$scheme" -configuration Debug -destination "platform=iOS Simulator,id=$SIMULATOR_ID" -derivedDataPath "$results/DerivedData" -resultBundlePath "$results/$stage.xcresult" -parallel-testing-enabled NO -collect-test-diagnostics never -test-timeouts-enabled YES -default-test-execution-time-allowance 180 -maximum-test-execution-time-allowance 240 -only-testing:"$suite" test-without-building CODE_SIGNING_ALLOWED=NO
    ;;
  summarize)
    verify_source
    [ ! -f "$results/selection.json" ] || cat "$results/selection.json"
    for result in "$results"/*.xcresult; do
      [ -f "$result/Info.plist" ] || continue
      xcrun xcresulttool get test-results summary --path "$result" | tee -a "$GITHUB_STEP_SUMMARY"
    done
    # Only already-bounded synthetic screenshot blocks from checked-in tests are emitted.
    python3 - "$results/ui.log" <<'PY'
import pathlib,re,sys
p=pathlib.Path(sys.argv[1]); lines=p.read_text(errors='replace').splitlines() if p.exists() else []
blocks=[]; current=None
for line in lines:
    if 'SCREENSHOT_BEGIN:' in line:current=[line]
    elif current is not None:
        current.append(line)
        if 'SCREENSHOT_END:' in line:
            if sum(len(x) for x in current)<=800000:blocks.append(current)
            current=None
for block in blocks[:2]:print('\n'.join(block))
PY
    ;;
  shutdown)
    [ -z "${SIMULATOR_ID:-}" ] || xcrun simctl shutdown "$SIMULATOR_ID" || true
    ;;
  *) exit 2 ;;
esac
