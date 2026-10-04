#!/usr/bin/env python3
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from required_reason_symbols import file_metadata_symbols
class SymbolFormatTests(unittest.TestCase):
    def test_plain_and_columnar_darwin_symbols(self):
        for output in ['_fstat\n','                 U _fstat\n','_fstat$INODE64\n','  U _fstat$INODE64\n']:
            self.assertEqual(len(file_metadata_symbols(output)),1)
    def test_unrelated_names_or_fat_headers_do_not_count(self):
        self.assertEqual(file_metadata_symbols('/tmp/_fstat:\n_fstatat\n_Zfoo_fstat\n_fstat_extra\n_fstat$UNVERIFIED\n_fstat$INODE64extra\n'),[])
if __name__=='__main__':unittest.main()
