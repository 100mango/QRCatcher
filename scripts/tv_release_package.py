#!/usr/bin/env python3
"""Read-only fixed tvOS package validation; native execution belongs to archive route.

Mach-O/project/localization parsers adapted from the reviewed iOS package verifier.
No iOS source, runtime fixtures, signing or Store acceptance is implied.
"""
from pathlib import Path
import hashlib
import json
import plistlib
import re
import stat
import struct
import time
ROOT = Path(__file__).resolve().parents[1]
MACH_MAGICS = (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf")
SEAMS = (b'QRCATCHER_TEST_STORE', b'QRCATCHER_SANDBOX_', b'QRCATCHER_TV_TEST_STORE', b'QRCATCHER_TV_LAYOUT_STRESS', b'QRCATCHER_TV_LAYOUT_PROBE', b'fixture-payload', b'reset-history', b'QRCatcherExportTestReceipts', b'Export readback verification failed')
APP_FILES = frozenset(('Assets.car', 'PrivacyInfo.xcprivacy', 'Info.plist', 'PkgInfo', 'QRCatcherTV', 'zh-Hans.lproj/Localizable.strings'))
def require(ok, message):
    if not ok:
        raise ValueError(message)


def version(number):
    return [number >> 16, (number >> 8) & 255, number & 255]


def mach_info(raw):
    """Read bounded 64-bit thin/fat headers and load commands, never execute."""
    require(len(raw) >= 32, 'Truncated Mach-O')
    magic = raw[:4]
    if magic in MACH_MAGICS[2:]:
        count = struct.unpack_from('>I', raw, 4)[0]
        width = 32 if magic == MACH_MAGICS[3] else 20
        require(0 < count <= 8 and 8 + width * count <= len(raw), 'Invalid fat architecture table')
        result, intervals, cpus = [], [], set()
        for i in range(count):
            pos = 8 + i * width
            cpu, subtype = struct.unpack_from('>II', raw, pos)
            if width == 32:
                offset, size, align, reserved = struct.unpack_from('>QQII', raw, pos + 8)
                require(reserved == 0, 'Invalid fat reserved value')
            else:
                offset, size, align = struct.unpack_from('>III', raw, pos + 8)
            require(cpu not in cpus and align <= 30 and offset % (1 << align) == 0,
                    'Duplicate or misaligned fat slice')
            require(offset >= 8 + width * count and size >= 32 and offset + size <= len(raw), 'Invalid fat slice bounds')
            require(all(offset + size <= a or offset >= b for a, b in intervals), 'Overlapping fat slices')
            require(raw[offset:offset + 4] in MACH_MAGICS[:2], 'Nested or unsupported Mach-O slice')
            slices = mach_info(raw[offset:offset + size])
            require(len(slices) == 1 and slices[0]['cpu'] == cpu and slices[0]['subtype'] == subtype, 'Fat slice identity mismatch')
            cpus.add(cpu); intervals.append((offset, offset + size)); result.extend(slices)
        return result
    require(magic in MACH_MAGICS[:2], 'Expected a 64-bit Mach-O product')
    endian = '<' if magic == MACH_MAGICS[0] else '>'
    _, cpu, subtype, kind, count, size, _, reserved = struct.unpack_from(endian + '8I', raw)
    require(reserved == 0 and kind in (2, 6, 8), 'Unsupported Mach-O type')
    require(0 < count <= 4096 and 32 + size <= len(raw), 'Invalid Mach-O command bounds')
    position, builds, links = 32, [], []
    for _ in range(count):
        require(position + 8 <= 32 + size, 'Truncated load command')
        command, length = struct.unpack_from(endian + 'II', raw, position)
        require(length >= 8 and length % 8 == 0 and position + length <= 32 + size, 'Invalid load command size')
        if command == 0x32:  # LC_BUILD_VERSION
            require(length >= 24, 'Short build version')
            platform, minimum, sdk, tools = struct.unpack_from(endian + '4I', raw, position + 8)
            require(length == 24 + tools * 8, 'Malformed build tool table')
            builds.append({'platform': platform, 'minimum': version(minimum), 'sdk': version(sdk)})
        if command in (0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023):
            require(length >= 24, 'Short dylib command')
            offset = struct.unpack_from(endian + 'I', raw, position + 8)[0]
            require(24 <= offset < length, 'Invalid dylib name offset')
            name = raw[position + offset:position + length]
            require(b'\0' in name, 'Unterminated dylib path')
            links.append(name.split(b'\0', 1)[0].decode('utf-8'))
        position += length
    require(position == 32 + size and len(builds) == 1, 'Missing, duplicate or inconsistent build version')
    return [{'cpu': cpu, 'subtype': subtype, 'kind': kind, **builds[0], 'libraries': links}]


def generated_project(raw):
    """Parse only our deterministic quoted-key OpenStep serialization."""
    text = raw.decode('utf-8')
    require(text.startswith('// !$*UTF8*$!\n'), 'Unexpected generated project format')
    text = text.split('\n', 1)[1]
    token = re.compile(r'\s*("(?:\\.|[^"\\])*"|[{}()=;,]|[0-9]+)')
    tokens, at = [], 0
    while at < len(text) and text[at:].strip():
        found = token.match(text, at)
        require(found is not None, 'Invalid generated project token')
        tokens.append(found.group(1)); at = found.end()
    cursor = 0
    def take():
        nonlocal cursor
        require(cursor < len(tokens), 'Truncated generated project')
        item = tokens[cursor]; cursor += 1; return item
    def value(depth=0):
        require(depth < 32, 'Generated project nesting too deep')
        item = take()
        if item == '{':
            result = {}
            while tokens[cursor] != '}':
                key = json.loads(take()); require(key not in result, 'Duplicate project key')
                require(take() == '=', 'Missing project assignment')
                result[key] = value(depth + 1); require(take() == ';', 'Missing project terminator')
            take(); return result
        if item == '(':
            result = []
            while tokens[cursor] != ')':
                result.append(value(depth + 1))
                require(cursor < len(tokens), 'Truncated project array')
                if tokens[cursor] != ')':
                    require(take() == ',', 'Missing project separator')
            take(); return result
        return json.loads(item)
    try:
        result = value()
    except (IndexError, json.JSONDecodeError) as error:
        raise ValueError('Malformed generated project') from error
    require(cursor == len(tokens), 'Trailing generated project tokens')
    return result


def strings_dictionary(raw):
    """Accept compiled binary/XML plists or the checked-in quoted strings grammar."""
    try:
        value = plistlib.loads(raw)
    except (plistlib.InvalidFileException, ValueError, TypeError):
        text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        token = re.compile(r'\s*(?:(?://[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)|("(?:[^"\\]|\\.)*")\s*=\s*("(?:[^"\\]|\\.)*")\s*;)')
        value, offset = {}, 0
        while text[offset:].strip():
            match = token.match(text, offset)
            require(match is not None, 'Malformed localization strings')
            offset = match.end()
            if match.group(1) is not None:
                key, item = json.loads(match.group(1)), json.loads(match.group(2))
                require(key not in value, 'Duplicate localization key')
                value[key] = item
    require(isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()),
            'Localization must be a string dictionary')
    return value



def contract(root=ROOT):
    return json.loads((root/'scripts/tv_release_contract.json').read_text())


def source_graph(root=ROOT):
    value = contract(root)
    for name, expected in {**value['unchanged_inputs'], **value['asset_catalog_files']}.items():
        path = root/name
        require(path.is_file() and not path.is_symlink(), 'Source input missing or linked: '+name)
        require({'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} == expected,
                'Reviewed source/resource changed: '+name)
    project = generated_project((root/'QRCatcher.xcodeproj/project.pbxproj').read_bytes())
    objects = project['objects']
    targets = {x['name']:x for x in objects.values() if x.get('isa') == 'PBXNativeTarget'}
    require({'QRCatcherTV','QRCatcherTVTests','QRCatcherTVUITests'} <= set(targets), 'Missing TV targets')
    target = targets['QRCatcherTV']; memberships=[]
    require(target.get('dependencies',[]) == [], 'Unexpected TV target dependency')
    for phase_id in target['buildPhases']:
        phase=objects[phase_id]
        require(phase['isa'] in ('PBXSourcesBuildPhase','PBXFrameworksBuildPhase','PBXResourcesBuildPhase'), 'Unexpected app phase')
        if phase['isa'] == 'PBXSourcesBuildPhase':
            memberships += [objects[objects[b]['fileRef']]['path'] for b in phase['files']]
    expected=value['shipping_sources']
    require(sorted(memberships) == expected, 'TV app source membership changed')
    def release_settings(owner):
        configs=objects[owner['buildConfigurationList']]['buildConfigurations']
        release=[objects[c]['buildSettings'] for c in configs if objects[c]['name']=='Release']
        require(len(release)==1, 'Missing Release configuration')
        return release[0]
    settings={**release_settings(objects[project['rootObject']]), **release_settings(target)}
    for key,val in {'PRODUCT_NAME':'$(TARGET_NAME)','PRODUCT_BUNDLE_IDENTIFIER':'100mango.QRCatcher','TVOS_DEPLOYMENT_TARGET':'17.0','SDKROOT':'appletvos','TARGETED_DEVICE_FAMILY':'3','MARKETING_VERSION':'1.1','CURRENT_PROJECT_VERSION':'2','DEBUG_INFORMATION_FORMAT':'dwarf-with-dsym','INFOPLIST_FILE':'QRCatcherTV/Info.plist'}.items():
        require(settings.get(key)==val,'Release source setting mismatch: '+key)
    require(not settings.get('SWIFT_ACTIVE_COMPILATION_CONDITIONS') and not settings.get('ENABLE_TESTABILITY') in ('YES', True), 'Release debug compilation enabled')
    require(not target.get('packageProductDependencies') and not objects[project['rootObject']].get('packageReferences'), 'Unexpected package dependency')
    return {'source_paths':expected,'release_settings':settings,'code_signing_override':'NO',
        'source_contract_sha256':hashlib.sha256((root/'scripts/tv_release_contract.json').read_bytes()).hexdigest(),
        'resource_files':value['asset_catalog_files']}


def verify(app, mode='device', release=True, *, root=ROOT, clock=time.monotonic):
    require(mode == 'device' and release is True, 'Only unsigned Release tvOS device is supported')
    app=Path(app);started=clock();deadline=started+30
    def timely():require(clock()<deadline,'Package inspection exceeded original deadline')
    graph=source_graph(root);timely()
    files={};raw_files={}
    for name in sorted(APP_FILES):
        timely();path=app/name;st=path.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_nlink==1, 'Missing or linked resource: '+name)
        require(st.st_size <= 128*1024*1024,'Resource byte limit')
        data=path.read_bytes();timely();after=path.lstat()
        require((st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) and len(data)==st.st_size,'Product changed during inspection')
        files['app/'+name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};raw_files[name]=data
    metadata=plistlib.loads(raw_files['Info.plist'])
    for key,val in {'CFBundleIdentifier':'100mango.QRCatcher','CFBundleExecutable':'QRCatcherTV','CFBundleName':'QRCatcher','CFBundlePackageType':'APPL','CFBundleShortVersionString':'1.1','CFBundleVersion':'2','MinimumOSVersion':'17.0','CFBundleSupportedPlatforms':['AppleTVOS'],'UIDeviceFamily':[3]}.items():
        require(metadata.get(key)==val,'App metadata mismatch: '+key)
    require(metadata.get('CFBundleIcons',{}).get('CFBundlePrimaryIcon')=='Small','Compiled TV icon identity missing')
    require(metadata.get('NSPhotoLibraryUsageDescription')=='Choose QR images and verify QR images you save in Photos. Processing happens on this TV.','Photos permission copy changed')
    require(metadata.get('DTSDKName')=='appletvos27.0','SDK metadata mismatch')
    require(len(raw_files['Assets.car'])>64,'Compiled asset catalog missing or invalid')
    require(raw_files['PkgInfo']==b'APPL????','Package signature metadata mismatch')
    require(plistlib.loads(raw_files['PrivacyInfo.xcprivacy'])==plistlib.loads((root/'QRCatcherTV/PrivacyInfo.xcprivacy').read_bytes()),'Privacy manifest changed')
    name='zh-Hans.lproj/Localizable.strings'
    require(strings_dictionary(raw_files[name])==strings_dictionary((root/'QRCatcherMac'/name).read_bytes()),'Bundled localization differs: '+name)
    require(metadata.get('NSPhotoLibraryAddUsageDescription')=='Save the QR image you explicitly choose to your photo library.','Photos add permission copy changed')
    raw=raw_files['QRCatcherTV'];slices=mach_info(raw)
    require(len(slices)==1 and slices[0]['cpu']==0x100000c and slices[0]['kind']==2,'Expected one arm64 executable')
    piece=slices[0]
    require(piece['platform']==3 and piece['minimum']==[17,0,0] and piece['sdk']==[27,0,0],'Mach-O tvOS/minimum/SDK mismatch')
    require(not any(t in raw for t in SEAMS),'Debug test helper embedded in Release')
    require(all(link.startswith(('/System/Library/Frameworks/','/usr/lib/')) for link in piece['libraries']),'Non-system runtime linked')
    require(not any('/WatchKit.framework/' in x or '/WatchConnectivity.framework/' in x for x in piece['libraries']),'Unexpected paired runtime linked')
    # An archive built without signing must not contain a populated signature command.
    count,size=struct.unpack_from('<II',raw,16);pos=32
    for _ in range(count):
        command,length=struct.unpack_from('<II',raw,pos)
        if command==0x1d:
            require(length==16 and struct.unpack_from('<I',raw,pos+12)[0]==0,'Code signature load command present')
        pos+=length
    timely()
    return {'files':files,'binaries':{'app/QRCatcherTV':{'slices':slices}},'metadata':metadata,'source':graph,'entries':len(files)+2,'unsigned':True,'native_runtime_qualified':False}
