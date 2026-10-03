"""Bound one owned command with live optional output and a bounded retained tail."""
import os,selectors,subprocess,sys,time

def execute(args,seconds=120,output_limit=2*1024*1024,tail_limit=512*1024,echo=True):
 started=time.monotonic();operation={'command':args,'timeout_seconds':seconds}
 process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
 selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
 tail=bytearray();total=0;forced=None;ended=None
 try:
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
  if forced is not None:
   # Stop only our owned CLI child, never simulator daemons or privileged helpers.
   try:
    process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
   except (PermissionError,ProcessLookupError,subprocess.TimeoutExpired) as error:operation['cleanup_error']=str(error)
  if forced is None:
   try:code=process.wait(timeout=max(.1,seconds-(time.monotonic()-started)))
   except subprocess.TimeoutExpired:
    forced=124;process.terminate()
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    code=124
  else:code=forced
 finally:selector.close();process.stdout.close()
 operation.update(state='completed' if forced is None else ('timed_out' if forced==124 else 'output_limit'),exit=code,output_bytes=total,elapsed_seconds=round(time.monotonic()-started,2))
 return code,tail.decode(errors='replace'),operation
