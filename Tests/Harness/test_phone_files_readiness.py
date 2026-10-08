"""Execute exact pure-C snapshot classifier; native AX/runtime remain CI gates."""
import copy,ctypes
from pathlib import Path
import subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
SOURCE=(ROOT/'QRCatcherUITests/QRCatcherImageImportUITests.m').read_text()
PREDICATE=SOURCE.split('NSPredicate *pickerReady =',1)[1].split('}];',1)[0]
class Frame(ctypes.Structure):
    _fields_=[(name,ctypes.c_double) for name in ['x','y','width','height']]
class Node(ctypes.Structure):
    _fields_=[('parent',ctypes.c_int),('kind',ctypes.c_int),('identifier',ctypes.c_char_p),('label',ctypes.c_char_p),('enabled',ctypes.c_int),('frame',Frame)]
def observed(profile):
    # Coordinates from actual retained hierarchies. Intermediate Other nodes
    # are collapsed; required identities, roles and ancestor order preserved.
    # SE3: 7239 CompactPhoneUIResults-files.log lines93,188,195,199.
    # Pro: 42477 job111533497083 native Files failure hierarchy.
    window,picker,bar,cancel={
        'SE3':[(0,0,375,667),(0,20,375,647),(0,36,375,108),(264.5,40,36.5,36)],
        'Pro':[(0,0,440,956),(0,62,440,894),(0,82,440,108),(325.3,86,36.7,36)]}[profile]
    return [dict(parent=-1,kind=4,identifier='',label='',enabled=1,frame=window),
            dict(parent=0,kind=1,identifier='',label='',enabled=1,frame=window),
            dict(parent=1,kind=0,identifier='Browse View (Picker)',label='',enabled=1,frame=picker),
            dict(parent=2,kind=2,identifier='FullDocumentManagerViewControllerNavigationBar',label='',enabled=1,frame=bar),
            dict(parent=3,kind=3,identifier='',label='Cancel',enabled=1,frame=cancel)]
class PhoneFilesSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();work=Path(cls.temp.name).resolve();source=work/'probe.c';library=work/'probe.so'
        source.write_text('#include "QRFilesPickerSnapshot.h"\nint ready(const QRFilesNode *nodes,size_t n){return QRFilesPickerPresentationReady(nodes,n);}\n')
        subprocess.run(['cc','-dynamiclib' if sys.platform=='darwin' else '-shared','-fPIC','-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'QRCatcherUITests'),str(source),'-o',str(library)],check=True,capture_output=True,timeout=20)
        cls.library=ctypes.CDLL(str(library));cls.library.ready.argtypes=[ctypes.POINTER(Node),ctypes.c_size_t];cls.library.ready.restype=ctypes.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def ready(self,rows):
        nodes=(Node*len(rows))(*[Node(r['parent'],r['kind'],r['identifier'].encode(),r['label'].encode(),r['enabled'],Frame(*r['frame'])) for r in rows]);return bool(self.library.ready(nodes,len(rows)))
    def test_both_actual_phone_contexts_classify_without_action_claim(self):
        for profile in ['SE3','Pro']:
            with self.subTest(profile=profile):self.assertTrue(self.ready(observed(profile)))
    def test_missing_wrong_identity_role_or_parent_fails_closed(self):
        for index,key,wrong in [(2,'identifier','other-picker'),(3,'identifier','QRCatcher'),(4,'label','Close'),(2,'kind',4),(3,'kind',0),(4,'kind',0),(3,'parent',1),(4,'parent',2),(2,'parent',0)]:
            rows=observed('Pro');rows[index][key]=wrong
            with self.subTest(index=index,key=key):self.assertFalse(self.ready(rows))
        self.assertFalse(self.ready(observed('Pro')[:-1]))
    def test_duplicate_picker_bar_or_cancel_fails_even_with_equal_bounds(self):
        for index in [2,3,4]:
            rows=observed('Pro');rows.append(copy.deepcopy(rows[index]))
            with self.subTest(index=index):self.assertFalse(self.ready(rows))
    def test_disabled_empty_nonfinite_or_outside_required_frame_fails(self):
        rows=observed('Pro');rows[4]['enabled']=0;self.assertFalse(self.ready(rows))
        for index in [1,2,3,4]:
            for frame in [(0,0,0,20),(0,0,20,0),(float('nan'),0,20,20),(0,0,float('inf'),20)]:
                rows=observed('Pro');rows[index]['frame']=frame
                with self.subTest(index=index,frame=frame):self.assertFalse(self.ready(rows))
        for index in [2,3,4]:
            rows=observed('Pro');rows[index]['frame']=(0,2000,20,20);self.assertFalse(self.ready(rows))
    def test_unknown_graph_or_budget_does_not_loop_or_classify(self):
        for parent in [-1,4,10000]:
            rows=observed('Pro');rows[3]['parent']=parent;self.assertFalse(self.ready(rows))
        rows=observed('Pro');rows += [dict(rows[0],parent=0) for _ in range(2048)]
        self.assertFalse(self.ready(rows));self.assertFalse(self.ready([]))
    def test_one_public_snapshot_per_poll_and_same_twenty_second_wait(self):
        self.assertEqual(PREDICATE.count('snapshotWithError:'),1)
        for remote in ['.exists','.enabled','.hittable','.frame','debugDescription',' tap]','swipe']:self.assertNotIn(remote,PREDICATE)
        self.assertIn('snapshot && !error && QRPhoneFilesPresentationSnapshotReady(snapshot)',PREDICATE)
        self.assertIn('XCTWaiterResult outcome = [XCTWaiter waitForExpectations:@[ready] timeout:20]',SOURCE)
        self.assertLess(SOURCE.index('if (outcome != XCTWaiterResultCompleted) return;'),SOURCE.index('if (![self visibleItem:@"QRCatcher-Test-Imports"])'))
        self.assertIn('if (item.exists && item.enabled && item.hittable) return item;',SOURCE)
        self.assertIn('snapshot.elementType == XCUIElementTypeOther ? QRFilesOther : QRFilesUnknown',SOURCE)
if __name__=='__main__':unittest.main()
