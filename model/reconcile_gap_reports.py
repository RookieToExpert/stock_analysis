"""Extract PIT evidence from a local CNINFO cache and a specified set of provider gaps."""
import argparse
import csv
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from decimal import Decimal
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

from collect_gap_reports import load, report_kind, save_json
from issuer_statements import Report, compact, ratio_agrees
from pit_audit import REQUIRED


def make_manifest(pit_dir, gap_files, day):
    """Bind the exact issuer and visible provider edition for each financial gap."""
    requested = defaultdict(lambda: defaultdict(set))
    for path in gap_files:
        with path.open(encoding='utf-8-sig') as source:
            for row in csv.DictReader(source):
                if row['评价日'] == day and row['待核事项'] == '财报':
                    requested[row['证券代码']][row['报告期或标志变化日']].add((row['数据表'], row['数据项']))
    manifest = {}
    for code, periods in sorted(requested.items()):
        stock = load(pit_dir / (code + '.json'))
        if stock.get('code') != code:
            raise ValueError(f'Provider identity mismatch for {code}')
        manifest[code] = {}
        for period, pairs in sorted(periods.items()):
            visible = {}
            for table in REQUIRED:
                rows = [r for r in stock['fin'].get(table, []) if r.get('statDate') == period
                        and period <= r.get('pubDate', '') < day]
                if len(rows) > 1 or any(r.get('code') != code for r in rows):
                    raise ValueError(f'Ambiguous provider row for {code} {period} {table}')
                if rows:
                    visible[table] = rows[0]
            for table, field in pairs:
                if table not in REQUIRED or (field != 'rows=0' and field not in REQUIRED[table]):
                    raise ValueError(f'Unknown field in gap list: {table} {field}')
                if (field == 'rows=0' and table in visible) or (field != 'rows=0' and
                        (table not in visible or visible[table].get(field) not in (None, ''))):
                    raise ValueError(f'Gap has changed since snapshot: {code} {period} {table} {field}')
            manifest[code][period] = {'fields': sorted(pairs), 'rows': visible,
                                      'company': stock['basic'][0]['code_name']}
    return manifest


def required_fields(pairs):
    fields = set()
    for table, name in pairs:
        fields.update(REQUIRED[table] if name == 'rows=0' else (name,))
    return {'operating_cash_flow' if name == 'CFOToNP' else name for name in fields}


@lru_cache(maxsize=1)
def reviewed_rows():
    return load(Path(__file__).with_name('reviewed_annual_rows.json'))


def checked_transcription(meta, record, report):
    row = reviewed_rows().get(meta['id'])
    if not row or (row['pdf_sha256'], row['code'], row['year']) != (record['pdf_sha256'], report.code, report.year):
        return None
    pages = report.text.split('\f')
    for page, *passages in row['checks']:
        if page > len(pages) or any(compact(p) not in compact(pages[page - 1]) for p in passages):
            return None
    if 'signed_components' in row and sum(map(Decimal, row['signed_components'])) != Decimal(row['value']):
        return None
    return row


def extract_filing(args):
    meta, year, item, cache = args
    source = cache/'text'/(meta['id'] + '.json')
    if not source.exists():
        return {'errors': {'document': 'source not downloaded'}}
    record = load(source)
    if any(record.get(k) != meta.get(k) for k in ('id', 'source', 'date')):
        return {'errors': {'document': 'cached filing differs from the issuer index'}}
    if meta.get('pdf_sha256') and meta['pdf_sha256'] != record['pdf_sha256']:
        return {'errors': {'document': 'PDF digest differs from the pinned filing'}}
    text_bytes = gzip.decompress(source.with_suffix('.txt.gz').read_bytes())
    if hashlib.sha256(text_bytes).hexdigest() != record['text_sha256']:
        return {'errors': {'document': 'source digest mismatch'}}
    report = Report(text_bytes.decode(), meta['code'], year)
    result = {'issuer_code': meta['code'], 'fiscal_year':year,
              'source': meta['source'], 'pdf_sha256': record['pdf_sha256'], 'title': meta['title'],
              'available_date': meta['date'], 'facts': {}, 'evidence': {}, 'errors': {}}
    facts, proof, errors = result['facts'], result['evidence'], result['errors']
    if not report.cover_ok:
        result['foreign_owner'] = report.foreign_owner
        errors['identity'] = 'annual report issuer/year not found on opening pages'
        return result
    proof['issuer_identity'] = report.identity
    raw = item['rows']
    wanted = required_fields(item['fields'])
    try:
        printed = report.consolidated_profit()
    except ValueError as exc:
        printed = None
        errors['profit_anchor'] = str(exc)
    expected = raw.get('profit', {}).get('netProfit')
    matched = bool(printed and expected not in (None,'') and
                   abs(Decimal(expected) - Decimal(printed['value'])) <= Decimal(printed['precision']) / 2)
    if printed:
        proof['consolidated_profit'] = printed
    if 'operating_cash_flow' in wanted or 'netProfit' in wanted:
        try:
            cash = report.cash()
            proof['cash_statement'] = cash
        except ValueError as exc:
            cash = None
            errors['cash_statement'] = str(exc)
        if cash:
            facts['operating_cash_flow'] = cash['value']
            result['cash_basis'] = 'consolidated_statement_and_subtotals'
        elif 'operating_cash_flow' in wanted:
            try:
                comparison = report.annual_cash_table()
                proof['annual_cash_comparison'] = comparison
                facts['operating_cash_flow'] = comparison['value']
                result['cash_basis'] = 'annual_cash_comparison_and_subtotals'
            except ValueError as exc:
                errors['cash_comparison'] = str(exc)
            if 'operating_cash_flow' not in facts:
                try:
                    highlights = report.corroborated_highlight_cash(raw, printed)
                    proof['annual_highlights'] = highlights
                    facts['operating_cash_flow'] = highlights['cash']['value']
                    result['cash_basis'] = 'annual_comparison_and_provider_ratios'
                except ValueError as exc:
                    errors['operating_cash_flow'] = str(exc)
    other = wanted - {'operating_cash_flow'}
    if other:
        fields, basis, field_errors = report.extra_fields(other, printed)
        if not expected and printed and raw.get('dupont', {}).get('dupontPnitoni'):
            parent = basis.get('parent')
            if parent and proof.get('cash_statement'):
                np = Decimal(printed['value'])
                matched = (ratio_agrees(Decimal(parent['value']), np, raw['dupont']['dupontPnitoni'])
                           and ratio_agrees(Decimal(proof['cash_statement']['value']), np, raw.get('cash',{}).get('CFOToNP')))
        if printed:
            facts.update(fields)
        else:
            errors['profit_anchor'] = 'issuer and archived profit need reconciling'
        proof['other_fields'] = basis
        errors.update(field_errors)
        if 'roeAvg' in facts and Decimal(basis['average_parent_equity']) <= 0:
            result['non_comparable'] = {'roeAvg': {'reason': 'nonpositive_average_parent_equity',
                                                   'signed_formula_value': facts.pop('roeAvg')}}
    reviewed = checked_transcription(meta, record, report)
    if reviewed and reviewed['field'] in wanted:
        field = reviewed['field']
        if field in facts and Decimal(facts[field]) != Decimal(reviewed['value']):
            raise ValueError(f"Transcription conflict for {meta['id']} {field}")
        proof['reviewed_rows'] = reviewed
        facts[field] = reviewed['value']
        errors.pop(field, None)
        if field == 'operating_cash_flow':
            result['cash_basis'] = reviewed['method']
    if 'operating_cash_flow' not in wanted:
        facts.pop('operating_cash_flow', None)
    result['profit_anchor_matches'] = matched
    if expected not in (None,'') and printed and not matched:
        result['provider_profit_conflict'] = {'provider':expected,'issuer':printed['value'],'precision':printed['precision']}
    return result


def filing_groups(cache, manifest, cutoff, inventory=None):
    if inventory:
        with gzip.open(inventory, 'rt', encoding='utf-8') as source:
            listed = json.load(source)
        return {(code, period): [doc for doc in listed.get(code, {}).get(period, []) if doc['date'] < cutoff]
                for code, years in manifest.items() for period in years}
    groups = {}
    for code, years in manifest.items():
        start = str(min(int(y[:4]) for y in years) + 1) + '-01-01'
        file = cache/'index'/f'{code}-{start}-{cutoff}.json'
        docs = load(file) if file.exists() else []
        for period in years:
            year = int(period[:4])
            full = [d for d in docs if d['date'] < cutoff and report_kind(d['title'], year, d['date']) == 'full']
            dates = {d['date'] for d in full}
            summaries = [d for d in docs if d['date'] < cutoff and report_kind(d['title'], year, d['date']) == 'summary'
                         and (not dates or d['date'] in dates) and (cache/'text'/(d['id']+'.json')).exists()]
            groups[(code, period)] = full + summaries
    return groups


def input_guard(rows):
    dates = {table: row['pubDate'] for table, row in rows.items()}
    anchors = {}
    for table, fields in {'profit':('netProfit','npMargin'), 'cash':('CFOToOR','CFOToGr'),
                          'dupont':('dupontPnitoni','dupontROE')}.items():
        if table in rows:
            anchors[table] = {k:rows[table][k] for k in fields if rows[table].get(k) not in (None,'')}
    return {'provider_dates': dates, 'anchors': anchors}


def choose_source(field, candidates):
    if field != 'operating_cash_flow':
        values = {Decimal(r['facts'][field]) for r in candidates}
        return min(candidates, key=lambda r:r['source']) if len(values) == 1 else None
    rank = {'consolidated_statement_and_subtotals': 0, 'consolidated_notes_and_annual_comparison': 1,
            'annual_cash_comparison_and_subtotals': 2, 'annual_cash_and_four_quarters': 2,
            'annual_comparison_and_provider_ratios': 3}
    def grade(r):
        return rank[r['cash_basis']]
    def precision(r):
        proof = r['evidence']
        cell = (proof.get('cash_statement') or proof.get('annual_cash_comparison') or
                proof.get('annual_highlights', {}).get('cash') or proof['reviewed_rows'])
        return Decimal(cell.get('precision', Decimal(1).scaleb(Decimal(r['facts'][field]).as_tuple().exponent)))
    best = min(candidates, key=lambda r:(grade(r), precision(r), r['source']))
    reference = Decimal(best['facts'][field])
    alternates = {r['source']:r['facts'][field] for r in candidates if Decimal(r['facts'][field]) != reference}
    for r in candidates:
        delta = abs(Decimal(r['facts'][field]) - reference)
        if not delta or (grade(best) == 0 and grade(r) > 0):
            continue
        if grade(r) == 0 or delta > (precision(best) + precision(r)) / 2:
            return None
    return {**best, 'same_day_alternate_amounts': alternates} if alternates else best


def build(groups, manifest, parsed):
    records, unresolved = {}, []
    for (code, period), docs in sorted(groups.items()):
        item = manifest[code][period]
        wanted = required_fields(item['fields'])
        guard = input_guard(item['rows'])
        versions = []
        def candidate(d):
            return parsed.get((code, int(period[:4]), d['id']), {})
        dated = [d for d in docs if not candidate(d).get('foreign_owner')]
        for day in sorted({d['date'] for d in dated}):
            candidates = [candidate(d) for d in dated if d['date'] == day]
            facts, by_source, non_comparable = {}, {}, {}
            for field in sorted(wanted):
                accepted = [r for r in candidates if field in r.get('facts', {})]
                if not accepted:
                    for r in candidates:
                        if field in r.get('non_comparable', {}):
                            non_comparable[field] = r['non_comparable'][field]
                            by_source[r['source']] = r
                    continue
                proof = choose_source(field, accepted)
                if not proof:
                    continue
                facts[field] = proof['facts'][field]
                by_source[proof['source']] = proof
            evidence = [{k:v for k,v in source.items() if k != 'input_sha256'} for source in by_source.values()]
            versions.append({'available_date':day,'facts':facts,'non_comparable':non_comparable,'sources':evidence})
        found = versions[-1]['facts'] if versions else {}
        absent = wanted - set(found)
        if absent:
            unresolved.append({'code':code,'period':period,'missing':sorted(absent),
                               'documents':[{**d,'errors':candidate(d).get('errors',{})} for d in docs]})
        if any(v['facts'] or v['non_comparable'] for v in versions):
            records.setdefault(code, {})[period] = {**guard, 'versions':versions}
    return records, unresolved


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('cache',type=Path)
    p.add_argument('manifest',type=Path)
    p.add_argument('--day',required=True)
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--pit-dir', type=Path, help='rebuild the manifest from a frozen PIT directory')
    p.add_argument('--gaps-csv', type=Path, nargs='+', help='the original coverage gap list(s)')
    p.add_argument('--manifest-only', action='store_true')
    p.add_argument('--inventory', type=Path, help='pin the exact official filing list (.json.gz)')
    p.add_argument('--write-inventory', type=Path, help='save all candidate filings and hashes for replay')
    p.add_argument('--only-pending',action='store_true')
    a=p.parse_args()
    if bool(a.gaps_csv) != bool(a.pit_dir) or (a.manifest_only and not a.pit_dir):
        p.error('Provide --pit-dir and --gaps-csv together to create a manifest.')
    if a.pit_dir:
        save_json(a.manifest, make_manifest(a.pit_dir, a.gaps_csv, a.day))
    if a.manifest_only:
        return
    manifest=load(a.manifest)
    groups=filing_groups(a.cache,manifest,a.day,a.inventory)
    if a.write_inventory:
        listed = {}
        for (code, period), docs in groups.items():
            entries = []
            for doc in docs:
                path = a.cache/'text'/(doc['id'] + '.json')
                entries.append({**doc, 'pdf_sha256': load(path)['pdf_sha256'] if path.exists() else None})
            listed.setdefault(code, {})[period] = entries
        a.write_inventory.write_bytes(gzip.compress(json.dumps(listed, ensure_ascii=False, sort_keys=True,
                                                    separators=(',', ':')).encode(), mtime=0))
    saved=a.cache/'issuer-parsed'
    saved.mkdir(exist_ok=True)
    jobs={}
    for (code, period),docs in groups.items():
        for d in docs:
            if (a.cache/'text'/(d['id']+'.json')).exists():
                jobs[(code,int(period[:4]),d['id'])] = (d,int(period[:4]),manifest[code][period],a.cache)
    def dest(key):
        code, year, ident = key
        return saved/f'{code}-{year}-{ident}.json'
    extractor = hashlib.sha256()
    for filename in ('issuer_statements.py', 'reconcile_gap_reports.py', 'reviewed_annual_rows.json'):
        extractor.update(Path(__file__).with_name(filename).read_bytes())
    def signature(job):
        doc, year, item, _ = job
        payload = json.dumps([doc, year, item], ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(extractor.digest() + payload).hexdigest()
    pending = {key: job for key, job in jobs.items() if not a.only_pending or not dest(key).exists()
               or load(dest(key)).get('input_sha256') != signature(job)}
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for key,rec in zip(pending,pool.map(extract_filing,pending.values(),chunksize=4)):
            rec['input_sha256'] = signature(pending[key])
            save_json(dest(key),rec)
    parsed={key:load(dest(key)) for key in jobs}
    records,unresolved=build(groups,manifest,parsed)
    save_json(a.cache/'unresolved.json',unresolved)
    save_json(a.cache/'ledger-draft.json',records)
    print('processed',len(pending),'cached',len(parsed),'company-years',len(groups),'unresolved',len(unresolved),
          Counter(f for r in unresolved for f in r['missing']))


if __name__=='__main__':
    main()
