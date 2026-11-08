import tempfile
import unittest
from pathlib import Path
from core import Store, usd

class CoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Store(Path(self.tmp.name)/'test.sqlite3')
 def tearDown(self):
  self.db.close();self.tmp.cleanup()
 def test_inventory_and_price_change(self):
  a,_=self.db.upsert('FB1314','1','Product','1.20',100)
  b,delta=self.db.upsert('FB1314','1','Product','1.50',87)
  self.assertEqual(a,b);self.assertEqual(delta,-13)
  self.assertEqual(len(self.db.history(a)),2)
  self.assertEqual(self.db.history(a)[0]['price_delta'],'0.30')
 def test_source_and_variant_isolation(self):
  self.db.upsert('FB1314','1','Test','1.0',10)
  self.db.upsert('CEOACC','1','Test','1.0',10,'US')
  self.db.upsert('CEOACC','1','Test','1.0',10,'JP')
  self.assertEqual(len(self.db.products()),3)
 def test_review_and_project_price(self):
  pid,_=self.db.upsert('CEOACC','1','Test','2.00',4)
  self.assertEqual(self.db.products()[0]['status'],'review')
  self.db.add_project('X');project=self.db.projects()[0]['id']
  self.db.project_assign(project,[pid]);self.db.set_project_price(project,pid,'9.99')
  self.assertEqual(self.db.project_products(project)[0]['custom_usd'],'9.99')
 def test_nonnegative_prices(self):
  with self.assertRaises(ValueError):usd('-2')
if __name__=='__main__':unittest.main()
