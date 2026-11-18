import json
import tempfile
import time
import unittest
from pathlib import Path

from core import Store
from site_discovery import write_scan_diagnostic


class V22CollectionOpsTests(unittest.TestCase):
    def test_custom_first_start_time_is_saved_and_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite3")
            try:
                future = time.localtime(time.time() + 3600)
                start = time.strftime("%Y-%m-%d %H:%M", future)
                job_id = store.add_job("CEOACC循环采集", "discover", 360, source="CEOACC",
                                       start_at=start)
                row = store.conn.execute(
                    "SELECT start_at,next_run,interval_minutes FROM automation_jobs WHERE id=?",
                    (job_id,)).fetchone()
                self.assertEqual(row["start_at"], start)
                self.assertGreater(row["next_run"], time.time())
                self.assertEqual(row["interval_minutes"], 360)
            finally:
                store.close()

    def test_invalid_or_past_start_time_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite3")
            try:
                with self.assertRaises(ValueError):
                    store.add_job("bad", "discover", 360, source="CEOACC",
                                  start_at="not-a-date")
                with self.assertRaises(ValueError):
                    store.add_job("past", "discover", 360, source="CEOACC",
                                  start_at="2000-01-01 00:00")
            finally:
                store.close()

    def test_scan_diagnostic_is_written_and_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = write_scan_diagnostic(Path(tmp) / "Diagnostics" / "ceoacc",
                "CEOACC", {"visited": 4, "failed": 2, "incomplete_cards": 5},
                ["category A failed", "category B failed"], [], 546)
            path = Path(report)
            self.assertTrue(path.is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["product_count"], 546)
            history = path.parent / "scan_history.jsonl"
            self.assertTrue(history.is_file())
            records = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertTrue(records)
            self.assertEqual(records[-1]["report"], str(path))
            self.assertEqual(records[-1]["product_count"], 546)

            # JSONL must contain one independently decodable JSON object per line.
            write_scan_diagnostic(path.parent, "CEOACC", {"visited": 1}, [], [], 12)
            records = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[-1]["product_count"], 12)

            # On Windows JSON escapes backslashes; comparing decoded fields is portable.
            windows_path = r"C:\Users\Test\Documents\scan_report.json"
            self.assertEqual(json.loads(json.dumps({"report": windows_path}))["report"], windows_path)


if __name__ == "__main__":
    unittest.main()
