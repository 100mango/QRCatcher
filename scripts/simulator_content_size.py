#!/usr/bin/env python3
"""Discover, verify and restore a system text-size setting on one owned simulator.

No SDK support is assumed. The installed tool's help must expose the action and
largest token before any setting write. A setting probe alone is not UI coverage.
"""
import argparse,hashlib,json,re,sys,uuid
from pathlib import Path
from atomic_json import write_json
from watch_process import execute
from owned_process_barrier import blocked,mark_unconfirmed

LARGEST='accessibility-extra-extra-extra-large'
TOKEN=re.compile(r'(?<![a-z-])(?:accessibility-)?(?:extra-){0,3}(?:small|medium|large)(?![a-z-])')

def validate_ui_command(command,device,contract):
    if not contract or command[:2]!=['xcodebuild','test-without-building']:
        raise ValueError('An explicit expected UI product/root contract is required')
    required={'root','project','scheme','derived_data','test_bundle','platform'}
    if not required<=set(contract) or any(not isinstance(contract[key],str) or not contract[key] for key in required):
        raise ValueError('Incomplete expected UI contract')
    root=Path(contract['root']).resolve(strict=True)
    if not root.is_dir():raise ValueError('Expected UI root is not a directory')
    options={};selectors=[];index=2
    paired={'-project','-scheme','-derivedDataPath','-destination','-configuration','-resultBundlePath',
            '-parallel-testing-enabled','-collect-test-diagnostics','-test-timeouts-enabled',
            '-default-test-execution-time-allowance','-maximum-test-execution-time-allowance',
            '-maximum-concurrent-test-simulator-destinations'}
    while index<len(command):
        token=command[index]
        if token.startswith('-only-testing:'):
            selectors.append(token.split(':',1)[1]);index+=1;continue
        if token in ['CODE_SIGNING_ALLOWED=NO','ARCHS=arm64']:
            if token in options:raise ValueError('Duplicate UI build option')
            options[token]=True;index+=1;continue
        if token not in paired or token in options or index+1>=len(command):
            raise ValueError('Unsupported, duplicate or incomplete UI option')
        options[token]=command[index+1];index+=2
    if options.get('-configuration')!='Debug' or options.get('-scheme')!=contract['scheme'] or not options.get('CODE_SIGNING_ALLOWED=NO'):
        raise ValueError('UI configuration or product does not match expected contract')
    for flag,value in [('-parallel-testing-enabled','NO'),('-collect-test-diagnostics','never'),('-test-timeouts-enabled','YES')]:
        if options.get(flag)!=value:raise ValueError('Required bounded serial UI option is missing or unsafe')
    if '-maximum-concurrent-test-simulator-destinations' in options and options['-maximum-concurrent-test-simulator-destinations']!='1':
        raise ValueError('Only the supplied simulator destination may run')
    for flag in ['-default-test-execution-time-allowance','-maximum-test-execution-time-allowance']:
        if flag in options and (not options[flag].isdigit() or not 1<=int(options[flag])<=600):
            raise ValueError('UI test allowance must be bounded')
    for flag,key in [('-project','project'),('-derivedDataPath','derived_data')]:
        expected=(root/contract[key]).resolve(strict=True)
        actual=Path(options.get(flag,'')).resolve(strict=True)
        if actual!=expected or not expected.is_relative_to(root) or not expected.is_dir():
            raise ValueError('UI project/build root differs from expected owned product')
    destination=options.get('-destination','').split(',')
    fields=[piece.split('=',1) for piece in destination]
    if any(len(piece)!=2 for piece in fields) or len(fields)!=2 or dict(fields)!={'platform':contract['platform'],'id':device}:
        raise ValueError('UI destination must name the exact owned simulator and platform')
    if not selectors or any(s!=contract['test_bundle'] and not s.startswith(contract['test_bundle']+'/') for s in selectors):
        raise ValueError('UI test selector targets another test product')
    result=Path(options.get('-resultBundlePath','')).resolve()
    if result.suffix!='.xcresult' or not result.is_relative_to(root) or result.exists():
        raise ValueError('UI result bundle must be a new path inside the expected root')
    return dict(contract,root=str(root))

def supported_syntax(help_text):
    # Validate the shape advertised by this actual simctl, not an invented
    # alternative action. Unknown/new help formats require inspection first.
    if not re.search(r'Usage:\s*simctl ui\s+<device>\s+<option>',help_text):return None
    start=re.search(r'^\s*content_size\s*$',help_text,re.M)
    if not start:return None
    section=help_text[start.end():]
    next_option=re.search(r'^\s{0,4}[a-z][a-z_]+\s*$',section,re.M)
    if next_option:section=section[:next_option.start()]
    choices=set(TOKEN.findall(section))
    return choices if LARGEST in choices and 'medium' in choices else None

def probe(device,report_path,ui_command=None,ui_timeout=300,runner=execute,expected_ui=None):
    device=str(uuid.UUID(device)).upper()
    if type(ui_timeout) not in (int,float) or not 1<=ui_timeout<=900:
        raise ValueError('UI timeout must be bounded between 1 and 900 seconds')
    if ui_command:expected_ui=validate_ui_command(ui_command,device,expected_ui)
    report={'device':device,'requested_largest':None,'observed_original':None,
            'observed_largest':None,'observed_restored':None,'ui_executed':False,
            'ui_exit':None,'status':'discovering','operations':[]}
    def save():write_json(report_path,report,limit=48*1024)
    def run(label,args,seconds=15,limit=64*1024):
        if report.get('cleanup_unconfirmed') or blocked():
            raise RuntimeError('No further command is permitted with unresolved owned process cleanup')
        try:
            code,text,operation=runner(args,seconds,output_limit=limit,tail_limit=limit,echo=label=='actual_ui')
        except Exception as error:
            code,text,operation=1,str(error),{'command':args,'state':'execution_error','error_type':type(error).__name__,'cleanup_confirmed':False}
        report['operations'].append({'label':label,'operation':operation,'output':text[:12000 if label=='help' else 2048]})
        if code==126 or operation.get('cleanup_confirmed') is not True:
            report.update(cleanup_unconfirmed=True,status='owned_process_cleanup_unconfirmed')
            mark_unconfirmed(operation)
        save();return code,text.strip()
    save()
    code,help_text=run('help',['xcrun','simctl','help','ui'])
    if report.get('cleanup_unconfirmed'):return report
    report['help_sha256']=hashlib.sha256(help_text.encode()).hexdigest()
    choices=supported_syntax(help_text) if code==0 else None
    if not choices:
        report['status']='help_action_unavailable' if code else 'help_syntax_not_recognized'
        save();return report
    report['help_advertised_sizes']=sorted(choices)
    code,inventory=run('device_inventory',['xcrun','simctl','list','devices','-j'],limit=512*1024)
    if report.get('cleanup_unconfirmed'):return report
    if code:
        report['status']='device_inventory_failed';save();return report
    try:
        matches=[(runtime,item) for runtime,items in json.loads(inventory)['devices'].items()
                 for item in items if item.get('udid','').upper()==device]
    except (ValueError,KeyError,TypeError):
        report['status']='device_inventory_not_recognized';save();return report
    if len(matches)!=1 or matches[0][1].get('state')!='Booted':
        report['status']='owned_device_not_booted';save();return report
    report['runtime']=matches[0][0]
    base=['xcrun','simctl','ui',device,'content_size']
    code,original=run('read_original',base)
    if report.get('cleanup_unconfirmed'):return report
    if code or original not in choices:
        report['status']='device_read_rejected' if code else 'original_value_not_recognized'
        report['original_raw']=original[:2048];save();return report
    report.update(observed_original=original,requested_largest=LARGEST)
    if expected_ui:report['expected_ui_contract']=expected_ui
    # Persist the original before the first attempted write. Even a timed-out
    # write may have applied; its outcome is reconciled by readback, not retried.
    report['status']='original_saved';save()
    try:
        if original!=LARGEST:
            run('set_largest',base+[LARGEST])
            if report.get('cleanup_unconfirmed'):return report
        code,largest=run('read_largest',base)
        if report.get('cleanup_unconfirmed'):return report
        report['observed_largest']=largest
        if code or largest!=LARGEST:
            report['status']='largest_readback_failed';save();return report
        report['status']='largest_setting_verified';save()
        if ui_command:
            report['ui_executed']=True;save()
            code,_=run('actual_ui',ui_command,ui_timeout,limit=2*1024*1024)
            report['ui_exit']=code
            if not report.get('cleanup_unconfirmed'):
                report['status']='largest_ui_passed' if code==0 else 'largest_ui_failed'
        else:report['status']='setting_probe_only_ui_not_executed'
    finally:
        if not report.get('cleanup_unconfirmed'):
            code,current=run('read_before_restore',base)
            if not report.get('cleanup_unconfirmed') and (code or current!=original):run('restore_original',base+[original])
            if not report.get('cleanup_unconfirmed'):
                code,restored=run('read_restored',base)
                report['observed_restored']=restored
                report['restore_verified']=code==0 and restored==original and not report.get('cleanup_unconfirmed')
                if not report['restore_verified'] and not report.get('cleanup_unconfirmed'):report['status']='restore_readback_failed'
        if report.get('cleanup_unconfirmed'):
            report['restore_verified']=False
            report['restore_action']='Not attempted further: owned setter/reader/test process exit is unconfirmed; disposable VM teardown is required'
        save()
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('device');p.add_argument('--report',type=Path,required=True)
    p.add_argument('--ui-timeout',type=int,default=300)
    p.add_argument('--ui-contract',type=Path)
    argv=sys.argv[1:];separator=argv.index('--') if '--' in argv else len(argv)
    args=p.parse_args(argv[:separator]);command=argv[separator+1:]
    args.report.parent.mkdir(parents=True,exist_ok=True)
    contract=None
    if command:
        if not args.ui_contract:p.error('--ui-contract is required with a UI command')
        root=Path(__file__).resolve().parents[1]
        path=args.ui_contract.resolve(strict=True)
        if not path.is_relative_to(root):p.error('UI contract must be within this repository root')
        contract=json.loads(path.read_text());contract['root']=str(root)
    result=probe(args.device,args.report,command or None,args.ui_timeout,expected_ui=contract)
    print(json.dumps({k:v for k,v in result.items() if k!='operations'}),flush=True)
    # Unsupported/unrecognized operations stay explicit, and do not masquerade
    # as either a largest-size UI pass or an app regression.
    if result.get('cleanup_unconfirmed'):raise SystemExit(126)
    if result['status'] not in ['setting_probe_only_ui_not_executed','largest_ui_passed']:raise SystemExit(2)
if __name__=='__main__':main()
