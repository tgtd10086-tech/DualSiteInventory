import json
import tempfile
import unittest
from pathlib import Path
from site_discovery import write_scan_diagnostic

class ScanDiagnosticTests(unittest.TestCase):
    def test_report_records_coverage_without_private_page_content(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(write_scan_diagnostic(d,'CEOACC',{'coverage':'incomplete','visited':2},
                ['page failed'],[{'url':'https://ceoacc.com/?action=home&category=123','title':'catalogue',
                                  'category_links':4,'pagination_links':2}],7))
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['source'],'CEOACC')
            self.assertEqual(data['product_count'],7)
            self.assertEqual(data['stats']['coverage'],'incomplete')
            self.assertIn('login-restricted',data['note'])
            self.assertNotIn('cookies',data)

    def test_report_caps_error_list(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(write_scan_diagnostic(d,'FB1314',{},[str(i) for i in range(150)],[],0))
            data=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(len(data['errors']),100)

if __name__=='__main__':
    unittest.main()
