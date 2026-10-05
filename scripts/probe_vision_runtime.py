#!/usr/bin/env python3
"""Same bounded boot route, with durable ownership before every device command."""
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
from atomic_json import write_json
from owned_process_barrier import blocked, mark_unconfirmed
from vision_command_fence import VisionCommandFence, NAME
from watch_process import execute

SCOPES = {'visionos_photos', 'visionos_files', 'visionos_chinese', 'visionos_largest'}
ALREADY_BOOTED = ('An error was encountered processing the command (domain=com.apple.CoreSimulator.SimError, code=405):\n'
                  'Unable to boot device in current state: Booted')


def require(value, message):
    if not value: raise ValueError(message)


def claim(action, root):
    require(action in {'inventory', 'boot', 'bootstatus'}, 'Unknown bootstrap command')
    require(not blocked(), 'Existing uncertainty forbids bootstrap')
    nonce = f'{uuid.uuid4().int % 32768}-{uuid.uuid4().int % 32768}-{os.getppid()}'
    value = dict(version=1, source=os.environ['GITHUB_SHA'],
                 device=None if action == 'inventory' else os.environ['VISION_SIMULATOR_ID'],
                 scope=os.environ['EVIDENCE_SCOPE'], action=action, owner_pid=os.getppid(), nonce=nonce)
    raw = (json.dumps(value) + '\n').encode()
    # The same existing latch is established before dispatch. No overwrite,
    # new marker namespace, alternate device or replay of a consumed grant.
    parent = root/'build'
    require(parent.is_dir() and not parent.is_symlink() and parent.resolve(strict=True) == parent, 'Noncanonical build parent')
    fd = os.open(parent/NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fence = VisionCommandFence(action, nonce)
    try:
        fence.activate()
        return fence
    except BaseException:
        fence.close()
        raise


def main():
    # A fresh interpreter must not issue even inventory after earlier uncertainty.
    if blocked(): return 126
    root = Path.cwd().resolve()
    report = {'stage': 'runtime_boot', 'source_commit': os.environ.get('GITHUB_SHA'), 'ready': False, 'operations': []}
    out = root/'build/vision-runtime'
    active_operation = {'state': 'probe_not_started', 'exit': 126}
    fence = None
    try:
        require(os.environ.get('GITHUB_WORKSPACE') == str(root) and
                os.environ.get('GITHUB_REPOSITORY') == '100mango/QRCatcher' and
                os.environ.get('EVIDENCE_SCOPE') in SCOPES and
                re.fullmatch('[0-9a-f]{40}', os.environ.get('GITHUB_SHA', '')), 'Wrong bootstrap source/workspace/scope')
        require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == report['source_commit'], 'Wrong checked-out source')
        require(out.parent.is_dir() and not out.parent.is_symlink() and out.parent.resolve(strict=True) == out.parent, 'Missing canonical build directory')
        out.mkdir(exist_ok=True)
        require(not out.is_symlink() and out.resolve(strict=True) == out, 'Aliased runtime evidence directory')

        def record():
            write_json(out/'runtime.json', report, limit=16*1024)

        def run(action, validate):
            nonlocal active_operation
            require(fence.expected['action'] == action, 'Unexpected bootstrap phase')
            command, seconds = fence.command(), fence.seconds()
            row = {'label': action, 'command': command, 'timeout_seconds': seconds, 'state': 'starting'}
            report['operations'].append(row)
            active_operation = row
            try:
                record()
                def started(pid):
                    row.update(pid=pid, state='running'); record()
                code, output, operation = execute(command, seconds, output_limit=2*1024*1024,
                                                   tail_limit=256*1024, echo=False, on_spawn=started)
                confirmed = fence.observe(operation, code)
                row.update(operation, device_command_completion_confirmed=confirmed,
                           output_tail=output.encode()[-2048:].decode(errors='replace'))
                active_operation = row
                (out/(action+'.log')).write_text(output[-256*1024:])
                record()
                require(confirmed, 'Bootstrap device command completion is uncertain')
                result = validate(code, output)
                # Validation precedes the in-owner transition. The latch is
                # retained until all phases and the final readiness receipt.
                record()
                return result
            except BaseException:
                row['device_command_completion_confirmed'] = False
                fence.uncertain = True
                raise

        def inventory(code, output):
            require(code == 0, 'Simulator inventory did not complete successfully')
            value = json.loads(output)
            candidates = [(runtime, item) for runtime, rows in value['devices'].items()
                          if runtime.endswith('xrOS-27-0') for item in rows]
            require(candidates, 'No available installed visionOS27 simulator device was discovered')
            runtime, device = candidates[0]  # Preserve original target/order.
            require(str(uuid.UUID(device['udid'])).upper() == device['udid'], 'Invalid selected device identity')
            return runtime, device

        fence = claim('inventory', root)
        runtime, device = run('inventory', inventory)
        report.update(runtime=runtime, device=device)
        os.environ['VISION_SIMULATOR_ID'] = device['udid']
        with open(os.environ['GITHUB_ENV'], 'a') as stream: stream.write('VISION_SIMULATOR_ID='+device['udid']+'\n')

        def boot(code, output):
            report['boot_exit'] = code
            require(code == 0 or (code == 149 and device.get('state') == 'Booted' and output.strip() == ALREADY_BOOTED),
                    'Boot failed or returned an unrecognized already-booted response')

        fence.advance_probe('boot', device['udid'])
        run('boot', boot)
        def bootstatus(code, output):
            report['bootstatus_exit'] = code
            require(code == 0, 'Installed visionOS simulator did not finish booting within the bounded route')
        fence.advance_probe('bootstatus', device['udid'])
        run('bootstatus', bootstatus)
        report['ready'] = True
        report['readiness_scope'] = 'Boot completed; actual app install/launch/XCTest is the next required gate'
        record()
        with open(os.environ['GITHUB_ENV'], 'a') as stream: stream.write('VISION_READY=true\n')
        fence.clear_confirmed(active_operation)
        print(json.dumps(report, indent=2), flush=True)
        return 0
    except BaseException as error:
        if fence is not None: fence.uncertain = True
        report['environment_observation'] = str(error)
        report['ready'] = False
        # Preserve known host-cleanup facts; the device outcome is separately
        # uncertain. The existing latch is never removed on this path.
        observation = dict(active_operation, state='vision_bootstrap_uncertain', original_exit=active_operation.get('exit'))
        try: mark_unconfirmed(observation)
        except (OSError, ValueError): pass  # The pre-dispatch latch remains.
        try:
            if out.is_dir() and not out.is_symlink(): write_json(out/'runtime.json', report, limit=16*1024)
        except (OSError, ValueError): pass
        try:
            with open(os.environ['GITHUB_ENV'], 'a') as stream: stream.write('VISION_READY=false\n')
        except (OSError, KeyError): pass
        print(json.dumps(report, indent=2), flush=True)
        return 126
    finally:
        if fence is not None: fence.close()


if __name__ == '__main__':
    raise SystemExit(main())
