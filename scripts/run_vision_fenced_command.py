#!/usr/bin/env python3
"""The exclusive shell latch already exists before this interpreter starts."""
print('VISION_FENCE_PYTHON_ENTRY', flush=True)
import time
CLOCK_READY = {'monotonic': time.monotonic(), 'unix': time.time()}
print('VISION_FENCE_CLOCK_READY ' + repr(CLOCK_READY), flush=True)
import json
import os
from pathlib import Path
import sys
from owned_process_barrier import blocked
from vision_command_fence import VisionCommandFence
from watch_process import execute
IMPORTS_READY = {'monotonic': time.monotonic(), 'unix': time.time()}
print('VISION_FENCE_IMPORTS_READY ' + json.dumps(IMPORTS_READY), flush=True)


def main():
    if len(sys.argv) != 3:
        raise ValueError('Expected action and exact parent-shell nonce')
    action, nonce = sys.argv[1:]
    fence = VisionCommandFence(action, nonce)
    try:
        fence.activate()
        seconds = 90 if action == 'install' else 45
        command = fence.command()
        if blocked(command):
            raise ValueError('Existing cleanup barrier forbids this owned command')
        print('BOUNDED_COMMAND_START ' + json.dumps({'seconds': seconds, 'command': command}), flush=True)
        timing = {'clock_ready': CLOCK_READY, 'imports_ready': IMPORTS_READY,
                  'before_execute': {'monotonic': time.monotonic(), 'unix': time.time()}}
        def started(pid):
            timing['child_started'] = {'monotonic': time.monotonic(), 'unix': time.time()}
            print('VISION_FENCE_CHILD_STARTED ' + json.dumps({'action': action, 'pid': pid, 'nonce': nonce, **timing['child_started']}), flush=True)
        code, _, operation = execute(command, seconds, output_limit=16 * 1024 * 1024, tail_limit=64 * 1024, on_spawn=started)
        timing['command_finished'] = {'monotonic': time.monotonic(), 'unix': time.time()}
        print('BOUNDED_COMMAND_END ' + json.dumps(operation), flush=True)
        receipt = {**fence.expected, 'controller_pid': os.getpid(), 'operation': operation,
                   'command_exit': code, 'cleanup_confirmed': operation.get('cleanup_confirmed') is True,
                   'timing_observations': timing}
        target = Path('build/vision-runtime')
        target.mkdir(exist_ok=True)
        fence.current()
        if target.resolve(strict=True) != target.absolute():
            raise ValueError('Receipt directory must be canonical')
        data = (json.dumps(receipt, allow_nan=False, indent=2) + '\n').encode()
        if len(data) > 16 * 1024:
            raise ValueError('Command receipt exceeded its bound')
        directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            descriptor = os.open('fenced-' + action + '.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
            info = os.fstat(directory); current = target.stat()
            if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                raise ValueError('Receipt directory changed')
        finally:
            os.close(directory)
        if operation.get('cleanup_confirmed') is not True or blocked(command):
            return 126
        fence.clear_confirmed(operation)
        print('VISION_FENCE_CLEARED_CONFIRMED ' + action, flush=True)
        return code
    finally:
        fence.close() # Unknown/failed bootstrap never deletes the durable latch.


if __name__ == '__main__':
    try:
        result = main()
    except BaseException as error:
        # Shell ownership outlives the controller. A missing/replaced latch or
        # failed receipt must not be mistaken for ordinary confirmed completion.
        print('VISION_FENCE_CONTROLLER_UNCONFIRMED ' + type(error).__name__, flush=True)
        result = 126
    raise SystemExit(result)
