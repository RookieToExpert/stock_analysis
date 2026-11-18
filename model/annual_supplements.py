"""Dated issuer amounts and ratios supplementing the PIT provider's missing annual fields."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import zlib

EVIDENCE = Path(__file__).resolve().parents[1] / 'results' / 'issuer-annual-2026-11-18'
PROVIDER_TABLES = ('profit', 'cash', 'balance', 'dupont')


@lru_cache(maxsize=1)
def bundle_index():
    return json.loads((EVIDENCE / 'index.json').read_bytes())['shards']


@lru_cache(maxsize=32)
def shard(prefix):
    expected = bundle_index().get(prefix)
    if not expected:
        return {}
    content = (EVIDENCE / 'evidence' / (prefix + '.json.gz')).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        return {}
    return json.loads(gzip.decompress(content))


def verified_annual_version(data, period, day):
    """Use only publications visible as of day, tied to the observed provider edition."""
    code = data.get('code')
    if not isinstance(code, str):
        return None
    try:
        date.fromisoformat(period)
        date.fromisoformat(day)
        company = shard(code[:6]).get(code, {})
        record = company.get(period)
        if not record:
            return None
        versions = [v for v in record['versions'] if period <= v['available_date'] < day]
        if not versions:
            return None
        version = max(versions, key=lambda v: v['available_date'])
        for table in PROVIDER_TABLES:
            rows = [r for r in data.get('fin', {}).get(table, []) if r.get('statDate') == period
                    and r.get('pubDate') and r['pubDate'] < day]
            pub = record['provider_dates'].get(table)
            if not pub and not rows:
                continue
            if len(rows) != 1 or rows[0]['pubDate'] != pub or rows[0].get('code', code) != code:
                return None
            for field, expected in record['anchors'].get(table, {}).items():
                if Decimal(rows[0][field]) != Decimal(expected):
                    return None
        return version
    except (OSError, EOFError, zlib.error, KeyError, ValueError, TypeError, InvalidOperation):
        return None


def field_value(version, field):
    if version is None:
        return None
    value = version['facts'].get(field)
    if value is None:
        return None
    number = Decimal(value)
    return number if number.is_finite() else None


def later_reported_shares(data, day, after_period):
    """Find a later, already published annual share count when its provider profit row is absent."""
    code = data.get('code')
    if not isinstance(code, str):
        return None
    try:
        years = shard(code[:6]).get(code, {})
        for period in sorted((p for p in years if after_period < p < day), reverse=True):
            if 'profit' in years[period]['provider_dates']:
                continue
            version = verified_annual_version(data, period, day)
            shares = field_value(version, 'totalShare')
            if shares is not None:
                return period, version['available_date'], shares
    except (OSError, EOFError, zlib.error, KeyError, ValueError, TypeError, InvalidOperation):
        pass
    return None
