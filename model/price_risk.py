"""同一前复权月线上的风险代理；不是已验证的全收益序列。"""
import math
from datetime import date
from statistics import stdev


def calculate(klines, as_of):
    day = date.fromisoformat(as_of)
    cutoff = day.year * 12 + day.month - 1  # 当前月永远排除
    result = dict(version='monthly-proxy-1', basis='eastmoney-fqt1',
                  total_return_verified=False, as_of=as_of, status='unknown',
                  reason=None, drawdown=None, vol=None, high36=None,
                  reference_close=None, reference_date=None, closes=[])
    try:
        rows = {}
        for raw in klines:
            fields = raw.split(',')
            stamp = date.fromisoformat(fields[0])
            month = stamp.year * 12 + stamp.month - 1
            if month >= cutoff:
                continue
            close, high, low = map(float, (fields[2], fields[3], fields[4]))
            if month in rows:
                raise ValueError('duplicate month')
            rows[month] = (stamp.isoformat(), close, high, low)
        required = list(range(cutoff - 37, cutoff))
        if any(m not in rows for m in required):
            raise ValueError('need 37 consecutive completed months')
        selected = [rows[m] for m in required]
        if any(not all(math.isfinite(v) and v > 0 for v in row[1:]) or not row[3] <= row[1] <= row[2] for row in selected):
            raise ValueError('invalid price')
        closes = [row[1] for row in selected]
        high = max(row[2] for row in selected[-36:])
        returns = [b/a-1 for a,b in zip(closes, closes[1:])]
        result.update(status='proxy', drawdown=(1-closes[-1]/high)*100,
                      vol=stdev(returns)*math.sqrt(12)*100, high36=high,
                      reference_close=closes[-1], reference_date=selected[-1][0], closes=closes)
    except (ValueError, IndexError, TypeError, OverflowError) as exc:
        result['reason'] = str(exc)
    return result
