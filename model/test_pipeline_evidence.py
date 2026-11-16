"""离线复算已保存的真实输入，避免仅用模拟对象验证集成。"""
import gzip
import json
import unittest
from pathlib import Path
from benchmark_data import normalize
from total_return import build, risk

ROOT = Path(__file__).resolve().parents[1] / 'results/default-pipeline-2026-11-16'


def read(name):
    with gzip.open(ROOT / name, 'rt') as f:
        return json.load(f)


class Evidence(unittest.TestCase):
    def test_three_live_series_reproduce(self):
        for code in ('600900', '601919', '601225'):
            with self.subTest(code=code):
                result = read(code + '-risk.json.gz')
                source = result['source']; cal = source['calendar']
                self.assertEqual(sorted(r['date'] for r in source['daily']), cal['dates'])
                metrics = risk(build(source['daily'], source['events'], cal['start'], cal['end']))
                for field, actual in metrics.items():
                    stored = result['drawdown' if field == 'current_drawdown' else field]
                    self.assertAlmostEqual(actual, stored, places=10)

    def test_official_benchmarks_reproduce(self):
        calendars = read('benchmark-calendar.json.gz')
        sets = [{r[0] for r in calendars[c]['rows']} for c in ('sh000001', 'sz399001')]
        self.assertEqual(*sets)
        days = sorted(d for d in sets[0] if '2017-05-02' <= d <= '2026-10-30')
        self.assertEqual(len(days), 2307)
        for code in ('H00300', 'H00922'):
            actual = normalize(read(code + '-official.json.gz'), code, days)
            self.assertEqual(actual, read(code + '-normalized.json.gz'))
