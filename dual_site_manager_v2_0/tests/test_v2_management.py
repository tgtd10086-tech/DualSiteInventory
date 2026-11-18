import tempfile
import unittest
from pathlib import Path
from core import Store
from image_render import prepare_public_items, render_project

class V2ManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite3')
        self.store.register_categories('FB1314',[{'key':'cat','title':'分类'}]);self.store.set_category_state([1],'enabled')
        self.store.ingest_category_scan('FB1314',[
            {'external_id':'1','name':'商品A','price':'1.00','stock':100,'category_key':'cat','product_type':'Facebook'},
            {'external_id':'2','name':'商品B','price':'2.00','stock':80,'category_key':'cat','product_type':'邮箱'}],{'cat'},True)
        self.ids={r['external_id']:r['id'] for r in self.store.products('FB1314')}
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def test_pending_assigned_excluded_move_between_views(self):
        self.assertEqual(len(self.store.products_for_management(membership='pending')),2)
        self.store.add_project('项目A');pid=self.store.projects()[0]['id']
        self.store.project_assign(pid,[self.ids['1']])
        self.assertEqual([r['external_id'] for r in self.store.products_for_management(membership='pending')],['2'])
        self.assertEqual([r['external_id'] for r in self.store.products_for_management(membership='assigned')],['1'])
        self.store.project_remove(pid,[self.ids['1']])
        self.assertEqual(len(self.store.products_for_management(membership='pending')),2)
    def test_multi_project_overrides_and_exclusion(self):
        self.store.add_project('A');self.store.add_project('B');a,b=[r['id'] for r in self.store.projects()]
        product=self.ids['1'];self.store.project_assign(a,[product]);self.store.project_assign(b,[product])
        self.store.set_project_display(a,product,'A名称','5.00');self.store.set_project_display(b,product,'B名称','7.00')
        self.assertEqual(self.store.project_products(a)[0]['effective_name'],'A名称')
        self.assertEqual(self.store.project_products(b)[0]['effective_usd'],'7.00')
        self.store.set_status([product],'excluded')
        row=self.store.project_products(a)[0]
        self.assertEqual(row['include_in_capture'],1)
    def test_single_sales_window(self):
        self.store.add_project('销量');pid=self.store.projects()[0]['id']
        self.store.set_project_periods(pid,['7d'])
        self.assertEqual(self.store.get_project_periods(pid),('7d',))
        with self.assertRaises(ValueError):self.store.set_project_periods(pid,['24h','30d'])
    def test_management_sort_and_counts(self):
        rows=self.store.products_for_management(membership='pending',sort='price_desc')
        self.assertEqual(rows[0]['external_id'],'2')
        self.assertEqual(self.store.management_counts()['pending'],2)

    def test_management_sales_sort_uses_conservative_sales_window(self):
        # No sufficient history means the management table must return None,
        # rather than inventing zero sales or sorting by a stale fixed 3h rule.
        rows=self.store.products_for_management(sort='sales_24h')
        self.assertEqual(len(rows),2)
        self.assertTrue(all(row['sales24'] is None for row in rows))
        self.assertTrue(all('sales7' in row and 'sales30' in row for row in rows))

    def test_project_remove_does_not_delete_product(self):
        self.store.add_project('项目');pid=self.store.projects()[0]['id'];product=self.ids['1']
        self.store.project_assign(pid,[product]);self.store.project_remove(pid,[product])
        self.assertIsNotNone(self.store.conn.execute('SELECT id FROM products WHERE id=?',(product,)).fetchone())
    def test_batch_rename_and_project_batch_price(self):
        product=self.ids['1'];self.store.bulk_set_display([product],name_prefix='特价-',price_mode='keep')
        self.assertEqual(self.store.conn.execute('SELECT display_name FROM products WHERE id=?',(product,)).fetchone()['display_name'],'特价-商品A')
        self.store.add_project('项目批量');project=self.store.projects()[0]['id'];self.store.project_assign(project,[product])
        self.store.bulk_set_project_display(project,[product],name_suffix='-专属',price='6.66')
        row=self.store.project_products(project)[0]
        self.assertEqual((row['effective_name'],row['effective_usd']),('特价-商品A-专属','6.66'))

    def test_excluded_project_item_is_not_public(self):
        product=self.ids['1'];self.store.add_project('隐藏测试');project=self.store.projects()[0]['id']
        self.store.project_assign(project,[product]);self.store.set_project_display(project,product,'测试展示','5.00')
        self.store.set_status([product],'excluded')
        self.assertEqual(prepare_public_items(self.store.project_products(project)),[])

    def test_render_uses_single_sales_column_and_custom_price(self):
        self.store.add_project('截图项目');project=self.store.projects()[0]['id'];product=self.ids['1']
        self.store.project_assign(project,[product]);self.store.set_project_display(project,product,'截图商品名','8.88')
        rows=self.store.project_products(project)
        with tempfile.TemporaryDirectory() as out:
            paths=render_project(rows,'截图项目',Path(out),sales_periods=('7d',),sales_by_product={product:{'7d':12}})
            self.assertEqual(len(paths),1)
            self.assertTrue(Path(paths[0]).is_file())
        with self.assertRaises(ValueError):
            render_project(rows,'截图项目',Path(self.tmp.name),sales_periods=('24h','7d'))

    def test_bulk_price_never_uses_raw_price_as_fallback(self):
        product=self.ids['1'];self.store.bulk_set_display([product],price='3.50')
        row=self.store.conn.execute('SELECT raw_usd,display_usd FROM products WHERE id=?',(product,)).fetchone()
        self.assertEqual((row['raw_usd'],row['display_usd']),('1.00','3.50'))

if __name__=='__main__':unittest.main()
