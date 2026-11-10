import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from core import Store
from image_render import prepare_public_items

class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.ca='https://ceoacc.com/category/11'
        self.cb='https://ceoacc.com/category/22'
        self.store.register_categories('CEOACC',[{'key':self.ca,'title':'采集类目'},{'key':self.cb,'title':'排除类目'}])
        self.ids={r['category_key']:r['id'] for r in self.store.categories('CEOACC')}
        self.store.set_category_state([self.ids[self.ca]],'enabled')
        self.store.set_category_state([self.ids[self.cb]],'excluded')
    def tearDown(self):
        self.store.close();self.tmp.cleanup()
    def item(self,id,key=None):
        return {'source':'CEOACC','external_id':id,'name':'测试商品'+id,
                'price':'0.63','stock':25,'url':'https://ceoacc.com/',
                'category_keys':[key or self.ca]}
    def test_excluded_category_cannot_write(self):
        n=self.store.ingest_category_scan('CEOACC',[self.item('1'),self.item('2',self.cb)],{self.ca},True)
        self.assertEqual(n,1)
        self.assertEqual([r['external_id'] for r in self.store.products('CEOACC')],['1'])
    def test_unverified_scan_does_not_touch_db_or_snapshots(self):
        self.store.ingest_category_scan('CEOACC',[self.item('1')],{self.ca},True)
        before=self.store.conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
        item=self.item('1');item['stock']=1
        n=self.store.ingest_category_scan('CEOACC',[item],{self.ca},False)
        self.assertEqual(n,0)
        self.assertEqual(self.store.products('CEOACC')[0]['stock'],25)
        self.assertEqual(self.store.conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0],before)
    def test_atomic_rollback_on_bad_item(self):
        bad=self.item('bad');bad['price']='not usd'
        with self.assertRaises(ValueError):self.store.ingest_category_scan('CEOACC',[self.item('1'),bad],{self.ca},True)
        self.assertEqual(len(self.store.products('CEOACC')),0)
    def test_category_whitelist_cannot_escalate(self):
        with self.assertRaises(ValueError):self.store.ingest_category_scan('CEOACC',[self.item('2',self.cb)],{self.cb},True)
    def test_custom_prices_never_fall_back_to_raw(self):
        self.store.ingest_category_scan('CEOACC',[self.item('1')],{self.ca},True)
        pid=self.store.products()[0]['id']
        self.store.add_project('我的项目'); project=self.store.projects()[0]['id'];self.store.project_assign(project,[pid])
        row=self.store.project_products(project)[0]
        self.assertIsNone(row['effective_usd'])
        with self.assertRaisesRegex(ValueError,'原价'):
            prepare_public_items([row])
        self.store.set_project_price(project,pid,'3.45')
        public=prepare_public_items(self.store.project_products(project))
        self.assertEqual(public[0]['price'],'3.45')
        self.assertNotIn('raw_usd',public[0])
    def test_original_and_overrides_survive_rescan(self):
        self.store.ingest_category_scan('CEOACC',[self.item('1')],{self.ca},True)
        pid=self.store.products()[0]['id'];self.store.set_display(pid,'我自己的名称','4.20')
        item=self.item('1');item.update(name='网站改名',price='0.99',stock=15)
        self.store.ingest_category_scan('CEOACC',[item],{self.ca},True)
        p=self.store.products()[0]
        self.assertEqual((p['name'],p['raw_usd'],p['stock']),('网站改名','0.99',15))
        self.assertEqual((p['display_name'],p['display_usd']),('我自己的名称','4.20'))
    def test_periods_and_insufficient_history(self):
        self.store.ingest_category_scan('CEOACC',[self.item('1')],{self.ca},True)
        pid=self.store.products()[0]['id']
        self.assertEqual(self.store.sales_windows(pid),{'24h':None,'7d':None,'30d':None})
        self.store.add_project('周报');proj=self.store.projects()[0]['id']
        self.store.set_project_periods(proj,['7d','30d'])
        self.assertEqual(self.store.get_project_periods(proj),('7d','30d'))
    def test_product_exclusion_is_respected(self):
        self.store.ingest_category_scan('CEOACC',[self.item('1')],{self.ca},True)
        pid=self.store.products()[0]['id'];self.store.set_status([pid],'excluded')
        item=self.item('1');item['stock']=1
        self.assertEqual(self.store.ingest_category_scan('CEOACC',[item],{self.ca},True),0)
        self.assertEqual(self.store.products()[0]['stock'],25)
if __name__=='__main__':unittest.main()

class ScheduleTests(unittest.TestCase):
    def test_daily_clock_validation(self):
        self.assertRaises(ValueError,Store.next_daily_run,'25:00')
        self.assertRaises(ValueError,Store.next_daily_run,'')
        now=datetime.now().astimezone()
        nxt=Store.next_daily_run('08:00,20:00',now.timestamp())
        self.assertTrue(0<nxt-now.timestamp()<=24*3600)
