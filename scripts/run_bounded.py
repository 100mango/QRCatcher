#!/usr/bin/env python3
"""Bound one owned command and retain timeout identity without privileged cleanup."""
import json,subprocess,sys,time
seconds=int(sys.argv[1]);command=sys.argv[2:];assert seconds>0 and command
start=time.monotonic();print('BOUNDED_COMMAND_START '+json.dumps({'seconds':seconds,'command':command}),flush=True)
process=subprocess.Popen(command)
try:code=process.wait(timeout=seconds)
except subprocess.TimeoutExpired:
 code=124;print('BOUNDED_COMMAND_TIMEOUT '+json.dumps({'pid':process.pid,'command':command}),flush=True)
 try:
  process.terminate()
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
 except (PermissionError,ProcessLookupError,subprocess.TimeoutExpired) as error:print('BOUNDED_OWN_CHILD_CLEANUP '+str(error),flush=True)
print('BOUNDED_COMMAND_END '+json.dumps({'exit':code,'elapsed_seconds':round(time.monotonic()-start,2),'command':command}),flush=True)
sys.exit(code)
