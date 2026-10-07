"""Local image generation regressions; never launch native tools."""
import hashlib,json,shutil,tempfile,unittest
from pathlib import Path
import materialize_tv_2x_assets as assets
class AssetTests(unittest.TestCase):
    def test_exact_two_mechanical_outputs_and_honest_raster_limits(self):
        result=assets.verify()
        self.assertEqual(len(result['assets']),2)
        self.assertFalse(result['vector_source_available']);self.assertFalse(result['new_detail_created'])
        self.assertFalse(result['existing_small_2x_or_1x_files_rewritten'])
        self.assertEqual(result['source_enlargement'],1.40625)
    def test_regeneration_changes_only_two_top_shelf_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            paths=[assets.SOURCE]+[str(p.relative_to(assets.ROOT)) for p in (assets.ROOT/assets.CATALOG).rglob('*') if p.is_file()]
            for name in paths:
                out=root/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(assets.ROOT/name,out)
            before={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths}
            assets.materialize(root)
            self.assertEqual(before,{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in paths})
    def test_missing_scale_and_changed_source_or_output_reject(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in [assets.SOURCE]+[str(p.relative_to(assets.ROOT)) for p in (assets.ROOT/assets.CATALOG).rglob('*') if p.is_file()]:
                out=root/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(assets.ROOT/name,out)
            path=root/assets.CATALOG/'TopShelf.imageset/Contents.json';v=json.loads(path.read_text());v['images'].pop();path.write_text(json.dumps(v))
            with self.assertRaises(ValueError):assets.verify(root)
            (root/assets.SOURCE).write_bytes(b'changed')
            with self.assertRaises(ValueError):assets.source(root)
    def test_archive_materializer_preserves_existing_native_recipe_without_other_platforms(self):
        original=(assets.ROOT/'scripts/materialize_native_icons.swift').read_text()
        projected=(assets.ROOT/'scripts/materialize_tv_archive_assets.swift').read_text()
        def function(text):return text[text.index('func render('):text.index('\n}',text.index('func render('))+2]
        self.assertEqual(function(original),function(projected))
        self.assertEqual(original[original.index('let tv = '):],projected[projected.index('let tv = '):])
        self.assertNotIn('QRCatcherWatch',projected);self.assertNotIn('QRCatcherVision',projected)
    def test_existing_small_two_scale_declarations_untouched(self):
        for layer in ('Back','Front'):
            p=assets.ROOT/assets.CATALOG/f'Small.imagestack/{layer}.imagestacklayer/Content.imageset/Contents.json'
            self.assertEqual(json.loads(p.read_text())['images'],[{'filename':'Icon-1x.png','idiom':'tv','scale':'1x'},{'filename':'Icon-2x.png','idiom':'tv','scale':'2x'}])
if __name__=='__main__':unittest.main()
