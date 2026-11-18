"""Dated issuer amounts and ratios supplementing the PIT provider's missing annual fields."""
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import csv
import gzip
import hashlib
import json
from pathlib import Path
import zlib

EVIDENCE = Path(__file__).resolve().parents[1] / 'results' / 'issuer-annual-2026-11-18'
PROVIDER_TABLES = ('profit', 'cash', 'balance', 'dupont')


@lru_cache(maxsize=1)
def first_annual_releases():
    history = EVIDENCE / 'historical'
    releases = {}
    for name, field, link in [('late-annual-reports.csv', '首次公开年报或摘要日', '公司公告'),
                              ('late-financial-fields.csv', '首次正式年报或摘要日', '首次正式披露')]:
        with (history / name).open(encoding='utf-8-sig', newline='') as source:
            for row in csv.DictReader(source):
                releases[row['证券代码'], row['报告期']] = {
                    'date': date.fromisoformat(row[field]).isoformat(), 'source': row[link],
                    'delay_notice': row.get('相关延期公告', '')}
    return releases


@lru_cache(maxsize=1)
def first_annual_release_dates():
    return {key: release['date'] for key, release in first_annual_releases().items()}


def effective_publication_date(code, period, provider_date):
    if not provider_date:
        return ''
    return max(provider_date, first_annual_release_dates().get((code, period), ''))


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


def visible_version(versions, period, day):
    visible = (v for v in versions if period <= v['available_date'] < day
               and v.get('identity_available_date', '') < day)
    latest = max(visible, key=lambda v: v['available_date'], default=None)
    if latest and latest.get('valid_through') and day > latest['valid_through']:
        return None
    return latest


def verified_annual_version(data, period, day):
    """Use only publications visible as of day, tied to the observed provider edition."""
    code = data.get('code')
    if not isinstance(code, str):
        return None
    try:
        date.fromisoformat(period)
        date.fromisoformat(day)
        if day <= first_annual_release_dates().get((code, period), ''):
            return None
        company = shard(code[:6]).get(code, {})
        record = company.get(period)
        if not record:
            return None
        version = visible_version(record['versions'], period, day)
        if version is None:
            return None
        for table in PROVIDER_TABLES:
            rows = [r for r in data.get('fin', {}).get(table, []) if r.get('statDate') == period
                    and r.get('pubDate') and effective_publication_date(code, period, r['pubDate']) < day]
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
                return period, max(version['available_date'], version.get('identity_available_date', '')), shares
    except (OSError, EOFError, zlib.error, KeyError, ValueError, TypeError, InvalidOperation):
        pass
    return None
