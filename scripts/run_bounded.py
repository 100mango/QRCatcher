#!/usr/bin/env python3
"""Bound an owned command, including output ownership when descendants linger."""
import json,sys
from watch_process import execute
seconds=int(sys.argv[1]);command=sys.argv[2:];assert seconds>0 and command
print('BOUNDED_COMMAND_START '+json.dumps({'seconds':seconds,'command':command}),flush=True)
# Owning the pipe prevents a surviving child inheriting tee's output handle from
# holding the shell pipeline open after our exact CLI process is terminated.
# Never restart daemons or signal privileged helpers/process groups.
code,_,operation=execute(command,seconds,output_limit=16*1024*1024,tail_limit=64*1024)
print('BOUNDED_COMMAND_END '+json.dumps(operation),flush=True)
sys.exit(code)
