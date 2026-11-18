import tempfile
import unittest
from pathlib import Path
from core import Store

class PublishResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.store.add_project('测试项目')
        self.pid=self.store.projects()[0]['id']
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def test_successful_page_is_remembered(self):
        self.store.record_publish_page(self.pid,'-1001','batch-1',0,'success',message_id=123)
        self.assertTrue(self.store.publish_page_done('batch-1',0))
        self.assertFalse(self.store.publish_page_done('batch-1',1))
    def test_failed_page_can_be_retried(self):
        self.store.record_publish_page(self.pid,'-1001','batch-1',1,'failed',detail='timeout')
        self.assertFalse(self.store.publish_page_done('batch-1',1))
        self.store.record_publish_page(self.pid,'-1001','batch-1',1,'success',message_id=456)
        self.assertTrue(self.store.publish_page_done('batch-1',1))
    def test_legacy_publish_log_migrates(self):
        self.store.record_publish_page(self.pid,'-1001','batch-2',0,'success',message_id=789)
        row=self.store.conn.execute('SELECT message_id FROM publish_log WHERE batch_key=?',('batch-2',)).fetchone()
        self.assertEqual(row['message_id'],'789')

if __name__=='__main__': unittest.main()
