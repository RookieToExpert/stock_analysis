from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from collect_gap_reports import disclosures, report_kind


class IssuerArchive(unittest.TestCase):
    def test_truncated_index_is_bisected_without_trusting_repeated_page_numbers(self):
        seen = []
        def query(method, url, pace, *, data):
            interval = data['seDate']
            seen.append(interval)
            truncated = len(seen) == 1
            code = '600001'
            ident = '100' if len(seen) < 3 else '101'
            notice = {'secCode': code, 'orgId': 'org', 'announcementTime':
                      datetime.fromisoformat(interval[:10]).replace(tzinfo=timezone.utc).timestamp() * 1000,
                      'adjunctUrl': f'finalpage/2023-03-01/{ident}.PDF',
                      'announcementId': ident, 'announcementTitle': '2022年年度报告'}
            result = {'totalAnnouncement': 31 if truncated else 1, 'hasMore': truncated,
                      'announcements': [notice]}
            return Mock(json=lambda: result)
        with tempfile.TemporaryDirectory() as tmp, patch('collect_gap_reports.request', query):
            root = Path(tmp)
            (root/'index').mkdir()
            result = disclosures('sh.600001', 'org', {2022}, '2023-02-28', root, None)
        self.assertEqual(len(set(seen)), 3)
        self.assertEqual([r['id'] for r in result], ['100', '101'])

    def test_annual_report_titles_preserve_revisions_and_ignore_written_opinions(self):
        self.assertEqual(report_kind('600199_2021年_年度报告（修订版）', 2021), 'full')
        self.assertEqual(report_kind('2021年度报告摘要', 2021), 'summary')
        self.assertIsNone(report_kind('关于2021年度报告的书面确认意见', 2021))
