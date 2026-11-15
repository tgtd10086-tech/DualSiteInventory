import tempfile
import unittest
import sqlite3
from pathlib import Path
from core import Store

class CustomDisplayTest(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.path=Path(self.dir.name)/'store.sqlite3'
        self.store=Store(self.path)
    def tearDown(self):
        self.store.close(); self.dir.cleanup()
    def test_override_survives_scrape(self):
        pid,_=self.store.upsert('FB1314','8031','网站原名','7.20',230)
        self.store.set_display(pid,'我的展示名','12')
        self.store.add_project('A');project_a=self.store.projects()[0]['id']
        self.store.add_project('B');project_b=self.store.projects()[1]['id']
        self.store.project_assign(project_a,[pid]);self.store.project_assign(project_b,[pid])
        self.store.set_project_display(project_a,pid,'项目A名称','15')
        self.store.upsert('FB1314','8031','网站更改后的名称','8.20',210)
        raw=self.store.products()[0]
        self.assertEqual(raw['name'],'网站更改后的名称')
        self.assertEqual(raw['display_name'],'我的展示名')
        self.assertEqual(raw['display_usd'],'12.00')
        self.assertEqual(raw['stock'],210)
        ra=self.store.project_products(project_a)[0]
        rb=self.store.project_products(project_b)[0]
        self.assertEqual((ra['effective_name'],ra['effective_usd']),('项目A名称','15.00'))
        self.assertEqual((rb['effective_name'],rb['effective_usd']),('我的展示名','12.00'))
    def test_clear_overrides(self):
        pid,_=self.store.upsert('CEOACC','10','原名','3.20',2)
        self.store.set_display(pid,'临时','5')
        self.store.set_display(pid,'','')
        self.assertIsNone(self.store.products()[0]['display_name'])
        self.assertIsNone(self.store.products()[0]['display_usd'])
    def test_upgrade_legacy_schema(self):
        self.store.close()
        db=sqlite3.connect(str(self.path))
        db.execute('DROP TABLE project_products'); db.execute('DROP TABLE products')
        db.execute("CREATE TABLE products(id INTEGER PRIMARY KEY, source TEXT, external_id TEXT,variant TEXT,name TEXT,url TEXT,raw_usd TEXT,stock INTEGER,status TEXT,first_seen TEXT,updated_at TEXT)")
        db.execute("CREATE TABLE project_products(project_id INTEGER,product_id INTEGER,custom_usd TEXT,sort_order INTEGER)")
        db.commit();db.close()
        self.store=Store(self.path)
        cols=[r['name'] for r in self.store.conn.execute('PRAGMA table_info(products)')]
        self.assertIn('display_name',cols)
        cols=[r['name'] for r in self.store.conn.execute('PRAGMA table_info(project_products)')]
        self.assertIn('custom_name',cols)

if __name__=='__main__': unittest.main()
