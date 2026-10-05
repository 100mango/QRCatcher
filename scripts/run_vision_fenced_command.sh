#!/bin/bash
# Source this entry in the existing workflow shell, before any Python process.
# An interrupted bootstrap leaves this exclusive latch for the global barrier.
set -euo pipefail
ACTION="${1:-}"
printf 'VISION_FENCE_SHELL_ENTRY action=%s shell_elapsed_seconds=%s\n' "$ACTION" "$SECONDS"
case "$ACTION" in install|shutdown) ;; *) exit 2 ;; esac
case "${EVIDENCE_SCOPE:-}" in visionos_photos|visionos_files|visionos_chinese|visionos_largest) ;; *) exit 2 ;; esac
[[ "${GITHUB_REPOSITORY:-}" == '100mango/QRCatcher' ]]
[[ "${GITHUB_SHA:-}" =~ ^[0-9a-f]{40}$ ]]
[[ "${VISION_SIMULATOR_ID:-}" =~ ^[A-F0-9-]{36}$ ]]
[[ "${PWD:-}" == "${GITHUB_WORKSPACE:-}" && "$PWD" == "$(builtin pwd -P)" ]]
[[ -d build && ! -L build ]]
LATCH='build/vision-command-inflight.json'
if [[ "${QRCATCHER_OWNED_CLEANUP_UNCONFIRMED:-}" == true || -e build/owned-process-cleanup.json || -L build/owned-process-cleanup.json || -e "$LATCH" || -L "$LATCH" || -e build/fixture-query-inflight.json || -L build/fixture-query-inflight.json || -e build/settings-discovery-inflight.json || -L build/settings-discovery-inflight.json ]]; then
    printf 'VISION_FENCE_BLOCKED_EXISTING_UNCERTAINTY\n'
    exit 126
fi
if [[ -e "build/vision-runtime/fenced-$ACTION.json" || -L "build/vision-runtime/fenced-$ACTION.json" ]]; then
    printf 'VISION_FENCE_REFUSED_REPEAT_OPERATION\n'
    exit 126
fi
NONCE="${RANDOM}-${RANDOM}-$$"
# noclobber uses exclusive creation. Never overwrite or reset an old latch.
if ! (umask 077; set -o noclobber; printf '{"version":1,"source":"%s","device":"%s","scope":"%s","action":"%s","owner_pid":%s,"nonce":"%s"}\n' \
    "$GITHUB_SHA" "$VISION_SIMULATOR_ID" "$EVIDENCE_SCOPE" "$ACTION" "$$" "$NONCE" > "$LATCH"); then
    printf 'VISION_FENCE_EXCLUSIVE_CREATE_FAILED\n'
    exit 126
fi
printf 'VISION_FENCE_BEFORE_PYTHON action=%s nonce=%s shell_elapsed_seconds=%s\n' "$ACTION" "$NONCE" "$SECONDS"
set +e
python3 -u scripts/run_vision_fenced_command.py "$ACTION" "$NONCE"
STATUS=$?
set -e
printf 'VISION_FENCE_AFTER_PYTHON action=%s exit=%s\n' "$ACTION" "$STATUS"
if [[ "$STATUS" == 126 || -e "$LATCH" || -L "$LATCH" ]]; then
    printf 'QRCATCHER_OWNED_CLEANUP_UNCONFIRMED=true\n' >> "$GITHUB_ENV"
    printf 'VISION_FENCE_UNRESOLVED_RETAINED\n'
    exit 126
fi
return "$STATUS"
