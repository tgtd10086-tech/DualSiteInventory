import tempfile
import time
import unittest
from pathlib import Path
from core import Store


class SchedulerClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'inventory.sqlite3'
        self.a = Store(self.path)
        self.b = Store(self.path)
        self.job_id = self.a.add_job('定时全站采集', 'discover', 30, source='FB1314')
        with self.a.conn:
            self.a.conn.execute('UPDATE automation_jobs SET next_run=? WHERE id=?', (time.time()-1, self.job_id))

    def tearDown(self):
        self.a.close(); self.b.close(); self.tmp.cleanup()

    def test_only_one_instance_claims_due_job(self):
        first = self.a.claim_due_job(lease_seconds=120)
        second = self.b.claim_due_job(lease_seconds=120)
        self.assertIsNotNone(first)
        self.assertEqual(first['id'], self.job_id)
        self.assertIsNone(second)

    def test_expired_claim_can_be_recovered(self):
        first = self.a.claim_due_job(lease_seconds=60)
        with self.b.conn:
            self.b.conn.execute('UPDATE automation_jobs SET claimed_until=? WHERE id=?', (time.time()-1, self.job_id))
        second = self.b.claim_due_job(lease_seconds=60)
        self.assertIsNotNone(second)
        self.assertNotEqual(first['claim_token'], second['claim_token'])

    def test_mark_job_clears_claim_and_schedules_next_run(self):
        claimed = self.a.claim_due_job(lease_seconds=120)
        self.a.mark_job(self.job_id, 'test failure')
        row = self.a.conn.execute('SELECT * FROM automation_jobs WHERE id=?', (self.job_id,)).fetchone()
        self.assertIsNone(row['claim_token'])
        self.assertIsNone(row['claimed_until'])
        self.assertEqual(row['last_error'], 'test failure')
        self.assertGreater(row['next_run'], time.time())

    def test_release_claim_is_token_scoped(self):
        claimed = self.a.claim_due_job(lease_seconds=120)
        self.b.release_job_claim(self.job_id, 'wrong-token')
        row = self.a.conn.execute('SELECT claim_token FROM automation_jobs WHERE id=?', (self.job_id,)).fetchone()
        self.assertEqual(row['claim_token'], claimed['claim_token'])
        self.b.release_job_claim(self.job_id, claimed['claim_token'])
        row = self.a.conn.execute('SELECT claim_token FROM automation_jobs WHERE id=?', (self.job_id,)).fetchone()
        self.assertIsNone(row['claim_token'])


if __name__ == '__main__':
    unittest.main()
