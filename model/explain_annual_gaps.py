"""Explain outstanding PIT gaps with the issuer evidence available for that evaluation."""
from collections import defaultdict
import csv
from functools import lru_cache
import json

from annual_supplements import EVIDENCE, first_annual_releases, verified_annual_version
from pit_audit import REQUIRED
from publish_annual_evidence import metric_pages


@lru_cache(maxsize=1)
def nonfiling_notices():
    notices = json.loads((EVIDENCE / 'historical/notice-queue.json').read_bytes())
    return {(n['code'], n['statDate']): n for n in notices if 'verified_as_of' in n}


def explain(code, period, day, table, field, version):
    release = first_annual_releases().get((code, period))
    if release and day <= release['date']:
        links = [url for url in (release['source'], release['delay_notice']) if url]
        return '调仓日前尚未披露', '首次正式披露 ' + release['date'], links
    notice = nonfiling_notices().get((code, period))
    if notice and not version and notice['available_date'] < day <= notice['verified_as_of']:
        return '发行人公告无法按期披露', notice['title'], [notice['source']]
    if version:
        required = REQUIRED[table] if field == 'rows=0' else (field,)
        metrics = {'operating_cash_flow' if item == 'CFOToNP' else item for item in required}
        missing = metrics - version['facts'].keys()
        limited = version.get('non_comparable', {})
        if missing and missing <= limited.keys():
            meanings = {'nonpositive_average_parent_equity': '平均归母净资产为负',
                        'zero_average_parent_equity': '平均归母净资产为零',
                        'zero_operating_revenue': '营业收入为零，毛利率无法计算',
                        'zero_consolidated_profit': '合并净利润为零，归母净利润占比无法计算'}
            reasons = [meanings[limited[m]['reason']] for m in sorted(missing)]
            links = [s['source'] + '#page=' + str(page) for s in version['sources'] for m in sorted(missing)
                     if m in s.get('non_comparable', {}) for page in metric_pages(s, m)]
            return '已核实但指标不可比', ' / '.join(reasons), list(dict.fromkeys(links))
    return '待核', '仍需核对该调仓日可用的发行人披露', []


def write_explanations(evaluations, pit_dir, path):
    by_code = defaultdict(list)
    for day, evaluation in evaluations.items():
        for row in evaluation['eligible_annual_missing']:
            for reason in row['reasons']:
                table, period, field = reason.split(':', 2)
                by_code[row['code']].append((day, period, table, field))
        for row in evaluation['unknown_eligibility']:
            if row['reason'] == 'ST_release_requires_issuer_evidence':
                by_code[row['code']].append((day, row['flag_date'], 'daily', 'isST'))
    with path.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['评价日', '证券代码', '报告期', '原表', '原缺项', '报表核对结论', '说明', '公告'])
        for code, rows in sorted(by_code.items()):
            stock = json.loads((pit_dir / (code + '.json')).read_bytes())
            if stock.get('code') != code:
                raise ValueError(f'Stock file changed during audit: {code}')
            versions = {}
            for day, period, table, field in sorted(rows):
                if table == 'daily':
                    state, detail, links = '摘帽公告待核', '需要发行人公告确认撤销风险警示的生效日', []
                else:
                    if (period, day) not in versions:
                        versions[period, day] = verified_annual_version(stock, period, day)
                    state, detail, links = explain(code, period, day, table, field, versions[period, day])
                writer.writerow([day, code, period, table, field, state, detail, ' | '.join(links)])
