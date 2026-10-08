"""Bound one owned command with live optional output and a bounded retained tail."""
import os,selectors,subprocess,sys,time
from owned_process_group import stop_group
from owned_process_barrier import blocked,mark_unconfirmed

def execute(args,seconds=120,output_limit=2*1024*1024,tail_limit=512*1024,echo=True,on_spawn=None):
 if blocked(args):return 126,'',{'command':args,'state':'blocked_owned_process_cleanup_unconfirmed','exit':126,'cleanup_confirmed':False}
 started=time.monotonic();operation={'command':args,'timeout_seconds':seconds}
 process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
 tail=bytearray();total=0;forced=None;ended=None
 try:
  if on_spawn is not None:on_spawn(process.pid)
  while selector.get_map():
   for key,_ in selector.select(timeout=.5):
    chunk=os.read(key.fileobj.fileno(),65536)
    if not chunk:selector.unregister(key.fileobj);continue
    total+=len(chunk);tail.extend(chunk)
    if len(tail)>tail_limit:del tail[:-tail_limit]
    if echo and total<=output_limit:sys.stdout.buffer.write(chunk);sys.stdout.buffer.flush()
   if total>output_limit:forced=125;break
   if time.monotonic()-started>seconds:forced=124;break
   if process.poll() is not None:
    if ended is None:ended=time.monotonic()
    if time.monotonic()-ended>2:break
  if forced is None:
   try:code=process.wait(timeout=max(.1,seconds-(time.monotonic()-started)))
   except subprocess.TimeoutExpired:
    forced=124;code=124
  else:code=forced
 finally:
  # Covers ordinary leader exit as well as timeout/output limits. An inherited
  # pipe or reaped session leader cannot conceal a still-live owned group.
  try:operation['cleanup_confirmed']=stop_group(process)
  except (PermissionError,ProcessLookupError,OSError) as error:
   operation['cleanup_confirmed']=False;operation['cleanup_error']=str(error)
  selector.close();process.stdout.close()
 if not operation['cleanup_confirmed'] or code==126:
  operation['original_exit']=code;forced=126;code=126
  operation['cleanup_confirmed']=False
 operation.update(state='completed' if forced is None else ('timed_out' if forced==124 else 'output_limit'),exit=code,output_bytes=total,elapsed_seconds=round(time.monotonic()-started,2))
 if not operation['cleanup_confirmed']:operation['state']='cleanup_unconfirmed'
 if not operation['cleanup_confirmed']:mark_unconfirmed(operation)
 return code,tail.decode(errors='replace'),operation
