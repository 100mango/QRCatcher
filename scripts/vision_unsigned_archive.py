#!/usr/bin/env python3
"""Fixed, bounded unsigned Vision archive proof; never a signing handoff.

The retained JSON describes this observation interval. Host capture/owned-group
cleanup does not establish the lifetime of Xcode's independent system daemons.
"""
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import plistlib
import re
import stat
import struct
import sys
import time
import xml.etree.ElementTree as ET

import vision_archive_macho as package
from vision_archive_capture import capture, CaptureStopped
from required_reason_symbols import file_metadata_symbols

ROOT = Path(__file__).resolve().parents[1]
BASE = 'd5a7b3cf13db823d02a9c84b6bbef8311e06ce13'
BASE_TREE = '1597e75141cd4e146d2291158ef4a99bdbbe5f73'
BRANCH = 'refs/heads/codex/vision-unsigned-archive'
WORKFLOW = '.github/workflows/vision-unsigned-archive.yml'
NEW_PATHS = (WORKFLOW,'scripts/vision_unsigned_archive.py','scripts/test_vision_unsigned_archive.py',
    'scripts/vision_archive_macho.py','scripts/vision_archive_capture.py','scripts/fixtures/vision-archive-inputs.json')
ARCHIVE = Path('build/QRCatcherVision.xcarchive')
APP = 'Products/Applications/QRCatcherVision.app'
DSYM = 'dSYMs/QRCatcherVision.app.dSYM'
DWARF = DSYM + '/Contents/Resources/DWARF/QRCatcherVision'
EXECUTABLE = APP + '/QRCatcherVision'
MAX_ENTRIES, MAX_BYTES, SCAN_SECONDS = 2048, 1024 ** 3, 30
MAX_INVENTORY = 1024 ** 2
MAX_REPORT = 2 * 1024 ** 2
ARCHIVE_COMMAND = ['xcodebuild','-quiet','-project','QRCatcher.xcodeproj','-scheme','QRCatcherVision',
    '-configuration','Release','-destination','generic/platform=visionOS','-archivePath',str(ARCHIVE),
    '-derivedDataPath','build/VisionArchiveDerived','ARCHS=arm64','ONLY_ACTIVE_ARCH=NO',
    'CODE_SIGNING_ALLOWED=NO','archive']
PHASE_END = {'prepare':180,'archive':800,'proof':950,'final_source_pack':980,'evidence':1040,'finalization':1060}
MACH_MAGICS = package.MACH_MAGICS + (b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
                                     b'\xbe\xba\xfe\xca', b'\xbf\xba\xfe\xca')


class Rejected(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def need(ok, reason):
    if not ok:
        raise Rejected(reason)


def timely(deadline, clock=time.monotonic):
    need(math.isfinite(deadline) and clock() < deadline, 'deadline-exceeded')


def command(argv, *, deadline, seconds, cap, receipts, clock=time.monotonic,
            runner=capture, cleanup=2):
    """One command grant with the existing helper's two cleanup phases reserved."""
    start = clock()
    grant = min(seconds, deadline - start - 2 * cleanup)
    need(math.isfinite(grant) and grant > 0, 'command-cleanup-admission-expired')
    receipt = {'command': argv, 'start': start, 'grant_seconds': grant,
               'cleanup_reserve_seconds': 2 * cleanup, 'complete': False}
    receipts.append(receipt)
    try:
        result = runner(argv, seconds=grant, cap=cap, cleanup_grace=cleanup)
    except CaptureStopped as error:
        receipt.update(reason=str(error), owned_cleanup_confirmed=error.cleanup_confirmed,
                       cancelled_signal=error.cancelled_signal,
                       stdout=getattr(error, 'stdout_prefix', b'')[:cap].decode('utf-8', 'replace'),
                       stderr=getattr(error, 'stderr_capture', b'')[:cap].decode('utf-8', 'replace'))
        raise Rejected('capture-stopped') from error
    finally:
        receipt['end'] = clock()
    receipt.update(returncode=result.returncode, stdout=result.stdout.decode('utf-8', 'replace'),
                   stderr=result.stderr.decode('utf-8', 'replace'),
                   owned_host_observation='client-reaped-pipes-closed-group-absent-at-return')
    need(len(result.stdout) + len(result.stderr) <= cap, 'command-byte-limit')
    need(receipt['end'] < start + grant and receipt['end'] < deadline, 'command-late-return')
    need(result.returncode == 0, 'command-failed')
    if argv == ARCHIVE_COMMAND:
        need(re.search(rb'(?im)(?:^|[ :])(?:fatal )?error:', result.stdout + b'\n' + result.stderr) is None, 'archive-reported-error')
    receipt['complete'] = True
    return result.stdout


def environment(env):
    expected = {'GITHUB_REPOSITORY': '100mango/QRCatcher', 'GITHUB_REF': BRANCH,
        'GITHUB_WORKFLOW_REF': '100mango/QRCatcher/' + WORKFLOW + '@' + BRANCH,
        'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_JOB': 'archive',
        'DEVELOPER_DIR': '/Applications/Xcode_27.app/Contents/Developer'}
    need(all(env.get(k) == v for k, v in expected.items()), 'job-identity-mismatch')
    need(env.get('GITHUB_EVENT_NAME') == 'push', 'event-mismatch')
    sha = env.get('GITHUB_SHA', '')
    need(re.fullmatch('[0-9a-f]{40}', sha) is not None and env.get('GITHUB_WORKFLOW_SHA') == sha,
         'source-workflow-sha-mismatch')
    need(re.fullmatch('[1-9][0-9]{0,19}', env.get('GITHUB_RUN_ID', '')) is not None, 'run-identity-mismatch')
    return {k: env[k] for k in (*expected, 'GITHUB_EVENT_NAME', 'GITHUB_SHA',
                               'GITHUB_WORKFLOW_SHA', 'GITHUB_RUN_ID')}


def source_identity(env, run, root=ROOT):
    identity = environment(env)
    def git(*args):
        return run(['git', *args], seconds=5, cap=256 * 1024).decode().strip()
    need(git('rev-parse', 'HEAD') == identity['GITHUB_SHA'], 'head-mismatch')
    need(git('rev-parse', BASE + '^{tree}') == BASE_TREE, 'base-tree-mismatch')
    lineage = git('rev-list', '--parents', '-n', '1', 'HEAD').split()
    need(lineage == [identity['GITHUB_SHA'], BASE], 'source-sole-parent-mismatch')
    identity['parents'] = lineage[1:]
    need(git('status', '--porcelain', '--untracked-files=all') == '', 'source-not-clean')
    differences = git('diff', '--name-status', BASE, 'HEAD', '--').splitlines()
    need(sorted(differences) == sorted('A\t' + p for p in NEW_PATHS), 'source-scope-mismatch')
    identity.update(tree=git('rev-parse', 'HEAD^{tree}'), base=BASE, base_tree=BASE_TREE)
    root = root.resolve()
    fixture=json.loads((root/'scripts/fixtures/vision-archive-inputs.json').read_bytes())
    need(fixture['parent']==BASE and fixture['parent_tree']==BASE_TREE,'input-fixture-base-mismatch')
    for path,expected in fixture['app_inputs'].items():
        need(hashlib.sha256((root/path).read_bytes()).hexdigest()==expected,'app-input-changed: '+path)
    scheme=root/'QRCatcher.xcodeproj/xcshareddata/xcschemes/QRCatcherVision.xcscheme'
    parsed=ET.fromstring(scheme.read_bytes())
    need(parsed.find('ArchiveAction').get('buildConfiguration')=='Release','archive-configuration-mismatch')
    entries=parsed.findall('./BuildAction/BuildActionEntries/BuildActionEntry')
    archived=[e.find('BuildableReference') for e in entries if e.get('buildForArchiving')=='YES']
    need(len(archived)==1 and archived[0].get('BuildableName')=='QRCatcherVision.app' and
        archived[0].get('BlueprintName')=='QRCatcherVision' and archived[0].get('ReferencedContainer')=='container:QRCatcher.xcodeproj','archive-scheme-mismatch')
    paths=sorted(set(NEW_PATHS)|set(fixture['app_inputs']))
    identity['files']={path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in paths}
    identity['app_input_count']=len(fixture['app_inputs'])
    identity['functional_evidence_reused']=fixture['functional_evidence_reused']
    return identity


def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def scan(archive, deadline, *, clock=time.monotonic, hash_files=True, progress=None):
    """Complete bounded catalogue before policy; resource names are not a whitelist."""
    deadline=min(deadline,clock()+SCAN_SECONDS)
    progress={} if progress is None else progress
    progress.update(paths={},entries=0,bytes=0,complete=False)
    paths=progress['paths'];pending=[archive];metadata_bytes=0
    def admit(ok,reason,key):need(ok,reason+': '+key)
    root_stat=archive.lstat();admit(stat.S_ISDIR(root_stat.st_mode),'archive-missing-or-linked','.')
    paths['.']={'identity':file_identity(root_stat),'type':'directory'}
    while pending:
        folder=pending.pop();timely(deadline,clock)
        with os.scandir(folder) as entries:
            for entry in entries:
                timely(deadline,clock);path=Path(entry.path);key=path.relative_to(archive).as_posix()
                progress['last_path']=key
                admit(len(paths)<=MAX_ENTRIES,'archive-entry-limit',key);admit(len(key)<=1024,'archive-path-limit',key)
                admit(path.suffix.lower() not in ('.p8','.p12','.pfx','.key','.keychain','.keychain-db','.mobileprovision','.provisionprofile'), 'signing-input-present', key)
                value=path.lstat();mode=value.st_mode
                kind='directory' if stat.S_ISDIR(mode) else 'file' if stat.S_ISREG(mode) else 'symlink' if stat.S_ISLNK(mode) else 'nonregular'
                receipt={'identity':file_identity(value),'type':kind};paths[key]=receipt;progress['entries']+=1
                if kind=='symlink':
                    target=os.readlink(path);receipt['target']=target
                    admit(len(target)<=1024 and not os.path.isabs(target),'unsafe-link-target',key)
                    resolved=path.resolve();admit(resolved.is_relative_to(archive.resolve()),'archive-link-escape',key)
                    receipt['resolved']=resolved.relative_to(archive.resolve()).as_posix()
                elif kind=='directory':pending.append(path)
                elif kind=='file':
                    progress['bytes']+=value.st_size;receipt['bytes']=value.st_size
                    admit(progress['bytes']<=MAX_BYTES,'archive-byte-limit',key)
                    if hash_files:
                        h=hashlib.sha256();count=0;prefix=b'';tail=b''
                        with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
                            admit(file_identity(os.fstat(stream.fileno()))==receipt['identity'],'archive-file-changed',key)
                            while chunk:=stream.read(1024*1024):
                                timely(deadline,clock);count+=len(chunk);admit(count<=value.st_size,'archive-file-grew',key)
                                if not prefix:prefix=chunk[:4]
                                probe=tail+chunk
                                admit(not re.search(rb'-----BEGIN (?:[A-Z0-9 ]* )?PRIVATE KEY-----',probe), 'private-key-material-present', key)
                                tail=probe[-128:]
                                h.update(chunk)
                            admit(file_identity(os.fstat(stream.fileno()))==receipt['identity'],'archive-file-changed',key)
                        admit(count==value.st_size,'archive-file-size-changed',key)
                        receipt.update(sha256=h.hexdigest(),prefix_hex=prefix.hex())
                else:admit(False,'archive-nonregular',key)
                metadata_bytes+=len(json.dumps({key:receipt},sort_keys=True).encode())
                admit(metadata_bytes<=MAX_INVENTORY,'inventory-metadata-limit',key)
    for key,receipt in paths.items():
        timely(deadline,clock);admit(file_identity((archive/key).lstat())==receipt['identity'],'archive-snapshot-changed',key)
    progress['complete']=True;progress.pop('last_path',None);timely(deadline,clock)
    return progress


def dwarf_headers(raw):
    """Reuse mature fat-table bounds while checking DWARF's different file type."""
    need(len(raw)>=32,'dwarf-header-truncated')
    if raw[:4] in package.MACH_MAGICS[2:]:
        count=struct.unpack_from('>I',raw,4)[0];width=32 if raw[:4]==package.MACH_MAGICS[3] else 20
        need(0<count<=8 and 8+width*count<=len(raw),'dwarf-fat-table-invalid')
        cpus=set();intervals=[];result={}
        for i in range(count):
            pos=8+i*width;cpu,subtype=struct.unpack_from('>II',raw,pos)
            if width==32:
                offset,size,align,reserved=struct.unpack_from('>QQII',raw,pos+8);need(reserved==0,'dwarf-fat-reserved')
            else:offset,size,align=struct.unpack_from('>III',raw,pos+8)
            need(cpu not in cpus and align<=30 and offset%(1<<align)==0 and offset>=8+width*count and size>=32 and offset+size<=len(raw),'dwarf-fat-slice-invalid')
            need(all(offset+size<=a or offset>=b for a,b in intervals),'dwarf-fat-overlap')
            need(raw[offset:offset+4] in package.MACH_MAGICS[:2],'dwarf-nested-fat')
            found=dwarf_headers(raw[offset:offset+size]);need(found=={cpu:subtype},'dwarf-fat-cpu-mismatch');cpus.add(cpu);result[cpu]=subtype;intervals.append((offset,offset+size))
        return result
    need(raw[:4] in package.MACH_MAGICS[:2],'dwarf-mach-magic')
    endian='<' if raw[:4]==package.MACH_MAGICS[0] else '>'
    _,cpu,subtype,kind,commands,size,flags,reserved=struct.unpack_from(endian+'8I',raw)
    need(kind==10 and reserved==0 and 0<commands<=4096 and 32+size<=len(raw),'dwarf-mach-identity')
    return {cpu:subtype}


def matching_uuid(raw, executable, dwarf):
    rows = raw.decode('utf-8').splitlines(); found = {}
    pattern = r'UUID: ([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}) \(arm64\) (.+)'
    for line in rows:
        match = re.fullmatch(pattern, line)
        need(match is not None, 'uuid-output-invalid')
        uuid, path = match.groups()
        need(path in (str(executable), str(dwarf)) and path not in found, 'uuid-product-mismatch')
        need(uuid.replace('-', '').strip('0'), 'uuid-zero')
        found[path] = uuid.upper()
    need(len(found) == 2 and len(set(found.values())) == 1, 'uuid-mismatch')
    return next(iter(found.values()))


def read_metadata(path, deadline, clock):
    timely(deadline, clock)
    need(path.lstat().st_size <= 64 * 1024, 'metadata-byte-limit')
    with path.open('rb') as stream:
        raw = stream.read(64 * 1024 + 1)
    need(len(raw) <= 64 * 1024, 'metadata-byte-limit')
    result = plistlib.loads(raw)
    timely(deadline, clock)
    need(isinstance(result, dict), 'metadata-not-dictionary')
    return result


def compiled_assets(raw):
    """Observe the native CAR decoder; do not guess Xcode's rendition filenames."""
    values = json.loads(raw)
    need(isinstance(values, list) and 0 < len(values) <= 2048, 'compiled-asset-inventory-invalid')
    pixels = []
    for value in values:
        need(isinstance(value, dict), 'compiled-asset-record-invalid')
        width, height = value.get('PixelWidth'), value.get('PixelHeight')
        if width is not None or height is not None:
            need(type(width) is int and type(height) is int and 0 < width <= 32768
                 and 0 < height <= 32768, 'compiled-asset-dimensions-invalid')
            pixels.append({k: value.get(k) for k in ('Name', 'RenditionName', 'PixelWidth', 'PixelHeight', 'Scale')})
    need(any(row['Name'] == 'AppIcon' and row['PixelWidth'] == 1024 and row['PixelHeight'] == 1024 for row in pixels), 'compiled-appicon-rendition-missing')
    return {'records': len(values), 'pixel_renditions': pixels,
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
            'icon_scope': 'unchanged artwork and native materializer; layered AppIcon plus actual metadata and decoded CAR inventory',
            'rendered_icon_pixels_qualified': False}


def icon_inputs(root):
    result = {}
    for layer in ('Front', 'Back'):
        relative = 'QRCatcherVision/Assets.xcassets/AppIcon.solidimagestack/' + layer + '.solidimagestacklayer/Content.imageset/Icon.png'
        path = root/relative
        value = path.lstat()
        need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and 33 <= value.st_size <= 8*1024*1024, 'generated-icon-not-bounded-regular')
        raw = path.read_bytes()
        need(raw[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' and struct.unpack('>II',raw[16:24]) == (1024,1024), 'generated-icon-dimensions-mismatch')
        result[relative] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'width': 1024, 'height': 1024}
    return result


def verify_archive(archive, run, deadline, *, root=ROOT, clock=time.monotonic, report=None):
    root = root.resolve(); archive = Path(archive)
    archive = archive.parent.resolve() / archive.name
    need(archive == root / ARCHIVE, 'archive-path-mismatch')
    started = clock(); report = {} if report is None else report
    catalogue = report.setdefault('archive_inventory', {})
    before = scan(archive, deadline, clock=clock, progress=catalogue)
    # Complete bounded names/types/bytes/hash catalogue precedes semantic policy.
    (root/'build/archive-inventory.json').write_bytes(json.dumps(before, sort_keys=True).encode())
    timely(deadline, clock)
    def need_path(ok, reason, path):
        if not ok: report['offending_path'] = str(path.relative_to(archive))
        need(ok, reason + ': ' + str(path.relative_to(archive)))
    for key, item in before['paths'].items():
        path = archive/key
        need_path(path.name not in ('embedded.mobileprovision', 'embedded.provisionprofile', '_CodeSignature', 'CodeResources')
            and path.suffix not in ('.xctest', '.appex', '.framework', '.dylib')
            and 'QRCatcherTests' not in key, 'unexpected-code-test-or-signing-payload', path)
        if path.suffix in ('.app', '.dSYM'):
            need_path(key in (APP, DSYM), 'unexpected-nested-product', path)
        if item['type'] == 'file':
            need_path(item['identity'][3] == 1, 'archive-hardlink', path)
            need_path(key in (EXECUTABLE, DWARF) or not item['identity'][2] & 0o111,
                      'unexpected-executable', path)
        allowed = key in ('.', 'Info.plist', 'Products', 'Products/Applications', APP, 'dSYMs', DSYM, 'Assets')
        allowed = allowed or key.startswith((APP+'/', DSYM+'/', 'Assets/'))
        need_path(allowed, 'unexpected-archive-topology', path)
    def own_bytes(path, cap=1024*1024):
        relative = path.relative_to(archive).as_posix()
        report['current_proof_path'] = relative
        row = before['paths'].get(relative, {})
        need_path(row.get('type') == 'file' and row.get('bytes', cap+1) <= cap,
                  'required-resource-not-bounded-regular-file', path)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
            need_path(file_identity(os.fstat(stream.fileno())) == row['identity'], 'archive-file-changed', path)
            value = stream.read(cap+1)
            need_path(file_identity(os.fstat(stream.fileno())) == row['identity'], 'archive-file-changed', path)
        need_path(len(value) == row['bytes'] and hashlib.sha256(value).hexdigest() == row['sha256'],
                  'archive-content-changed', path)
        timely(deadline, clock)
        return value
    def own_metadata(path):
        value = plistlib.loads(own_bytes(path))
        need_path(isinstance(value, dict), 'metadata-not-dictionary', path)
        return value
    app = archive/APP; executable = archive/EXECUTABLE; dwarf = archive/DWARF
    metadata = own_metadata(archive/'Info.plist')
    need_path(type(metadata.get('ArchiveVersion')) is int and metadata['ArchiveVersion'] == 2
              and metadata.get('SchemeName') == 'QRCatcherVision', 'archive-metadata-mismatch', archive/'Info.plist')
    need_path(isinstance(metadata.get('CreationDate'), datetime.datetime), 'archive-creation-date-missing', archive/'Info.plist')
    info = own_metadata(app/'Info.plist')
    expected = {'CFBundleIdentifier': '100mango.QRCatcher', 'CFBundleExecutable': 'QRCatcherVision',
        'CFBundleName': 'QRCatcher', 'CFBundlePackageType': 'APPL',
        'CFBundleShortVersionString': '1.1', 'CFBundleVersion': '2', 'MinimumOSVersion': '1.0',
        'CFBundleSupportedPlatforms': ['XROS'], 'UIDeviceFamily': [7], 'DTSDKName': 'xros27.0'}
    need_path(all(info.get(k) == v for k, v in expected.items()), 'application-identity-mismatch', app/'Info.plist')
    need_path(info.get('CFBundleIcons', {}).get('CFBundlePrimaryIcon') == 'AppIcon',
              'compiled-icon-identity-missing', app/'Info.plist')
    properties = metadata.get('ApplicationProperties', {})
    need_path(isinstance(properties, dict), 'archive-application-properties-type', archive/'Info.plist')
    need_path(properties.get('ApplicationPath') == 'Applications/QRCatcherVision.app'
        and all(properties.get(k) == info[k] for k in ('CFBundleIdentifier', 'CFBundleShortVersionString', 'CFBundleVersion')),
        'archive-application-properties-mismatch', archive/'Info.plist')
    need_path(not any(properties.get(k) for k in ('SigningIdentity', 'Team')), 'distribution-signing-identity-present', archive/'Info.plist')
    manifest = app/'PrivacyInfo.xcprivacy'; actual = own_metadata(manifest)
    source = plistlib.loads((root/'Shared/FileImportResources/PrivacyInfo.xcprivacy').read_bytes())
    need_path(actual == source, 'privacy-manifest-source-mismatch', manifest)
    reasons = actual.get('NSPrivacyAccessedAPITypes', [])
    expected_reasons = {'NSPrivacyAccessedAPICategoryFileTimestamp': {'C617.1', '3B52.1'}}
    need_path(len(reasons) == 1 and {v['NSPrivacyAccessedAPIType']: set(v['NSPrivacyAccessedAPITypeReasons']) for v in reasons}
              == expected_reasons and actual.get('NSPrivacyTracking') is False
              and actual.get('NSPrivacyCollectedDataTypes') == [] and actual.get('NSPrivacyTrackingDomains') == [],
              'privacy-required-reasons-mismatch', manifest)
    for locale in ('zh-Hans',):
        for name in ('Localizable.strings',):
            path = app/(locale+'.lproj')/name
            need_path(package.strings_dictionary(own_bytes(path)) == package.strings_dictionary(
                (root/'QRCatcherMac'/(locale+'.lproj')/name).read_bytes()), 'localization-source-mismatch', path)
    need_path(own_bytes(app/'PkgInfo') == b'APPL????', 'package-signature-metadata-mismatch', app/'PkgInfo')
    assets = app/'Assets.car'
    need_path(len(own_bytes(assets, 64*1024*1024)) > 64, 'compiled-asset-catalog-missing', assets)
    need_path(len(own_bytes(app/'QR.momd/QR.mom')) > 0, 'compiled-core-data-model-missing', app/'QR.momd/QR.mom')
    asset_inventory = compiled_assets(run(['xcrun', 'assetutil', '--info', str(assets)], seconds=15, cap=256*1024, cleanup=10))
    binaries = {}
    for key, item in before['paths'].items():
        if item['type'] != 'file' or bytes.fromhex(item.get('prefix_hex', '')) not in MACH_MAGICS: continue
        path = archive/key; raw = own_bytes(path, 64*1024*1024)
        if key == DWARF:
            need_path(set(dwarf_headers(raw)) == {0x100000c}, 'dwarf-architecture-mismatch', path)
            continue
        need_path(key == EXECUTABLE, 'unexpected-mach-o-product', path)
        rows = package.mach_info(raw)
        need_path(len(rows) == 1 and rows[0]['cpu'] == 0x100000c and rows[0]['kind'] == 2,
                  'binary-product-or-architecture-mismatch', path)
        need_path(rows[0]['platform'] == 11 and rows[0]['minimum'] == [1,0,0]
                  and rows[0]['sdk'] == [27,0,0], 'binary-platform-version-mismatch', path)
        need_path(all(link.startswith(('/System/Library/Frameworks/', '/usr/lib/')) for link in rows[0]['libraries'])
                  and not any('/WatchKit.framework/' in link or '/WatchConnectivity.framework/' in link
                              for link in rows[0]['libraries']), 'unexpected-runtime-library', path)
        need_path(not any(bad in raw for bad in (b'QRCATCHER_TEST_STORE', b'QRCatcherExportTestReceipts', b'VisionExportTestReceipt',
                  b'QRCATCHER_SANDBOX_', b'sandboxDiagnostics', b'fixture-payload', b'reset-history')), 'debug-test-seam-present', path)
        need_path(raw[:4] == b'\xcf\xfa\xed\xfe', 'expected-thin-arm64', path)
        count, size = struct.unpack_from('<II', raw, 16); position = 32
        for _ in range(count):
            command, length = struct.unpack_from('<II', raw, position)
            if command == 0x1d:
                need_path(length == 16 and struct.unpack_from('<I', raw, position+12)[0] == 0,
                          'code-signature-load-command-present', path)
            position += length
        binaries[key] = rows
    need_path(EXECUTABLE in binaries and DWARF in before['paths'], 'required-binary-missing', executable)
    # A regular file with UUID text cannot substitute for an actual DWARF object.
    need_path(set(dwarf_headers(own_bytes(dwarf, 64*1024*1024))) == {0x100000c}, 'dwarf-architecture-mismatch', dwarf)
    dsym = own_metadata(archive/DSYM/'Contents/Info.plist')
    need_path(dsym.get('CFBundleIdentifier') == 'com.apple.xcode.dsym.100mango.QRCatcher'
              and dsym.get('CFBundlePackageType') == 'dSYM', 'dSYM-metadata-mismatch', archive/DSYM/'Contents/Info.plist')
    versions = {k: {'observed': dsym.get(k), 'comparison': 'missing' if k not in dsym else
                   'same' if dsym[k] == info[k] else 'different'} for k in ('CFBundleVersion', 'CFBundleShortVersionString')}
    symbols = file_metadata_symbols(run(['xcrun', 'nm', '-u', str(executable)], seconds=15, cap=256*1024).decode())
    need_path(bool(symbols), 'file-metadata-reader-import-missing', executable)
    uuid = matching_uuid(run(['xcrun', 'dwarfdump', '--uuid', str(executable), str(dwarf)],
                            seconds=10, cap=8192, cleanup=10), executable, dwarf)
    after = scan(archive, deadline, clock=clock, hash_files=False)
    need(before['entries'] == after['entries'] and before['bytes'] == after['bytes'] and
         {k:v['identity'] for k,v in before['paths'].items()} == {k:v['identity'] for k,v in after['paths'].items()},
         'archive-changed-during-proof')
    timely(deadline, clock); report.pop('current_proof_path', None)
    return {'metadata': metadata, 'application_metadata': info, 'privacy_manifest': actual,
        'compiled_assets': asset_inventory, 'actual_file_metadata_imports': symbols, 'binaries': binaries, 'dSYM_metadata': dsym,
        'dSYM_version_observations': versions, 'arm64_uuid': uuid, 'unsigned': True,
        'archive_entries': before['entries'], 'archive_bytes': before['bytes'], 'elapsed_seconds': clock()-started,
        'observation': 'complete catalogue persisted before semantic checks; stable identity and content interval',
        'resource_policy': 'ordinary generated resource names are catalogued; code and signing payloads remain rejected'}


def json_value(value):
    if isinstance(value, datetime.datetime):
        return {'plist_date': value.isoformat()}
    if isinstance(value, bytes):
        return {'plist_data_hex': value.hex()}
    raise TypeError(type(value).__name__)


def report_bytes(report):
    raw = (json.dumps(report, sort_keys=True, default=json_value, allow_nan=False, separators=(',', ':')) + '\n').encode()
    if len(raw) > MAX_REPORT:
        # Keep the bounded catalogue/source/clock even when another field overflows.
        keep=('schema','scope','signing_qualified','store_qualified','older_os_qualified','ui_qualification_separate',
            'source_before','clock','archive_inventory','owned_output','binary_handoff','upload_qualified')
        compact={k:report[k] for k in keep if k in report}
        compact.update(qualified=False,failure={'type':'Rejected','reason':'report-byte-limit','original_failure':report.get('failure')})
        raw=(json.dumps(compact,sort_keys=True,default=json_value,allow_nan=False,separators=(',',':'))+'\n').encode()
        need(len(raw)<=MAX_REPORT,'bounded-inventory-report-byte-limit')
    return raw


def execute(*, env=None, root=ROOT, clock=time.monotonic, runner=capture):
    env = os.environ if env is None else env
    root = root.resolve()
    began = clock(); receipts = []; phase = 'prepare'; phase_deadline = began + 180
    report = {'schema': 1, 'scope': 'Vision-unsigned-archive-observation', 'qualified': False,
        'signing_qualified': False, 'store_qualified': False, 'older_os_qualified': False,
        'ui_qualification_separate': True, 'binary_handoff': False, 'commands': receipts,
        'upload_qualified': False, 'qualification_scope': 'archive-observation-before-retention',
        'clock': {'started_monotonic': began, 'phase_end_seconds': PHASE_END,
                  'report_ready_deadline': began + PHASE_END['final_source_pack']},
        'host_scope': 'owned-client-and-process-group-observation; no independent-daemon lifetime claim'}
    def run(argv, **kwargs):
        return command(argv, deadline=phase_deadline, receipts=receipts,
                       clock=clock, runner=runner, **kwargs)
    try:
        need(not (root / 'build').exists() and not (root / 'build').is_symlink(), 'output-not-fresh')
        (root / 'build').mkdir()
        report['owned_output'] = file_identity((root / 'build').lstat())[:2]
        report['source_before'] = source_identity(env, run, root)
        report['toolchain'] = {
            'os': run(['sw_vers'], seconds=5, cap=4096).decode(),
            'xcode': run(['xcodebuild', '-version'], seconds=10, cap=4096).decode(),
            'sdks': run(['xcodebuild', '-showsdks'], seconds=15, cap=16384).decode()}
        need(report['toolchain']['xcode'].strip().splitlines() == ['Xcode 27.0', 'Build version 27A266a'], 'toolchain-mismatch')
        need('xros27.0' in report['toolchain']['sdks'], 'sdk-mismatch')
        for optimize in ([], ['-O']):
            run([sys.executable, *optimize, '-m', 'unittest', 'discover', '-s', 'scripts',
                 '-p', 'test_vision_unsigned_archive.py'], seconds=40, cap=65536)
        run([sys.executable, 'scripts/generate_project.py'], seconds=10, cap=4096)
        need(source_identity(env, run, root) == report['source_before'], 'generated-project-changed')
        run(['xcrun', 'swift', 'scripts/materialize_native_icons.swift'], seconds=60, cap=16384, cleanup=10)
        report['generated_vision_icons'] = icon_inputs(root)
        timely(began + PHASE_END['prepare'], clock)
        phase = 'archive'; phase_deadline = min(began + PHASE_END[phase], clock() + 620)
        run(ARCHIVE_COMMAND, seconds=600, cap=512 * 1024, cleanup=10)
        phase = 'proof'; phase_deadline = min(began + PHASE_END[phase], clock() + 150)
        report['proof'] = verify_archive(root / ARCHIVE, run, phase_deadline, root=root, clock=clock, report=report)
        phase = 'final_source_pack'; phase_deadline = min(began + PHASE_END[phase], clock() + 30)
        report['clock']['report_ready_deadline'] = phase_deadline
        need(icon_inputs(root) == report['generated_vision_icons'], 'generated-icon-input-changed')
        report['source_after'] = source_identity(env, run, root)
        need(report['source_after'] == report['source_before'], 'source-changed')
        timely(phase_deadline, clock)
        report['qualified'] = True
    except (Exception, KeyboardInterrupt) as error:
        report['clock']['report_ready_deadline'] = min(report['clock']['report_ready_deadline'], clock() + 30)
        report['failure'] = {'phase': phase, 'type': type(error).__name__,
                             'reason': str(error)[:4096], 'offending_path':report.get('offending_path') or report.get('current_proof_path') or report.get('archive_inventory',{}).get('last_path')}
    report['clock']['elapsed_seconds'] = clock() - began
    return report


def retain_report(result, output, marker, *, clock=time.monotonic):
    """Finish every report/marker write against the original final phase clock."""
    deadline = result['clock']['report_ready_deadline']
    offset = None
    try:
        timely(deadline, clock)
        output.mkdir(exist_ok=False)
        payload = report_bytes(result)
        timely(deadline, clock)
        (output / 'report.json').write_bytes(payload)
        timely(deadline, clock)
        # This is the current step's owned output file. Roll back this append if
        # it returns late, so a late artifact cannot gain upload admission.
        with marker.open('a+', encoding='utf-8') as stream:
            stream.seek(0, os.SEEK_END); offset = stream.tell()
            stream.write('evidence_ready=true\n'); stream.flush()
            if clock() >= deadline:
                stream.truncate(offset)
                raise Rejected('deadline-exceeded')
        timely(deadline, clock)
        return json.loads(payload)
    except Rejected as error:
        if offset is not None:
            with marker.open('r+', encoding='utf-8') as stream:
                stream.truncate(offset)
        result['qualified'] = False
        result['failure'] = {'phase': 'final_source_pack', 'type': type(error).__name__, 'reason': str(error)}
        # Local typed failure only: no new command and no upload admission.
        if output.is_dir() and not output.is_symlink():
            (output / 'report.json').write_bytes(report_bytes(result))
        return result


def upload_ceiling(result):
    value = result.get('clock', {})
    began = value.get('started_monotonic')
    need(type(began) in (int, float) and math.isfinite(began) and began >= 0
         and value.get('phase_end_seconds') == PHASE_END, 'upload-clock-identity-mismatch')
    return began, began + PHASE_END['evidence'], began + PHASE_END['finalization']


def admit_upload(result, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    now = clock()
    # Full action timeout plus the original finalization reserve. No fresh clock.
    need(began <= now and now + 60 < evidence_end and now + 80 < global_end,
         'upload-full-admission-expired')
    return {'status': 'admitted', 'admitted_monotonic': now,
        'elapsed_at_admission': now - began, 'evidence_deadline': evidence_end,
        'global_deadline': global_end, 'action_timeout_seconds': 60,
        'finalization_reserve_seconds': 20, 'upload_qualified': False,
        'interval_scope': 'admission-through-post-action-observation-including-step-delays'}


def finish_upload(result, outcome, *, clock=time.monotonic):
    began, evidence_end, global_end = upload_ceiling(result)
    admission = result.get('upload_observation', {})
    started = admission.get('admitted_monotonic')
    now = clock()
    receipt = {'scope': 'post-upload-clock-gate', 'upload_qualified': False,
        'archive_qualified': result.get('qualified') is True,
        'action_outcome': outcome, 'started_monotonic': started,
        'observed_finished_monotonic': now, 'elapsed_since_original_start': now - began,
        'evidence_deadline': evidence_end, 'global_deadline': global_end,
        'interval_scope': 'includes-action-setup-and-inter-step-delay'}
    if (type(started) not in (int, float) or not math.isfinite(started)
            or admission.get('status') != 'admitted' or started < began
            or started + 60 >= evidence_end or started + 80 >= global_end
            or admission.get('evidence_deadline') != evidence_end
            or admission.get('global_deadline') != global_end or not math.isfinite(now) or now < started):
        receipt['failure'] = 'upload-admission-identity-mismatch'
    elif outcome != 'success':
        receipt['failure'] = 'upload-action-not-successful'
    elif now >= global_end:
        receipt['failure'] = 'upload-global-deadline-exceeded'
    elif now >= evidence_end:
        receipt['failure'] = 'upload-evidence-deadline-exceeded'
    elif now >= started + 60:
        receipt['failure'] = 'upload-admitted-phase-exceeded'
    else:
        receipt['upload_qualified'] = True
    return receipt


def upload_gate(mode, *, root=ROOT, env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    identity = environment(env)
    path = root / 'build/archive-proof/report.json'
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_REPORT, 'upload-report-invalid')
    with path.open('rb') as stream:
        payload = stream.read(MAX_REPORT + 1)
    need(len(payload) <= MAX_REPORT and file_identity(path.lstat()) == file_identity(before),
         'upload-report-changed')
    result = json.loads(payload)
    need(all(result.get('source_before', {}).get(k) == v for k, v in identity.items()),
         'upload-source-run-mismatch')
    if mode == 'finish-upload':
        receipt = finish_upload(result, env.get('QR_ARCHIVE_UPLOAD_OUTCOME', ''), clock=clock)
        # The uploaded proof explicitly leaves upload_qualified=false. This
        # final workflow log receipt is the separate retention qualification.
        print(json.dumps(receipt, sort_keys=True))
        _, _, global_end = upload_ceiling(result)
        admitted = result['upload_observation']['admitted_monotonic']
        timely(min(global_end, admitted + 80), clock)
        return 0 if receipt['upload_qualified'] else 1
    need(mode == 'admit-upload', 'unknown-upload-gate')
    result['upload_observation'] = admit_upload(result, clock=clock)
    payload = report_bytes(result)
    need(json.loads(payload).get('upload_observation') == result['upload_observation'], 'upload-report-byte-limit')
    path.write_bytes(payload)
    admit_upload(result, clock=clock)  # Report packing must not consume admission.
    marker = Path(env['GITHUB_OUTPUT']); offset = None
    try:
        with marker.open('a+', encoding='utf-8') as stream:
            stream.seek(0, os.SEEK_END); offset = stream.tell()
            stream.write('upload_admitted=true\n'); stream.flush()
            admit_upload(result, clock=clock)
        admit_upload(result, clock=clock)
        print(json.dumps(result['upload_observation'], sort_keys=True))
        admit_upload(result, clock=clock)
    except Rejected:
        if offset is not None:
            with marker.open('r+', encoding='utf-8') as stream:
                stream.truncate(offset)
        raise
    return 0


def main():
    os.chdir(ROOT)
    if len(sys.argv) == 2 and sys.argv[1] in ('admit-upload', 'finish-upload'):
        return upload_gate(sys.argv[1])
    need(len(sys.argv) == 1, 'no-input-selectors')
    result = execute()
    output = ROOT / 'build/archive-proof'
    # Never follow an existing output path after a failed freshness check.
    if 'owned_output' not in result:
        print(json.dumps(result, default=json_value)); return 1
    need(stat.S_ISDIR((ROOT / 'build').lstat().st_mode) and
         file_identity((ROOT / 'build').lstat())[:2] == result['owned_output'], 'output-ownership-changed')
    decoded = retain_report(result, output, Path(os.environ['GITHUB_OUTPUT']))
    print(json.dumps({'qualified': decoded['qualified'], 'failure': decoded.get('failure')}))
    return 0 if decoded['qualified'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
