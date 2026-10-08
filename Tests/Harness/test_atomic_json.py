#!/usr/bin/env python3
from pathlib import Path
import json,os,subprocess,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from atomic_json import write_json
class AtomicAcknowledgementTests(unittest.TestCase):
    def test_optimized_python_rejects_symlink_destination_and_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);real=root/'real';real.mkdir();target=real/'target.json';target.write_text('original')
            link=root/'linked.json';link.symlink_to(target);parent=root/'linked-parent';parent.symlink_to(real,target_is_directory=True)
            source='from atomic_json import write_json\nimport sys\nfor path in sys.argv[1:]:\n try: write_json(path,{"new":True})\n except ValueError: continue\n raise SystemExit("guard omitted")\n'
            result=subprocess.run([sys.executable,'-O','-c',source,str(link),str(parent/'new.json')],env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[2]/'scripts')),capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);self.assertEqual(target.read_text(),'original');self.assertFalse((real/'new.json').exists())
    def test_file_is_first_visible_only_as_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'request.ack';value={'id':'synthetic-id','success':True,'payload':'你好'}
            original_replace=os.replace
            def observe(source,destination):
                self.assertFalse(target.exists())
                self.assertEqual(json.loads(Path(source).read_bytes()),value)
                original_replace(source,destination)
            with patch('atomic_json.os.replace',side_effect=observe) as replaced:write_json(target,value)
            replaced.assert_called_once();self.assertEqual(json.loads(target.read_bytes()),value)
    def test_oversized_or_failed_write_preserves_previous_document(self):
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'request.ack';write_json(target,{'original':True});original=target.read_bytes()
            with self.assertRaises(ValueError):write_json(target,{'large':'x'*1000},limit=32)
            with patch('atomic_json.os.replace',side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):write_json(target,{'replacement':True})
            self.assertEqual(target.read_bytes(),original);self.assertEqual(list(Path(directory).iterdir()),[target])
if __name__=='__main__':unittest.main()
