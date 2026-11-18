import tempfile
import unittest
from pathlib import Path
from core import Store
from site_discovery import canonical_url, is_detail
from telegram_sender import send_photo

class AutomationTests(unittest.TestCase):
    def test_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            s=Store(Path(directory)/'db.sqlite3')
            jid=s.add_job('capture','capture',30,project_id=1)
            self.assertEqual(s.jobs()[0]['id'],jid)
            s.mark_job(jid)
            self.assertTrue(s.jobs()[0]['last_run'])
            s.delete_job(jid)
            self.assertFalse(s.jobs())
            s.close()
    def test_scan_host_restriction(self):
        self.assertIsNone(canonical_url('FB1314','https://bad.example/goods/42.html','https://fb1314.com/'))
        self.assertTrue(is_detail('FB1314','https://fb1314.com/goods/42.html'))
        self.assertIsNone(canonical_url('CEOACC','/checkout','https://ceoacc.com/'))
    def test_telegram_requires_credentials(self):
        with self.assertRaises(ValueError):send_photo('', '-100123', 'x.png')

if __name__=='__main__':unittest.main()
