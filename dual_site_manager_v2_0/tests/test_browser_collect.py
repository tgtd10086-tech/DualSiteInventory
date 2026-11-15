import unittest
from browser_collect import validate_link,modal_action,extract_fb,extract_ceo_from_jsonld

class BrowserTest(unittest.TestCase):
    def test_popup_decision(self):
        self.assertEqual(modal_action('FB1314',['收藏本站','继续 Continue']),'继续 Continue')
        self.assertEqual(modal_action('CEOACC',['关闭','不再显示']),'不再显示')
    def test_reject_other_domains(self):
        for s,url in [('CEOACC','https://ceoacc.com.evil.com/a'),('FB1314','http://fb1314.com/goods/1.html')]:
            with self.assertRaises(ValueError):validate_link(s,url)
    def test_fb_extract(self):
        text='商品A\n自动发货 库存 28\n$2.70\n立即购买'
        rec=extract_fb(text,'https://fb1314.com/goods/8031.html')
        self.assertEqual((rec['stock'],rec['price'],rec['external_id']),(28,'2.70','8031'))
    def test_ceo_requires_explicit_usd_and_stock(self):
        block='{"@type":"Product","name":"A","sku":"20","offers":{"price":"1.99","priceCurrency":"USD","inventoryLevel":5}}'
        rec=extract_ceo_from_jsonld([block],'https://ceoacc.com/a')
        self.assertEqual(rec['stock'],5)
        with self.assertRaises(ValueError):extract_ceo_from_jsonld([block.replace('"USD"','"CNY"')],'https://ceoacc.com/a')
        with self.assertRaises(ValueError):extract_ceo_from_jsonld(['{}'],'https://ceoacc.com/a')
if __name__=='__main__':unittest.main()
