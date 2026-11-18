"""Guard browser-list readiness detection against regressions on Windows."""
import unittest
from pathlib import Path
from unittest.mock import Mock
import site_discovery


class ListingWaitRegressionTests(unittest.TestCase):
    def test_wait_expression_uses_real_js_digit_and_whitespace_patterns(self):
        page = Mock()
        self.assertTrue(site_discovery.wait_for_catalogue_signal(page, 18000, 'CEOACC'))
        js = page.wait_for_function.call_args.args[0]
        self.assertIn(r'\d+', js)
        self.assertIn(r'\s*', js)
        self.assertNotIn(r'\\d', js)
        self.assertNotIn(r'\\s', js)

    def test_browser_evaluation_exception_is_not_reported_as_timeout(self):
        page = Mock()
        page.wait_for_function.side_effect = ValueError('unexpected browser error')
        with self.assertRaisesRegex(RuntimeError, 'unexpected browser error'):
            site_discovery.wait_for_catalogue_signal(page, 18000, 'FB1314')

    def test_timeout_returns_false(self):
        class TimeoutError(Exception):
            pass
        page = Mock()
        page.wait_for_function.side_effect = TimeoutError('waited for catalogue')
        self.assertFalse(site_discovery.wait_for_catalogue_signal(page, 18000, 'CEOACC'))

    def test_jsonl_log_writer_uses_newline_not_backslash_n(self):
        # Confirm source literal: a single escaped Python newline, not \\n text.
        src = (Path(__file__).resolve().parents[1] / 'task_runner.py').read_text(encoding='utf-8')
        self.assertIn("+'\\n')", src)
        self.assertNotIn("+'\\\\n')", src)


if __name__ == '__main__':
    unittest.main()
