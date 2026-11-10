import unittest
from site_discovery import should_finish_scroll, scroll_catalogue

class FastScrollTests(unittest.TestCase):
    def test_stops_after_stable_bottom(self):
        self.assertEqual(should_finish_scroll(3, True, False, True, 5), (True, True))
    def test_early_stop_if_zero_items(self):
        self.assertEqual(should_finish_scroll(4, False, False, False, 5), (True, False))
    def test_no_premature_success(self):
        self.assertEqual(should_finish_scroll(1, True, False, True, 1), (False, False))
    def test_does_not_require_movement_if_end_hint(self):
        self.assertEqual(should_finish_scroll(2, False, True, True, 4), (True, True))
    def test_defaults(self):
        self.assertEqual(scroll_catalogue.__defaults__[:2], (90,650))

if __name__=='__main__': unittest.main()
