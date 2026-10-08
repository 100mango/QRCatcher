#!/usr/bin/env python3
"""One unsigned iOS icon-fix archive; only bounded JSON proof is retained."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from ios_icon_capture import capture, CaptureStopped
from verify_ios_icons import source_icons, built_icons, built_observation, read, require
from verify_ios_only_release import verify_package

ROOT=Path(__file__).resolve().parents[1]
PARENT='176b03855d16fbd5ccdb7e959ce3648d4546b0a5'
PARENT_TREE='968a9cc0ad1ee3861dd2a4d401e0579ee497f435'
SUCCESSOR_CHANGED={'scripts/verify_ios_icons.py','scripts/ios_icon_archive.py','Tests/Harness/test_ios_icon_fix.py'}
BRANCH='refs/heads/ios-icon-fix'
WORKFLOW='.github/workflows/ios-icon-fix.yml'
ARCHIVE=Path('build/ios-icon-fix/QRCatcher.xcarchive')
APP=ARCHIVE/'Products/Applications/QRCatcher.app'
PROOF=Path('build/ios-icon-proof/report.json')
LOG_CAP=16*1024*1024
RETAIN_LOG=512*1024
MAX_REPORT=2*1024*1024

def bounded_log(raw):
    if len(raw)<=RETAIN_LOG:return {'bytes':len(raw),'truncated':False,'text':raw.decode('utf-8','replace')}
    half=RETAIN_LOG//2
    return {'bytes':len(raw),'truncated':True,'omitted_bytes':len(raw)-RETAIN_LOG,
            'prefix':raw[:half].decode('utf-8','replace'),'tail':raw[-half:].decode('utf-8','replace')}

def archive_command():
    return ['xcodebuild','archive','-project','QRCatcher-iOS-Only.xcodeproj','-scheme','QRCatcher',
            '-configuration','Release','-sdk','iphoneos','-destination','generic/platform=iOS',
            '-derivedDataPath','build/ios-icon-fix/DerivedData','-archivePath',str(ARCHIVE),
            '-disableAutomaticPackageResolution','-onlyUsePackageVersionsFromResolvedFile',
            'ARCHS=arm64','ONLY_ACTIVE_ARCH=NO','CODE_SIGNING_ALLOWED=NO','CODE_SIGNING_REQUIRED=NO',
            'CODE_SIGN_IDENTITY=','CODE_SIGN_STYLE=Manual','DEVELOPMENT_TEAM=',
            'PROVISIONING_PROFILE=','PROVISIONING_PROFILE_SPECIFIER=','OTHER_CODE_SIGN_FLAGS=']

def environment(env):
    fixed={'GITHUB_REPOSITORY':'100mango/QRCatcher','GITHUB_REF':BRANCH,'GITHUB_EVENT_NAME':'push',
           'GITHUB_RUN_ATTEMPT':'1','GITHUB_JOB':'archive',
           'GITHUB_WORKFLOW_REF':'100mango/QRCatcher/'+WORKFLOW+'@'+BRANCH,
           'DEVELOPER_DIR':'/Applications/Xcode_27.app/Contents/Developer'}
    require(all(env.get(k)==v for k,v in fixed.items()),'fixed unsigned icon job mismatch')
    require(re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) is not None
            and env.get('GITHUB_WORKFLOW_SHA')==env['GITHUB_SHA'],'source/workflow mismatch')
    require(re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')) is not None,'run mismatch')
    return {k:env[k] for k in (*fixed,'GITHUB_SHA','GITHUB_WORKFLOW_SHA','GITHUB_RUN_ID')}

def source_snapshot(root, run, identity):
    def git(*args):return run(['git',*args],5,256*1024).decode().strip()
    require(git('rev-parse','HEAD')==identity['GITHUB_SHA'],'wrong source HEAD')
    require(git('rev-list','--parents','-n','1','HEAD').split()==[identity['GITHUB_SHA'],PARENT],'wrong sole parent')
    require(git('rev-parse',PARENT+'^{tree}')==PARENT_TREE,'wrong reviewed icon-fix parent tree')
    require(git('status','--porcelain','--untracked-files=all')=='','source not clean')
    require(set(git('diff','--name-only',PARENT,'HEAD','--').splitlines())==SUCCESSOR_CHANGED,'unreviewed successor delta')
    files=git('ls-files','-z').split('\0'); rows={}
    for name in files:
        if not name:continue
        require(not Path(name).is_absolute() and '..' not in Path(name).parts,'escaped source path')
        raw=read(root/name,4*1024*1024)
        rows[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    return {**identity,'tree':git('rev-parse','HEAD^{tree}'),'parent':PARENT,'parent_tree':PARENT_TREE,'files':rows}

def execute(root=ROOT, env=None, clock=time.monotonic, runner=capture):
    env=os.environ if env is None else env
    identity=environment(env); began=float(env['QR_ICON_JOB_STARTED'])
    require(0<began<=clock() and clock()-began<90,'invalid original job clock')
    deadline=began+960
    report={'scope':'unsigned iOS 1.1 build 3 icon qualification','qualified':False,
            'signing_qualified':False,'store_upload_qualified':False,'binary_handoff':False,
            'identity':identity,'commands':[],'clock':{'original_started':began,'controller_deadline':deadline}}
    def run(args, seconds, cap=LOG_CAP):
        require(clock()+seconds+8<deadline,'original job clock cannot admit command and cleanup')
        started=clock();row={'command':args,'seconds':seconds,'cap':cap,'started':started,'complete':False}
        report['commands'].append(row)
        try:
            result=runner(args,seconds=seconds,cap=cap,cleanup_grace=2)
        except CaptureStopped as error:
            row.update(error=str(error),cleanup_confirmed=error.cleanup_confirmed,
                       cancelled_signal=error.cancelled_signal,
                       stdout=bounded_log(getattr(error,'stdout_prefix',b'')),
                       stderr=bounded_log(getattr(error,'stderr_capture',b'')))
            raise
        finally:row['finished']=clock()
        row.update(exit=result.returncode,cleanup_confirmed=True,
                   stdout=bounded_log(result.stdout),stderr=bounded_log(result.stderr),
                   reported_error=re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:',result.stdout+b'\n'+result.stderr) is not None)
        require(row['finished']<started+seconds and row['finished']<deadline,'late command return')
        require(result.returncode==0,'command failed: '+args[0])
        row['complete']=True
        return result.stdout
    archive_returned=False
    try:
        require(not (root/'build').exists(),'expected fresh checkout output')
        report['source_before']=source_snapshot(root,run,identity)
        # Every declared image must exist before any xcodebuild invocation.
        report['source_icons']=source_icons(root)
        for flags in ([],['-O']):
            run([sys.executable,*flags,'-m','unittest','discover','-s','Tests/Harness','-p','test_ios_icon_fix.py'],40,65536)
        require(run(['xcodebuild','-version'],10,4096).decode().strip()=='Xcode 27.0\nBuild version 27A266a','unexpected Xcode')
        (root/'build/ios-icon-fix').mkdir(parents=True)
        output=run(archive_command(),720)
        archive_returned=True
        require(b'** ARCHIVE SUCCEEDED **' in output,'missing actual archive success')
        require(not report['commands'][-1]['reported_error'],'archive reported error')
        report['built_observation']=built_observation(root/APP)
        report['package']=verify_package(root/ARCHIVE,'device','Release')
        require(not (root/APP/'embedded.mobileprovision').exists()
                and not (root/APP/'_CodeSignature').exists(),'unexpected signed payload')
        car=json.loads(run(['xcrun','assetutil','--info',str(APP/'Assets.car')],30,4*1024*1024))
        report['asset_catalog']=car
        report['built_icons']=built_icons(root/APP,car,report['built_observation'])
        require(clock()<deadline,'inspection exceeded original deadline')
    except (Exception,KeyboardInterrupt) as error:
        report['failure']={'type':type(error).__name__,'reason':str(error)[:3000]}
    # Only a known completed archive permits this host-only observation. It
    # preserves an inspection failure and records source-check failure separately.
    if archive_returned:
        try:
            report['source_after']=source_snapshot(root,run,identity)
            require(report['source_before']==report['source_after'],'archive changed tested source inputs')
        except (Exception,KeyboardInterrupt) as error:
            report['source_after_failure']={'type':type(error).__name__,'reason':str(error)[:3000]}
            if 'failure' not in report:report['failure']=report['source_after_failure']
    report['qualified']=archive_returned and 'failure' not in report and 'source_after' in report
    report['clock']['finished']=clock();report['clock']['elapsed']=clock()-began
    return report

def main():
    if sys.argv[1:]==['finish']:
        row=json.loads(read(ROOT/PROOF,MAX_REPORT));identity=environment(os.environ)
        require(row['identity']==identity,'retained source/run mismatch')
        require(time.monotonic()<float(os.environ['QR_ICON_JOB_STARTED'])+1170,'evidence retention exceeded original job clock')
        print(json.dumps({'retention_clock_qualified':True,'archive_qualified':row['qualified']}));return 0
    require(len(sys.argv)==1,'unexpected command')
    report=execute();raw=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    require(len(raw)<=MAX_REPORT,'proof report exceeds byte limit')
    path=ROOT/PROOF;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    require(time.monotonic()<report['clock']['original_started']+1080,'no time for bounded artifact retention')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:output.write('evidence_ready=true\n')
    print(json.dumps({'qualified':report['qualified'],'failure':report.get('failure'),'report_bytes':len(raw)}))
    return 0 if report['qualified'] else 1

if __name__=='__main__':raise SystemExit(main())
