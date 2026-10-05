#!/bin/bash
# LOCAL PROPOSAL. Invoke only inside the existing owned device lifetime.
# Argument 3 is the ORIGINAL parent-step monotonic origin, never a fresh clock.
# The caller must capture it once at that step's start and preserve it unchanged.
set -euo pipefail
PLATFORM="${1:-}"; DEVICE="${2:-}"; PARENT_START="${3:-}"
case "$PLATFORM:${EVIDENCE_SCOPE:-}" in watch:watchos) EXPECTED_DEVICE="${WATCH_SIMULATOR_ID:-}" ;; tv:tvos) EXPECTED_DEVICE="${TV_SIMULATOR_ID:-}" ;; *) exit 2 ;; esac
[[ "$DEVICE" == "$EXPECTED_DEVICE" && "$DEVICE" =~ ^[A-F0-9-]{36}$ ]]
[[ "$PARENT_START" =~ ^[0-9]{1,12}([.][0-9]{1,9})?$ ]]
[[ "${GITHUB_REPOSITORY:-}" == '100mango/QRCatcher' ]]
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ && "${GITHUB_WORKFLOW_SHA:-}" == "$GITHUB_SHA" ]]
[[ "${PWD:-}" == "${GITHUB_WORKSPACE:-}" && "$PWD" == "$(builtin pwd -P)" ]]
[[ -d build && ! -L build ]]
LATCH='build/settings-discovery-inflight.json'
for PATH_TO_CHECK in "$LATCH" build/owned-process-cleanup.json build/vision-command-inflight.json build/fixture-query-inflight.json "build/settings-discovery-$PLATFORM" "build/settings-discovery-$PLATFORM-fence.json"; do
    if [[ -e "$PATH_TO_CHECK" || -L "$PATH_TO_CHECK" ]]; then exit 126; fi
done
[[ "${QRCATCHER_OWNED_CLEANUP_UNCONFIRMED:-}" != true ]]
NONCE="${RANDOM}-${RANDOM}-$$"
# This exclusive, owner-only latch exists BEFORE launching any Python process.
if ! (umask 077; set -o noclobber; printf '{"version":1,"source":"%s","device":"%s","scope":"%s","platform":"%s","owner_pid":%s,"nonce":"%s","parent_started_monotonic":"%s"}\n' \
    "$GITHUB_SHA" "$DEVICE" "$EVIDENCE_SCOPE" "$PLATFORM" "$$" "$NONCE" "$PARENT_START" > "$LATCH"); then exit 126; fi
printf 'SETTINGS_FENCE_BEFORE_PYTHON platform=%s nonce=%s\n' "$PLATFORM" "$NONCE"
set +e
python3 -u scripts/run_settings_discovery_fenced.py "$PLATFORM" "$DEVICE" "$NONCE" "$PARENT_START"
STATUS=$?
set -e
if [[ "$STATUS" != 2 || -e "$LATCH" || -L "$LATCH" || ! -f "build/settings-discovery-$PLATFORM-fence.json" ]]; then
    # Even if a replaced/missing latch concealed the failure, later steps stop.
    export QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true
    if [[ -n "${GITHUB_ENV:-}" ]]; then printf 'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true\n' >> "$GITHUB_ENV"; fi
    printf 'SETTINGS_FENCE_UNRESOLVED_RETAINED\n'
    exit 126
fi
# Diagnostic completion NEVER changes the original lane's red acceptance result.
exit 2
