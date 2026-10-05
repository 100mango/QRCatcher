#!/usr/bin/env python3
"""Shell latch precedes Python startup; read-only discovery stays unqualified."""
print('SETTINGS_FENCE_PYTHON_ENTRY', flush=True)
import sys
from settings_discovery_fence import SettingsDiscoveryFence


def main():
    if len(sys.argv) != 5:
        raise ValueError('Expected platform, owned device, shell nonce, original parent-step clock')
    with SettingsDiscoveryFence(*sys.argv[1:]) as claim:
        claim.activate()
        if not claim.admitted():
            claim.finish_without_commands('insufficient_existing_parent_step_budget')
            return 2
        # Import after activation: failed imports leave the durable shell latch.
        import discover_native_settings as discovery
        report = discovery.discover(claim.platform, claim.device, runner=claim.run)
        claim.finish(report)
        return 2


if __name__ == '__main__':
    try:
        result = main()
    except BaseException as error:
        print('SETTINGS_FENCE_CONTROLLER_UNCONFIRMED ' + type(error).__name__, flush=True)
        result = 126
    raise SystemExit(result)
