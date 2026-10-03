#!/usr/bin/env python3
"""Bounded SDK/linked-libc++ inventory for the declared older Watch slice.

This is not an older-system launch test. No availability macro is overridden.
Apple documents floating-point charconv as watchOS 9.3+, beyond our 9.0 floor:
https://developer.apple.com/xcode/cpp/
"""
import hashlib,json,re,subprocess,sys
from pathlib import Path

app=Path(sys.argv[1]);binary=app/'QRCatcherWatch'
sdk=subprocess.check_output(['xcrun','--sdk','watchos','--show-sdk-path'],text=True,timeout=20).strip()
report={'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'sdk':sdk,'slices':{},
        'older_runtime_launch':'not executed; linked-symbol review and SDK diagnostics are static gates only'}
for arch,minimum in [('arm64_32','9.0'),('arm64','26.0')]:
    raw=subprocess.check_output(['xcrun','nm','-arch',arch,'-u',str(binary)],text=True,timeout=20)
    assert len(raw.encode())<512*1024
    symbols=sorted(set(line.split()[-1] for line in raw.splitlines() if line.split()))
    cpp=[s[1:] for s in symbols if s.startswith('__Z')]
    text=subprocess.check_output(['xcrun','c++filt'],input='\n'.join(cpp)+'\n',text=True,timeout=20)
    assert len(text.encode())<64*1024
    command=['xcrun','clang++','-target',f'{arch}-apple-watchos{minimum}','-isysroot',sdk,'-std=c++20','-dM','-E','-x','c++','-']
    macros=subprocess.check_output(command,input='#include <version>\n#include <charconv>\n',text=True,timeout=20)
    selected=[line for line in macros.splitlines() if re.match(r'#define (__cpp_lib_(format|to_chars|ranges)\b|_LIBCPP_(VERSION|AVAILABILITY_HAS_(TO_CHARS|FORMAT)))',line)]
    report['slices'][arch]={'deployment_target':minimum,'undefined_cpp_symbols':cpp,'demangled_cpp_symbols':text.splitlines(),'sdk_feature_macros':selected}
    # Never claim watchOS 9.0 compatibility if a known newer floating-point
    # charconv runtime entry is imported. The full bounded list remains visible
    # for review of less obvious facilities and compiler-generated helpers.
    if arch=='arm64_32':
        newer=[line for line in text.splitlines() if re.search(r'(to_chars|from_chars).*\b(float|double)\b',line)]
        report['slices'][arch]['known_newer_runtime_imports']=newer
encoded=json.dumps(report,indent=2)+'\n';assert len(encoded.encode())<60*1024
out=Path('build/native-release-evidence');out.mkdir(parents=True,exist_ok=True)
(out/'watch-cpp-compatibility.json').write_text(encoded);print(encoded,flush=True)
assert not report['slices']['arm64_32']['known_newer_runtime_imports'],'Watch 9.0 must not import watchOS 9.3 floating-point charconv'
