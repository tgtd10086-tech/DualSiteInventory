import unittest
from task_runner import scan_result_complete

class ScanGateTests(unittest.TestCase):
    def test_clean_scan_is_accepted(self):
        self.assertTrue(scan_result_complete({'listed':10,'truncated':False,'failed':0,'incomplete_cards':0}))
    def test_incomplete_cards_reject_scan(self):
        self.assertFalse(scan_result_complete({'listed':10,'truncated':False,'failed':0,'incomplete_cards':2}))
    def test_truncated_or_failed_scan_rejected(self):
        self.assertFalse(scan_result_complete({'listed':10,'truncated':True,'failed':0,'incomplete_cards':0}))
        self.assertFalse(scan_result_complete({'listed':10,'truncated':False,'failed':1,'incomplete_cards':0}))
    def test_empty_scan_rejected(self):
        self.assertFalse(scan_result_complete({'listed':0,'truncated':False,'failed':0,'incomplete_cards':0}))

if __name__ == '__main__': unittest.main()
