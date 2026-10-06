#!/usr/bin/env python3
"""Pure source-reader adversaries; no launcher scenario or expression executes."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[2]
TREE=ast.parse((ROOT/'Tests/Harness/test_ios_launcher.py').read_text())
FUNCTION=next(node for node in TREE.body if isinstance(node,ast.FunctionDef) and node.name=='exporter_inventory')
SCOPE={'ast':ast}
exec(compile(ast.Module(body=[FUNCTION],type_ignores=[]),'<owned exporter inventory reader>','exec'),SCOPE)
inventory=SCOPE['exporter_inventory']


class LauncherInventoryTests(unittest.TestCase):
    def test_actual_exporter_retains_all_original_files_results_and_logs(self):
        rows,logs=inventory(ast.parse((ROOT/'scripts/export_ios_platform_screenshots.py').read_text()))
        for basename,label in [('PhoneUIResults','pro-max'),('CompactPhoneUIResults','SE3'),('PadUIResults','ipad-pro-13'),('MiniUIResults','ipad-mini')]:
            self.assertIn((basename+'-files.xcresult',label+'-files'),rows)
            self.assertIn(basename+'-files.log',logs)

    def test_new_warmup_tuple_is_literal_and_processing_is_profile_gated(self):
        source=(ROOT/'scripts/export_ios_platform_screenshots.py').read_text()
        rows,_=inventory(ast.parse(source))
        self.assertEqual(rows.count(('MiniUIResults-warmup.xcresult','ipad-mini-warmup')),1)
        self.assertIn("if label=='ipad-mini-warmup' and not selected_identity:continue",source)

    def test_unrelated_dynamic_name_cap_inventory_is_not_evaluated(self):
        source="for name,cap in [('ipad-mini-job-state.json',job_ledger_limit())]:\n pass\nfor result,label in [('kept.xcresult','kept')]:\n pass\nfor name in ['ios-test-build.log','kept.log']:\n pass\n"
        self.assertEqual(inventory(ast.parse(source)),([('kept.xcresult','kept')],['ios-test-build.log','kept.log']))

    def test_other_dynamic_loop_target_is_ignored(self):
        self.assertEqual(inventory(ast.parse('for stage in [never_execute()]:\n pass\n')),([],[]))

    def test_dynamic_owned_result_inventory_still_fails_closed(self):
        with self.assertRaises(ValueError):inventory(ast.parse("for result,label in [('result.xcresult',never_execute())]:\n pass\n"))

    def test_dynamic_owned_log_inventory_still_fails_closed(self):
        with self.assertRaises(ValueError):inventory(ast.parse("for name in ['ios-test-build.log',never_execute()]:\n pass\n"))

    def test_wrong_result_target_cannot_supply_owned_inventory(self):
        self.assertEqual(inventory(ast.parse("for result,other in [('wrong.xcresult','wrong')]:\n pass\n")),([],[]))

    def test_parser_only_reads_literals_and_does_not_execute_source(self):
        source="raise RuntimeError('must not run')\nfor result,label in [('safe.xcresult','safe')]:\n pass\n"
        self.assertEqual(inventory(ast.parse(source)),([('safe.xcresult','safe')],[]))


if __name__=='__main__':unittest.main()
