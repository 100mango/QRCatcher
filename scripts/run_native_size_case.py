#!/usr/bin/env python3
"""Run one existing native UI case at an actually read-back system text size."""
import json,sys
from pathlib import Path
from simulator_content_size import probe
from owned_process_barrier import mark_unconfirmed

CONFIG={
 'watch':('Watch','watchOS Simulator','testFixtureFedOfflineResultSourceImageAndRelaunch',240,'build/watch-runtime/system-content-size.json','WatchLargestUIResults.xcresult'),
 'vision':('Vision','visionOS Simulator','testChineseEmptyPhotosResultAndOfflinePolicy',300,'build/vision-runtime/system-content-size.json','VisionLargestUIResults.xcresult'),
 'tv':('TV','tvOS Simulator','testExplicitlyPreconditionedPhotosDecodeExportAndReopen',420,'build/native-release-evidence/tv-system-content-size.json','TVLargestUIResults.xcresult'),
}

def run_case(platform,device,precondition=True):
 label,destination,case,cap,report_file,result=CONFIG[platform]
 root=Path.cwd().resolve();target='QRCatcher'+label+'UITests';scheme='QRCatcher'+label
 command=['xcodebuild','test-without-building','-project',str(root/'QRCatcher.xcodeproj'),'-scheme',scheme,
  '-configuration','Debug','-derivedDataPath',str(root/'build'/(label+'Tests')),
  '-destination','platform='+destination+',id='+device,'-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
  '-test-timeouts-enabled','YES','-default-test-execution-time-allowance','180','-maximum-test-execution-time-allowance','240',
  '-only-testing:'+target+'/'+target+'/'+case,'-resultBundlePath',str(root/result),'CODE_SIGNING_ALLOWED=NO']
 contract=dict(root=str(root),project='QRCatcher.xcodeproj',scheme=scheme,derived_data='build/'+label+'Tests',test_bundle=target,platform=destination)
 path=root/report_file;path.parent.mkdir(parents=True,exist_ok=True)
 try:report=probe(device,path,command if precondition else None,cap,expected_ui=contract if precondition else None)
 except (OSError,ValueError,RuntimeError) as error:
  report={'status':'contract_or_execution_unresolved','error_type':type(error).__name__,'message':str(error)[:1024]}
  mark_unconfirmed({'state':report['status'],'exit':126,'cleanup_confirmed':False})
  path.write_text(json.dumps(report,indent=2)+'\n');return 126,report
 if report.get('cleanup_unconfirmed') or report['status']=='restore_readback_failed':
  mark_unconfirmed({'state':report['status'],'exit':126,'cleanup_confirmed':False});return 126,report
 return (0 if report['status']=='largest_ui_passed' and report.get('restore_verified') else 2),report

if __name__=='__main__':
 if len(sys.argv)!=3 or sys.argv[1] not in CONFIG:raise SystemExit('Expected watch|vision|tv and owned device UUID')
 code,report=run_case(sys.argv[1],sys.argv[2]);print(json.dumps(report),flush=True);raise SystemExit(code)
