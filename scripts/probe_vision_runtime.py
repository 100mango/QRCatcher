#!/usr/bin/env python3
"""Bounded real simulator boot; preserve command evidence even if cleanup fails."""
import json,os,pathlib,signal,subprocess,time
out=pathlib.Path('build/vision-runtime');out.mkdir(parents=True,exist_ok=True)
report={'stage':'runtime_boot','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'ready':False,'operations':[]}
def record():
 (out/'runtime.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,arguments,timeout):
 operation={'label':label,'command':arguments,'timeout_seconds':timeout,'state':'starting'}
 report['operations'].append(operation);record();started=time.monotonic()
 p=subprocess.Popen(arguments,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
 operation.update(pid=p.pid,state='running');record()
 output=''
 try:
  output,_=p.communicate(timeout=timeout);operation.update(state='completed',exit=p.returncode);return p.returncode,output
 except subprocess.TimeoutExpired as error:
  operation['state']='timed_out';operation['exit']=124
  partial=error.output or '';output=partial.decode(errors='replace') if isinstance(partial,bytes) else partial
  # Never let process-group cleanup hide the actual timed-out command/result.
  try:os.killpg(p.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  except PermissionError as cleanup:
   operation['group_cleanup_error']=str(cleanup)
   # Stop only our own Popen child; do not signal privileged simulator helpers.
   try:p.terminate()
   except (ProcessLookupError,PermissionError) as child_error:operation['child_cleanup_error']=str(child_error)
  try:output,_=p.communicate(timeout=10)
  except subprocess.TimeoutExpired:
   try:p.kill()
   except (ProcessLookupError,PermissionError) as child_error:operation['child_kill_error']=str(child_error)
   try:output,_=p.communicate(timeout=5)
   except subprocess.TimeoutExpired:operation['child_still_running']=True
  return 124,output+'\nBOUNDED_TIMEOUT\n'
 finally:
  operation['elapsed_seconds']=round(time.monotonic()-started,2)
  (out/(label+'.log')).write_text(output[-256*1024:]);record()
try:
 devices=json.loads(subprocess.check_output(['xcrun','simctl','list','devices','available','-j'],timeout=30))
 candidates=[(runtime,d) for runtime,rows in devices['devices'].items() if runtime.endswith('xrOS-27-0') for d in rows]
 if not candidates:raise RuntimeError('No available installed visionOS27 simulator device was discovered')
 runtime,device=candidates[0];report.update(runtime=runtime,device=device);record()
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('VISION_SIMULATOR_ID='+device['udid']+'\n')
 boot_code,boot=run('boot',['xcrun','simctl','boot',device['udid']],180)
 report['boot_exit']=boot_code;record()
 status_code,status=run('bootstatus',['xcrun','simctl','bootstatus',device['udid'],'-b'],420)
 report['bootstatus_exit']=status_code;record()
 if status_code!=0:raise RuntimeError('Installed visionOS simulator did not finish booting within the bounded route')
 report['ready']=True
 report['readiness_scope']='Boot completed; actual app install/launch/XCTest is the next required gate'
except Exception as error:report['environment_observation']=str(error)
finally:
 record();print(json.dumps(report,indent=2),flush=True)
 with open(os.environ['GITHUB_ENV'],'a') as f:f.write('VISION_READY='+str(report['ready']).lower()+'\n')
if not report['ready']:raise SystemExit('Vision runtime readiness was not established; see runtime.json. This is not an app-test result.')
