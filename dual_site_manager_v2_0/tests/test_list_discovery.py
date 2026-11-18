import unittest
from site_discovery import parse_listing_cards,stable_id,canonical_url,is_detail,CATEGORY
class ListingTests(unittest.TestCase):
    def test_ceo_table(self):
        rows=[{'text':'', 'name':'','cells':['产品 A','120','$2.50'],'href':'','id':'product-7'}]
        items,missing=parse_listing_cards('CEOACC',rows,'https://ceoacc.com/')
        self.assertEqual((len(items),items[0]['stock'],items[0]['price']), (1,120,'2.50'))
        self.assertEqual(items[0]['external_id'],'product-7')
    def test_fb_cards(self):
        rows=[{'text':'热门商品 库存：1,250 $3.99','name':'热门商品','href':'/goods/8031.html','id':''}]
        items,missing=parse_listing_cards('FB1314',rows,'https://fb1314.com/')
        self.assertEqual((items[0]['external_id'],items[0]['stock']),('8031',1250))
    def test_no_invented_currency_or_stock(self):
        rows=[{'text':'商品 价 99元 库存 30','name':'商品测试','href':'','id':''},
              {'text':'商品 $5.00 库存未知','name':'库存测试','href':'','id':''}]
        items,missing=parse_listing_cards('CEOACC',rows,'https://ceoacc.com/')
        self.assertEqual((len(items),missing),(0,2))

    def test_navigation_heading_is_not_counted_as_incomplete_product(self):
        rows=[{'text':'账号商城 热门推荐','name':'热门推荐','href':'','id':'','cells':[]}]
        items,missing=parse_listing_cards('CEOACC',rows,'https://ceoacc.com/')
        self.assertEqual((items,missing),([],0))

    def test_stable_id_across_categories(self):
        a=stable_id('CEOACC','同一商品')
        b=stable_id('CEOACC',' 同一商品 ')
        self.assertEqual(a,b)
    def test_disallow_external(self):
        self.assertIsNone(canonical_url('CEOACC','https://evil.com/abc','https://ceoacc.com/'))
    def test_fb_category_id_link_recognized(self):
        self.assertTrue(CATEGORY.search("https://fb1314.com/?category_id=12"))
    def test_detail_not_category(self):
        self.assertTrue(is_detail('FB1314','https://fb1314.com/goods/8031.html'))
if __name__=='__main__': unittest.main()

class _FakeLocator:
    def __init__(self, rows): self.rows=rows
    def evaluate_all(self, js): return self.rows

class _FakePage:
    def __init__(self, rows): self.rows=rows
    def locator(self, selector): return _FakeLocator(self.rows)

class PaginationTests(unittest.TestCase):
    def test_explicit_next_link_is_followed(self):
        from site_discovery import pagination_links
        page=_FakePage([{'href':'?page=2','text':'下一页','rel':'','aria':'','cls':'','parent':''}])
        self.assertEqual(pagination_links(page,'CEOACC','https://ceoacc.com/category/a'),
                         ['https://ceoacc.com/category/a?page=2'])

    def test_pagination_number_links_are_followed(self):
        from site_discovery import pagination_links
        page=_FakePage([{'href':'?page=3','text':'3','rel':'','aria':'','cls':'page-item','parent':'pagination'}])
        self.assertEqual(pagination_links(page,'FB1314','https://fb1314.com/category/a'),
                         ['https://fb1314.com/category/a?page=3'])

    def test_product_detail_and_external_links_are_rejected(self):
        from site_discovery import pagination_links
        page=_FakePage([
            {'href':'/goods/123.html','text':'下一页','rel':'next','aria':'','cls':'','parent':''},
            {'href':'https://evil.example/page/2','text':'下一页','rel':'next','aria':'','cls':'','parent':''},
        ])
        self.assertEqual(pagination_links(page,'FB1314','https://fb1314.com/category/a'), [])

class CEOACCCategoryURLTests(unittest.TestCase):
    def test_ceoacc_query_category_url_is_catalogue(self):
        from site_discovery import canonical_url, CATEGORY, is_detail
        url=canonical_url('CEOACC','/?action=home&category=1370660','https://ceoacc.com/')
        self.assertEqual(url,'https://ceoacc.com/?action=home&category=1370660')
        self.assertTrue(CATEGORY.search(url))
        self.assertFalse(is_detail('CEOACC',url))
