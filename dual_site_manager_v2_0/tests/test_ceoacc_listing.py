import unittest
from site_discovery import parse_listing_cards

class CEOACCListParsing(unittest.TestCase):
    def test_ceoacc_visible_table_row(self):
        items,missing=parse_listing_cards('CEOACC',[{'text':'Facebook-存活 3-15 天(2FA-SMS-域名Email) 剩余:25 $0.63 购买', 'name':'','href':'','cells':['Facebook-存活 3-15 天(2FA-SMS-域名Email)','剩余:25','$0.63']}], 'https://ceoacc.com/')
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['stock'],25)
        self.assertEqual(items[0]['price'],'0.63')
    def test_missing_usd_does_not_invent_price(self):
        items,missing=parse_listing_cards('CEOACC',[{'text':'测试商品 剩余:25 0.63', 'name':'测试商品','cells':['测试商品','剩余:25','0.63']}],'https://ceoacc.com/')
        self.assertEqual(items,[])
