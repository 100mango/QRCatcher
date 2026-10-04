"""Parse real nm undefined-symbol output without assuming a leading type column."""
import json,subprocess
from pathlib import Path

# Apple stat.h declares fstat through __DARWIN_INODE64; cdefs.h defines the
# optional $INODE64 suffix. Accept these exact two ABI tokens only.
# https://github.com/apple/darwin-xnu/blob/main/bsd/sys/stat.h
# https://github.com/apple/darwin-xnu/blob/main/bsd/sys/cdefs.h
def file_metadata_symbols(output):
    return sorted({word for line in output.splitlines() for word in line.split()
                   if word in {'_fstat','_fstat$INODE64'}})

def inspect_file_reader_imports(executable,expected):
    output=subprocess.check_output(['xcrun','nm','-u',str(executable)],text=True,timeout=30)
    assert len(output.encode())<2*1024*1024
    symbols=file_metadata_symbols(output)
    record={'executable':Path(executable).name,'actual_file_metadata_imports':symbols,'expected_reader':expected}
    print('ACTUAL_REQUIRED_REASON_SYMBOLS '+json.dumps(record),flush=True)
    assert bool(symbols)==expected,record
    return symbols
