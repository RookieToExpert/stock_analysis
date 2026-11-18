#!/usr/bin/env python3
"""只读复核上市年限/ST资格后的年报覆盖。行业/市值过滤未知则不宣称正式门槛通过。"""
import argparse
import csv
import json
from collections import Counter
import gzip,hashlib
from functools import lru_cache
from datetime import date
from pathlib import Path
from pit_audit import annual_missing
from historical_industry import lookup as industry_at
from historical_market_cap import calculate as market_cap_at


@lru_cache(maxsize=1)
def release_ledger():
    return json.loads(Path(__file__).with_name('verified_st_releases.json').read_text())


@lru_cache(maxsize=1)
def delisting_periods():
    return json.loads(Path(__file__).with_name('verified_delisting_periods.json').read_text())


def source_matches(proof):
    try:
        with gzip.open(Path(__file__).resolve().parents[1]/proof['source_text_path'], 'rb') as handle:
            return bool(proof['source']) and hashlib.sha256(handle.read()).hexdigest() == proof['source_text_sha256']
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        return False


def verified_release(code, effective, *, match_on='effective_date'):
    matches=[r for r in release_ledger() if r['code']==code and r.get(match_on)==effective]
    if len(matches)!=1:return {}
    return matches[0] if source_matches(matches[0]) else {}


def delisting_reason(data, effective, day):
    notices = [row for row in delisting_periods()
               if row['code'] == data.get('code') and row['effective_date'] == effective]
    if len(notices) != 1:
        return None
    notice = notices[0]
    if not notice['available_date'] < effective <= day or not source_matches(notice):
        return None
    last_trade = notice['scheduled_last_trade']
    if day <= last_trade:
        return 'delisting_period'

    # The final notice can identify the remaining session and the exchange's removal window.
    pending = notice.get('pending_removal')
    if not pending or day not in pending['removal_sessions'] or not source_matches(pending):
        return None
    prior_day = pending['remaining_as_of']
    if not prior_day < pending['available_date'] <= last_trade < day or pending['remaining_trade_sessions'] != 1:
        return None
    expected = {d: '0' for d in pending['removal_sessions'] if d <= day}
    expected[last_trade] = '1'
    bars = [row for row in data['daily'] if prior_day < row['date'] <= day]
    if len(bars) == len(expected) and {row['date']: row.get('tradestatus') for row in bars} == expected:
        return 'awaiting_delisting_after_final_trade'
    return None


def first_zero_after_st(data, day):
    history = data.get('daily', [])
    last_st = max((r['date'] for r in history if r.get('isST') == '1' and r['date'] <= day), default=None)
    if last_st is None:
        return None
    return min((r['date'] for r in history if r.get('isST') == '0' and last_st < r['date'] <= day), default=None)


def confirmed_after_suspension(data, flag_day, day):
    """A later issuer notice can establish status for subsequent evaluations."""
    proof = verified_release(data.get('code'), flag_day, match_on='provider_zero_date')
    if proof.get('status') != 'normal_listing' or not proof.get('source'):
        return False
    first_trade = proof['effective_date']
    if not flag_day < first_trade <= proof['available_date'] < day:
        return False
    bars = [r for r in data['daily'] if flag_day <= r['date'] <= first_trade]
    days = {r['date'] for r in bars}
    if len(days) != len(bars) or flag_day not in days or first_trade not in days:
        return False
    return all(row.get('isST') == '0' and row.get('tradestatus') == ('1' if row['date'] == first_trade else '0')
               for row in bars)


def eligibility(data, day):
    basic=data.get('basic') or []
    if len(basic)!=1:return None,'basic_missing_or_ambiguous'
    try:
        ipo=date.fromisoformat(basic[0]['ipoDate']);when=date.fromisoformat(day)
    except (ValueError,KeyError,TypeError):return None,'ipo_unknown'
    age=when.year-ipo.year-((when.month,when.day)<(ipo.month,ipo.day))
    if age<5:return False,'listed_under_5_years'
    out=basic[0].get('outDate')
    if out and out<=day:return None,'universe_conflicts_with_delisting'
    rows=[r for r in data.get('daily',[]) if r.get('date')==day]
    if len(rows)!=1 or rows[0].get('isST') not in ('0','1'):return None,'evaluation_day_ST_unknown'
    if rows[0]['isST']=='1':return False,'ST'
    # A 1 -> 0 flag also occurs during delisting. It is not proof of ST release.
    effective = first_zero_after_st(data, day)
    if effective:
        terminal = delisting_reason(data, effective, day)
        if terminal:
            return False, terminal
        proof=data.get('st_release_verification') or verified_release(data.get('code'),effective)
        try:
            available=date.fromisoformat(proof.get('available_date',''))
            valid=(proof.get('source') and proof.get('effective_date')==effective
                   and available<=date.fromisoformat(effective)
                   and proof.get('status')=='normal_listing')
        except (ValueError,TypeError):valid=False
        if not valid and not confirmed_after_suspension(data, effective, day):
            return None,'ST_release_requires_issuer_evidence'
    return True,'age_ST_pass'


def audit(root, evaluation_date=None):
    universe=json.loads((root/'universe.json').read_text());members={}
    if evaluation_date is not None:
        if evaluation_date not in universe:
            raise ValueError('日期不在本地调仓日列表中。可查日期为 ' + ', '.join(sorted(universe)))
        universe = {evaluation_date: universe[evaluation_date]}
    result={d:dict(universe=len(set(cs)),excluded=[],unknown_eligibility=[],eligible_annual_missing=[],eligible_complete=[],known_age_ST_eligible=0,market_cap_proxies={}) for d,cs in universe.items()}
    for day,codes in universe.items():
        for c in set(codes):members.setdefault(c,[]).append(day)
    for code,days in members.items():
        try:
            d=json.loads((root/(code+'.json')).read_text())
            if d.get('code')!=code:raise ValueError('code mismatch')
        except (OSError,ValueError) as exc:
            for day in days:result[day]['unknown_eligibility'].append({'code':code,'reason':'file_missing_or_invalid'})
            continue
        for day in days:
            eligible,reason=eligibility(d,day);entry=result[day]
            if eligible is None:
                unknown = {'code': code, 'reason': reason}
                if reason == 'ST_release_requires_issuer_evidence':
                    unknown['flag_date'] = first_zero_after_st(d, day)
                entry['unknown_eligibility'].append(unknown)
            elif not eligible:entry['excluded'].append({'code':code,'reason':reason})
            else:
                entry['known_age_ST_eligible']+=1
                industry=industry_at(code,day)
                if industry is None:
                    entry['unknown_eligibility'].append({'code':code,'reason':'historical_industry_missing_or_ambiguous'})
                    continue
                if industry['financial']:
                    entry['excluded'].append({'code':code,'reason':'financial_industry_as_published','industry':industry})
                    continue
                entry['market_cap_proxies'][code]=market_cap_at(d,day)
                missing=annual_missing(d,day)
                if missing:entry['eligible_annual_missing'].append({'code':code,'reasons':missing})
                else:entry['eligible_complete'].append(code)
    for day,entry in result.items():
        n=len(entry['eligible_annual_missing'])+len(entry['eligible_complete'])
        entry['known_age_ST_industry_eligible']=n
        entry['industry_reference']=industry_at('000001',day)
        entry['market_cap_proxy_at_least_20bn']=sum(1 for r in entry['market_cap_proxies'].values() if r and r['value_yuan']>=20_000_000_000)
        entry['market_cap_proxy_unknown']=sum(r is None for r in entry['market_cap_proxies'].values())
        entry['missing_fraction_among_known_eligible']=len(entry['eligible_annual_missing'])/n if n else None
    return {'scope':'IPO age, evidence-backed ST release and latest published official industry; market-cap cut not yet certified',
            'strategy_gate_pass':False,'evaluations':result}


def write_gap_csv(evaluations, path):
    """One row per financial field/year or outstanding ST notice."""
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['评价日', '证券代码', '待核事项', '报告期或标志变化日', '数据表', '数据项'])
        for day, entry in sorted(evaluations.items()):
            for row in sorted(entry['eligible_annual_missing'], key=lambda r: r['code']):
                for reason in row['reasons']:
                    table, period, field = reason.split(':', 2)
                    writer.writerow([day, row['code'], '财报', period, table, field])
            for row in sorted(entry['unknown_eligibility'], key=lambda r: r['code']):
                if row['reason'] == 'ST_release_requires_issuer_evidence':
                    writer.writerow([day, row['code'], '摘帽公告', row['flag_date'], 'daily', 'isST'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pit_dir', type=Path)
    parser.add_argument('output_json', nargs='?', type=Path, help='完整审计结果，可省略')
    parser.add_argument('--day', help='只检查指定调仓日，如 2026-09-01')
    parser.add_argument('--gaps-csv', type=Path, help='按股票列出待核的财报字段和 ST 公告')
    parser.add_argument('--explain-csv', type=Path, help='导出每个剩余缺项的中文原因和发行人公告')
    args = parser.parse_args()
    try:
        result = audit(args.pit_dir, args.day)
    except ValueError as exc:
        parser.exit(2, str(exc) + '\n')
    if args.output_json:
        args.output_json.write_text(json.dumps(result, ensure_ascii=False))
    if args.gaps_csv:
        write_gap_csv(result['evaluations'], args.gaps_csv)
    if args.explain_csv:
        from explain_annual_gaps import write_explanations
        write_explanations(result['evaluations'], args.pit_dir, args.explain_csv)
    for day, entry in sorted(result['evaluations'].items()):
        if args.output_json and not args.day and not args.gaps_csv:
            print(day, 'age_ST_industry_eligible', entry['known_age_ST_industry_eligible'],
                  'annual_missing', len(entry['eligible_annual_missing']),
                  'eligibility_unknown', len(entry['unknown_eligibility']))
            continue
        reasons = Counter(row['reason'] for row in entry['unknown_eligibility'])
        print(day, '年限/ST/行业通过', entry['known_age_ST_industry_eligible'],
              '其中年报有缺项', len(entry['eligible_annual_missing']),
              '待核摘帽公告', reasons['ST_release_requires_issuer_evidence'],
              '文件未下载或无效', reasons['file_missing_or_invalid'],
              '资格未知合计', len(entry['unknown_eligibility']))
    if args.gaps_csv:
        print('待核明细', args.gaps_csv)
