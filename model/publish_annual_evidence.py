"""Publish the dated evidence in deterministic, checksum-verified shards and a gap-level CSV."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path

from annual_supplements import visible_version
from collect_gap_reports import load, save, save_json
from pit_audit import REQUIRED


def bundle(records, destination):
    groups = defaultdict(dict)
    for code, years in sorted(records.items()):
        groups[code[:6]][code] = years
    directory = destination / 'evidence'
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for prefix, companies in sorted(groups.items()):
        content = json.dumps(companies, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        compressed = gzip.compress(content, compresslevel=9, mtime=0)
        save(directory / (prefix + '.json.gz'), compressed)
        hashes[prefix] = hashlib.sha256(compressed).hexdigest()
    save_json(destination / 'index.json', {'schema': 1, 'shards': hashes})


def metric_pages(source, field):
    proof = source['evidence']
    if field in proof.get('reviewed_fields', {}):
        return [proof['reviewed_fields'][field]['page']]
    review = proof.get('reviewed_rows', {})
    if review.get('field') == field:
        return [review['page']]
    if field == 'operating_cash_flow':
        cell = (proof.get('cash_statement') or proof.get('annual_cash_comparison')
                or proof.get('annual_highlights', {}).get('cash'))
        return [cell['page']]
    basis = proof.get('other_fields', {})
    names = {'netProfit': [], 'roeAvg': ['parent', 'equity'], 'gpMargin': ['turnover', 'cost'],
             'MBRevenue': ['main_business'], 'totalShare': ['shares'], 'dupontPnitoni': ['parent'],
             'liabilityToAsset': ['assets', 'liabilities']}[field]
    pages = [basis[name]['page'] for name in names]
    if field in ('netProfit', 'dupontPnitoni'):
        pages.append(proof['consolidated_profit']['page'])
    return sorted(set(pages))


def resolutions(manifest, records, day, path):
    counts = Counter()
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(['评价日', '证券代码', '证券简称', '报告期', '原表', '原缺项', '结论',
                         '核实数值或不可比原因', '证据公开日', '公告及PDF页码'])
        for code, years in sorted(manifest.items()):
            for period, item in sorted(years.items()):
                versions = records.get(code, {}).get(period, {}).get('versions', [])
                version = visible_version(versions, period, day) or {}
                for table, name in item['fields']:
                    wanted = REQUIRED[table] if name == 'rows=0' else [name]
                    state, results, links = '已核实', [], []
                    for field in wanted:
                        metric = 'operating_cash_flow' if field == 'CFOToNP' else field
                        value = version.get('facts', {}).get(metric)
                        limitation = version.get('non_comparable', {}).get(metric)
                        if value is None and not limitation:
                            state = '待核'
                            results.append(metric)
                            continue
                        if limitation:
                            if state != '待核':
                                state = '已核实但不可比'
                            reason = {'nonpositive_average_parent_equity':'平均归母净资产非正',
                                      'zero_average_parent_equity':'平均归母净资产为零',
                                      'zero_consolidated_profit':'合并净利润为零',
                                      'zero_operating_revenue':'营业收入为零'}[limitation['reason']]
                            signed = limitation.get('signed_formula_value')
                            results.append(metric + ':' + reason + ('，算术结果=' + signed if signed else ''))
                        else:
                            results.append(metric + '=' + value)
                        for source in version['sources']:
                            if source.get('facts', {}).get(metric) == value and value is not None or (
                                    limitation and source.get('non_comparable', {}).get(metric) == limitation):
                                for page in metric_pages(source, metric):
                                    links.append(source['source'] + '#page=' + str(page))
                    counts[state] += 1
                    writer.writerow([day, code, item['company'], period, table, name, state, ' | '.join(results),
                                     version.get('available_date', ''), ' | '.join(dict.fromkeys(links))])
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--day', required=True)
    parser.add_argument('--additional-ledger', type=Path, action='append', default=[],
                        help='include disjoint company-years from another source selection')
    args = parser.parse_args()
    records, manifest = load(args.ledger), load(args.manifest)
    for path in args.additional_ledger:
        for code, years in load(path).items():
            existing = records.setdefault(code, {})
            for period, record in years.items():
                if period in existing and existing[period] != record:
                    raise ValueError(f'Incompatible evidence for {code} {period}')
                existing[period] = record
    bundle(records, args.destination)
    print(dict(resolutions(manifest, records, args.day, args.destination / ('resolutions-' + args.day + '.csv'))))
